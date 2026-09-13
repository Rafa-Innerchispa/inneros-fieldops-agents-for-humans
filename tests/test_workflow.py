from src.fieldops.contracts import (
    ActionRequest,
    ApprovalArtifact,
    ApprovalStatus,
    ExecutionResult,
    VerificationResult,
)
from src.fieldops.workflow import ApprovalDenied, ApprovalRequired, run_action


class FakeExecutor:
    def __init__(self):
        self.calls = 0

    def execute(self, request):
        self.calls += 1
        success = request.action_type != "fail_execution"
        return ExecutionResult(
            correlation_id=request.correlation_id,
            executor="inneros-edge-01",
            success=success,
            details={
                "command": "bounded-demo-action",
                "evidence_ref": f"evidence://execution/{request.correlation_id}",
            },
        )


class FakeVerifier:
    def __init__(self, passed=True):
        self.passed = passed
        self.calls = 0

    def verify(self, request, execution):
        self.calls += 1
        return VerificationResult(
            correlation_id=request.correlation_id,
            verifier="synthetic-state-probe",
            passed=self.passed,
            observed_state={"healthy": self.passed},
        )


def risky_request():
    return ActionRequest(
        correlation_id="demo-001",
        action_type="service_restart",
        target_ref="synthetic-camera-gateway",
        expected_state={"healthy": True},
        requires_approval=True,
    )


def test_missing_approval_fails_before_execution():
    executor = FakeExecutor()
    try:
        run_action(
            request=risky_request(),
            approval=ApprovalArtifact(status=ApprovalStatus.PENDING),
            executor=executor,
            verifier=FakeVerifier(),
            route="local-edge",
            route_reason="privacy",
        )
        assert False, "expected ApprovalRequired"
    except ApprovalRequired:
        assert executor.calls == 0


def test_rejected_approval_fails_before_execution():
    executor = FakeExecutor()
    try:
        run_action(
            request=risky_request(),
            approval=ApprovalArtifact(status=ApprovalStatus.REJECTED),
            executor=executor,
            verifier=FakeVerifier(),
            route="local-edge",
            route_reason="privacy",
        )
        assert False, "expected ApprovalDenied"
    except ApprovalDenied:
        assert executor.calls == 0


def test_approved_action_is_executed_and_verified():
    executor = FakeExecutor()
    verifier = FakeVerifier(passed=True)
    receipt = run_action(
        request=risky_request(),
        approval=ApprovalArtifact(
            status=ApprovalStatus.APPROVED,
            approval_id="approval-demo-001",
            approver_id="synthetic-human",
            evidence_ref="evidence://approval-demo-001",
        ),
        executor=executor,
        verifier=verifier,
        route="local-edge",
        route_reason="privacy_and_device_locality",
    )
    assert executor.calls == 1
    assert verifier.calls == 1
    assert receipt.action_success is True
    assert receipt.verification_passed is True
    assert receipt.executor == "inneros-edge-01"
    assert receipt.verifier == "synthetic-state-probe"
    assert receipt.quality_gate == "passed"
    assert receipt.requested_action == "service_restart"
    assert receipt.target_ref == "synthetic-camera-gateway"
    assert "evidence://approval-demo-001" in receipt.evidence_refs
    assert "evidence://execution/demo-001" in receipt.evidence_refs



def test_failed_execution_still_gets_verified_and_fails_quality_gate():
    executor = FakeExecutor()
    verifier = FakeVerifier(passed=True)
    request = ActionRequest(
        correlation_id="demo-failed-execution",
        action_type="fail_execution",
        target_ref="synthetic-camera-gateway",
        expected_state={"healthy": True},
        requires_approval=True,
    )

    receipt = run_action(
        request=request,
        approval=ApprovalArtifact(
            status=ApprovalStatus.APPROVED,
            approval_id="approval-demo-failed-execution",
            approver_id="synthetic-human",
            evidence_ref="evidence://approval-demo-failed-execution",
        ),
        executor=executor,
        verifier=verifier,
        route="local-edge",
        route_reason="test_failed_execution",
    )

    assert executor.calls == 1
    assert verifier.calls == 1
    assert receipt.action_success is False
    assert receipt.verification_passed is True
    assert receipt.quality_gate == "failed"


def test_failed_verification_fails_quality_gate_even_when_execution_succeeds():
    executor = FakeExecutor()
    verifier = FakeVerifier(passed=False)

    receipt = run_action(
        request=risky_request(),
        approval=ApprovalArtifact(
            status=ApprovalStatus.APPROVED,
            approval_id="approval-demo-failed-verification",
            approver_id="synthetic-human",
            evidence_ref="evidence://approval-demo-failed-verification",
        ),
        executor=executor,
        verifier=verifier,
        route="local-edge",
        route_reason="test_failed_verification",
    )

    assert executor.calls == 1
    assert verifier.calls == 1
    assert receipt.action_success is True
    assert receipt.verification_passed is False
    assert receipt.quality_gate == "failed"
