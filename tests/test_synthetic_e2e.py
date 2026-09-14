import pytest

from src.fieldops.contracts import ActionRequest, ApprovalArtifact, ApprovalStatus
from src.fieldops.synthetic import SyntheticDevice, SyntheticEdgeExecutor, SyntheticStateVerifier
from src.fieldops.workflow import ApprovalRequired, run_action


def test_synthetic_edge_flow_changes_state_and_verifies():
    device = SyntheticDevice()
    assert device.state["healthy"] is False

    # Legacy wire name is accepted but canonicalized by central governance.
    request = ActionRequest(
        correlation_id="e2e-001",
        action_type="service_restart",
        target_ref=device.name,
        expected_state={"healthy": True},
        requires_approval=False,
    )
    receipt = run_action(
        request=request,
        approval=ApprovalArtifact(
            status=ApprovalStatus.APPROVED,
            approval_id="approval-e2e-001",
            approver_id="synthetic-human",
            evidence_ref="evidence://approval-e2e-001",
        ),
        executor=SyntheticEdgeExecutor(device),
        verifier=SyntheticStateVerifier(device),
        route="local-edge",
        route_reason="privacy_and_device_locality",
    )

    assert device.state["healthy"] is True
    assert receipt.action_success is True
    assert receipt.verification_passed is True
    assert receipt.requested_action == "camera.service_restart"
    assert receipt.approval_ref == "evidence://approval-e2e-001"


def test_unknown_target_without_approval_never_reaches_executor():
    device = SyntheticDevice()
    request = ActionRequest(
        correlation_id="e2e-002",
        action_type="service_restart",
        target_ref="unknown-device",
        expected_state={"healthy": True},
        requires_approval=False,
    )
    with pytest.raises(ApprovalRequired):
        run_action(
            request=request,
            approval=ApprovalArtifact(status=ApprovalStatus.NOT_REQUIRED),
            executor=SyntheticEdgeExecutor(device),
            verifier=SyntheticStateVerifier(device),
            route="local-edge",
            route_reason="synthetic_test",
        )

    assert device.state["healthy"] is False
