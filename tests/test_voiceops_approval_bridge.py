from __future__ import annotations

from src.fieldops.operator_api import (
    voiceops_execute_response,
    voiceops_propose_response,
)
from src.fieldops.operator_web import _direct_local_execution_allowed
from src.fieldops.product_runtime import build_product_runtime


class FakeHA:
    def __init__(self):
        self.states = {"light.cinta_escritorio": "off"}

    def configured(self):
        return True

    def get_state(self, entity_id):
        if entity_id not in self.states:
            return {"ok": False}
        return {
            "ok": True,
            "entity": {"entity_id": entity_id, "state": self.states[entity_id]},
        }

    def call_service(self, domain, service, *, entity_id=None, data=None):
        if domain != "light" or entity_id not in self.states:
            return {"ok": False}
        self.states[entity_id] = "on" if service == "turn_on" else "off"
        return {"ok": True}


def bundle():
    return build_product_runtime(
        {"FIELDOPS_HA_LIGHT_ALLOWLIST": "light.cinta_escritorio"},
        ha_client=FakeHA(),
    )


def request_payload():
    return {
        "correlation_id": "voiceops-fieldops-001",
        "action_type": "homeassistant.entity_control",
        "target_ref": "light.cinta_escritorio",
        "parameters": {"state": "on"},
        "expected_state": {"state": "on"},
    }


def test_voiceops_propose_uses_central_governance():
    out = voiceops_propose_response(bundle(), request_payload())

    assert out["ok"] is True
    assert out["bridge"] == "voiceops-loopback"
    assert out["proposal"]["requires_approval"] is True
    assert out["proposal"]["availability"] == "enabled_real"
    assert out["runtime_bound"] is True


def test_voice_approval_enters_normal_execute_and_independent_verifier():
    runtime = bundle()
    out = voiceops_execute_response(
        runtime,
        {
            "request": request_payload(),
            "voice_approval": {
                "approval_id": "vxp_123456",
                "evidence_ref": "evidence://voiceops/approval/voiceops-fieldops-001/vxp_123456",
                "approver_id": "ignored-client-value",
            },
        },
    )

    assert out["ok"] is True
    assert out["status"] == "completed"
    receipt = out["receipt"]
    assert receipt["quality_gate"] == "passed"
    assert receipt["verification_passed"] is True
    assert receipt["approval_ref"].startswith("evidence://voiceops/approval/")
    assert receipt["observed_state"]["state"] == "on"
    assert "ejecutada y verificada" in out["spoken_summary"]


def test_invalid_voice_evidence_fails_closed_before_execution():
    runtime = bundle()
    out = voiceops_execute_response(
        runtime,
        {
            "request": request_payload(),
            "voice_approval": {
                "approval_id": "vxp_bad",
                "evidence_ref": "https://not-accepted.example/approval",
            },
        },
    )

    assert out["ok"] is False
    assert out["status"] == "blocked"
    assert out["error"] == "OperatorRequestError"
    assert runtime.runtime.is_bound("homeassistant.entity_control") is True


def test_blocked_action_remains_blocked_even_with_voice_approval():
    out = voiceops_execute_response(
        bundle(),
        {
            "request": {
                "correlation_id": "voiceops-energy-001",
                "action_type": "energy.apply_bounded_control",
                "target_ref": "inverter",
                "parameters": {"mode": "anything"},
            },
            "voice_approval": {
                "approval_id": "vxp_energy",
                "evidence_ref": "evidence://voiceops/approval/voiceops-energy-001/vxp_energy",
            },
        },
    )

    assert out["ok"] is False
    assert out["status"] == "blocked"
    assert "No marqué la acción" in out["spoken_summary"]


class DummyHandler:
    def __init__(self, client, host):
        self.client_address = (client, 45678)
        self.headers = {"Host": host}


def test_voiceops_http_bridge_requires_explicit_loopback_execution_gate(monkeypatch):
    monkeypatch.setenv("FIELDOPS_OPERATOR_HTTP_EXECUTION", "1")
    assert _direct_local_execution_allowed(DummyHandler("127.0.0.1", "127.0.0.1:8777")) is True
    assert _direct_local_execution_allowed(DummyHandler("192.168.1.4", "127.0.0.1:8777")) is False
    assert _direct_local_execution_allowed(DummyHandler("127.0.0.1", "inneros.creatorcore.ai")) is False

    monkeypatch.setenv("FIELDOPS_OPERATOR_HTTP_EXECUTION", "0")
    assert _direct_local_execution_allowed(DummyHandler("127.0.0.1", "127.0.0.1:8777")) is False
