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


class FakeDMX:
    def status(self):
        return {
            "ok": True,
            "status": "online",
            "running": False,
            "current_effect": None,
            "supported_scenes": ["aurora_verde_demo"],
        }

    def set_scene(self, scene, speed=1.0):
        return {"ok": True}

    def blackout(self):
        return {"ok": True}


class FakeTelephonyRead:
    def status(self):
        return {
            "ok": True,
            "voiceops": {
                "ok": True,
                "service": "inneros-voiceops",
                "live_voice_enabled": True,
                "credential_configured": True,
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


def test_product_runtime_binds_real_ha_and_dmx_when_configured():
    bundle = build_product_runtime(
        {"FIELDOPS_HA_LIGHT_ALLOWLIST": "light.cinta_escritorio"},
        ha_client=FakeHA(),
        dmx_client=FakeDMX(),
    )
    assert "homeassistant.entity_control" in bundle.bindings
    assert "dmx.set_scene" in bundle.bindings
    assert "dmx.blackout" in bundle.bindings
    assert bundle.ha_allowlist == ("light.cinta_escritorio",)


def test_product_runtime_binds_telephony_observation_without_owning_sip_execution():
    bundle = build_product_runtime(
        {"FIELDOPS_HA_LIGHT_ALLOWLIST": "light.cinta_escritorio"},
        ha_client=FakeHA(),
        telephony_read_client=FakeTelephonyRead(),
    )
    assert "telephony.read_status" in bundle.observation_bindings
    assert "telephony.originate_call" not in bundle.bindings


def test_product_runtime_does_not_bind_ha_without_explicit_allowlist():
    bundle = build_product_runtime(
        {"FIELDOPS_HA_LIGHT_ALLOWLIST": ""},
        ha_client=FakeHA(),
    )
    assert "homeassistant.entity_control" not in bundle.bindings
    assert any(item.startswith("homeassistant:") for item in bundle.errors)
