from src.fieldops.contracts import ActionRequest, ExecutionResult
from src.fieldops.ha_adapter import (
    HomeAssistantBindingConfig,
    HomeAssistantEntityExecutor,
    HomeAssistantEntityVerifier,
    allowlist_from_env,
)


class FakeHA:
    def __init__(self):
        self.states = {
            "light.cinta_escritorio": "off",
            "light.luz_estudio_uno": "off",
        }
        self.calls = []

    def configured(self):
        return True

    def get_state(self, entity_id):
        if entity_id not in self.states:
            return {"ok": False, "error": "not_found"}
        return {
            "ok": True,
            "entity": {"entity_id": entity_id, "state": self.states[entity_id]},
        }

    def call_service(self, domain, service, *, entity_id=None, data=None):
        self.calls.append((domain, service, entity_id, data))
        if domain != "light" or entity_id not in self.states:
            return {"ok": False}
        if service == "turn_on":
            self.states[entity_id] = "on"
        elif service == "turn_off":
            self.states[entity_id] = "off"
        else:
            return {"ok": False}
        return {"ok": True}


def request(target="light.cinta_escritorio", state="on"):
    return ActionRequest(
        correlation_id="ha-real-001",
        action_type="homeassistant.entity_control",
        target_ref=target,
        parameters={"state": state},
        expected_state={"state": state},
    )


def config():
    return HomeAssistantBindingConfig(
        allowed_lights=frozenset({"light.cinta_escritorio", "light.luz_estudio_uno"})
    )


def test_env_allowlist_accepts_only_light_entities():
    allowed = allowlist_from_env(
        {
            "FIELDOPS_HA_LIGHT_ALLOWLIST": (
                "light.cinta_escritorio,switch.unsafe, light.luz_estudio_uno, nonsense"
            )
        }
    )
    assert allowed == frozenset({"light.cinta_escritorio", "light.luz_estudio_uno"})


def test_executor_sets_allowlisted_light_and_verifier_reads_it_back():
    client = FakeHA()
    execution = HomeAssistantEntityExecutor(client, config()).execute(request())
    assert execution.success is True
    assert execution.details["before_state"] == "off"
    assert execution.details["rollback_state"] == "off"
    assert client.calls == [("light", "turn_on", "light.cinta_escritorio", None)]

    verification = HomeAssistantEntityVerifier(client, config()).verify(request(), execution)
    assert verification.passed is True
    assert verification.observed_state["state"] == "on"


def test_non_allowlisted_entity_never_reaches_home_assistant_service_call():
    client = FakeHA()
    execution = HomeAssistantEntityExecutor(client, config()).execute(
        request(target="light.luz_cocina")
    )
    assert execution.success is False
    assert execution.details["reason"] == "target_not_allowlisted"
    assert client.calls == []


def test_invalid_state_never_reaches_home_assistant_service_call():
    client = FakeHA()
    execution = HomeAssistantEntityExecutor(client, config()).execute(request(state="toggle"))
    assert execution.success is False
    assert execution.details["reason"] == "invalid_desired_state"
    assert client.calls == []


def test_verifier_rejects_executor_ack_when_readback_does_not_match():
    client = FakeHA()
    fake_ack = ExecutionResult(
        correlation_id="ha-real-001",
        executor="inneros-ha-service-bridge",
        success=True,
        details={"backend_ack": True},
    )
    verification = HomeAssistantEntityVerifier(client, config()).verify(request(), fake_ack)
    assert verification.passed is False
    assert verification.observed_state["state"] == "off"
