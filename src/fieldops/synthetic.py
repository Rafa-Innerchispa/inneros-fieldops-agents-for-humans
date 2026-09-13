"""Synthetic adapters used to prove the FieldOps control loop safely.

These adapters never touch customer systems. They model an edge node and an
independent verifier so the workflow can be demonstrated and tested without
production credentials or physical hardware.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .contracts import ActionRequest, ExecutionResult, VerificationResult


@dataclass
class SyntheticDevice:
    name: str = "synthetic-camera-gateway"
    state: dict[str, Any] = field(default_factory=lambda: {"healthy": False})


class SyntheticEdgeExecutor:
    """Applies bounded state transitions to a synthetic device."""

    def __init__(self, device: SyntheticDevice, executor_id: str = "inneros-edge-01"):
        self.device = device
        self.executor_id = executor_id

    def execute(self, request: ActionRequest) -> ExecutionResult:
        if request.target_ref != self.device.name:
            return ExecutionResult(
                correlation_id=request.correlation_id,
                executor=self.executor_id,
                success=False,
                details={"reason": "unknown_target", "target_ref": request.target_ref},
            )

        if request.action_type == "service_restart":
            self.device.state["healthy"] = True
            return ExecutionResult(
                correlation_id=request.correlation_id,
                executor=self.executor_id,
                success=True,
                details={"action": request.action_type, "target": request.target_ref},
            )

        return ExecutionResult(
            correlation_id=request.correlation_id,
            executor=self.executor_id,
            success=False,
            details={"reason": "unsupported_action", "action": request.action_type},
        )


class SyntheticStateVerifier:
    """Observes state independently from the command result."""

    def __init__(self, device: SyntheticDevice, verifier_id: str = "synthetic-state-probe"):
        self.device = device
        self.verifier_id = verifier_id

    def verify(
        self, request: ActionRequest, execution: ExecutionResult
    ) -> VerificationResult:
        observed = dict(self.device.state)
        expected = dict(request.expected_state)
        passed = execution.success and all(
            observed.get(key) == value for key, value in expected.items()
        )
        return VerificationResult(
            correlation_id=request.correlation_id,
            verifier=self.verifier_id,
            passed=passed,
            observed_state=observed,
        )
