"""Bounded real DMX adapter for the universal FieldOps governance boundary.

Only high-level backend-advertised scenes and blackout are supported. Raw DMX
channels, universes, fixture addresses and arbitrary network destinations are
intentionally unavailable.
"""

from __future__ import annotations

import ipaddress
import json
import os
from typing import Any, Mapping, Protocol
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .contracts import ActionRequest, ExecutionResult, VerificationResult


class DMXClient(Protocol):
    def status(self) -> Mapping[str, Any]: ...
    def set_scene(self, scene: str, speed: float = 1.0) -> Mapping[str, Any]: ...
    def blackout(self) -> Mapping[str, Any]: ...


class DMXConfigurationError(RuntimeError):
    pass


def _is_private_local_url(value: str) -> bool:
    try:
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return False
        host = parsed.hostname.lower()
        if host in {"localhost", "127.0.0.1", "::1"} or host.endswith(".local"):
            return True
        try:
            return ipaddress.ip_address(host).is_private
        except ValueError:
            return False
    except Exception:
        return False


def _scene_id(value: object) -> str | None:
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    if not text or len(text) > 80:
        return None
    if any(ch not in "abcdefghijklmnopqrstuvwxyz0123456789_" for ch in text):
        return None
    forbidden = {"channel", "channels", "canal", "canales", "universe", "universo"}
    if set(text.split("_")).intersection(forbidden):
        return None
    return text


class LocalDMXHTTPClient:
    """Private/local HTTP client for the existing bounded InnerOS DMX engine."""

    def __init__(self, base_url: str | None = None, timeout: float = 2.5):
        resolved = (base_url or os.getenv("FIELDOPS_DMX_ENGINE_URL") or "").strip().rstrip("/")
        if not resolved or not _is_private_local_url(resolved):
            raise DMXConfigurationError("FIELDOPS_DMX_ENGINE_URL must be an explicit private/local HTTP(S) endpoint")
        self.base_url = resolved
        self.timeout = timeout

    def _request(self, method: str, path: str, payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
        data = None if payload is None else json.dumps(dict(payload)).encode("utf-8")
        request = Request(
            f"{self.base_url}{path}",
            data=data,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method=method,
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:  # noqa: S310 - URL is private/local only
                body = response.read().decode("utf-8", errors="replace")
            decoded = json.loads(body) if body else {}
        except (OSError, URLError, ValueError, json.JSONDecodeError) as exc:
            return {"ok": False, "error": type(exc).__name__}
        return decoded if isinstance(decoded, dict) else {"ok": False, "error": "invalid_backend_response"}

    def status(self) -> Mapping[str, Any]:
        return self._request("GET", "/api/status")

    def set_scene(self, scene: str, speed: float = 1.0) -> Mapping[str, Any]:
        return self._request("POST", "/api/scene", {"mode": scene, "speed": float(speed)})

    def blackout(self) -> Mapping[str, Any]:
        return self._request("POST", "/api/blackout", {})


class DMXExecutor:
    """Execute only the two DMX mutations registered in FieldOps governance."""

    def __init__(self, client: DMXClient, executor_id: str = "inneros-ag59"):
        self.client = client
        self.executor_id = executor_id

    def execute(self, request: ActionRequest) -> ExecutionResult:
        if request.action_type == "dmx.set_scene":
            requested = _scene_id(request.parameters.get("scene"))
            status = dict(self.client.status())
            advertised = {
                scene
                for raw in status.get("supported_scenes", []) or []
                if (scene := _scene_id(raw)) is not None
            }
            if not requested or requested not in advertised:
                return ExecutionResult(
                    correlation_id=request.correlation_id,
                    executor=self.executor_id,
                    success=False,
                    details={"reason": "scene_not_advertised", "scene": requested},
                )
            result = dict(self.client.set_scene(requested, float(request.parameters.get("speed", 1.0))))
            return ExecutionResult(
                correlation_id=request.correlation_id,
                executor=self.executor_id,
                success=bool(result.get("ok")),
                details={
                    "action": "dmx.set_scene",
                    "scene": requested,
                    "backend_ack": bool(result.get("ok")),
                    "evidence_ref": f"evidence://dmx/execution/{request.correlation_id}",
                },
            )

        if request.action_type == "dmx.blackout":
            result = dict(self.client.blackout())
            return ExecutionResult(
                correlation_id=request.correlation_id,
                executor=self.executor_id,
                success=bool(result.get("ok")),
                details={
                    "action": "dmx.blackout",
                    "backend_ack": bool(result.get("ok")),
                    "evidence_ref": f"evidence://dmx/execution/{request.correlation_id}",
                },
            )

        return ExecutionResult(
            correlation_id=request.correlation_id,
            executor=self.executor_id,
            success=False,
            details={"reason": "unsupported_governed_action", "action": request.action_type},
        )


class DMXVerifier:
    """Read the backend after execution; never infer success from the executor ACK."""

    def __init__(self, client: DMXClient, verifier_id: str = "inneros-ag59-status"):
        self.client = client
        self.verifier_id = verifier_id

    def verify(self, request: ActionRequest, execution: ExecutionResult) -> VerificationResult:
        status = dict(self.client.status())
        current_scene = status.get("current_effect", status.get("current_scene"))
        running = bool(status.get("running"))
        backend_online = bool(status.get("ok")) and str(status.get("status", "online")) != "unavailable"

        if request.action_type == "dmx.set_scene":
            expected_scene = _scene_id(request.parameters.get("scene"))
            passed = bool(execution.success and backend_online and current_scene == expected_scene)
        elif request.action_type == "dmx.blackout":
            # The engine may retain the last scene name after blackout. Physical
            # inactivity is represented by running=false, which is the verified state.
            passed = bool(execution.success and backend_online and not running)
        else:
            passed = False

        return VerificationResult(
            correlation_id=request.correlation_id,
            verifier=self.verifier_id,
            passed=passed,
            observed_state={
                "backend_online": backend_online,
                "running": running,
                "current_scene": current_scene,
            },
        )
