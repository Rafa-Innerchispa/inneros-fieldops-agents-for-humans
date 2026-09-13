"""Run a safe end-to-end InnerOS FieldOps demonstration."""

from __future__ import annotations

import json
from dataclasses import asdict

from src.fieldops.contracts import ActionRequest, ApprovalArtifact, ApprovalStatus
from src.fieldops.synthetic import SyntheticDevice, SyntheticEdgeExecutor, SyntheticStateVerifier
from src.fieldops.workflow import run_action


def main() -> None:
    device = SyntheticDevice()
    request = ActionRequest(
        correlation_id="fieldops-demo-001",
        action_type="service_restart",
        target_ref=device.name,
        expected_state={"healthy": True},
        requires_approval=True,
    )
    approval = ApprovalArtifact(
        status=ApprovalStatus.APPROVED,
        approval_id="approval-fieldops-demo-001",
        approver_id="synthetic-human",
        policy_version="fieldops-v1",
        evidence_ref="evidence://approval-fieldops-demo-001",
    )

    before = dict(device.state)
    receipt = run_action(
        request=request,
        approval=approval,
        executor=SyntheticEdgeExecutor(device),
        verifier=SyntheticStateVerifier(device),
        route="local-edge",
        route_reason="privacy_and_device_locality",
    )
    output = {
        "before": before,
        "after": dict(device.state),
        "receipt": asdict(receipt),
    }
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
