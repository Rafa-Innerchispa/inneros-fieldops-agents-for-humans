import pytest

from src.fieldops.contracts import (
    ActionRequest,
    ApprovalArtifact,
    ApprovalStatus,
    ExecutionResult,
    VerificationResult,
)
from src.fieldops.governance import (
    ActionUnavailable,
    READ_ONLY_CAPABILITIES,
    UnknownActionPolicy,
    action_catalog_payload,
    action_policy,
    list_action_policies,
    propose_action,
)
from src.fieldops.workflow import ApprovalRequired, run_action


class RecordingExecutor:
    def __init__(self):
        self.calls = 0

    def execute(self, request):
        self.calls += 1
        return ExecutionResult(
            correlation_id=request.correlation_id,
            executor="test-executor",
            success=True,
            details={},
        )


class PassingVerifier:
    def verify(self, request, execution):
        return VerificationResult(
            correlation_id=request.correlation_id,
            verifier="test-verifier",
            passed=True,
            observed_state={"ok": True},
        )


def test_every_registered_mutation_uses_the_same_approval_contract():
    policies = list_action_policies()
    assert len(policies) >= 9
    assert all(policy.requires_approval for policy in policies)
    assert {policy.domain for policy in policies} >= {
        "security",
        "lighting",
        "facility_iot",
        "telephony",
        "network",
        "energy",
        "alarm",
        "access",
    }


def test_every_registered_mutation_can_be_proposed_even_when_executor_is_blocked():
    for policy in list_action_policies():
        proposal = propose_action(
            ActionRequest(
                correlation_id=f"proposal-{policy.domain}",
                action_type=policy.action_type,
                target_ref=f"target-{policy.domain}",
                requires_approval=False,
            )
        )
        assert proposal.requires_approval is True
        assert proposal.action_type == policy.action_type
        assert proposal.availability == policy.availability.value


def test_read_only_observations_are_separate_and_do_not_need_mutation_approval():
    assert "energy.telemetry" in READ_ONLY_CAPABILITIES
    assert "network.telemetry" in READ_ONLY_CAPABILITIES
    assert all("apply" not in name for name in READ_ONLY_CAPABILITIES)


def test_dmx_is_registered_as_real_governed_physical_action():
    scene = action_policy("dmx.set_scene")
    blackout = action_policy("dmx.blackout")
    assert scene.availability.value == "enabled_real"
    assert scene.executor_id == "inneros-ag59"
    assert scene.verifier_id == "inneros-ag59-status"
    assert scene.safe_return_action == "dmx.blackout"
    assert blackout.availability.value == "enabled_real"


def test_blocked_domain_can_be_approved_but_cannot_reach_executor():
    executor = RecordingExecutor()
    request = ActionRequest(
        correlation_id="energy-blocked",
        action_type="energy.apply_bounded_control",
        target_ref="inverter-01",
        requires_approval=False,
    )
    with pytest.raises(ActionUnavailable):
        run_action(
            request=request,
            approval=ApprovalArtifact(
                status=ApprovalStatus.APPROVED,
                approval_id="approval-energy",
                policy_version="fieldops-v1",
            ),
            executor=executor,
            verifier=PassingVerifier(),
            route="local-edge",
            route_reason="test",
        )
    assert executor.calls == 0


def test_blocked_domain_still_requires_approval_before_execution_gate():
    executor = RecordingExecutor()
    request = ActionRequest(
        correlation_id="network-pending",
        action_type="network.apply_bounded_recovery",
        target_ref="ap-01",
        requires_approval=False,
    )
    with pytest.raises(ApprovalRequired):
        run_action(
            request=request,
            approval=ApprovalArtifact(status=ApprovalStatus.PENDING),
            executor=executor,
            verifier=PassingVerifier(),
            route="local-edge",
            route_reason="test",
        )
    assert executor.calls == 0


def test_caller_cannot_bypass_approval_for_real_dmx_action():
    executor = RecordingExecutor()
    request = ActionRequest(
        correlation_id="dmx-no-bypass",
        action_type="dmx.set_scene",
        target_ref="ag59",
        parameters={"scene": "aurora_verde_demo"},
        requires_approval=False,
    )
    with pytest.raises(ApprovalRequired):
        run_action(
            request=request,
            approval=ApprovalArtifact(status=ApprovalStatus.NOT_REQUIRED),
            executor=executor,
            verifier=PassingVerifier(),
            route="local-edge",
            route_reason="test",
        )
    assert executor.calls == 0


def test_unknown_mutation_fails_closed_before_executor():
    executor = RecordingExecutor()
    request = ActionRequest(
        correlation_id="unknown-action",
        action_type="robot.launch_missiles",
        target_ref="definitely-not-a-real-target",
    )
    with pytest.raises(UnknownActionPolicy):
        run_action(
            request=request,
            approval=ApprovalArtifact(
                status=ApprovalStatus.APPROVED,
                approval_id="approval-unknown",
            ),
            executor=executor,
            verifier=PassingVerifier(),
            route="local-edge",
            route_reason="test",
        )
    assert executor.calls == 0


def test_catalog_payload_is_serializable_and_truthful():
    payload = action_catalog_payload()
    telephony = next(item for item in payload if item["action_type"] == "telephony.originate_call")
    assert telephony["availability"] == "blocked"
    assert telephony["requires_approval"] is True
    assert "route verification" in str(telephony["truth_note"])
