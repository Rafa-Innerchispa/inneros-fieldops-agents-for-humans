"""Provider-neutral contracts for the reusable InnerOS FieldOps layer.

These contracts intentionally contain no AWS credentials, customer data, or direct
production integrations. Concrete adapters should live behind these interfaces.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Protocol


class ApprovalStatus(str, Enum):
    NOT_REQUIRED = "not_required"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass(frozen=True)
class ApprovalArtifact:
    status: ApprovalStatus
    approval_id: str | None = None
    approver_id: str | None = None
    policy_version: str | None = None
    evidence_ref: str | None = None


@dataclass(frozen=True)
class ActionRequest:
    correlation_id: str
    action_type: str
    target_ref: str
    parameters: Mapping[str, Any] = field(default_factory=dict)
    expected_state: Mapping[str, Any] = field(default_factory=dict)
    policy_version: str = "fieldops-v1"
    requires_approval: bool = False


@dataclass(frozen=True)
class ExecutionResult:
    correlation_id: str
    executor: str
    success: bool
    details: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class VerificationResult:
    correlation_id: str
    verifier: str
    passed: bool
    observed_state: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EvidenceReceipt:
    correlation_id: str
    route: str
    route_reason: str
    policy_version: str
    requested_action: str
    target_ref: str
    executor: str
    verifier: str
    action_success: bool
    verification_passed: bool
    quality_gate: str
    approval_ref: str | None = None
    evidence_refs: tuple[str, ...] = ()
    execution_details: Mapping[str, Any] = field(default_factory=dict)
    observed_state: Mapping[str, Any] = field(default_factory=dict)


class Executor(Protocol):
    """Executes a bounded action after policy/approval gates have passed."""

    def execute(self, request: ActionRequest) -> ExecutionResult:
        ...


class Verifier(Protocol):
    """Independently observes whether the requested resulting state exists."""

    def verify(
        self, request: ActionRequest, execution: ExecutionResult
    ) -> VerificationResult:
        ...
