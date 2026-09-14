"""Authenticated FieldOps Judge Console and bounded HTTP control surface.

The console keeps human-facing results separate from raw Evidence Receipts. Read
operations are real and independently verified. Physical mutations remain bounded
and loopback-gated. Camera preview is a transient authenticated proxy over the
existing Physical Guardian snapshot endpoint via the FieldOps read-only sidecar.
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
import time
from typing import Any, Mapping
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

from . import demo_web
from .architecture_asset import render_architecture_svg
from .inneros_adapter import read_inneros_context_snapshot
from .operator_api import catalog_response, execute_response, observe_response, propose_response
from .product_runtime import ProductRuntimeBundle, build_product_runtime

MAX_BODY_BYTES = 64 * 1024
MAX_CAMERA_PREVIEW_BYTES = 2 * 1024 * 1024
SESSION_COOKIE = "fieldops_session"
SESSION_TTL_SECONDS = 6 * 60 * 60
JUDGE_PUBLIC_PREFIX = "/app/judge"


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
    return _sign_session(config, config.username, int(time.time()) + SESSION_TTL_SECONDS)


def _parse_cookies(raw: str) -> dict[str, str]:
    cookies: dict[str, str] = {}
    for item in raw.split(";"):
        if "=" in item:
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
    token = _parse_cookies(str(handler.headers.get("Cookie") or "")).get(SESSION_COOKIE)
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


def _base_path_for_request_path(path: str) -> str:
    return JUDGE_PUBLIC_PREFIX if path == JUDGE_PUBLIC_PREFIX or path.startswith(f"{JUDGE_PUBLIC_PREFIX}/") else ""


def _normalize_request_path(path: str) -> str:
    if path == JUDGE_PUBLIC_PREFIX:
        return JUDGE_PUBLIC_PREFIX
    if path.startswith(f"{JUDGE_PUBLIC_PREFIX}/"):
        return path[len(JUDGE_PUBLIC_PREFIX) :] or JUDGE_PUBLIC_PREFIX
    return path


def _route(base_path: str, path: str) -> str:
    return f"{base_path}{path}" if base_path else path


def _login_page(message: str = "", *, base_path: str = "") -> str:
    note = (
        f"<p class='error'>{escape(message)}</p>"
        if message
        else "<p>Enter the judge/operator credential configured securely on the server.</p>"
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>InnerOS FieldOps · Login</title><style>
:root{{--bg:#07101c;--panel:#101923;--line:#29394a;--text:#f4f8fb;--muted:#9eb0bf;--accent:#25d1b4;--danger:#ff7777}}
*{{box-sizing:border-box}}body{{margin:0;min-height:100vh;display:grid;place-items:center;background:radial-gradient(circle at top,#10283b,#07101c 52%);color:var(--text);font-family:Inter,system-ui,sans-serif}}.login{{width:min(430px,92vw);padding:26px;border:1px solid var(--line);border-radius:14px;background:var(--panel);box-shadow:0 24px 90px rgba(0,0,0,.35)}}h1{{margin:0 0 8px;font-size:27px}}p{{color:var(--muted);line-height:1.45}}label{{display:block;color:var(--muted);font-size:13px;margin:14px 0 6px}}input,button{{width:100%;padding:12px;border-radius:8px;border:1px solid var(--line);background:#09131d;color:var(--text);font:inherit}}button{{margin-top:17px;background:var(--accent);border-color:var(--accent);color:#041511;font-weight:900;cursor:pointer}}.error{{color:var(--danger)}}
</style></head><body><main class="login"><div style="color:var(--accent);font-weight:900;font-size:12px;letter-spacing:.08em">AWS AGENTS FOR HUMANS</div><h1>InnerOS FieldOps</h1>{note}<form method="post" action="{escape(_route(base_path, '/api/login'))}"><label>User</label><input name="username" autocomplete="username" autofocus><label>Password</label><input name="password" type="password" autocomplete="current-password"><button>Sign in to Judge Console</button></form></main></body></html>"""


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
    parsed = parse_qs(handler.rfile.read(length).decode("utf-8", "replace"), keep_blank_values=True)
    return {key: values[0] if values else "" for key, values in parsed.items()}


def _camera_preview_from_edge(channel: int) -> tuple[bytes, dict[str, str]]:
    if channel not in {2, 3}:
        raise ValueError("camera channel is not allowlisted")
    base_url = str(os.getenv("FIELDOPS_READOPS_EDGE_URL") or "").strip()
    parsed = urlparse(base_url)
    if parsed.scheme != "http" or not parsed.hostname or not _private_or_loopback(parsed.hostname):
        raise ValueError("camera preview edge route is not a private HTTP endpoint")
    req = Request(
        base_url.rstrip("/") + f"/camera/preview?channel={channel}",
        headers={"User-Agent": "InnerOS-FieldOps-Judge/1"},
    )
    with urlopen(req, timeout=7.0) as response:
        if not str(response.headers.get("Content-Type") or "").lower().startswith("image/jpeg"):
            raise ValueError("camera preview did not return JPEG")
        body = response.read(MAX_CAMERA_PREVIEW_BYTES + 1)
        headers = {
            "channel": str(response.headers.get("X-FieldOps-Camera-Channel") or channel),
            "captured_at": str(response.headers.get("X-FieldOps-Captured-At") or ""),
            "sha256": str(response.headers.get("X-FieldOps-SHA256") or ""),
        }
    if len(body) > MAX_CAMERA_PREVIEW_BYTES or not body.startswith(b"\xff\xd8") or not body.endswith(b"\xff\xd9"):
        raise ValueError("camera preview failed JPEG validation")
    return body, headers


def _action_rows(bundle: ProductRuntimeBundle) -> str:
    rows: list[str] = []
    for item in catalog_response(bundle)["actions"]:  # type: ignore[index]
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
            f"<td>{escape(str(row.get('description')))}</td><td>{escape(str(row.get('risk')))}</td>"
            f"<td class='{cls}'>{state}</td><td>{'yes' if row.get('requires_approval') else 'no'}</td></tr>"
        )
    return "".join(rows)


def _observation_rows(bundle: ProductRuntimeBundle) -> str:
    rows: list[str] = []
    for item in catalog_response(bundle)["observations"]:  # type: ignore[index]
        row = dict(item)
        bound = bool(row.get("runtime_bound"))
        rows.append(
            "<tr>"
            f"<td><code>{escape(str(row.get('observation_type')))}</code><small>{escape(str(row.get('domain')))}</small></td>"
            f"<td>{escape(str(row.get('description')))}</td>"
            f"<td class='{'good' if bound else 'warn'}'>{'REAL · BOUND' if bound else 'NOT BOUND'}</td><td>no</td></tr>"
        )
    return "".join(rows)


def _module_card(*, title: str, domain: str, source: str, status: str, status_class: str, observation_type: str, target_ref: str, action_label: str, note: str) -> str:
    return (
        f"<article class='module'><div class='module-head'><div><span>{escape(domain)}</span><h3>{escape(title)}</h3></div>"
        f"<b class='{escape(status_class)}'>{escape(status)}</b></div>"
        f"<dl><dt>Source</dt><dd>{escape(source)}</dd><dt>Flow</dt><dd>OBSERVE → VERIFY → EVIDENCE</dd></dl>"
        f"<p>{escape(note)}</p><button data-read='{escape(observation_type)}' data-target='{escape(target_ref)}'>{escape(action_label)}</button>"
        "<div class='mini-result'>Ready. Run the observation to see a human-readable verified result.</div></article>"
    )


def _runtime_state(bound: bool) -> tuple[str, str]:
    return ("READY", "good") if bound else ("BLOCKED", "warn")


def _error_panel(status: Mapping[str, object]) -> str:
    errors = status.get("binding_errors") or []
    if not errors:
        return ""
    items = "".join(f"<li>{escape(str(item))}</li>" for item in errors)
    return f"<section class='panel trace'><div class='eyebrow'>Technical trace</div><h2>Runtime binding notes</h2><ul>{items}</ul></section>"


def render_final_operator_page(bundle: ProductRuntimeBundle, *, base_path: str = "") -> str:
    status = bundle.status_payload()
    bound = set(bundle.bindings)
    read_bound = set(bundle.observation_bindings)
    ha_options = "".join(f'<option value="{escape(item)}">{escape(item)}</option>' for item in bundle.ha_allowlist)
    modules = [
        _module_card(
            title="Security / Camera", domain="security",
            source="REAL Physical Guardian snapshot via read-only edge adapter",
            status=_runtime_state("camera.capture_evidence" in read_bound)[0], status_class=_runtime_state("camera.capture_evidence" in read_bound)[1],
            observation_type="camera.capture_evidence", target_ref="camera.dahua.ch2", action_label="Capture Evidence",
            note="Captures a real allowlisted JPEG, verifies it, shows it transiently, and keeps only metadata/hash in the receipt.",
        ),
        _module_card(
            title="Solar / Energy", domain="energy", source="REAL Pi01/Xmart PI30 through Home Assistant",
            status=_runtime_state("energy.read_status" in read_bound)[0], status_class=_runtime_state("energy.read_status" in read_bound)[1],
            observation_type="energy.read_status", target_ref="solar.pi01", action_label="Read Solar",
            note="Read-only mode, grid, battery, output, load, PV, temperature and freshness. No inverter write path.",
        ),
        _module_card(
            title="Network / Facility", domain="network", source="REAL AMD edge RF scan + Ethernet route readback",
            status=_runtime_state("network.scan_wifi" in read_bound)[0], status_class=_runtime_state("network.scan_wifi" in read_bound)[1],
            observation_type="network.scan_wifi", target_ref="wifi.amd-dedicated", action_label="Scan Wi-Fi",
            note="Scans RF conditions only and independently proves the production route stayed on Ethernet.",
        ),
        _module_card(
            title="Alarm / Security Panel", domain="alarm", source="REAL Home Assistant / Intelbras Guardian projection",
            status=_runtime_state("alarm.read_status" in read_bound)[0], status_class=_runtime_state("alarm.read_status" in read_bound)[1],
            observation_type="alarm.read_status", target_ref="alarm.panel_home_ralphi", action_label="Read Alarm",
            note="Shows panel and zone state read-only. Arm/disarm, panic, siren and PGM are deliberately not exposed.",
        ),
        _module_card(
            title="Telephony / PBX", domain="telephony", source="REAL VoiceOps health + independent PBX AMI probe",
            status=_runtime_state("telephony.read_status" in read_bound)[0], status_class=_runtime_state("telephony.read_status" in read_bound)[1],
            observation_type="telephony.read_status", target_ref="voiceops.ucm", action_label="Read PBX",
            note="FieldOps verifies the phone control plane read-only. VoiceOps remains the only owner of SIP/RTP and calls.",
        ),
    ]
    badges = [
        ("Agent / Strands", "READY", "good"),
        ("Edge Node / Pi", "READY" if "energy.read_status" in read_bound else "BLOCKED", "good" if "energy.read_status" in read_bound else "warn"),
        ("Home Assistant", "READY" if "homeassistant.entity_control" in bound else "DEGRADED", "good" if "homeassistant.entity_control" in bound else "warn"),
        ("PBX", "READY" if "telephony.read_status" in read_bound else "BLOCKED", "good" if "telephony.read_status" in read_bound else "warn"),
        ("Alarm", "READY" if "alarm.read_status" in read_bound else "BLOCKED", "good" if "alarm.read_status" in read_bound else "warn"),
        ("Camera / RF", "READY" if {"camera.capture_evidence", "network.scan_wifi"}.issubset(read_bound) else "DEGRADED", "good" if {"camera.capture_evidence", "network.scan_wifi"}.issubset(read_bound) else "warn"),
    ]
    badge_html = "".join(f"<span class='badge'><small>{escape(name)}</small><b class='{cls}'>{escape(value)}</b></span>" for name, value, cls in badges)
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    observe_route = escape(_route(base_path, "/api/observe"))
    propose_route = escape(_route(base_path, "/api/propose"))
    preview_route = escape(_route(base_path, "/api/camera/preview"))
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>InnerOS FieldOps · Judge Console</title>
<style>
:root{{--bg:#06101b;--panel:#0e1822;--panel2:#09131d;--line:#26394a;--text:#f3f7fb;--muted:#9eb0bf;--accent:#24d1b3;--blue:#69bdfa;--amber:#f3c75e;--red:#ff7777}}
*{{box-sizing:border-box}}body{{margin:0;background:radial-gradient(circle at 15% 0,#10283b,#06101b 40%);color:var(--text);font-family:Inter,ui-sans-serif,system-ui,sans-serif}}.shell{{max-width:1500px;margin:auto;padding:18px 22px 30px}}header{{display:grid;grid-template-columns:minmax(330px,1fr) minmax(440px,1.35fr);gap:16px}}.hero,.panel,.module{{background:rgba(14,24,34,.96);border:1px solid var(--line);border-radius:12px}}.hero,.panel{{padding:18px}}.eyebrow{{font-size:11px;text-transform:uppercase;font-weight:900;color:var(--accent);letter-spacing:.09em}}h1{{margin:7px 0 9px;font-size:31px;line-height:1.05}}h2{{margin:6px 0 10px;font-size:19px}}h3{{margin:4px 0 0;font-size:17px}}p{{color:var(--muted);line-height:1.43;margin:8px 0}}a{{color:var(--blue)}}code{{color:#c2edff}}.status-grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}}.badge{{display:flex;justify-content:space-between;gap:8px;align-items:center;padding:9px;border:1px solid var(--line);border-radius:9px;background:var(--panel2)}}.badge small{{color:var(--muted)}}.good{{color:var(--accent)}}.warn{{color:var(--amber)}}.bad{{color:var(--red)}}.flow{{display:grid;grid-template-columns:repeat(6,1fr);gap:8px;margin-top:13px}}.step{{min-height:66px;border:1px solid var(--line);background:var(--panel2);border-radius:9px;padding:10px}}.step b{{display:block;font-size:13px}}.step small{{color:var(--muted);font-size:11px}}.modules{{display:grid;grid-template-columns:repeat(5,1fr);gap:11px;margin-top:13px}}.module{{padding:14px;display:flex;flex-direction:column;min-height:300px}}.module-head{{display:flex;justify-content:space-between;gap:9px;align-items:flex-start}}.module-head span{{font-size:10px;color:var(--muted);text-transform:uppercase;font-weight:900}}.module-head b{{font-size:11px}}dl{{display:grid;grid-template-columns:54px 1fr;gap:5px;margin:11px 0;color:var(--muted);font-size:11px}}dt{{color:#c9d5de}}dd{{margin:0}}button,select,input{{border:1px solid var(--line);border-radius:8px;background:#08131d;color:var(--text);font:inherit;padding:10px}}button{{cursor:pointer;background:#123e38;border-color:#226c60;font-weight:900;margin-top:auto}}button:disabled{{opacity:.55;cursor:wait}}.secondary{{background:#131f2a}}.mini-result{{margin-top:10px;min-height:66px;color:#d8e6ed;font-size:12px;border-top:1px solid var(--line);padding-top:9px;line-height:1.42}}.mini-result.verified{{color:#c8f7e9}}.work{{display:grid;grid-template-columns:.9fr 1.1fr;gap:13px;margin-top:13px}}label{{display:block;color:var(--muted);font-size:12px;margin:9px 0 5px}}select,input{{width:100%}}.human-result{{border:1px solid #255c55;background:#0a211e;border-radius:9px;padding:12px;margin:8px 0 10px;color:#d8fff7;font-size:14px;line-height:1.45}}details{{border-top:1px solid var(--line);padding-top:8px}}summary{{cursor:pointer;color:var(--muted);font-size:12px;font-weight:800}}pre{{white-space:pre-wrap;word-break:break-word;background:#05090d;border:1px solid var(--line);border-radius:8px;padding:11px;min-height:160px;max-height:370px;overflow:auto;color:#d7efe8;font-size:11px}}table{{width:100%;border-collapse:collapse;margin-top:8px;font-size:12px}}th,td{{text-align:left;padding:8px;border-bottom:1px solid var(--line);vertical-align:top}}td small{{display:block;color:var(--muted);margin-top:3px}}ul{{color:var(--muted)}}.modal{{position:fixed;inset:0;background:rgba(0,0,0,.78);display:none;place-items:center;z-index:40;padding:20px}}.modal.open{{display:grid}}.modal-card{{width:min(980px,96vw);max-height:94vh;overflow:auto;background:#0b151f;border:1px solid #335066;border-radius:14px;padding:14px;box-shadow:0 30px 120px rgba(0,0,0,.55)}}.modal-head{{display:flex;justify-content:space-between;gap:12px;align-items:center;margin-bottom:10px}}.modal-head button{{margin:0;width:auto;background:#172532}}.camera-frame{{width:100%;max-height:68vh;object-fit:contain;background:#020507;border-radius:9px;border:1px solid var(--line)}}.camera-meta{{color:#c8d7e0;font-size:12px;margin-top:9px}}
@media(max-width:1180px){{header,.work{{grid-template-columns:1fr}}.modules{{grid-template-columns:repeat(2,1fr)}}.status-grid{{grid-template-columns:repeat(2,1fr)}}.flow{{grid-template-columns:repeat(3,1fr)}}}}@media(max-width:700px){{.shell{{padding:12px}}.modules,.status-grid,.flow{{grid-template-columns:1fr}}h1{{font-size:25px}}}}
</style></head><body><div class="shell">
<header><section class="hero"><div class="eyebrow">AWS Agents for Humans · InnerOS FieldOps</div><h1>Judge Console</h1><p>Real operational evidence translated for humans first, with the full auditable receipt one click below.</p><p><a href="{escape(_route(base_path, '/judge'))}?scenario=happy">Open Judge Mode</a> · <a href="{escape(_route(base_path, '/api/status'))}">API status</a> · <a href="{escape(_route(base_path, '/logout'))}">Logout</a></p><p>UTC freshness: <code>{escape(now)}</code></p></section><section class="hero"><div class="eyebrow">Runtime health</div><div class="status-grid">{badge_html}</div></section></header>
<section class="panel" style="margin-top:13px"><div class="eyebrow">Governed lifecycle</div><div class="flow"><div class="step"><b>OBSERVE</b><small>real telemetry/context</small></div><div class="step"><b>ANALYZE</b><small>policy + route</small></div><div class="step"><b>APPROVAL</b><small>when consequence requires it</small></div><div class="step"><b>EXECUTE</b><small>bounded adapter</small></div><div class="step"><b>VERIFY</b><small>independent readback</small></div><div class="step"><b>EVIDENCE</b><small>human result + receipt</small></div></div></section>
<section class="modules">{''.join(modules)}</section>
<section class="work"><aside class="panel"><div class="eyebrow">Governed proposal</div><h2>Safe Home Assistant action</h2><p>Only allowlisted noncritical lights can be proposed. Consequential execution never becomes a public browser free-for-all.</p><label>Target</label><select id="ha-target">{ha_options or '<option>No HA targets bound</option>'}</select><label>Desired state</label><select id="ha-state"><option value="on">on</option><option value="off">off</option></select><button id="propose-ha" class="secondary">Prepare Proposal</button></aside><section class="panel"><div class="eyebrow">Latest verified result</div><h2>What happened, in plain English</h2><div id="human-result" class="human-result">Run any module above. The judge will see the operational answer here before the technical receipt.</div><details><summary>Technical Evidence Receipt · expand for audit JSON</summary><pre id="result">No operation yet.</pre></details></section></section>
<section class="panel" style="margin-top:13px"><div class="eyebrow">Capabilities</div><h2>What the agent can observe and safely do</h2><table><thead><tr><th>Action</th><th>Purpose</th><th>Risk</th><th>Runtime</th><th>Approval</th></tr></thead><tbody>{_action_rows(bundle)}</tbody></table><table><thead><tr><th>Observation</th><th>Purpose</th><th>Runtime</th><th>Approval</th></tr></thead><tbody>{_observation_rows(bundle)}</tbody></table></section>{_error_panel(status)}</div>
<div id="camera-modal" class="modal" aria-hidden="true"><div class="modal-card"><div class="modal-head"><div><div class="eyebrow">REAL CAMERA EVIDENCE</div><h2 style="margin:3px 0">Physical Guardian snapshot</h2></div><button id="camera-close" class="secondary">Close</button></div><img id="camera-image" class="camera-frame" alt="Real allowlisted camera evidence"><div id="camera-meta" class="camera-meta"></div></div></div>
<script>
const result=document.getElementById('result');const human=document.getElementById('human-result');const modal=document.getElementById('camera-modal');const cameraImage=document.getElementById('camera-image');const cameraMeta=document.getElementById('camera-meta');
const fmt=(v,suffix='')=>v===null||v===undefined||v===''?'n/a':String(v)+suffix;const shortHash=v=>v?String(v).slice(0,12)+'…':'n/a';
function humanSummary(type,data){{if(!data?.ok)return data?.message||data?.error||data?.status||'Observation blocked.';const r=data.receipt||{{}};const d=r.read_details||{{}};const s=r.observed_state||{{}};const verified=r.verification_passed===true?'Verified':'Not verified';switch(type){{case 'camera.capture_evidence':return `${{verified}} real JPEG · channel ${{fmt(s.channel)}} · ${{Math.round((Number(s.bytes)||0)/1024)}} KB · captured ${{fmt(s.captured_at)}} · SHA ${{shortHash(s.sha256)}}`;case 'energy.read_status':return `${{verified}} solar telemetry · mode ${{fmt(s.mode)}} · battery ${{fmt(s.battery_voltage_v,' V')}} (${{fmt(d.battery_capacity_percent,'%')}}) · grid ${{fmt(s.grid_voltage_v,' V')}} · output ${{fmt(s.output_power_w,' W')}} · load ${{fmt(d.output_load_percent,'%')}} · PV ${{fmt(d.pv_charging_power_w,' W')}} · temp ${{fmt(d.temperature_c,' °C')}}`;case 'network.scan_wifi':return `${{verified}} RF scan · ${{fmt(s.network_count)}} networks · interface ${{fmt(s.interface)}} · Ethernet route ${{s.ethernet_route_intact?'intact':'CHANGED'}} · configuration changed: ${{s.configuration_changed?'yes':'no'}}`;case 'alarm.read_status':return `${{verified}} alarm state · panel ${{fmt(s.panel_state)}} · ${{fmt(s.zone_count)}} zones · ${{fmt(s.open_zone_count)}} open · read-only: ${{s.read_only?'yes':'no'}}`;case 'telephony.read_status':return `${{verified}} telephony control plane · VoiceOps ${{s.voiceops_ok?'online':'offline'}} · PBX ${{s.pbx_ami_reachable?'reachable':'unreachable'}} · execution owner: ${{fmt(s.execution_owner)}} · FieldOps reads credentials: ${{s.fieldops_reads_credentials?'yes':'no'}}`;default:return `${{verified}} · Evidence Receipt created.`}}}}
function showCameraPreview(state){{const ch=Number(state?.channel||2);cameraMeta.textContent=`Channel ${{ch}} · ${{Math.round((Number(state?.bytes)||0)/1024)}} KB · ${{fmt(state?.captured_at)}} · SHA-256 ${{shortHash(state?.sha256)}} · preview is transient / no-store`;cameraImage.src=`{preview_route}?channel=${{ch}}&t=${{Date.now()}}`;modal.classList.add('open');modal.setAttribute('aria-hidden','false');}}
function closeCamera(){{modal.classList.remove('open');modal.setAttribute('aria-hidden','true');cameraImage.removeAttribute('src');}}document.getElementById('camera-close').addEventListener('click',closeCamera);modal.addEventListener('click',e=>{{if(e.target===modal)closeCamera();}});
document.getElementById('propose-ha')?.addEventListener('click',async()=>{{const body={{action_type:'homeassistant.entity_control',target_ref:document.getElementById('ha-target').value,parameters:{{state:document.getElementById('ha-state').value}},expected_state:{{state:document.getElementById('ha-state').value}}}};const r=await fetch('{propose_route}',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(body)}});const data=await r.json();result.textContent=JSON.stringify(data,null,2);human.textContent=data.ok?'Proposal prepared. Human approval is still required before bounded physical execution.':(data.message||data.error||'Proposal blocked.');}});
document.querySelectorAll('[data-read]').forEach(button=>button.addEventListener('click',async()=>{{const type=button.dataset.read;const body={{observation_type:type,target_ref:button.dataset.target,correlation_id:'judge-'+Date.now()}};button.disabled=true;const slot=button.closest('.module')?.querySelector('.mini-result');if(slot){{slot.classList.remove('verified');slot.textContent='Reading real adapter and independently verifying…';}}try{{const r=await fetch('{observe_route}',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(body)}});const data=await r.json();result.textContent=JSON.stringify(data,null,2);const summary=humanSummary(type,data);human.textContent=summary;if(slot){{slot.textContent=summary;slot.classList.toggle('verified',Boolean(data.ok));}}if(data.ok&&type==='camera.capture_evidence')showCameraPreview(data.receipt?.observed_state||{{}});}}catch(e){{const msg='Request failed: '+String(e);result.textContent=msg;human.textContent=msg;if(slot)slot.textContent=msg;}}finally{{button.disabled=false;}}}}));
</script></body></html>"""


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
        parsed = urlparse(self.path)
        base_path = _base_path_for_request_path(parsed.path)
        path = _normalize_request_path(parsed.path)
        query = parse_qs(parsed.query)
        if path == "/login":
            self._send_bytes(200, "text/html; charset=utf-8", _login_page(base_path=base_path).encode())
            return
        if path == "/logout":
            self._redirect(_route(base_path, "/login"), clear_session=True)
            return
        if path in {"/", "/app/judge"}:
            if not _operator_authenticated(self):
                self._send_bytes(401, "text/html; charset=utf-8", _login_page(base_path=base_path).encode())
                return
            self._send_bytes(200, "text/html; charset=utf-8", render_operator_page(self.runtime_bundle, base_path=base_path).encode())
            return
        if path == "/judge":
            if not _operator_authenticated(self):
                self._send_bytes(401, "text/html; charset=utf-8", _login_page(base_path=base_path).encode())
                return
            scenario = query.get("scenario", ["happy"])[0]
            self._send_bytes(200, "text/html; charset=utf-8", demo_web.render_demo_page(scenario).encode())
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
            self._json(200, demo_web.demo_payload(query.get("scenario", ["happy"])[0]))
            return
        if path == "/api/camera/preview":
            if not _operator_authenticated(self):
                self._json(401, {"ok": False, "error": "authentication_required"})
                return
            try:
                channel = int((query.get("channel") or ["2"])[0])
                body, meta = _camera_preview_from_edge(channel)
            except (ValueError, OSError, TimeoutError) as exc:
                self._json(502, {"ok": False, "error": "camera_preview_unavailable", "message": str(exc)[:180]})
                return
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-FieldOps-Camera-Channel", meta.get("channel", str(channel)))
            self.send_header("X-FieldOps-Captured-At", meta.get("captured_at", ""))
            self.send_header("X-FieldOps-SHA256", meta.get("sha256", ""))
            self.end_headers()
            self.wfile.write(body)
            return
        if path == "/assets/fieldops-architecture.svg":
            asset_path = Path(__file__).resolve().parents[2] / "docs" / "assets" / "fieldops-architecture.svg"
            body = asset_path.read_text(encoding="utf-8") if asset_path.exists() else render_architecture_svg()
            self._send_bytes(200, "image/svg+xml; charset=utf-8", body.encode())
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
                self._send_bytes(400, "text/html; charset=utf-8", _login_page(str(exc), base_path=base_path).encode())
                return
            config = _auth_config()
            username = str(payload.get("username") or "")
            password = str(payload.get("password") or "")
            if config.configured and hmac.compare_digest(username, config.username) and hmac.compare_digest(password, config.password):
                self._redirect(base_path or "/", session_cookie=_new_session_cookie(config))
                return
            self._send_bytes(401, "text/html; charset=utf-8", _login_page("Invalid FieldOps credential.", base_path=base_path).encode())
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
            response = propose_response(self.runtime_bundle, payload)
            self._json(200 if response.get("ok") else 400, response)
            return
        if path == "/api/observe":
            if not (_operator_authenticated(self) or _private_observation_allowed(self)):
                self._json(403, {"ok": False, "status": "blocked", "error": "http_observation_not_private", "message": "Live physical observations require an authenticated judge/operator session or explicitly enabled private access."})
                return
            response = observe_response(self.runtime_bundle, payload)
            self._json(200 if response.get("ok") else 409, response)
            return
        if path == "/api/execute":
            if not (_operator_authenticated(self) and _direct_local_execution_allowed(self)):
                self._json(403, {"ok": False, "status": "blocked", "error": "http_execution_not_local", "message": "Physical HTTP execution is restricted to the explicitly enabled direct loopback operator path."})
                return
            response = execute_response(self.runtime_bundle, payload)
            self._json(200 if response.get("ok") else 409, response)
            return
        self._json(404, {"ok": False, "error": "not_found"})

    def log_message(self, format: str, *args: object) -> None:
        return

    def _json(self, status: int, payload: Mapping[str, Any]) -> None:
        self._send_bytes(status, "application/json; charset=utf-8", json.dumps(payload, indent=2, sort_keys=True).encode())

    def _redirect(self, target: str, *, session_cookie: str | None = None, clear_session: bool = False) -> None:
        self.send_response(303)
        self.send_header("Location", target)
        cookie_parts: list[str] = []
        if session_cookie is not None:
            cookie_parts = [f"{SESSION_COOKIE}={session_cookie}", f"Max-Age={SESSION_TTL_SECONDS}"]
        elif clear_session:
            cookie_parts = [f"{SESSION_COOKIE}=", "Max-Age=0"]
        if cookie_parts:
            cookie_parts.extend(["HttpOnly", "SameSite=Lax", "Path=/"])
            if _auth_config().cookie_secure or str(self.headers.get("X-Forwarded-Proto") or "").lower() == "https":
                cookie_parts.append("Secure")
            self.send_header("Set-Cookie", "; ".join(cookie_parts))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def _send_bytes(self, status: int, content_type: str, body: bytes) -> None:
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
