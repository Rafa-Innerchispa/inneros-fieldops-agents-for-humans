"""Real FieldOps Operator Console and bounded HTTP control surface.

The judge-facing surface is intentionally a single guided page. Read-only
observations are separated from the one consequential governed-action demo so a
judge can understand the trust boundary without opening another screen.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import hmac
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
import os
from pathlib import Path
import secrets
import time
from typing import Any, Mapping
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

from .architecture_asset import render_architecture_svg
from . import demo_web
from .inneros_adapter import read_inneros_context_snapshot
from .operator_api import (
    catalog_response,
    execute_response,
    observe_response,
    propose_response,
    voiceops_execute_response,
    voiceops_propose_response,
)
from .product_runtime import ProductRuntimeBundle, build_product_runtime

MAX_BODY_BYTES = 64 * 1024
MAX_CAMERA_PREVIEW_BYTES = 2 * 1024 * 1024
SESSION_COOKIE = "fieldops_session"
SESSION_TTL_SECONDS = 6 * 60 * 60


@dataclass(frozen=True)
class AuthConfig:
    username: str
    password: str
    secret: str
    cookie_secure: bool = False

    @property
    def configured(self) -> bool:
        return bool(self.username and self.password and self.secret)


def _auth_config(env: Mapping[str, str] | None = None) -> AuthConfig:
    source = env or os.environ
    return AuthConfig(
        username=str(source.get("FIELDOPS_JUDGE_USERNAME") or "").strip(),
        password=str(source.get("FIELDOPS_JUDGE_PASSWORD") or "").strip(),
        secret=str(source.get("FIELDOPS_JUDGE_SESSION_SECRET") or "").strip(),
        cookie_secure=str(source.get("FIELDOPS_COOKIE_SECURE") or "").strip() == "1",
    )


def _sign_session(config: AuthConfig, username: str, expires_at: int) -> str:
    body = f"{username}:{expires_at}"
    digest = hmac.new(config.secret.encode(), body.encode(), hashlib.sha256).hexdigest()
    return f"{username}.{expires_at}.{digest}"


def _new_session_cookie(config: AuthConfig) -> str:
    expires_at = int(time.time()) + SESSION_TTL_SECONDS
    return _sign_session(config, config.username, expires_at)


def _parse_cookies(raw: str) -> dict[str, str]:
    cookies: dict[str, str] = {}
    for item in raw.split(";"):
        if "=" not in item:
            continue
        key, value = item.split("=", 1)
        cookies[key.strip()] = value.strip()
    return cookies


def _loopback(value: str) -> bool:
    try:
        return ipaddress.ip_address(value).is_loopback
    except ValueError:
        return value.lower() == "localhost"


def _private_or_loopback(value: str) -> bool:
    if value.lower() == "localhost":
        return True
    try:
        ip = ipaddress.ip_address(value)
    except ValueError:
        return False
    return ip.is_private or ip.is_loopback


def _request_host(handler: BaseHTTPRequestHandler) -> str:
    return str(handler.headers.get("Host") or "").split(":", 1)[0].strip("[]")


def _direct_local_execution_allowed(handler: BaseHTTPRequestHandler) -> bool:
    if os.getenv("FIELDOPS_OPERATOR_HTTP_EXECUTION", "0").strip() != "1":
        return False
    client = str(handler.client_address[0] if handler.client_address else "")
    return _loopback(client) and _loopback(_request_host(handler))


def _private_observation_allowed(handler: BaseHTTPRequestHandler) -> bool:
    if os.getenv("FIELDOPS_OPERATOR_HTTP_OBSERVATION", "0").strip() != "1":
        return False
    client = str(handler.client_address[0] if handler.client_address else "")
    host = _request_host(handler)
    return _private_or_loopback(client) and _private_or_loopback(host)


def _private_readops_url() -> str | None:
    raw = str(os.environ.get("FIELDOPS_READOPS_EDGE_URL") or "").strip().rstrip("/")
    if not raw:
        return None
    parsed = urlparse(raw)
    if parsed.scheme != "http" or not parsed.hostname:
        return None
    if not _private_or_loopback(parsed.hostname):
        return None
    return raw


def _local_request(handler: BaseHTTPRequestHandler) -> bool:
    client = str(handler.client_address[0] if handler.client_address else "")
    return _loopback(client)


def _session_authenticated(handler: BaseHTTPRequestHandler, config: AuthConfig) -> bool:
    if not config.configured:
        return False
    cookies = _parse_cookies(str(handler.headers.get("Cookie") or ""))
    token = cookies.get(SESSION_COOKIE)
    if not token:
        return False
    try:
        username, expires_raw, digest = token.split(".", 2)
        expires_at = int(expires_raw)
    except ValueError:
        return False
    if username != config.username or expires_at < int(time.time()):
        return False
    expected = _sign_session(config, username, expires_at).rsplit(".", 1)[-1]
    return hmac.compare_digest(digest, expected)


def _operator_authenticated(handler: BaseHTTPRequestHandler) -> bool:
    config = _auth_config()
    if config.configured:
        return _session_authenticated(handler, config)
    return _local_request(handler) and _loopback(_request_host(handler))


JUDGE_PUBLIC_PREFIX = "/app/judge"


def _base_path_for_request_path(path: str) -> str:
    return JUDGE_PUBLIC_PREFIX if path == JUDGE_PUBLIC_PREFIX or path.startswith(f"{JUDGE_PUBLIC_PREFIX}/") else ""


def _normalize_request_path(path: str) -> str:
    if path == JUDGE_PUBLIC_PREFIX:
        return JUDGE_PUBLIC_PREFIX
    if path.startswith(f"{JUDGE_PUBLIC_PREFIX}/"):
        suffix = path[len(JUDGE_PUBLIC_PREFIX) :]
        return suffix or JUDGE_PUBLIC_PREFIX
    return path


def _route(base_path: str, path: str) -> str:
    return f"{base_path}{path}" if base_path else path


def _login_page(message: str = "", *, base_path: str = "") -> str:
    note = (
        "<p class='error'>" + escape(message) + "</p>"
        if message
        else "<p>Enter the temporary judge/operator credential configured on the server.</p>"
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>InnerOS FieldOps · Login</title>
<style>
:root{{--bg:#080b10;--panel:#111820;--line:#273341;--text:#f3f7fb;--muted:#9aa8b5;--accent:#35c2a1;--danger:#ff6b6b}}
*{{box-sizing:border-box}}body{{margin:0;min-height:100vh;display:grid;place-items:center;background:var(--bg);color:var(--text);font-family:Inter,system-ui,sans-serif}}
.login{{width:min(420px,92vw);border:1px solid var(--line);background:var(--panel);border-radius:8px;padding:24px;box-shadow:0 18px 80px rgba(0,0,0,.28)}}
h1{{font-size:24px;margin:0 0 8px}}p{{color:var(--muted);line-height:1.45}}label{{display:block;color:var(--muted);font-size:13px;margin:14px 0 6px}}input,button{{width:100%;padding:11px;border-radius:6px;border:1px solid var(--line);background:#0b1118;color:var(--text);font:inherit}}button{{margin-top:16px;background:var(--accent);border-color:var(--accent);color:#04100d;font-weight:800;cursor:pointer}}.error{{color:var(--danger)}}
</style></head><body><main class="login"><h1>InnerOS FieldOps</h1>{note}
<form method="post" action="{escape(_route(base_path, '/api/login'))}"><label>User</label><input name="username" autocomplete="username" autofocus>
<label>Password</label><input name="password" type="password" autocomplete="current-password">
<button>Sign in</button></form></main></body></html>"""


def _json_body(handler: BaseHTTPRequestHandler) -> Mapping[str, Any]:
    try:
        length = int(handler.headers.get("Content-Length") or "0")
    except ValueError as exc:
        raise ValueError("invalid Content-Length") from exc
    if length <= 0 or length > MAX_BODY_BYTES:
        raise ValueError("request body must be between 1 and 65536 bytes")
    raw = handler.rfile.read(length)
    try:
        decoded = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("request body must be valid JSON") from exc
    if not isinstance(decoded, Mapping):
        raise ValueError("request body must be a JSON object")
    return decoded


def _form_body(handler: BaseHTTPRequestHandler) -> Mapping[str, str]:
    try:
        length = int(handler.headers.get("Content-Length") or "0")
    except ValueError as exc:
        raise ValueError("invalid Content-Length") from exc
    if length <= 0 or length > 8192:
        raise ValueError("request body must be between 1 and 8192 bytes")
    raw = handler.rfile.read(length).decode("utf-8", "replace")
    parsed = parse_qs(raw, keep_blank_values=True)
    return {key: values[0] if values else "" for key, values in parsed.items()}


def _action_rows(bundle: ProductRuntimeBundle) -> str:
    payload = catalog_response(bundle)
    rows = []
    for item in payload["actions"]:  # type: ignore[index]
        row = dict(item)
        availability = str(row.get("availability"))
        bound = bool(row.get("runtime_bound"))
        if availability == "enabled_real" and bound:
            state, cls = "REAL · BOUND", "good"
        elif availability == "enabled_synthetic":
            state, cls = "SYNTHETIC", "warn"
        else:
            state, cls = "BLOCKED", "bad"
        rows.append(
            "<tr>"
            f"<td><code>{escape(str(row.get('action_type')))}</code><small>{escape(str(row.get('domain')))}</small></td>"
            f"<td>{escape(str(row.get('description')))}</td>"
            f"<td>{escape(str(row.get('risk')))}</td>"
            f"<td class='{cls}'>{state}</td>"
            f"<td>{'yes' if row.get('requires_approval') else 'no'}</td>"
            "</tr>"
        )
    return "".join(rows)


def _observation_rows(bundle: ProductRuntimeBundle) -> str:
    payload = catalog_response(bundle)
    rows = []
    for item in payload["observations"]:  # type: ignore[index]
        row = dict(item)
        bound = bool(row.get("runtime_bound"))
        state = "REAL · BOUND" if bound else "NOT BOUND"
        cls = "good" if bound else "warn"
        rows.append(
            "<tr>"
            f"<td><code>{escape(str(row.get('observation_type')))}</code><small>{escape(str(row.get('domain')))}</small></td>"
            f"<td>{escape(str(row.get('description')))}</td>"
            f"<td class='{cls}'>{state}</td><td>no</td></tr>"
        )
    return "".join(rows)


def _module_card(
    *, step_number: int, title: str, domain: str, source: str, status: str,
    status_class: str, observation_type: str, target_ref: str,
    action_label: str, note: str,
) -> str:
    return (
        f"<article class='module' data-step='{step_number}' data-status='{escape(status)}'>"
        f"<div class='module-head'><div><span>STEP {step_number} · {escape(domain)}</span><h3>{escape(title)}</h3></div>"
        f"<b class='{escape(status_class)}'>{escape(status)}</b></div>"
        f"<dl><dt>Source</dt><dd>{escape(source)}</dd><dt>Flow</dt><dd>OBSERVE → VERIFY → EVIDENCE</dd></dl>"
        f"<p>{escape(note)}</p>"
        f"<button type='button' data-read='{escape(observation_type)}' data-target='{escape(target_ref)}' data-step='{step_number}'>{escape(action_label)}</button>"
        "<div class='mini-result'>Not run yet.</div></article>"
    )


def _runtime_state(bound: bool) -> tuple[str, str]:
    return ("READY", "good") if bound else ("BLOCKED", "warn")


def _error_panel(status: Mapping[str, object]) -> str:
    errors = status.get("binding_errors") or []
    if not errors:
        return ""
    items = "".join(f"<li>{escape(str(item))}</li>" for item in errors)
    return "<details class='technical'><summary>Runtime binding notes</summary><ul>" + items + "</ul></details>"


def render_final_operator_page(bundle: ProductRuntimeBundle, *, base_path: str = "") -> str:
    status = bundle.status_payload()
    bound = set(bundle.bindings)
    read_bound = set(bundle.observation_bindings)
    modules = [
        _module_card(step_number=1,title="Security / Camera",domain="security",source="REAL edge camera adapter",status=_runtime_state("camera.capture_evidence" in read_bound)[0],status_class=_runtime_state("camera.capture_evidence" in read_bound)[1],observation_type="camera.capture_evidence",target_ref="camera.dahua.ch2",action_label="1. Capture Evidence",note="Capture an allowlisted real frame. The photo is transient; metadata and SHA evidence are receipted."),
        _module_card(step_number=2,title="Solar / Energy",domain="energy",source="REAL Pi01 / Xmart telemetry",status=_runtime_state("energy.read_status" in read_bound)[0],status_class=_runtime_state("energy.read_status" in read_bound)[1],observation_type="energy.read_status",target_ref="solar.pi01",action_label="2. Read Solar",note="Read-only inverter telemetry: mode, grid, battery, load, PV, temperature and freshness."),
        _module_card(step_number=3,title="Network / Facility",domain="network",source="REAL edge Wi-Fi scan",status=_runtime_state("network.scan_wifi" in read_bound)[0],status_class=_runtime_state("network.scan_wifi" in read_bound)[1],observation_type="network.scan_wifi",target_ref="wifi.amd-dedicated",action_label="3. Scan Wi-Fi",note="Read RF evidence while independently proving the production route stays on Ethernet."),
        _module_card(step_number=4,title="Alarm / Security Panel",domain="alarm",source="REAL Home Assistant / Intelbras projection",status=_runtime_state("alarm.read_status" in read_bound)[0],status_class=_runtime_state("alarm.read_status" in read_bound)[1],observation_type="alarm.read_status",target_ref="alarm.panel_home_ralphi",action_label="4. Read Alarm",note="Read panel and zone state. Arm, disarm, panic, siren and PGM are intentionally not exposed."),
        _module_card(step_number=5,title="Telephony / PBX",domain="telephony",source="REAL VoiceOps + PBX control-plane probe",status=_runtime_state("telephony.read_status" in read_bound)[0],status_class=_runtime_state("telephony.read_status" in read_bound)[1],observation_type="telephony.read_status",target_ref="voiceops.ucm",action_label="5. Read PBX",note="Read PBX/VoiceOps health. A real bidirectional call has been owner-validated end to end."),
    ]
    badges = [
        ("Agent / Strands", "READY", "good"),
        ("Edge / Pi", "READY" if "energy.read_status" in read_bound else "BLOCKED", "good" if "energy.read_status" in read_bound else "warn"),
        ("Home Assistant", "READY" if "homeassistant.entity_control" in bound else "DEGRADED", "good" if "homeassistant.entity_control" in bound else "warn"),
        ("PBX", "READY" if "telephony.read_status" in read_bound else "BLOCKED", "good" if "telephony.read_status" in read_bound else "warn"),
        ("Alarm", "READY" if "alarm.read_status" in read_bound else "BLOCKED", "good" if "alarm.read_status" in read_bound else "warn"),
        ("Wi-Fi / RF", "READY" if "network.scan_wifi" in read_bound else "BLOCKED", "good" if "network.scan_wifi" in read_bound else "warn"),
    ]
    badge_html = "".join(f"<span class='badge'><small>{escape(name)}</small><b class='{cls}'>{escape(value)}</b></span>" for name,value,cls in badges)
    routes = {"STATUS":escape(_route(base_path,"/api/status")),"LOGOUT":escape(_route(base_path,"/logout")),"OBSERVE":escape(_route(base_path,"/api/observe")),"DEMO":escape(_route(base_path,"/api/demo")),"CAMERA":escape(_route(base_path,"/api/camera/preview"))}
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    template = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>InnerOS FieldOps · Guided Judge Demo</title><style>
:root{--bg:#07090d;--panel:#10151b;--panel2:#0b1016;--line:#29313b;--text:#f4f7fb;--muted:#9ba8b5;--accent:#36c8a6;--blue:#64b5f6;--amber:#f5c95f;--red:#ff7676}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font-family:Inter,ui-sans-serif,system-ui,sans-serif}.shell{max-width:1480px;margin:0 auto;padding:18px 22px 34px}header{display:grid;grid-template-columns:minmax(340px,1.05fr) minmax(420px,1.25fr);gap:14px}.hero,.panel,.module{background:var(--panel);border:1px solid var(--line);border-radius:9px}.hero,.panel{padding:18px}.eyebrow{font-size:11px;text-transform:uppercase;font-weight:900;color:var(--accent);letter-spacing:.08em}h1{margin:7px 0 8px;font-size:30px}h2{margin:5px 0 9px;font-size:19px}h3{margin:4px 0 0;font-size:17px}p{color:var(--muted);line-height:1.45;margin:7px 0}a{color:var(--blue)}code{color:#bfe9ff}.status-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:7px}.badge{display:flex;justify-content:space-between;gap:8px;align-items:center;padding:9px;border:1px solid var(--line);border-radius:7px;background:var(--panel2)}.badge small{color:var(--muted)}.good{color:var(--accent)}.warn{color:var(--amber)}.bad{color:var(--red)}.guide{margin-top:14px;border-color:#2b6258;background:#0c1515}.guide-grid{display:grid;grid-template-columns:repeat(6,1fr);gap:8px}.guide-step{min-height:92px;padding:10px;border:1px solid var(--line);background:var(--panel2);border-radius:8px}.guide-step strong{display:block;margin-bottom:4px;font-size:13px}.guide-step small{display:block;color:var(--muted);line-height:1.3}.guide-step.active{border-color:var(--accent)}.guide-step.complete{border-color:#2b6258;background:#0d211d}.guide-step.complete strong{color:var(--accent)}.modules{display:grid;grid-template-columns:repeat(5,1fr);gap:11px;margin-top:14px}.module{padding:14px;display:flex;flex-direction:column;min-height:280px}.module.done{border-color:#2b6258}.module-head{display:flex;justify-content:space-between;gap:9px;align-items:flex-start}.module-head span{font-size:11px;color:var(--muted);font-weight:900}.module-head b{font-size:12px}dl{display:grid;grid-template-columns:56px 1fr;gap:6px;margin:11px 0;color:var(--muted);font-size:12px}dt{color:#c8d3de}dd{margin:0}button{border:1px solid #22695d;border-radius:6px;background:#153c36;color:var(--text);font:inherit;font-weight:850;padding:10px;cursor:pointer;margin-top:auto}.mini-result{margin-top:10px;min-height:52px;color:var(--muted);font-size:12px;border-top:1px solid var(--line);padding-top:9px}.module.done .mini-result{color:#bfe9dc}.result-panel{margin-top:14px}.result-summary{padding:13px;border:1px solid var(--line);background:#0a1118;border-radius:7px;white-space:pre-line;line-height:1.5;color:#dbe9e4}.technical{margin-top:10px;border-top:1px solid var(--line);padding-top:9px}.technical summary{cursor:pointer;color:var(--muted);font-weight:800}.technical pre{white-space:pre-wrap;word-break:break-word;background:#05080c;border:1px solid var(--line);border-radius:7px;padding:11px;max-height:300px;overflow:auto;color:#b9d7c9;font-size:11px}.governed{margin-top:14px;border-color:#425c47}.governed-head{display:flex;justify-content:space-between;gap:18px;align-items:flex-start}.scenario{font-size:21px;color:var(--text);margin:5px 0 8px}.flow{display:grid;grid-template-columns:repeat(6,1fr);gap:8px;margin-top:12px}.flow-step{min-height:76px;border:1px solid var(--line);background:var(--panel2);border-radius:7px;padding:9px}.flow-step b{display:block;font-size:12px}.flow-step small{color:var(--muted)}.governed-actions{display:flex;gap:9px;flex-wrap:wrap;margin-top:12px}.governed-actions button{margin-top:0;width:auto;min-width:180px}.governed-actions .danger{background:#391a20;border-color:#74333d;color:#ffd1d5}.governed-output{margin-top:12px;padding:13px;border:1px solid var(--line);background:#080d12;border-radius:7px}.receipt-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:10px}.receipt-item{padding:9px;border:1px solid var(--line);border-radius:6px;background:var(--panel2)}.receipt-item small{display:block;color:var(--muted);margin-bottom:3px}.receipt-item b{overflow-wrap:anywhere}table{width:100%;border-collapse:collapse;margin-top:8px;font-size:13px}th,td{text-align:left;padding:8px;border-bottom:1px solid var(--line);vertical-align:top}td small{display:block;color:var(--muted);margin-top:3px}.catalog{margin-top:14px}.modal{position:fixed;inset:0;background:rgba(0,0,0,.74);display:grid;place-items:center;padding:18px;z-index:20}.modal[hidden]{display:none}.modal-box{width:min(920px,96vw);background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:14px}.modal-head{display:flex;justify-content:space-between;gap:12px;align-items:center}.modal img{width:100%;max-height:72vh;object-fit:contain;background:#05080c;border:1px solid var(--line);border-radius:6px}.modal button{margin-top:0;width:auto}@media(max-width:1180px){header{grid-template-columns:1fr}.modules{grid-template-columns:repeat(2,1fr)}.guide-grid,.flow{grid-template-columns:repeat(3,1fr)}.status-grid{grid-template-columns:repeat(2,1fr)}}@media(max-width:700px){.shell{padding:12px}.modules,.guide-grid,.flow,.receipt-grid,.status-grid{grid-template-columns:1fr}h1{font-size:25px}}
</style></head><body><div class="shell"><header><section class="hero"><div class="eyebrow">AWS Agents for Humans · InnerOS FieldOps</div><h1>Guided Judge Demo</h1><p>Live operational evidence across security, energy, network, alarm and telephony, followed by an optional safe governance sandbox.</p><p><a href="__STATUS__">API status</a> · <a href="__LOGOUT__">Logout</a></p><p>UTC freshness: <code>__NOW__</code></p></section><section class="hero"><div class="eyebrow">Runtime health</div><div class="status-grid">__BADGES__</div></section></header>
<style>
body{background:radial-gradient(circle at 18% -8%,#123047 0,#07090d 42%)}
.hero,.panel{border-radius:16px;box-shadow:0 18px 45px rgba(0,0,0,.20)}
.guide{background:linear-gradient(180deg,rgba(13,28,36,.98),rgba(8,18,24,.98));border-color:#245466}
.guide h2{font-size:22px;margin-bottom:7px}.guide-grid{gap:10px}
.guide-step{appearance:none;text-align:left;margin:0;min-height:132px;padding:14px;border:1px solid #294457;border-radius:13px;background:linear-gradient(180deg,#0d1b27,#08121a);color:var(--text);cursor:pointer;transition:transform .15s ease,border-color .15s ease,box-shadow .15s ease;position:relative;overflow:hidden}
.guide-step:hover{transform:translateY(-2px);border-color:var(--blue);box-shadow:0 10px 24px rgba(0,0,0,.24)}
.guide-step:focus{outline:2px solid var(--blue);outline-offset:2px}.guide-step.active{border-color:var(--blue);box-shadow:inset 0 0 0 1px rgba(100,181,246,.2)}
.guide-step.complete{border-color:#2f806c;background:linear-gradient(180deg,#102b27,#091b18)}
.guide-step strong{font-size:16px;margin-bottom:7px}.guide-step small{font-size:12px;min-height:32px}.guide-step em{display:block;margin-top:10px;color:#7fb9cc;font-style:normal;font-size:9px;font-weight:900;letter-spacing:.04em}
.tile-result{display:block;margin-top:9px;padding-top:8px;border-top:1px solid rgba(74,111,130,.35);color:var(--muted);font-size:10px;font-weight:700;line-height:1.25}
.guide-step.complete .tile-result{color:#9be4c9}.modules{display:none!important}.result-panel{border-color:#244558;background:linear-gradient(180deg,#0d1823,#091119)}
[hidden]{display:none!important}.governed{background:linear-gradient(180deg,#111b28,#08111a);border-color:#336177;box-shadow:0 20px 55px rgba(0,0,0,.28)}
.flow-step{border-radius:12px;min-height:88px}.governed-actions button{padding:12px 18px;border-radius:10px}.governed-actions #approve-action{background:linear-gradient(135deg,#087f72,#146db2);border-color:#32b4b0}.scenario{font-size:24px;line-height:1.25}
</style>
<section class="panel guide"><div class="eyebrow">LIVE EVIDENCE · CLICK EACH STEP</div><h2>Observe the real environment, then run one safe governance simulation.</h2><p>Steps 1–5 are real read-only observations. Each click creates verified evidence. Step 6 is a separate sandbox drill that demonstrates human approval, bounded execution and independent verification without modifying any live system.</p><div class="guide-grid"><button type="button" class="guide-step active" id="guide-1" data-read="camera.capture_evidence" data-target="camera.dahua.ch2" data-step="1"><strong>1 · Camera</strong><small>Capture a real frame</small><em>OBSERVE → VERIFY → EVIDENCE</em><span class="tile-result" id="tile-result-1">Click to capture</span></button><button type="button" class="guide-step" id="guide-2" data-read="energy.read_status" data-target="solar.pi01" data-step="2"><strong>2 · Solar</strong><small>Read inverter + battery</small><em>OBSERVE → VERIFY → EVIDENCE</em><span class="tile-result" id="tile-result-2">Click to read</span></button><button type="button" class="guide-step" id="guide-3" data-read="network.scan_wifi" data-target="wifi.amd-dedicated" data-step="3"><strong>3 · Wi-Fi</strong><small>Scan RF safely</small><em>OBSERVE → VERIFY → EVIDENCE</em><span class="tile-result" id="tile-result-3">Click to scan</span></button><button type="button" class="guide-step" id="guide-4" data-read="alarm.read_status" data-target="alarm.panel_home_ralphi" data-step="4"><strong>4 · Alarm</strong><small>Read panel + zones</small><em>OBSERVE → VERIFY → EVIDENCE</em><span class="tile-result" id="tile-result-4">Click to read</span></button><button type="button" class="guide-step" id="guide-5" data-read="telephony.read_status" data-target="voiceops.ucm" data-step="5"><strong>5 · PBX</strong><small>Read VoiceOps health</small><em>OBSERVE → VERIFY → EVIDENCE</em><span class="tile-result" id="tile-result-5">Click to read</span></button><button type="button" class="guide-step" id="guide-6" onclick="var p=document.getElementById('governed-action');p.hidden=false;p.scrollIntoView({behavior:'smooth',block:'start'});"><strong>6 · Governance Simulation</strong><small>Safe sandbox recovery drill</small><em>SIMULATE → APPROVE → EXECUTE → VERIFY</em><span class="tile-result">Open safe simulation ↓</span></button></div></section>
<section class="modules">__MODULES__</section>
<section class="panel result-panel"><div class="eyebrow">What happened</div><h2>Latest verified result</h2><div class="result-summary" id="result-summary">Start with Step 1: Capture Evidence. This panel explains what FieldOps observed, verified, and receipted.</div><details class="technical"><summary>Technical Evidence Receipt</summary><pre id="technical-result">No operation yet.</pre></details></section>
<section class="panel governed" id="governed-action" hidden><div class="governed-head"><div><div class="eyebrow">STEP 6 · SAFE GOVERNANCE SIMULATION</div><h2>Simulated Recovery Drill</h2><div class="scenario">Simulated incident: a sandbox field service enters a degraded state.</div><p><b>This sandbox is independent from the live evidence above.</b> It does not modify Camera, Solar, Wi-Fi, Alarm, PBX, or any production system. It exists only to demonstrate human approval, bounded execution, independent verification, and an Evidence Receipt.</p></div><span class="badge"><small>Mode</small><b class="warn">SAFE SANDBOX · SYNTHETIC</b></span></div><div class="flow"><div class="flow-step"><b>01 SIMULATE</b><small>Sandbox outage created</small></div><div class="flow-step"><b>02 ANALYZE</b><small>Strands selects bounded restart</small></div><div class="flow-step"><b>03 APPROVE</b><small>Human authority</small></div><div class="flow-step"><b>04 EXECUTE</b><small>Sandbox executor only</small></div><div class="flow-step"><b>05 VERIFY</b><small>Independent state check</small></div><div class="flow-step"><b>06 EVIDENCE</b><small>Receipt + quality gate</small></div></div><div class="governed-actions"><button class="danger" id="deny-action">6A. Deny Simulated Recovery</button><button id="approve-action">6B. Approve Simulated Recovery</button></div><div class="governed-output"><h3 id="governed-title">Simulation not run yet</h3><p id="governed-summary">First deny the simulated recovery to prove human authority. Then approve it to demonstrate bounded execution and independent verification inside the sandbox.</p><div class="receipt-grid" id="receipt-grid"></div><details class="technical"><summary>Simulation technical trace</summary><pre id="governed-technical">No governance simulation yet.</pre></details></div></section>
<details class="panel catalog"><summary><b>Technical capability catalog</b> — optional judge detail</summary><h2>Governed actions</h2><table><thead><tr><th>Action</th><th>Purpose</th><th>Risk</th><th>Runtime</th><th>Approval</th></tr></thead><tbody>__ACTIONS__</tbody></table><h2>Read-only observations</h2><table><thead><tr><th>Observation</th><th>Purpose</th><th>Runtime</th><th>Approval</th></tr></thead><tbody>__OBSERVATIONS__</tbody></table>__ERRORS__</details>
<div class="modal" id="camera-modal" hidden><div class="modal-box"><div class="modal-head"><div><div class="eyebrow">STEP 1 · TRANSIENT CAMERA PREVIEW</div><h2>Live captured frame</h2><p id="camera-preview-note">Image is served no-store and is not persisted in the evidence receipt.</p></div><button id="camera-modal-close" type="button">Close</button></div><img id="camera-preview-image" alt="Transient camera preview"></div></div></div>
<script>
var observeUrl='__OBSERVE__';
var demoUrl='__DEMO__';
var cameraPreviewUrl='__CAMERA__';
function byId(id){return document.getElementById(id);}
function valueFrom(details,names,fallback){var i,name;if(!details){return fallback;}for(i=0;i<names.length;i+=1){name=names[i];if(details[name]!==undefined&&details[name]!==null&&details[name]!==""){return details[name];}}return fallback;}
function receiptDetails(payload){if(payload&&payload.receipt&&payload.receipt.details){return payload.receipt.details;}if(payload&&payload.details){return payload.details;}return {};}
function setGuide(step,complete){var current=byId('guide-'+step);var next;if(current&&complete){current.classList.remove('active');current.classList.add('complete');}if(complete&&step<6){next=byId('guide-'+(step+1));if(next){next.classList.add('active');}}}
function humanSummary(payload,button){var receipt=payload&&payload.receipt?payload.receipt:{};var details=receiptDetails(payload);var type=receipt.observation_type||(button&&button.dataset?button.dataset.read:'');var lines=[];if(!(payload&&payload.ok)){return 'BLOCKED OR UNAVAILABLE\\n'+((payload&&(payload.message||payload.error||payload.status))||'The adapter did not return a valid evidence receipt.');}if(type==='camera.capture_evidence'){lines=['CAMERA EVIDENCE CAPTURED','A real allowlisted frame was captured and receipted.','Channel: '+valueFrom(details,['channel','camera_channel'],'2/3 allowlist'),'JPEG size: '+valueFrom(details,['bytes','byte_count','size_bytes'],'reported in receipt')+' bytes','SHA-256: '+valueFrom(details,['sha256','hash'],'recorded'),'The photo preview is transient and is not stored in the receipt.'];}else if(type==='energy.read_status'){lines=['SOLAR STATUS VERIFIED','Read-only telemetry was collected from the Pi01 / Xmart path.','Mode: '+valueFrom(details,['mode','inverter_mode','source'],'reported in receipt'),'Battery: '+valueFrom(details,['battery','battery_soc','battery_pct'],'reported in receipt'),'Grid: '+valueFrom(details,['grid','grid_status','utility'],'reported in receipt'),'Load/output: '+valueFrom(details,['load','output','output_load'],'reported in receipt'),'Freshness: '+valueFrom(details,['freshness','captured_at','updated_at'],'reported in receipt')];}else if(type==='network.scan_wifi'){lines=['WI-FI OBSERVATION VERIFIED','RF evidence was collected without changing network configuration.','Networks found: '+valueFrom(details,['network_count','count','wifi_count'],'reported in receipt'),'Interface: '+valueFrom(details,['interface','wifi_interface'],'reported in receipt'),'Ethernet route intact: '+valueFrom(details,['ethernet_route_intact','route_intact'],'reported in receipt')];}else if(type==='alarm.read_status'){lines=['ALARM STATUS VERIFIED','The real panel and zone projection was read in read-only mode.','Panel state: '+valueFrom(details,['state','panel_state','alarm_state'],'reported in receipt'),'Zones: '+valueFrom(details,['zone_count','zones_count'],'reported in receipt'),'Open zones: '+valueFrom(details,['open_zones','open_zone_count'],'reported in receipt'),'No arm, disarm, panic or siren control is exposed here.'];}else if(type==='telephony.read_status'){lines=['PBX / VOICEOPS STATUS VERIFIED','The VoiceOps and PBX control plane were checked read-only.','PBX/control plane: '+valueFrom(details,['pbx_status','ami_status','status'],'reported in receipt'),'A real bidirectional phone call has been owner-validated end to end.','FieldOps reads health here; VoiceOps owns call execution.'];}else{lines=['EVIDENCE RECEIPT CREATED','Quality gate: '+(receipt.quality_gate||'recorded')];}return lines.join('\\n');}
function miniSummary(payload,button){var receipt=payload&&payload.receipt?payload.receipt:{};var type=receipt.observation_type||(button&&button.dataset?button.dataset.read:'');if(!(payload&&payload.ok)){return 'Unavailable — see verified result below.';}if(type==='camera.capture_evidence'){return '✓ Real frame + SHA evidence';}if(type==='energy.read_status'){return '✓ Inverter + battery verified';}if(type==='network.scan_wifi'){return '✓ RF scan + route verified';}if(type==='alarm.read_status'){return '✓ Panel + zones verified';}if(type==='telephony.read_status'){return '✓ PBX health + call path validated';}return '✓ Evidence receipt created';}
function openCameraPreview(payload,button){var receipt=payload&&payload.receipt?payload.receipt:{};var details=receiptDetails(payload);var type=receipt.observation_type||(button&&button.dataset?button.dataset.read:'');var channel;if(type!=='camera.capture_evidence'||!(payload&&payload.ok)){return;}channel=valueFrom(details,['channel','camera_channel'],'2');byId('camera-preview-note').textContent='Channel '+channel+' · '+valueFrom(details,['bytes','byte_count','size_bytes'],'JPEG')+' bytes · SHA '+valueFrom(details,['sha256','hash'],'recorded')+'. Served no-store; not persisted in the receipt.';byId('camera-preview-image').src=cameraPreviewUrl+'?channel='+encodeURIComponent(channel)+'&t='+Date.now();byId('camera-modal').hidden=false;}
function runObservation(button){var step=Number(button.getAttribute('data-step')||0);var body={observation_type:button.getAttribute('data-read'),target_ref:button.getAttribute('data-target'),correlation_id:'judge-'+Date.now()};var slot=byId('tile-result-'+step);var summary=byId('result-summary');var technical=byId('technical-result');button.disabled=true;if(slot){slot.textContent='Reading real adapter…';}summary.textContent='Running Step '+step+'…';fetch(observeUrl,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}).then(function(response){return response.json();}).then(function(data){summary.textContent=humanSummary(data,button);technical.textContent=JSON.stringify(data,null,2);if(slot){slot.textContent=miniSummary(data,button);}if(data&&data.ok){setGuide(step,true);}openCameraPreview(data,button);}).catch(function(error){summary.textContent='REQUEST FAILED\\n'+String(error);technical.textContent=String(error);if(slot){slot.textContent='Request failed';}}).then(function(){button.disabled=false;});}
function receiptItem(label,value){var safe=value===undefined||value===null?'—':value;return '<div class="receipt-item"><small>'+label+'</small><b>'+String(safe)+'</b></div>';}
function runGovernedScenario(scenario){var title=byId('governed-title');var summary=byId('governed-summary');var technical=byId('governed-technical');var grid=byId('receipt-grid');var guide=byId('guide-6');if(guide){guide.classList.add('active');}title.textContent='Running safe governance simulation…';title.className='';summary.textContent='FieldOps is evaluating policy, human approval, bounded sandbox execution and independent verification. No live system is touched.';grid.innerHTML='';fetch(demoUrl+'?scenario='+encodeURIComponent(scenario)).then(function(response){return response.json();}).then(function(data){var receipt=data&&data.receipt?data.receipt:null;technical.textContent=JSON.stringify(data,null,2);if(scenario==='denied'){title.textContent='DENIED — NOTHING EXECUTED';title.className='bad';summary.textContent='Human authority rejected the simulated recovery. The sandbox executor never ran. No live system was involved.';grid.innerHTML=receiptItem('Decision','Denied by human')+receiptItem('Execution','Not started')+receiptItem('Environment','Safe sandbox');return;}if(receipt&&receipt.quality_gate==='passed'){title.textContent='SIMULATED RECOVERY · VERIFIED';title.className='good';summary.textContent='Human approval was accepted, the bounded sandbox executor ran, and an independent verifier confirmed the synthetic service recovered. Success is based on verified state, not a command ACK. No live system was modified.';grid.innerHTML=receiptItem('Action',receipt.requested_action)+receiptItem('Target',receipt.target_ref)+receiptItem('Quality gate',receipt.quality_gate)+receiptItem('Executor',receipt.executor)+receiptItem('Verifier',receipt.verifier)+receiptItem('Environment','Synthetic sandbox');setGuide(6,true);}else{title.textContent='SIMULATION NOT VERIFIED';title.className='warn';summary.textContent='The sandbox workflow did not pass the final verification gate. FieldOps refuses to call the simulated repair successful without independent proof.';grid.innerHTML=receipt?receiptItem('Action',receipt.requested_action)+receiptItem('Quality gate',receipt.quality_gate)+receiptItem('Verification',receipt.verification_passed):receiptItem('Status',(data&&data.status)||'blocked');}}).catch(function(error){title.textContent='REQUEST FAILED';title.className='bad';summary.textContent=String(error);technical.textContent=String(error);});}
(function bindControls(){var buttons=document.querySelectorAll('[data-read]');var i;for(i=0;i<buttons.length;i+=1){buttons[i].onclick=function(){runObservation(this);};}byId('deny-action').onclick=function(){runGovernedScenario('denied');};byId('approve-action').onclick=function(){runGovernedScenario('happy');};byId('camera-modal-close').onclick=function(){byId('camera-modal').hidden=true;byId('camera-preview-image').removeAttribute('src');};byId('camera-modal').onclick=function(event){if(event.target===byId('camera-modal')){byId('camera-modal').hidden=true;byId('camera-preview-image').removeAttribute('src');}};}());
</script></body></html>"""
    replacements={"__STATUS__":routes["STATUS"],"__LOGOUT__":routes["LOGOUT"],"__OBSERVE__":routes["OBSERVE"],"__DEMO__":routes["DEMO"],"__CAMERA__":routes["CAMERA"],"__NOW__":escape(now),"__BADGES__":badge_html,"__MODULES__":"".join(modules),"__ACTIONS__":_action_rows(bundle),"__OBSERVATIONS__":_observation_rows(bundle),"__ERRORS__":_error_panel(status)}
    for token,value in replacements.items():
        template=template.replace(token,value)
    return template


def render_operator_page(bundle: ProductRuntimeBundle, *, base_path: str = "") -> str:
    return render_final_operator_page(bundle, base_path=base_path)


class OperatorHandler(BaseHTTPRequestHandler):
    bundle: ProductRuntimeBundle | None = None

    @property
    def runtime_bundle(self) -> ProductRuntimeBundle:
        if self.bundle is None:
            raise RuntimeError("operator runtime was not initialized")
        return self.bundle

    def do_GET(self) -> None:  # noqa: N802
        parsed=urlparse(self.path);base_path=_base_path_for_request_path(parsed.path);path=_normalize_request_path(parsed.path);query=parse_qs(parsed.query)
        if path=="/login":self._send_json_or_bytes(200,"text/html; charset=utf-8",_login_page(base_path=base_path).encode());return
        if path=="/logout":self._redirect(_route(base_path,"/login"),clear_session=True);return
        if path in {"/","/app/judge"}:
            if not _operator_authenticated(self):self._send_json_or_bytes(401,"text/html; charset=utf-8",_login_page(base_path=base_path).encode());return
            self._send_json_or_bytes(200,"text/html; charset=utf-8",render_operator_page(self.runtime_bundle,base_path=base_path).encode());return
        if path=="/judge":
            if not _operator_authenticated(self):self._send_json_or_bytes(401,"text/html; charset=utf-8",_login_page(base_path=base_path).encode());return
            scenario=query.get("scenario",["happy"])[0];self._send_json_or_bytes(200,"text/html; charset=utf-8",demo_web.render_demo_page(scenario).encode());return
        if path=="/api/actions":
            if not _operator_authenticated(self):self._json(401,{"ok":False,"error":"authentication_required"});return
            self._json(200,catalog_response(self.runtime_bundle));return
        if path=="/api/status":
            if not _operator_authenticated(self):self._json(401,{"ok":False,"error":"authentication_required"});return
            self._json(200,{"ok":True,"operator_runtime":self.runtime_bundle.status_payload(),"inneros_context":read_inneros_context_snapshot()});return
        if path=="/api/demo":
            if not _operator_authenticated(self):self._json(401,{"ok":False,"error":"authentication_required"});return
            scenario=query.get("scenario",["happy"])[0]
            try:self._json(200,demo_web.demo_payload(scenario))
            except ValueError as exc:self._json(400,{"ok":False,"error":"invalid_scenario","message":str(exc)})
            return
        if path=="/api/camera/preview":
            if not _operator_authenticated(self):self._json(401,{"ok":False,"error":"authentication_required"});return
            try:channel=int((query.get("channel")or["2"])[0])
            except(TypeError,ValueError):self._json(400,{"ok":False,"error":"invalid_channel"});return
            if channel not in {2,3}:self._json(403,{"ok":False,"error":"channel_not_allowlisted"});return
            edge_url=_private_readops_url()
            if edge_url is None:self._json(503,{"ok":False,"error":"readops_preview_not_configured"});return
            try:
                req=Request(edge_url+f"/camera/preview?channel={channel}",headers={"User-Agent":"InnerOS-FieldOps-Operator/1"})
                with urlopen(req,timeout=5.0) as response:body=response.read(MAX_CAMERA_PREVIEW_BYTES+1);content_type=str(response.headers.get("Content-Type")or"")
                if len(body)>MAX_CAMERA_PREVIEW_BYTES:raise RuntimeError("preview_too_large")
                if "image/jpeg" not in content_type or not(body.startswith(b"\xff\xd8")and body.endswith(b"\xff\xd9")):raise RuntimeError("preview_not_valid_jpeg")
            except Exception as exc:self._json(502,{"ok":False,"error":type(exc).__name__,"message":str(exc)[:160]});return
            self._send_json_or_bytes(200,"image/jpeg",body);return
        if path=="/assets/fieldops-architecture.svg":
            asset_path=Path(__file__).resolve().parents[2]/"docs"/"assets"/"fieldops-architecture.svg";body=asset_path.read_text(encoding="utf-8")if asset_path.exists()else render_architecture_svg();self._send_json_or_bytes(200,"image/svg+xml; charset=utf-8",body.encode());return
        self._json(404,{"ok":False,"error":"not_found"})

    def do_HEAD(self) -> None:  # noqa: N802
        parsed=urlparse(self.path);path=_normalize_request_path(parsed.path)
        if path in {"/","/app/judge","/login","/judge"}:
            status=200 if path=="/login" or _operator_authenticated(self) else 401;self.send_response(status);self.send_header("Content-Type","text/html; charset=utf-8");self.send_header("Cache-Control","no-store");self.end_headers();return
        self.send_response(404);self.send_header("Cache-Control","no-store");self.end_headers()

    def do_POST(self) -> None:  # noqa: N802
        parsed=urlparse(self.path);base_path=_base_path_for_request_path(parsed.path);path=_normalize_request_path(parsed.path)
        if path=="/api/login":
            try:payload=_form_body(self)
            except ValueError as exc:self._send_json_or_bytes(400,"text/html; charset=utf-8",_login_page(str(exc)).encode());return
            config=_auth_config();username=str(payload.get("username")or"");password=str(payload.get("password")or"")
            if config.configured and hmac.compare_digest(username,config.username)and hmac.compare_digest(password,config.password):self._redirect(base_path or "/",session_cookie=_new_session_cookie(config));return
            self._send_json_or_bytes(401,"text/html; charset=utf-8",_login_page("Invalid FieldOps credential.",base_path=base_path).encode());return
        try:payload=_json_body(self)
        except ValueError as exc:self._json(400,{"ok":False,"error":"invalid_request","message":str(exc)});return
        if path=="/api/voiceops/propose":
            if not _direct_local_execution_allowed(self):self._json(403,{"ok":False,"status":"blocked","error":"voiceops_bridge_not_local","message":"VoiceOps action bridge is restricted to the enabled direct loopback path."});return
            result=voiceops_propose_response(self.runtime_bundle,payload);self._json(200 if result.get("ok")else 400,result);return
        if path=="/api/voiceops/execute":
            if not _direct_local_execution_allowed(self):self._json(403,{"ok":False,"status":"blocked","error":"voiceops_bridge_not_local","message":"VoiceOps action bridge is restricted to the enabled direct loopback path."});return
            result=voiceops_execute_response(self.runtime_bundle,payload);self._json(200 if result.get("ok")else 409,result);return
        if path=="/api/propose":
            if not _operator_authenticated(self):self._json(401,{"ok":False,"error":"authentication_required"});return
            result=propose_response(self.runtime_bundle,payload);self._json(200 if result.get("ok")else 400,result);return
        if path=="/api/observe":
            if not(_operator_authenticated(self)or _private_observation_allowed(self)):self._json(403,{"ok":False,"status":"blocked","error":"http_observation_not_private","message":"Live physical observations are restricted to explicitly enabled private/loopback operator access."});return
            result=observe_response(self.runtime_bundle,payload);self._json(200 if result.get("ok")else 409,result);return
        if path=="/api/execute":
            if not(_operator_authenticated(self)and _direct_local_execution_allowed(self)):self._json(403,{"ok":False,"status":"blocked","error":"http_execution_not_local","message":"Physical HTTP execution is restricted to the explicitly enabled direct loopback operator path."});return
            result=execute_response(self.runtime_bundle,payload);self._json(200 if result.get("ok")else 409,result);return
        self._json(404,{"ok":False,"error":"not_found"})

    def log_message(self,format:str,*args:object)->None:return
    def _json(self,status:int,payload:Mapping[str,Any])->None:self._send_json_or_bytes(status,"application/json; charset=utf-8",json.dumps(payload,indent=2,sort_keys=True).encode())
    def _redirect(self,target:str,*,session_cookie:str|None=None,clear_session:bool=False)->None:
        self.send_response(303);self.send_header("Location",target);cookie_parts=[]
        if session_cookie is not None:cookie_parts=[f"{SESSION_COOKIE}={session_cookie}",f"Max-Age={SESSION_TTL_SECONDS}"]
        elif clear_session:cookie_parts=[f"{SESSION_COOKIE}=","Max-Age=0"]
        if cookie_parts:
            cookie_parts.extend(["HttpOnly","SameSite=Lax","Path=/"]);forwarded_proto=str(self.headers.get("X-Forwarded-Proto")or"").lower()
            if _auth_config().cookie_secure or forwarded_proto=="https":cookie_parts.append("Secure")
            self.send_header("Set-Cookie","; ".join(cookie_parts))
        self.send_header("Cache-Control","no-store");self.end_headers()
    def _send_json_or_bytes(self,status:int,content_type:str,body:bytes)->None:self.send_response(status);self.send_header("Content-Type",content_type);self.send_header("Cache-Control","no-store");self.send_header("Content-Length",str(len(body)));self.end_headers();self.wfile.write(body)


def run_server(host:str="127.0.0.1",port:int=8777,bundle:ProductRuntimeBundle|None=None)->None:
    OperatorHandler.bundle=bundle or build_product_runtime();server=ThreadingHTTPServer((host,port),OperatorHandler);print(f"InnerOS FieldOps operator console listening on http://{host}:{port}");server.serve_forever()
