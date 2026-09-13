"""Minimal governed FieldOps workflow.

The workflow is deliberately provider-neutral so Strands, a local agent, or another
orchestrator can call the same execution boundary.
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


def run_action(
    *,
    request: ActionRequest,
    approval: ApprovalArtifact,
    executor: Executor,
    verifier: Verifier,
    route: str,
    route_reason: str,
) -> EvidenceReceipt:
    """Execute only after gates pass, then independently verify the outcome."""

    _enforce_approval(request, approval)
    execution = executor.execute(request)

    # A command returning success is not enough. Always call the verifier.
    verification = verifier.verify(request, execution)
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
        correlation_id=request.correlation_id,
        route=route,
        route_reason=route_reason,
        policy_version=request.policy_version,
        requested_action=request.action_type,
        target_ref=request.target_ref,
        executor=execution.executor,
        verifier=verification.verifier,
        action_success=execution.success,
        verification_passed=verification.passed,
        quality_gate=quality_gate,
        approval_ref=approval.evidence_ref,
        evidence_refs=tuple(evidence_refs),
        execution_details=dict(execution.details),
        observed_state=dict(verification.observed_state),
    )
