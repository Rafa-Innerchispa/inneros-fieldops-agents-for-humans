from src.fieldops.operator_api import catalog_response, execute_response, propose_response
from src.fieldops.product_runtime import build_product_runtime


class FakeHA:
    def __init__(self):
        self.states = {"light.cinta_escritorio": "off"}

    def configured(self):
        return True

    def get_state(self, entity_id):
        if entity_id not in self.states:
            return {"ok": False}
        return {"ok": True, "entity": {"entity_id": entity_id, "state": self.states[entity_id]}}

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


def ha_payload():
    return {
        "correlation_id": "operator-ha-001",
        "action_type": "homeassistant.entity_control",
        "target_ref": "light.cinta_escritorio",
        "parameters": {"state": "on"},
        "expected_state": {"state": "on"},
    }


def test_catalog_reports_real_runtime_binding():
    out = catalog_response(bundle())
    row = next(item for item in out["actions"] if item["action_type"] == "homeassistant.entity_control")
    assert row["availability"] == "enabled_real"
    assert row["runtime_bound"] is True


def test_proposal_centrally_requires_approval_even_if_client_does_not_request_it():
    out = propose_response(bundle(), ha_payload())
    assert out["ok"] is True
    assert out["request"]["requires_approval"] is False
    assert out["proposal"]["requires_approval"] is True
    assert out["proposal"]["executable"] is True


def test_execute_without_explicit_approval_is_blocked_before_mutation():
    runtime = bundle()
    out = execute_response(runtime, ha_payload())
    assert out["ok"] is False
    assert out["status"] == "blocked"
    assert out["error"] == "ApprovalRequired"


def test_approved_real_ha_action_executes_verifies_and_receipts():
    runtime = bundle()
    payload = {
        **ha_payload(),
        "approval": {
            "status": "approved",
            "approval_id": "approval-operator-ha-001",
            "approver_id": "owner",
            "evidence_ref": "evidence://approval/operator-ha-001",
        },
    }
    out = execute_response(runtime, payload)
    assert out["ok"] is True
    assert out["status"] == "completed"
    receipt = out["receipt"]
    assert receipt["requested_action"] == "homeassistant.entity_control"
    assert receipt["quality_gate"] == "passed"
    assert receipt["verification_passed"] is True
    assert receipt["observed_state"]["state"] == "on"


def test_registered_but_blocked_energy_action_cannot_execute():
    runtime = bundle()
    payload = {
        "action_type": "energy.apply_bounded_control",
        "target_ref": "inverter",
        "parameters": {"mode": "anything"},
        "approval": {
            "status": "approved",
            "approval_id": "approval-energy-001",
            "approver_id": "owner",
        },
    }
    out = execute_response(runtime, payload)
    assert out["ok"] is False
    assert out["status"] == "blocked"
    assert out["error"] in {"ActionAdapterNotBound", "ActionUnavailable"}
