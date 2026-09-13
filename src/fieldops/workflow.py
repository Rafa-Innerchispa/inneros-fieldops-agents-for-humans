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

    return EvidenceReceipt(
        correlation_id=request.correlation_id,
        route=route,
        route_reason=route_reason,
        policy_version=request.policy_version,
        executor=execution.executor,
        action_success=execution.success,
        verification_passed=verification.passed,
        approval_ref=approval.evidence_ref,
    )
