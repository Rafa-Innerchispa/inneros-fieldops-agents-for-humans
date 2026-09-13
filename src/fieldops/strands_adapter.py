"""Optional Strands-facing adapter boundary.

This module deliberately avoids importing Strands at module import time. It defines
safe tool-shaped functions over FieldOps so a future Strands integration can wrap
these capabilities without exposing unrestricted execution to a model.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Mapping

from .contracts import ActionRequest, ApprovalArtifact, Executor, Verifier
from .providers import ModelProviderConfig, load_provider_config
from .workflow import run_action


def execute_field_action(
    *,
    correlation_id: str,
    action_type: str,
    target_ref: str,
    parameters: Mapping[str, Any] | None,
    expected_state: Mapping[str, Any] | None,
    requires_approval: bool,
    approval: ApprovalArtifact,
    executor: Executor,
    verifier: Verifier,
    route: str,
    route_reason: str,
    provider: ModelProviderConfig | None = None,
    policy_version: str = "fieldops-v1",
) -> dict[str, Any]:
    """Bounded tool surface suitable for wrapping as a Strands tool."""

    request = ActionRequest(
        correlation_id=correlation_id,
        action_type=action_type,
        target_ref=target_ref,
        parameters=parameters or {},
        expected_state=expected_state or {},
        policy_version=policy_version,
        requires_approval=requires_approval,
    )
    provider_config = provider or load_provider_config()
    receipt = run_action(
        request=request,
        approval=approval,
        executor=executor,
        verifier=verifier,
        route=route or provider_config.route,
        route_reason=route_reason or provider_config.route_reason,
    )
    result = asdict(receipt)
    result["provider"] = asdict(provider_config)
    return result


def strands_tool_manifest() -> dict[str, Any]:
    """Return a dependency-free tool manifest for a future Strands wrapper."""

    return {
        "name": "execute_field_action",
        "description": (
            "Execute a bounded InnerOS FieldOps action only after policy and "
            "approval gates, then verify the resulting state."
        ),
        "requires_approval_for_risky_actions": True,
        "arbitrary_shell": False,
        "arbitrary_network": False,
        "inputs": [
            "correlation_id",
            "action_type",
            "target_ref",
            "expected_state",
            "approval",
        ],
    }
