"""Reusable synthetic FieldOps demo runner."""

from __future__ import annotations

from dataclasses import asdict

from .contracts import ActionRequest, ApprovalArtifact, ApprovalStatus
from .providers import ModelProviderConfig, load_provider_config
from .synthetic import SyntheticDevice, SyntheticEdgeExecutor, SyntheticStateVerifier
from .workflow import ApprovalDenied, ApprovalRequired, run_action

SCENARIOS = ("happy", "denied", "failed-execution", "failed-verification")


def approval_for_scenario(scenario: str) -> ApprovalArtifact:
    if scenario == "denied":
        return ApprovalArtifact(
            status=ApprovalStatus.REJECTED,
            approval_id="approval-fieldops-demo-denied",
            approver_id="synthetic-human",
            policy_version="fieldops-v1",
            evidence_ref="evidence://approval-fieldops-demo-denied",
        )
    return ApprovalArtifact(
        status=ApprovalStatus.APPROVED,
        approval_id="approval-fieldops-demo-001",
        approver_id="synthetic-human",
        policy_version="fieldops-v1",
        evidence_ref="evidence://approval-fieldops-demo-001",
    )


def run_demo(
    scenario: str = "happy", provider: ModelProviderConfig | None = None
) -> dict[str, object]:
    """Run one credential-free demo scenario and return serializable evidence."""

    if scenario not in SCENARIOS:
        raise ValueError(f"Unsupported scenario: {scenario}")
    provider_config = provider or load_provider_config()
    device = SyntheticDevice()
    action_type = "unsupported_action" if scenario == "failed-execution" else "service_restart"
    expected_state = {"healthy": False} if scenario == "failed-verification" else {"healthy": True}
    request = ActionRequest(
        correlation_id=f"fieldops-demo-{scenario}",
        action_type=action_type,
        target_ref=device.name,
        expected_state=expected_state,
        requires_approval=True,
    )
    approval = approval_for_scenario(scenario)

    before = dict(device.state)
    try:
        receipt = run_action(
            request=request,
            approval=approval,
            executor=SyntheticEdgeExecutor(device),
            verifier=SyntheticStateVerifier(device),
            route=provider_config.route,
            route_reason=provider_config.route_reason,
        )
        status = "ok" if receipt.quality_gate == "passed" else "not_ready"
        error = None
    except (ApprovalDenied, ApprovalRequired) as exc:
        receipt = None
        status = "blocked"
        error = {"type": exc.__class__.__name__, "message": str(exc)}

    output: dict[str, object] = {
        "before": before,
        "after": dict(device.state),
        "provider": asdict(provider_config),
        "receipt": asdict(receipt) if receipt else None,
        "scenario": scenario,
        "status": status,
    }
    if error:
        output["error"] = error
    return output
