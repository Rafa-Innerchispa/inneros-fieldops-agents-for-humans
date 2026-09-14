import pytest

from src.fieldops.contracts import (
    ActionRequest,
    ApprovalArtifact,
    ApprovalStatus,
    ExecutionResult,
    VerificationResult,
)
from src.fieldops.runtime import ActionAdapterNotBound, GovernedActionRuntime


class Executor:
    def execute(self, request):
        return ExecutionResult(
            correlation_id=request.correlation_id,
            executor="bound-executor",
            success=True,
            details={},
        )


class Verifier:
    def verify(self, request, execution):
        return VerificationResult(
            correlation_id=request.correlation_id,
            verifier="bound-verifier",
            passed=True,
            observed_state={"verified": True},
        )


def test_runtime_uses_same_proposal_contract_for_unbound_domains():
    runtime = GovernedActionRuntime()
    proposal = runtime.proposal(
        ActionRequest(
            correlation_id="call-proposal",
            action_type="telephony.originate_call",
            target_ref="owner-mobile",
        )
    )
    assert proposal.requires_approval is True
    assert proposal.availability == "blocked"
    assert proposal.domain == "telephony"


def test_runtime_requires_a_bound_adapter_before_execution():
    runtime = GovernedActionRuntime()
    with pytest.raises(ActionAdapterNotBound):
        runtime.execute(
            request=ActionRequest(
                correlation_id="dmx-unbound",
                action_type="dmx.set_scene",
                target_ref="ag59",
                parameters={"scene": "aurora_verde_demo"},
            ),
            approval=ApprovalArtifact(
                status=ApprovalStatus.APPROVED,
                approval_id="approved-dmx",
                policy_version="fieldops-v1",
            ),
        )


def test_runtime_binding_still_cannot_bypass_central_approval():
    runtime = GovernedActionRuntime()
    runtime.register("dmx.set_scene", executor=Executor(), verifier=Verifier())
    with pytest.raises(Exception) as exc:
        runtime.execute(
            request=ActionRequest(
                correlation_id="dmx-bound",
                action_type="dmx.set_scene",
                target_ref="ag59",
                parameters={"scene": "aurora_verde_demo"},
                requires_approval=False,
            ),
            approval=ApprovalArtifact(status=ApprovalStatus.PENDING),
        )
    assert exc.value.__class__.__name__ == "ApprovalRequired"


def test_runtime_emits_receipt_for_bound_approved_action():
    runtime = GovernedActionRuntime(route="local-edge", route_reason="test")
    runtime.register("dmx.set_scene", executor=Executor(), verifier=Verifier())
    receipt = runtime.execute(
        request=ActionRequest(
            correlation_id="dmx-bound-ok",
            action_type="dmx.set_scene",
            target_ref="ag59",
            parameters={"scene": "aurora_verde_demo"},
        ),
        approval=ApprovalArtifact(
            status=ApprovalStatus.APPROVED,
            approval_id="approved-dmx-ok",
            policy_version="fieldops-v1",
        ),
    )
    assert receipt.quality_gate == "passed"
    assert receipt.governance_domain == "lighting"
    assert runtime.bound_actions() == ("dmx.set_scene",)
