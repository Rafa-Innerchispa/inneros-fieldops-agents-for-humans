"""Run a safe end-to-end InnerOS FieldOps demonstration."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.fieldops.contracts import ActionRequest, ApprovalArtifact, ApprovalStatus
from src.fieldops.providers import ModelProviderConfig, ProviderConfigError, load_provider_config
from src.fieldops.synthetic import SyntheticDevice, SyntheticEdgeExecutor, SyntheticStateVerifier
from src.fieldops.workflow import ApprovalDenied, ApprovalRequired, run_action


def _approval_for_scenario(scenario: str) -> ApprovalArtifact:
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


def run_demo(scenario: str, provider: ModelProviderConfig) -> dict[str, object]:
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
    approval = _approval_for_scenario(scenario)

    before = dict(device.state)
    try:
        receipt = run_action(
            request=request,
            approval=approval,
            executor=SyntheticEdgeExecutor(device),
            verifier=SyntheticStateVerifier(device),
            route=provider.route,
            route_reason=provider.route_reason,
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
        "provider": asdict(provider),
        "receipt": asdict(receipt) if receipt else None,
        "scenario": scenario,
        "status": status,
    }
    if error:
        output["error"] = error
    return output


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a credential-free InnerOS FieldOps synthetic demo."
    )
    parser.add_argument(
        "--scenario",
        choices=["happy", "denied", "failed-execution", "failed-verification"],
        default="happy",
        help="Synthetic path to exercise.",
    )
    parser.add_argument(
        "--provider",
        choices=["local", "bedrock"],
        default=None,
        help="Override FIELDOPS_MODEL_PROVIDER for routing evidence only.",
    )
    args = parser.parse_args()

    try:
        provider = load_provider_config()
        if args.provider:
            provider = load_provider_config(
                {**provider.to_env_overlay(), "FIELDOPS_MODEL_PROVIDER": args.provider}
            )
    except ProviderConfigError as exc:
        parser.exit(2, f"configuration error: {exc}\n")

    output = run_demo(args.scenario, provider)
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
