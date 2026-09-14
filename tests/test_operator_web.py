import time

import pytest

from src.fieldops.operator_web import (
    _auth_config,
    _camera_preview_from_edge,
    _loopback,
    _operator_authenticated,
    _sign_session,
    render_operator_page,
)
from src.fieldops.product_runtime import build_product_runtime


class FakeHA:
    def configured(self):
        return True

    def get_state(self, entity_id):
        state = "disarmed" if entity_id.startswith("alarm_control_panel.") else "off"
        return {"ok": True, "entity": {"entity_id": entity_id, "state": state, "attributes": {}}}

    def list_states(self, *, domain=None, limit=80):
        return {
            "ok": True,
            "count": 1,
            "entities": [
                {
                    "entity_id": "binary_sensor.panel_home_ralphi_zona_01",
                    "state": "off",
                    "friendly_name": "Panel Home Ralphi Zona 01",
                }
            ],
        }

    def call_service(self, domain, service, *, entity_id=None, data=None):
        return {"ok": True}


def test_operator_console_is_primary_product_surface_not_judge_mode():
    bundle = build_product_runtime(
        {"FIELDOPS_HA_LIGHT_ALLOWLIST": "light.cinta_escritorio"},
        ha_client=FakeHA(),
    )
    html = render_operator_page(bundle)
    assert "Judge Console" in html
    assert "Safe Home Assistant action" in html
    assert "Home Assistant" in html
    assert "READY" in html
    assert "Security / Camera" in html
    assert "Solar / Energy" in html
    assert "Alarm / Security Panel" in html
    assert "Telephony / PBX" in html
    assert "Open Judge Mode" in html


def test_operator_console_uses_prefixed_routes_for_inneros_judge_path():
    bundle = build_product_runtime(
        {"FIELDOPS_HA_LIGHT_ALLOWLIST": "light.cinta_escritorio"},
        ha_client=FakeHA(),
    )
    html = render_operator_page(bundle, base_path="/app/judge")
    assert 'action="/app/judge/api/login"' not in html
    assert "fetch('/app/judge/api/observe'" in html
    assert "fetch('/app/judge/api/propose'" in html
    assert 'href="/app/judge/judge?scenario=happy"' in html
    assert 'href="/app/judge/api/status"' in html
    assert 'href="/app/judge/logout"' in html


def test_login_page_uses_prefixed_action_for_inneros_judge_path():
    from src.fieldops.operator_web import _login_page

    html = _login_page(base_path="/app/judge")
    assert 'action="/app/judge/api/login"' in html


def test_loopback_guard_accepts_only_loopback_addresses():
    assert _loopback("127.0.0.1") is True
    assert _loopback("::1") is True
    assert _loopback("localhost") is True
    assert _loopback("192.168.1.4") is False


class DummyHandler:
    def __init__(self, cookie="", client="203.0.113.10", host="inneros.creatorcore.ai"):
        self.headers = {"Cookie": cookie, "Host": host}
        self.client_address = (client, 44000)


def test_session_cookie_authenticates_public_operator_request(monkeypatch):
    monkeypatch.setenv("FIELDOPS_JUDGE_USERNAME", "judge")
    monkeypatch.setenv("FIELDOPS_JUDGE_PASSWORD", "secret")
    monkeypatch.setenv("FIELDOPS_JUDGE_SESSION_SECRET", "server-side-session-secret")
    config = _auth_config()
    token = _sign_session(config, "judge", int(time.time()) + 120)
    handler = DummyHandler(cookie=f"fieldops_session={token}")
    assert _operator_authenticated(handler) is True


def test_public_operator_request_fails_closed_without_session(monkeypatch):
    monkeypatch.setenv("FIELDOPS_JUDGE_USERNAME", "judge")
    monkeypatch.setenv("FIELDOPS_JUDGE_PASSWORD", "secret")
    monkeypatch.setenv("FIELDOPS_JUDGE_SESSION_SECRET", "server-side-session-secret")
    assert _operator_authenticated(DummyHandler()) is False


def test_judge_console_prioritizes_human_result_and_transient_camera_preview():
    bundle = build_product_runtime(
        {"FIELDOPS_HA_LIGHT_ALLOWLIST": "light.cinta_escritorio"},
        ha_client=FakeHA(),
    )
    html = render_operator_page(bundle, base_path="/app/judge")
    assert "What happened, in plain English" in html
    assert "Technical Evidence Receipt" in html
    assert "camera-modal" in html
    assert "/app/judge/api/camera/preview" in html
    assert "What the agent can observe and safely do" in html
    assert "PASS passed" not in html


def test_camera_preview_fails_closed_for_public_or_unallowlisted_edge(monkeypatch):
    monkeypatch.setenv("FIELDOPS_READOPS_EDGE_URL", "http://8.8.8.8:18787")
    with pytest.raises(ValueError):
        _camera_preview_from_edge(2)
    monkeypatch.setenv("FIELDOPS_READOPS_EDGE_URL", "http://127.0.0.1:18787")
    with pytest.raises(ValueError):
        _camera_preview_from_edge(99)
