"""Real FieldOps Operator Console and bounded HTTP control surface.

Public/browser access can inspect status and prepare proposals. Mutations remain
loopback-only. Read-only observations may additionally run from private/loopback
operator access when explicitly enabled, while public tunnels remain unable to
query private physical telemetry.
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

from .architecture_asset import render_architecture_svg
from . import demo_web
from .inneros_adapter import read_inneros_context_snapshot
from .operator_api import catalog_response, execute_response, observe_response, propose_response
from .product_runtime import ProductRuntimeBundle, build_product_runtime

MAX_BODY_BYTES = 64 * 1024
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
    # Development safety valve: if no credential has been configured yet, keep
    # the console local-only instead of silently opening public access.
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
        "<p class='error'>"
        + escape(message)
        + "</p>"
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
            state = "REAL · BOUND"
            cls = "good"
        elif availability == "enabled_synthetic":
            state = "SYNTHETIC"
            cls = "warn"
        else:
            state = "BLOCKED"
            cls = "bad"
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
            f"<td class='{cls}'>{state}</td>"
            "<td>no</td>"
            "</tr>"
        )
    return "".join(rows)


def _module_card(
    *,
    title: str,
    domain: str,
    source: str,
    status: str,
    status_class: str,
    observation_type: str,
    target_ref: str,
    action_label: str,
    note: str,
) -> str:
    return (
        f"<article class='module' data-status='{escape(status)}'>"
        f"<div class='module-head'><div><span>{escape(domain)}</span><h3>{escape(title)}</h3></div>"
        f"<b class='{escape(status_class)}'>{escape(status)}</b></div>"
        f"<dl><dt>Source</dt><dd>{escape(source)}</dd><dt>Flow</dt><dd>OBSERVE -> VERIFY -> EVIDENCE</dd></dl>"
        f"<p>{escape(note)}</p>"
        f"<button data-read='{escape(observation_type)}' data-target='{escape(target_ref)}'>{escape(action_label)}</button>"
        "<div class='mini-result'>Waiting for evidence receipt.</div>"
        "</article>"
    )


def _runtime_state(bound: bool) -> tuple[str, str]:
    return ("READY", "good") if bound else ("BLOCKED", "warn")


def _error_panel(status: Mapping[str, object]) -> str:
    errors = status.get("binding_errors") or []
    if not errors:
        return ""
    items = "".join(f"<li>{escape(str(item))}</li>" for item in errors)
    return (
        "<section class='panel trace'><div class='eyebrow'>Technical trace</div>"
        "<h2>Runtime binding notes</h2><ul>"
        + items
        + "</ul></section>"
    )


def render_final_operator_page(bundle: ProductRuntimeBundle, *, base_path: str = "") -> str:
    status = bundle.status_payload()
    bound = set(bundle.bindings)
    read_bound = set(bundle.observation_bindings)
    ha_targets = bundle.ha_allowlist
    ha_options = "".join(f'<option value="{escape(item)}">{escape(item)}</option>' for item in ha_targets)

    modules = [
        _module_card(
            title="Security / Camera",
            domain="security",
            source="REAL adapter when edge sidecar is reachable; synthetic only in Judge security demo",
            status=_runtime_state("camera.capture_evidence" in read_bound)[0],
            status_class=_runtime_state("camera.capture_evidence" in read_bound)[1],
            observation_type="camera.capture_evidence",
            target_ref="camera.dahua.ch2",
            action_label="Capture Evidence",
            note="Reads allowlisted camera evidence metadata. Images and credentials stay outside FieldOps.",
        ),
        _module_card(
            title="Solar / Energy",
            domain="energy",
            source="REAL Home Assistant projection from Pi01/Xmart PI30",
            status=_runtime_state("energy.read_status" in read_bound)[0],
            status_class=_runtime_state("energy.read_status" in read_bound)[1],
            observation_type="energy.read_status",
            target_ref="solar.pi01",
            action_label="Read Solar",
            note="Read-only inverter telemetry: mode, grid, battery, load, PV, temperature and freshness when available.",
        ),
        _module_card(
            title="Network / Facility",
            domain="network",
            source="REAL AMD edge Wi-Fi scan with Ethernet route readback",
            status=_runtime_state("network.scan_wifi" in read_bound)[0],
            status_class=_runtime_state("network.scan_wifi" in read_bound)[1],
            observation_type="network.scan_wifi",
            target_ref="wifi.amd-dedicated",
            action_label="Scan Wi-Fi",
            note="Scans RF evidence only. It must prove the production route stays on Ethernet.",
        ),
        _module_card(
            title="Alarm / Security Panel",
            domain="alarm",
            source="REAL Home Assistant / Intelbras Guardian projection",
            status=_runtime_state("alarm.read_status" in read_bound)[0],
            status_class=_runtime_state("alarm.read_status" in read_bound)[1],
            observation_type="alarm.read_status",
            target_ref="alarm.panel_home_ralphi",
            action_label="Read Alarm",
            note="Shows panel and zone state. Arm, disarm, panic, siren and PGM are intentionally not exposed here.",
        ),
        _module_card(
            title="Telephony / PBX",
            domain="telephony",
            source="REAL VoiceOps health plus PBX AMI banner probe",
            status=_runtime_state("telephony.read_status" in read_bound)[0],
            status_class=_runtime_state("telephony.read_status" in read_bound)[1],
            observation_type="telephony.read_status",
            target_ref="voiceops.ucm",
            action_label="Read PBX",
            note="FieldOps never registers SIP or originates arbitrary calls. VoiceOps owns audio and call execution.",
        ),
    ]
    badges = [
        ("Agent/Strands", "READY", "good"),
        ("Edge Node / Pi", "READY" if "energy.read_status" in read_bound else "BLOCKED", "good" if "energy.read_status" in read_bound else "warn"),
        ("Home Assistant", "READY" if "homeassistant.entity_control" in bound else "DEGRADED", "good" if "homeassistant.entity_control" in bound else "warn"),
        ("PBX", "READY" if "telephony.read_status" in read_bound else "BLOCKED", "good" if "telephony.read_status" in read_bound else "warn"),
        ("Alarm", "READY" if "alarm.read_status" in read_bound else "BLOCKED", "good" if "alarm.read_status" in read_bound else "warn"),
        ("UniFi / RF", "READY" if "network.scan_wifi" in read_bound else "BLOCKED", "good" if "network.scan_wifi" in read_bound else "warn"),
    ]
    badge_html = "".join(
        f"<span class='badge'><small>{escape(name)}</small><b class='{cls}'>{escape(value)}</b></span>"
        for name, value, cls in badges
    )
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>InnerOS FieldOps · Judge Console</title>
<style>
:root{{--bg:#07090d;--panel:#10151b;--panel2:#0b1016;--line:#29313b;--text:#f4f7fb;--muted:#9ba8b5;--accent:#36c8a6;--blue:#64b5f6;--amber:#f5c95f;--red:#ff7676}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font-family:Inter,ui-sans-serif,system-ui,sans-serif;letter-spacing:0}}.shell{{max-width:1480px;margin:0 auto;padding:18px 22px 28px}}
header{{display:grid;grid-template-columns:minmax(320px,1fr) minmax(420px,1.4fr);gap:18px;align-items:stretch}}.hero,.panel,.module{{background:var(--panel);border:1px solid var(--line);border-radius:8px}}.hero{{padding:20px}}.eyebrow{{font-size:11px;text-transform:uppercase;font-weight:800;color:var(--accent);letter-spacing:.08em}}h1{{margin:8px 0 10px;font-size:30px;line-height:1.05}}h2{{margin:6px 0 10px;font-size:18px}}h3{{margin:4px 0 0;font-size:17px}}p{{color:var(--muted);line-height:1.45;margin:8px 0}}a{{color:var(--blue)}}.logout{{display:inline-block;margin-top:8px;color:var(--muted);font-size:13px}}
.status-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}}.badge{{display:flex;justify-content:space-between;gap:10px;align-items:center;padding:10px;border:1px solid var(--line);border-radius:8px;background:var(--panel2)}}.badge small{{color:var(--muted)}}.badge b,.good{{color:var(--accent)}}.warn{{color:var(--amber)}}.bad{{color:var(--red)}}
.flow{{display:grid;grid-template-columns:repeat(6,1fr);gap:8px;margin-top:14px}}.step{{min-height:72px;border:1px solid var(--line);background:var(--panel2);border-radius:8px;padding:10px}}.step b{{display:block;font-size:13px}}.step small{{color:var(--muted);font-size:12px}}
.modules{{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin-top:14px}}.module{{padding:14px;display:flex;flex-direction:column;min-height:276px}}.module-head{{display:flex;justify-content:space-between;gap:10px;align-items:flex-start}}.module-head span{{font-size:11px;color:var(--muted);text-transform:uppercase;font-weight:800}}.module-head b{{font-size:12px}}dl{{display:grid;grid-template-columns:58px 1fr;gap:6px;margin:12px 0;color:var(--muted);font-size:12px}}dt{{color:#c8d3de}}dd{{margin:0}}button,select,input{{border:1px solid var(--line);border-radius:6px;background:#0c1219;color:var(--text);font:inherit;padding:10px}}button{{cursor:pointer;background:#153c36;border-color:#22695d;font-weight:800;margin-top:auto}}button.secondary{{background:#141b24;border-color:var(--line)}}.mini-result{{margin-top:10px;min-height:48px;color:var(--muted);font-size:12px;border-top:1px solid var(--line);padding-top:9px}}
.work{{display:grid;grid-template-columns:.95fr 1.05fr;gap:14px;margin-top:14px}}.panel{{padding:16px}}label{{display:block;color:var(--muted);font-size:12px;margin:10px 0 5px}}select,input{{width:100%}}pre{{white-space:pre-wrap;word-break:break-word;background:#05080c;border:1px solid var(--line);border-radius:8px;padding:12px;min-height:240px;max-height:440px;overflow:auto;color:#d7efe8}}table{{width:100%;border-collapse:collapse;margin-top:8px;font-size:13px}}th,td{{text-align:left;padding:9px;border-bottom:1px solid var(--line);vertical-align:top}}td small{{display:block;color:var(--muted);margin-top:3px}}code{{color:#bfe9ff}}ul{{color:var(--muted)}}
@media(max-width:1180px){{header,.work{{grid-template-columns:1fr}}.modules{{grid-template-columns:repeat(2,1fr)}}.status-grid{{grid-template-columns:repeat(2,1fr)}}.flow{{grid-template-columns:repeat(3,1fr)}}}}
@media(max-width:700px){{.shell{{padding:12px}}.modules,.status-grid,.flow{{grid-template-columns:1fr}}h1{{font-size:24px}}}}
</style></head><body><div class="shell">
<header><section class="hero"><div class="eyebrow">AWS Agents for Humans · InnerOS FieldOps</div><h1>Judge Console</h1><p>One governed operating surface for security, energy, network, alarm and telephony evidence. Reads are real when adapters are bound; synthetic content is labeled in Judge Mode only.</p><p><a href="{escape(_route(base_path, '/judge'))}?scenario=happy">Open Judge Mode</a> · <a href="{escape(_route(base_path, '/api/status'))}">API status</a> · <a class="logout" href="{escape(_route(base_path, '/logout'))}">Logout</a></p><p>UTC freshness: <code>{escape(now)}</code></p></section>
<section class="hero"><div class="eyebrow">Runtime health</div><div class="status-grid">{badge_html}</div></section></header>
<section class="panel"><div class="eyebrow">Unified lifecycle</div><div class="flow"><div class="step"><b>OBSERVE</b><small>telemetry/context</small></div><div class="step"><b>ANALYZE</b><small>policy + route</small></div><div class="step"><b>APPROVAL</b><small>only when needed</small></div><div class="step"><b>EXECUTE</b><small>bounded adapter</small></div><div class="step"><b>VERIFY</b><small>independent readback</small></div><div class="step"><b>EVIDENCE</b><small>receipt + trace</small></div></div></section>
<section class="modules">{''.join(modules)}</section>
<section class="work"><aside class="panel"><div class="eyebrow">Governed proposal</div><h2>Safe Home Assistant action</h2><p>This prepares a proposal for allowlisted lights only. Public sessions cannot execute it; execution remains loopback-gated.</p><label>Target</label><select id="ha-target">{ha_options or '<option>No HA targets bound</option>'}</select><label>Desired state</label><select id="ha-state"><option value="on">on</option><option value="off">off</option></select><button id="propose-ha" class="secondary">Prepare Proposal</button></aside>
<section class="panel"><div class="eyebrow">Evidence receipt</div><h2>Latest result</h2><pre id="result">No operation yet. Use a module button to create a real observe -> verify -> evidence receipt.</pre></section></section>
<section class="panel"><div class="eyebrow">Catalog</div><h2>Actions and observations</h2><table><thead><tr><th>Action</th><th>Purpose</th><th>Risk</th><th>Runtime</th><th>Approval</th></tr></thead><tbody>{_action_rows(bundle)}</tbody></table><table><thead><tr><th>Observation</th><th>Purpose</th><th>Runtime</th><th>Approval</th></tr></thead><tbody>{_observation_rows(bundle)}</tbody></table></section>
{_error_panel(status)}
</div><script>
const result=document.getElementById('result');
function summarize(payload){{return JSON.stringify(payload,null,2)}}
document.getElementById('propose-ha')?.addEventListener('click',async()=>{{const body={{action_type:'homeassistant.entity_control',target_ref:document.getElementById('ha-target').value,parameters:{{state:document.getElementById('ha-state').value}},expected_state:{{state:document.getElementById('ha-state').value}}}};const r=await fetch('{escape(_route(base_path, '/api/propose'))}',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(body)}});const data=await r.json();result.textContent=summarize(data);}});
document.querySelectorAll('[data-read]').forEach(button=>button.addEventListener('click',async()=>{{const body={{observation_type:button.dataset.read,target_ref:button.dataset.target,correlation_id:'judge-'+Date.now()}};button.disabled=true;const card=button.closest('.module');const slot=card?.querySelector('.mini-result');if(slot)slot.textContent='Reading real adapter...';try{{const r=await fetch('{escape(_route(base_path, '/api/observe'))}',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(body)}});const data=await r.json();result.textContent=summarize(data);if(slot)slot.textContent=(data.ok?'PASS ':'BLOCKED ')+(data.receipt?.quality_gate||data.error||data.status||'see evidence');}}catch(e){{result.textContent=String(e);if(slot)slot.textContent='Request failed';}}finally{{button.disabled=false;}}}}));
</script></body></html>"""


def render_operator_page(bundle: ProductRuntimeBundle, *, base_path: str = "") -> str:
    return render_final_operator_page(bundle, base_path=base_path)
    status = bundle.status_payload()
    bound = set(bundle.bindings)
    read_bound = set(bundle.observation_bindings)
    ha_targets = bundle.ha_allowlist
    ha_options = "".join(f'<option value="{escape(item)}">{escape(item)}</option>' for item in ha_targets)
    dmx_bound = "dmx.set_scene" in bound
    ha_bound = "homeassistant.entity_control" in bound
    solar_bound = "energy.read_status" in read_bound
    camera_bound = "camera.capture_evidence" in read_bound
    wifi_bound = "network.scan_wifi" in read_bound
    binding_errors = status.get("binding_errors") or []
    error_html = "".join(f"<li>{escape(str(item))}</li>" for item in binding_errors)
    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>InnerOS FieldOps · Operator Console</title>
<style>
:root{{--bg:#05090f;--panel:#0b131d;--line:#24384c;--text:#edf7ff;--muted:#91a7bb;--cyan:#42d7ff;--green:#55e49b;--amber:#ffc85a;--red:#ff7280}}
*{{box-sizing:border-box}}body{{margin:0;background:radial-gradient(circle at 18% 0,#123049 0,#05090f 42%);color:var(--text);font-family:Inter,system-ui,sans-serif}}.shell{{max-width:1450px;margin:auto;padding:24px}}
header{{display:flex;justify-content:space-between;gap:20px;align-items:flex-start;border-bottom:1px solid var(--line);padding-bottom:20px}}h1{{margin:0;font-size:34px}}h1 b{{color:var(--cyan)}}p{{color:var(--muted)}}.badges{{display:flex;gap:8px;flex-wrap:wrap}}.badge{{border:1px solid var(--line);border-radius:999px;padding:7px 10px;font-size:12px;font-weight:800;background:#08131e}}.good{{color:var(--green)}}.warn{{color:var(--amber)}}.bad{{color:var(--red)}}
.grid{{display:grid;grid-template-columns:1.2fr .8fr;gap:16px;margin-top:18px}}.panel{{background:linear-gradient(180deg,#111c28,#08111a);border:1px solid var(--line);border-radius:16px;padding:18px}}.eyebrow{{font-size:11px;color:var(--cyan);font-weight:900;text-transform:uppercase;letter-spacing:1.2px}}.flow{{display:grid;grid-template-columns:repeat(6,1fr);gap:8px;margin-top:14px}}.step{{border:1px solid var(--line);background:#07111a;border-radius:10px;padding:11px;min-height:82px}}.step b{{display:block}}.step small{{color:var(--muted)}}
table{{width:100%;border-collapse:collapse;margin-top:12px;font-size:13px}}th,td{{text-align:left;padding:10px;border-bottom:1px solid var(--line);vertical-align:top}}td small{{display:block;color:var(--muted);margin-top:4px}}code{{color:#b7edff}}label{{display:block;color:var(--muted);font-size:12px;margin:10px 0 5px}}select,input,button{{width:100%;border:1px solid var(--line);background:#081521;color:var(--text);border-radius:9px;padding:10px;font:inherit}}button{{cursor:pointer;font-weight:800;margin-top:10px;background:#0c5e80}}button.secondary{{background:#142332}}.read-buttons{{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}}pre{{white-space:pre-wrap;word-break:break-word;background:#03070b;border:1px solid #182637;border-radius:10px;padding:12px;max-height:420px;overflow:auto;color:#c2e9ce}}ul{{color:var(--muted)}}a{{color:var(--cyan)}}
@media(max-width:980px){{.grid{{grid-template-columns:1fr}}.flow{{grid-template-columns:1fr 1fr}}.read-buttons{{grid-template-columns:1fr}}header{{flex-direction:column}}}}
</style></head><body><div class="shell">
<header><div><div class="eyebrow">InnerOS · production-shaped physical operations</div><h1>FieldOps <b>Operator Console</b></h1><p>Reads are governed and receipted without fake approval theater. Mutations are proposed, approved, bounded, independently verified and receipted.</p></div><div class="badges"><span class="badge good">HA REAL: {'BOUND' if ha_bound else 'NOT BOUND'}</span><span class="badge {'good' if dmx_bound else 'warn'}">DMX REAL: {'BOUND' if dmx_bound else 'NOT BOUND'}</span><span class="badge {'good' if solar_bound else 'warn'}">SOLAR READ: {'BOUND' if solar_bound else 'NOT BOUND'}</span><span class="badge {'good' if camera_bound else 'warn'}">CAMERA READ: {'BOUND' if camera_bound else 'NOT BOUND'}</span><span class="badge {'good' if wifi_bound else 'warn'}">WI-FI READ: {'BOUND' if wifi_bound else 'NOT BOUND'}</span><span class="badge">PUBLIC MUTATION: OFF</span></div></header>
<section class="panel" style="margin-top:18px"><div class="eyebrow">Universal mutation lifecycle</div><div class="flow"><div class="step"><b>01 Observe</b><small>Real telemetry/context</small></div><div class="step"><b>02 Propose</b><small>Central action registry</small></div><div class="step"><b>03 Approve</b><small>Human artifact required</small></div><div class="step"><b>04 Execute</b><small>Bounded adapter only</small></div><div class="step"><b>05 Verify</b><small>Independent readback</small></div><div class="step"><b>06 Receipt</b><small>Evidence + quality gate</small></div></div></section>
<div class="grid"><section class="panel"><div class="eyebrow">Mutation registry</div><h2>Current truth, not marketing fiction</h2><table><thead><tr><th>Action</th><th>Purpose</th><th>Risk</th><th>Runtime</th><th>Approval</th></tr></thead><tbody>{_action_rows(bundle)}</tbody></table></section>
<aside class="panel"><div class="eyebrow">Prepare a real proposal</div><h2>Home Assistant bounded control</h2><p>Only server-allowlisted noncritical lights can be targeted. This browser prepares the action. Physical execution remains on the trusted local operator path.</p><label>Target</label><select id="ha-target">{ha_options or '<option>No HA targets bound</option>'}</select><label>Desired state</label><select id="ha-state"><option value="on">on</option><option value="off">off</option></select><button id="propose-ha">Prepare proposal</button><p><a href="/judge">Open hackathon judge evidence view</a></p>{('<h3>Binding diagnostics</h3><ul>'+error_html+'</ul>') if error_html else ''}</aside></div>
<section class="panel" style="margin-top:16px"><div class="eyebrow">Read-only observations</div><h2>Observe → Verify → Receipt</h2><p>Private/LAN operator access may run these reads. They never call mutation services and never require an approval artifact.</p><table><thead><tr><th>Observation</th><th>Purpose</th><th>Runtime</th><th>Approval</th></tr></thead><tbody>{_observation_rows(bundle)}</tbody></table><div class="read-buttons"><button data-read="energy.read_status" data-target="solar.pi01">Read Solar</button><button data-read="camera.capture_evidence" data-target="camera.dahua.ch2">Capture Camera Evidence</button><button data-read="network.scan_wifi" data-target="wifi.amd-dedicated">Scan Wi-Fi</button></div><label>Proposal / observation receipt</label><pre id="result">No operation yet.</pre></section>
<section class="panel" style="margin-top:16px"><div class="eyebrow">Real bindings</div><h2>{escape(', '.join((*bundle.observation_bindings, *bundle.bindings)) or 'No real adapters currently bound')}</h2><p>Public/judge access can inspect architecture and catalog but cannot manufacture approval or read private physical telemetry.</p></section>
</div><script>
const result=document.getElementById('result');
document.getElementById('propose-ha')?.addEventListener('click',async()=>{{const body={{action_type:'homeassistant.entity_control',target_ref:document.getElementById('ha-target').value,parameters:{{state:document.getElementById('ha-state').value}},expected_state:{{state:document.getElementById('ha-state').value}}}};const r=await fetch('/api/propose',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(body)}});result.textContent=JSON.stringify(await r.json(),null,2);}});
document.querySelectorAll('[data-read]').forEach(button=>button.addEventListener('click',async()=>{{const body={{observation_type:button.dataset.read,target_ref:button.dataset.target}};const r=await fetch('/api/observe',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(body)}});result.textContent=JSON.stringify(await r.json(),null,2);}}));
</script></body></html>"""


class OperatorHandler(BaseHTTPRequestHandler):
    bundle: ProductRuntimeBundle | None = None

    @property
    def runtime_bundle(self) -> ProductRuntimeBundle:
        if self.bundle is None:
            raise RuntimeError("operator runtime was not initialized")
        return self.bundle

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        base_path = _base_path_for_request_path(parsed.path)
        path = _normalize_request_path(parsed.path)
        query = parse_qs(parsed.query)
        if path == "/login":
            self._send_json_or_bytes(200, "text/html; charset=utf-8", _login_page(base_path=base_path).encode())
            return
        if path == "/logout":
            self._redirect(_route(base_path, "/login"), clear_session=True)
            return
        if path in {"/", "/app/judge"}:
            if not _operator_authenticated(self):
                self._send_json_or_bytes(401, "text/html; charset=utf-8", _login_page(base_path=base_path).encode())
                return
            self._send_json_or_bytes(200, "text/html; charset=utf-8", render_operator_page(self.runtime_bundle, base_path=base_path).encode())
            return
        if path == "/judge":
            if not _operator_authenticated(self):
                self._send_json_or_bytes(401, "text/html; charset=utf-8", _login_page(base_path=base_path).encode())
                return
            scenario = query.get("scenario", ["happy"])[0]
            self._send_json_or_bytes(200, "text/html; charset=utf-8", demo_web.render_demo_page(scenario).encode())
            return
        if path == "/api/actions":
            if not _operator_authenticated(self):
                self._json(401, {"ok": False, "error": "authentication_required"})
                return
            self._json(200, catalog_response(self.runtime_bundle))
            return
        if path == "/api/status":
            if not _operator_authenticated(self):
                self._json(401, {"ok": False, "error": "authentication_required"})
                return
            self._json(200, {"ok": True, "operator_runtime": self.runtime_bundle.status_payload(), "inneros_context": read_inneros_context_snapshot()})
            return
        if path == "/api/demo":
            if not _operator_authenticated(self):
                self._json(401, {"ok": False, "error": "authentication_required"})
                return
            scenario = query.get("scenario", ["happy"])[0]
            self._json(200, demo_web.demo_payload(scenario))
            return
        if path == "/assets/fieldops-architecture.svg":
            asset_path = Path(__file__).resolve().parents[2] / "docs" / "assets" / "fieldops-architecture.svg"
            body = asset_path.read_text(encoding="utf-8") if asset_path.exists() else render_architecture_svg()
            self._send_json_or_bytes(200, "image/svg+xml; charset=utf-8", body.encode())
            return
        self._json(404, {"ok": False, "error": "not_found"})

    def do_HEAD(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = _normalize_request_path(parsed.path)
        if path in {"/", "/app/judge", "/login", "/judge"}:
            status = 200 if path == "/login" or _operator_authenticated(self) else 401
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        self.send_response(404)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        base_path = _base_path_for_request_path(parsed.path)
        path = _normalize_request_path(parsed.path)
        if path == "/api/login":
            try:
                payload = _form_body(self)
            except ValueError as exc:
                self._send_json_or_bytes(400, "text/html; charset=utf-8", _login_page(str(exc)).encode())
                return
            config = _auth_config()
            username = str(payload.get("username") or "")
            password = str(payload.get("password") or "")
            if config.configured and hmac.compare_digest(username, config.username) and hmac.compare_digest(password, config.password):
                self._redirect(base_path or "/", session_cookie=_new_session_cookie(config))
                return
            self._send_json_or_bytes(401, "text/html; charset=utf-8", _login_page("Invalid FieldOps credential.", base_path=base_path).encode())
            return
        try:
            payload = _json_body(self)
        except ValueError as exc:
            self._json(400, {"ok": False, "error": "invalid_request", "message": str(exc)})
            return
        if path == "/api/propose":
            if not _operator_authenticated(self):
                self._json(401, {"ok": False, "error": "authentication_required"})
                return
            result = propose_response(self.runtime_bundle, payload)
            self._json(200 if result.get("ok") else 400, result)
            return
        if path == "/api/observe":
            if not (_operator_authenticated(self) or _private_observation_allowed(self)):
                self._json(403, {"ok": False, "status": "blocked", "error": "http_observation_not_private", "message": "Live physical observations are restricted to explicitly enabled private/loopback operator access."})
                return
            result = observe_response(self.runtime_bundle, payload)
            self._json(200 if result.get("ok") else 409, result)
            return
        if path == "/api/execute":
            if not (_operator_authenticated(self) and _direct_local_execution_allowed(self)):
                self._json(403, {"ok": False, "status": "blocked", "error": "http_execution_not_local", "message": "Physical HTTP execution is restricted to the explicitly enabled direct loopback operator path."})
                return
            result = execute_response(self.runtime_bundle, payload)
            self._json(200 if result.get("ok") else 409, result)
            return
        self._json(404, {"ok": False, "error": "not_found"})

    def log_message(self, format: str, *args: object) -> None:
        return

    def _json(self, status: int, payload: Mapping[str, Any]) -> None:
        self._send_json_or_bytes(status, "application/json; charset=utf-8", json.dumps(payload, indent=2, sort_keys=True).encode())

    def _redirect(self, target: str, *, session_cookie: str | None = None, clear_session: bool = False) -> None:
        self.send_response(303)
        self.send_header("Location", target)
        cookie_parts = []
        if session_cookie is not None:
            cookie_parts = [f"{SESSION_COOKIE}={session_cookie}", f"Max-Age={SESSION_TTL_SECONDS}"]
        elif clear_session:
            cookie_parts = [f"{SESSION_COOKIE}=", "Max-Age=0"]
        if cookie_parts:
            cookie_parts.extend(["HttpOnly", "SameSite=Lax", "Path=/"])
            forwarded_proto = str(self.headers.get("X-Forwarded-Proto") or "").lower()
            if _auth_config().cookie_secure or forwarded_proto == "https":
                cookie_parts.append("Secure")
            self.send_header("Set-Cookie", "; ".join(cookie_parts))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def _send_json_or_bytes(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def run_server(host: str = "127.0.0.1", port: int = 8777, bundle: ProductRuntimeBundle | None = None) -> None:
    OperatorHandler.bundle = bundle or build_product_runtime()
    server = ThreadingHTTPServer((host, port), OperatorHandler)
    print(f"InnerOS FieldOps operator console listening on http://{host}:{port}")
    server.serve_forever()
