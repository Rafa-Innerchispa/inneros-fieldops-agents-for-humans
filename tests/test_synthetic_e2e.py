from src.fieldops.contracts import ActionRequest, ApprovalArtifact, ApprovalStatus
from src.fieldops.synthetic import SyntheticDevice, SyntheticEdgeExecutor, SyntheticStateVerifier
from src.fieldops.workflow import run_action


def test_synthetic_edge_flow_changes_state_and_verifies():
    device = SyntheticDevice()
    assert device.state["healthy"] is False

    request = ActionRequest(
        correlation_id="e2e-001",
        action_type="service_restart",
        target_ref=device.name,
        expected_state={"healthy": True},
        requires_approval=True,
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
    assert receipt.approval_ref == "evidence://approval-e2e-001"


def test_unknown_target_does_not_verify_successfully():
    device = SyntheticDevice()
    request = ActionRequest(
        correlation_id="e2e-002",
        action_type="service_restart",
        target_ref="unknown-device",
        expected_state={"healthy": True},
        requires_approval=False,
    )
    receipt = run_action(
        request=request,
        approval=ApprovalArtifact(status=ApprovalStatus.NOT_REQUIRED),
        executor=SyntheticEdgeExecutor(device),
        verifier=SyntheticStateVerifier(device),
        route="local-edge",
        route_reason="synthetic_test",
    )

    assert receipt.action_success is False
    assert receipt.verification_passed is False
    assert device.state["healthy"] is False
