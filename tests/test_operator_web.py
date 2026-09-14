from src.fieldops.operator_web import _loopback, render_operator_page
from src.fieldops.product_runtime import build_product_runtime


class FakeHA:
    def configured(self):
        return True

    def get_state(self, entity_id):
        return {"ok": True, "entity": {"entity_id": entity_id, "state": "off"}}

    def call_service(self, domain, service, *, entity_id=None, data=None):
        return {"ok": True}


def test_operator_console_is_primary_product_surface_not_judge_mode():
    bundle = build_product_runtime(
        {"FIELDOPS_HA_LIGHT_ALLOWLIST": "light.cinta_escritorio"},
        ha_client=FakeHA(),
    )
    html = render_operator_page(bundle)
    assert "FieldOps <b>Operator Console</b>" in html
    assert "Prepare a real proposal" in html
    assert "HA REAL: BOUND" in html
    assert "Open hackathon judge evidence view" in html
    assert "Judge Mode" not in html


def test_loopback_guard_accepts_only_loopback_addresses():
    assert _loopback("127.0.0.1") is True
    assert _loopback("::1") is True
    assert _loopback("localhost") is True
    assert _loopback("192.168.1.4") is False
