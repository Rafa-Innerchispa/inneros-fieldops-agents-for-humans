"""Universal governed FieldOps execution boundary.

Every mutation enters through the same control loop. The central governance
registry, not an individual adapter, decides whether approval is required and
whether an action is currently executable.
"""

from __future__ import annotations

from .contracts import (
    ActionRequest,
    ApprovalArtifact,
    ApprovalStatus,
    EvidenceReceipt,
    Executor,
    Verifier,
)
from .governance import ActionUnavailable, UnknownActionPolicy, bind_request_to_policy


class ApprovalRequired(RuntimeError):
    pass


class ApprovalDenied(RuntimeError):
    pass


def _enforce_approval(request: ActionRequest, approval: ApprovalArtifact) -> None:
    if not request.requires_approval:
        return
    if approval.status in {ApprovalStatus.PENDING, ApprovalStatus.NOT_REQUIRED}:
        raise ApprovalRequired("A valid explicit approval is required")
    if approval.status is ApprovalStatus.REJECTED:
        raise ApprovalDenied("The requested action was rejected")
    if approval.status is not ApprovalStatus.APPROVED or not approval.approval_id:
        raise ApprovalRequired("Approval artifact is incomplete")
    if approval.policy_version and approval.policy_version != request.policy_version:
        raise ApprovalRequired("Approval artifact does not match the requested policy version")


def run_action(
    *,
    request: ActionRequest,
    approval: ApprovalArtifact,
    executor: Executor,
    verifier: Verifier,
    route: str,
    route_reason: str,
) -> EvidenceReceipt:
    """Execute one registered mutation after policy and approval gates, then verify.

    ``request.requires_approval`` is never trusted. The registry rewrites it from
    central policy before the executor is called. Registered but not-yet-enabled
    actions can still be proposed and approved, then fail closed at execution.
    """

    governed, policy = bind_request_to_policy(request)
    _enforce_approval(governed, approval)
    if not policy.executable:
        raise ActionUnavailable(
            f"Action {policy.action_type!r} is approved but execution remains blocked: {policy.truth_note}"
        )

    execution = executor.execute(governed)

    # A command returning success is not enough. Always call an independent verifier.
    verification = verifier.verify(governed, execution)
    quality_gate = "passed" if execution.success and verification.passed else "failed"
    evidence_refs: list[str] = []
    if approval.evidence_ref:
        evidence_refs.append(approval.evidence_ref)
    for key in ("evidence_ref", "evidence_refs"):
        value = execution.details.get(key)
        if isinstance(value, str):
            evidence_refs.append(value)
        elif isinstance(value, (list, tuple)):
            evidence_refs.extend(str(item) for item in value)

    return EvidenceReceipt(
        correlation_id=governed.correlation_id,
        route=route,
        route_reason=route_reason,
        policy_version=governed.policy_version,
        requested_action=governed.action_type,
        target_ref=governed.target_ref,
        executor=execution.executor,
        verifier=verification.verifier,
        action_success=execution.success,
        verification_passed=verification.passed,
        quality_gate=quality_gate,
        approval_ref=approval.evidence_ref,
        evidence_refs=tuple(evidence_refs),
        execution_details=dict(execution.details),
        observed_state=dict(verification.observed_state),
        governance_domain=policy.domain,
        risk_level=policy.risk.value,
        action_availability=policy.availability.value,
        requires_approval=policy.requires_approval,
        safe_return_action=policy.safe_return_action,
    )


__all__ = [
    "ActionUnavailable",
    "ApprovalDenied",
    "ApprovalRequired",
    "UnknownActionPolicy",
    "run_action",
]
