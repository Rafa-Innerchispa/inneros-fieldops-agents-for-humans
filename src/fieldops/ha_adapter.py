"""Bounded Home Assistant adapter for real FieldOps execution.

The adapter never accepts arbitrary HA domains/services. It can only set an
explicitly allowlisted light entity to ``on`` or ``off`` and independently reads
that entity back after execution. Credentials stay inside the canonical InnerOS
Home Assistant client on the local server.
"""

from __future__ import annotations

from dataclasses import dataclass
import importlib
import os
from pathlib import Path
import sys
from typing import Any, Mapping, Protocol

from .contracts import ActionRequest, ExecutionResult, VerificationResult


class HomeAssistantClient(Protocol):
    def configured(self) -> bool: ...
    def get_state(self, entity_id: str) -> Mapping[str, Any]: ...
    def call_service(
        self,
        domain: str,
        service: str,
        *,
        entity_id: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> Mapping[str, Any]: ...


class HomeAssistantConfigurationError(RuntimeError):
    pass


class HomeAssistantTargetDenied(RuntimeError):
    pass


def _normalize_allowlist(values: list[str] | tuple[str, ...] | set[str]) -> frozenset[str]:
    out: set[str] = set()
    for raw in values:
        value = str(raw or "").strip().lower()
        if value.startswith("light.") and len(value) <= 120:
            out.add(value)
    return frozenset(out)


def allowlist_from_env(env: Mapping[str, str] | None = None) -> frozenset[str]:
    source = env or os.environ
    raw = source.get("FIELDOPS_HA_LIGHT_ALLOWLIST", "")
    return _normalize_allowlist(raw.split(","))


def load_canonical_ha_client(
    platform_root: str | None = None,
) -> HomeAssistantClient:
    """Load the existing InnerOS HA client without copying its credential.

    The imported module itself reads the canonical platform ``.env`` and keeps the
    HA token server-side. FieldOps receives only the client functions/results.
    """

    root = (
        platform_root
        or os.getenv("FIELDOPS_INNEROS_PLATFORM_ROOT")
        or "/home/rlopez/inneros/inneros_core/platform"
    )
    root_path = Path(root).expanduser().resolve()
    if not root_path.is_dir():
        raise HomeAssistantConfigurationError("canonical InnerOS platform root is unavailable")
    root_text = str(root_path)
    if root_text not in sys.path:
        sys.path.insert(0, root_text)
    try:
        module = importlib.import_module("inneros_core_runtime.homeassistant_client")
    except Exception as exc:  # pragma: no cover - environment-specific import details
        raise HomeAssistantConfigurationError("canonical InnerOS HA client could not be loaded") from exc
    if not bool(module.configured()):
        raise HomeAssistantConfigurationError("canonical InnerOS HA client is not configured")
    return module  # type: ignore[return-value]


def _entity_state(result: Mapping[str, Any]) -> str | None:
    if not result.get("ok"):
        return None
    entity = result.get("entity")
    if not isinstance(entity, Mapping):
        return None
    state = entity.get("state")
    return str(state).strip().lower() if state is not None else None


@dataclass(frozen=True)
class HomeAssistantBindingConfig:
    allowed_lights: frozenset[str]

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "HomeAssistantBindingConfig":
        allowed = allowlist_from_env(env)
        if not allowed:
            raise HomeAssistantConfigurationError("FIELDOPS_HA_LIGHT_ALLOWLIST is empty")
        return cls(allowed_lights=allowed)


class HomeAssistantEntityExecutor:
    """Set one allowlisted light to an exact desired state."""

    def __init__(
        self,
        client: HomeAssistantClient,
        config: HomeAssistantBindingConfig,
        executor_id: str = "inneros-ha-service-bridge",
    ):
        self.client = client
        self.config = config
        self.executor_id = executor_id

    def execute(self, request: ActionRequest) -> ExecutionResult:
        entity_id = str(request.target_ref or "").strip().lower()
        desired = str(request.parameters.get("state") or "").strip().lower()
        if request.action_type != "homeassistant.entity_control":
            return ExecutionResult(
                correlation_id=request.correlation_id,
                executor=self.executor_id,
                success=False,
                details={"reason": "unsupported_governed_action", "action": request.action_type},
            )
        if entity_id not in self.config.allowed_lights:
            return ExecutionResult(
                correlation_id=request.correlation_id,
                executor=self.executor_id,
                success=False,
                details={"reason": "target_not_allowlisted", "target_ref": entity_id},
            )
        if desired not in {"on", "off"}:
            return ExecutionResult(
                correlation_id=request.correlation_id,
                executor=self.executor_id,
                success=False,
                details={"reason": "invalid_desired_state", "desired_state": desired},
            )

        before_raw = dict(self.client.get_state(entity_id))
        before_state = _entity_state(before_raw)
        if before_state is None:
            return ExecutionResult(
                correlation_id=request.correlation_id,
                executor=self.executor_id,
                success=False,
                details={"reason": "pre_state_unavailable", "target_ref": entity_id},
            )
        service = "turn_on" if desired == "on" else "turn_off"
        result = dict(self.client.call_service("light", service, entity_id=entity_id))
        return ExecutionResult(
            correlation_id=request.correlation_id,
            executor=self.executor_id,
            success=bool(result.get("ok")),
            details={
                "action": request.action_type,
                "target_ref": entity_id,
                "desired_state": desired,
                "before_state": before_state,
                "rollback_state": before_state,
                "backend_ack": bool(result.get("ok")),
                "evidence_ref": f"evidence://ha/execution/{request.correlation_id}",
            },
        )


class HomeAssistantEntityVerifier:
    """Read the target back from HA after execution."""

    def __init__(
        self,
        client: HomeAssistantClient,
        config: HomeAssistantBindingConfig,
        verifier_id: str = "homeassistant-state-readback",
    ):
        self.client = client
        self.config = config
        self.verifier_id = verifier_id

    def verify(self, request: ActionRequest, execution: ExecutionResult) -> VerificationResult:
        entity_id = str(request.target_ref or "").strip().lower()
        desired = str(request.parameters.get("state") or "").strip().lower()
        if entity_id not in self.config.allowed_lights or desired not in {"on", "off"}:
            return VerificationResult(
                correlation_id=request.correlation_id,
                verifier=self.verifier_id,
                passed=False,
                observed_state={"target_ref": entity_id, "state": None, "allowlisted": False},
            )
        raw = dict(self.client.get_state(entity_id))
        observed = _entity_state(raw)
        passed = bool(execution.success and observed == desired)
        return VerificationResult(
            correlation_id=request.correlation_id,
            verifier=self.verifier_id,
            passed=passed,
            observed_state={
                "target_ref": entity_id,
                "state": observed,
                "allowlisted": True,
            },
        )
