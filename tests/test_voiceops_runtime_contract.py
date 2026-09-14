from __future__ import annotations

import pytest

from src.fieldops.contracts import ActionRequest, ApprovalArtifact, ApprovalStatus
from src.fieldops.governance import action_policy
from src.fieldops.observations import ObservationRequest
from src.fieldops.product_runtime import build_product_runtime
from src.fieldops.telephony_read_adapter import (
    LocalVoiceOpsRuntimeClient,
    TelephonyReadConfigurationError,
    TelephonyStatusObserver,
    TelephonyStatusVerifier,
    VoiceOpsOwnerCallbackExecutor,
    VoiceOpsOwnerCallbackVerifier,
)


class FakeVoiceOpsRuntimeClient:
    def __init__(self, *, contract_state: str = "READY", owner_registered: bool = True):
        self.contract_state = contract_state
        self.owner_registered = owner_registered
        self.callback_requests: list[dict[str, str]] = []
        self.receipts: dict[str, dict] = {}

    def status(self):
        owner = {
            "extension": "1004",
            "registered": self.owner_registered,
            "status": "Idle" if self.owner_registered else "Unavailable",
            "address": "192.168.1.4:50000" if self.owner_registered else None,
        }
        return {
            "ok": True,
            "contract": {
                "contract_version": "voiceops.fieldops.telephony.v1",
                "state": self.contract_state,
                "truth_label": "REAL",
                "owner_endpoint": owner,
                "owner_endpoints": [owner, {"extension": "1006", "registered": False}],
                "owner_confirmed_e2e_calling": True,
                "runtime": {
                    "ok": True,
                    "service": "inneros-voiceops-runtime",
                    "runtime_version": "voiceops-runtime-v1",
                    "autonomous_pstn_enabled": False,
                    "public_sip_rtp": False,
                },
            },
            "pbx_ami": {
                "reachable": True,
                "banner_valid": True,
                "banner_family": "Asterisk Call Manager",
            },
            "execution_owner": "voiceops",
            "fieldops_registers_sip": False,
            "fieldops_reads_credentials": False,
        }

    def request_owner_callback(self, *, correlation_id: str, reason: str, requested_by: str):
        self.callback_requests.append(
            {
                "correlation_id": correlation_id,
                "reason": reason,
                "requested_by": requested_by,
            }
        )
        receipt = {
            "contract_version": "voiceops.fieldops.telephony.v1",
            "autonomous_pstn_enabled": False,
            "result": {
                "status": "dispatched",
                "reason": "internal_owner_call_dispatched",
                "correlation_id": correlation_id,
                "target_extension": "1004",
                "call_id": f"call-{correlation_id}",
            },
        }
        self.receipts[correlation_id] = receipt
        return receipt

    def receipt(self, correlation_id: str):
        return self.receipts.get(correlation_id, {})


def test_contract_read_passes_even_when_owner_endpoint_is_temporarily_unregistered():
    client = FakeVoiceOpsRuntimeClient(contract_state="BLOCKED", owner_registered=False)
    observer = TelephonyStatusObserver(client)
    verifier = TelephonyStatusVerifier()
    request = ObservationRequest(
        correlation_id="telephony-contract-read",
        observation_type="telephony.read_status",
        target_ref="voiceops.ucm",
    )

    result = observer.observe(request)
    verification = verifier.verify(request, result)

    assert result.success is True
    assert verification.passed is True
    assert result.details["contract_version"] == "voiceops.fieldops.telephony.v1"
    assert result.details["contract_state"] == "BLOCKED"
    assert result.details["callback_ready"] is False
    assert result.details["owner_confirmed_e2e_calling"] is True
    assert result.details["autonomous_pstn_enabled"] is False


def test_runtime_client_rejects_public_or_https_endpoint():
    with pytest.raises(TelephonyReadConfigurationError):
        LocalVoiceOpsRuntimeClient(
            base_url="https://127.0.0.1:8796",
            pbx_ami_host="192.168.1.6",
        )
    with pytest.raises(TelephonyReadConfigurationError):
        LocalVoiceOpsRuntimeClient(
            base_url="http://example.com:8796",
            pbx_ami_host="192.168.1.6",
        )


def test_owner_callback_executor_never_accepts_destination_override():
    client = FakeVoiceOpsRuntimeClient()
    executor = VoiceOpsOwnerCallbackExecutor(client)
    request = ActionRequest(
        correlation_id="forbidden-destination",
        action_type="telephony.request_owner_callback",
        target_ref="voiceops.owner",
        parameters={"target_extension": "0999999999", "reason": "do not dial this"},
    )

    result = executor.execute(request)

    assert result.success is False
    assert result.details["reason"] == "destination_override_forbidden"
    assert client.callback_requests == []


def test_governed_owner_callback_passes_approval_execute_verify_evidence_loop():
    client = FakeVoiceOpsRuntimeClient()
    bundle = build_product_runtime(
        env={},
        telephony_read_client=client,
        telephony_callback_client=client,
    )
    assert "telephony.request_owner_callback" in bundle.bindings
    policy = action_policy("telephony.request_owner_callback")
    assert policy.requires_approval is True
    assert policy.availability.value == "enabled_real"

    request = ActionRequest(
        correlation_id="governed-callback-001",
        action_type="telephony.request_owner_callback",
        target_ref="voiceops.owner",
        parameters={"reason": "FieldOps needs owner approval for a critical action."},
    )
    approval = ApprovalArtifact(
        status=ApprovalStatus.APPROVED,
        approval_id="approval-001",
        approver_id="owner",
        policy_version="fieldops-v1",
        evidence_ref="evidence://approval/001",
    )

    receipt = bundle.runtime.execute(request=request, approval=approval)

    assert receipt.quality_gate == "passed"
    assert receipt.requested_action == "telephony.request_owner_callback"
    assert receipt.target_ref == "voiceops.owner"
    assert receipt.execution_details["target_extension"] == "1004"
    assert receipt.execution_details["autonomous_pstn_enabled"] is False
    assert receipt.observed_state["owner_allowlisted"] is True
    assert receipt.observed_state["autonomous_pstn_enabled"] is False
    assert client.callback_requests == [
        {
            "correlation_id": "governed-callback-001",
            "reason": "FieldOps needs owner approval for a critical action.",
            "requested_by": "fieldops",
        }
    ]


def test_arbitrary_originate_policy_remains_blocked():
    policy = action_policy("telephony.originate_call")
    assert policy.availability.value == "blocked"
