import re
import shutil
import subprocess
import time

import pytest

from src.fieldops.operator_web import (
    _auth_config,
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


def _html(base_path=""):
    bundle = build_product_runtime(
        {"FIELDOPS_HA_LIGHT_ALLOWLIST": "light.cinta_escritorio"},
        ha_client=FakeHA(),
    )
    return render_operator_page(bundle, base_path=base_path)


def test_operator_console_is_single_page_clickable_demo():
    html = _html()
    assert "Guided Judge Demo" in html
    assert "LIVE EVIDENCE · CLICK EACH STEP" in html
    assert "Observe the real environment, then run one governed action." in html

    expected_controls = [
        ('guide-1', 'camera.capture_evidence', 'camera.dahua.ch2'),
        ('guide-2', 'energy.read_status', 'solar.pi01'),
        ('guide-3', 'network.scan_wifi', 'wifi.amd-dedicated'),
        ('guide-4', 'alarm.read_status', 'alarm.panel_home_ralphi'),
        ('guide-5', 'telephony.read_status', 'voiceops.ucm'),
    ]
    for element_id, observation, target in expected_controls:
        assert f'id="{element_id}"' in html
        assert f'data-read="{observation}"' in html
        assert f'data-target="{target}"' in html

    assert "function runObservation(button)" in html
    assert "buttons[i].onclick=function(){runObservation(this);}" in html
    assert "modules{display:none!important}" in html
    assert "What happened" in html
    assert "Deny Action" in html
    assert "Approve & Execute" in html
    assert "EXECUTED + VERIFIED" in html
    assert "DENIED — NOTHING EXECUTED" in html
    assert "TRANSIENT CAMERA PREVIEW" in html
    assert "/api/camera/preview" in html
    assert "/api/demo" in html
    assert "Safe Home Assistant action" not in html
    assert "Open Judge Mode" not in html
    assert "Nothing is hidden on another screen" not in html
    assert "Bidirectional microphone/STT remains" not in html
    assert "A real bidirectional phone call has been owner-validated end to end." in html
    assert "?." not in html
    assert "??" not in html
    assert "</script></script>" not in html
    assert "</section></section>" not in html


def test_operator_console_inline_javascript_parses(tmp_path):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    html = _html(base_path="/app/judge")
    match = re.search(r"<script>(.*?)</script>", html, flags=re.DOTALL)
    assert match is not None
    script_path = tmp_path / "fieldops-judge.js"
    script_path.write_text(match.group(1), encoding="utf-8")
    result = subprocess.run(
        [node, "--check", str(script_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_operator_console_uses_prefixed_routes_for_inneros_judge_path():
    html = _html(base_path="/app/judge")
    assert 'action="/app/judge/api/login"' not in html
    assert "var observeUrl='/app/judge/api/observe'" in html
    assert "var demoUrl='/app/judge/api/demo'" in html
    assert "var cameraPreviewUrl='/app/judge/api/camera/preview'" in html
    assert 'href="/app/judge/api/status"' in html
    assert 'href="/app/judge/logout"' in html
    assert 'href="/app/judge/judge?scenario=happy"' not in html


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
