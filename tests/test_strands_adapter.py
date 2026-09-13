from src.fieldops.contracts import ApprovalArtifact, ApprovalStatus
from src.fieldops.strands_adapter import execute_field_action
from src.fieldops.synthetic import SyntheticDevice, SyntheticEdgeExecutor, SyntheticStateVerifier


def test_strands_shaped_adapter_uses_governed_fieldops_boundary():
    device = SyntheticDevice()
    result = execute_field_action(
        correlation_id="strands-demo-001",
        action_type="service_restart",
        target_ref=device.name,
        parameters={},
        expected_state={"healthy": True},
        requires_approval=True,
        approval=ApprovalArtifact(
            status=ApprovalStatus.APPROVED,
            approval_id="approval-strands-demo-001",
            approver_id="synthetic-human",
            evidence_ref="evidence://approval-strands-demo-001",
        ),
        executor=SyntheticEdgeExecutor(device),
        verifier=SyntheticStateVerifier(device),
        route="local-edge",
        route_reason="privacy_and_device_locality",
    )

    assert result["action_success"] is True
    assert result["verification_passed"] is True
    assert result["executor"] == "inneros-edge-01"
