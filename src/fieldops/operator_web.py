"""Real FieldOps Operator Console and bounded HTTP control surface.

Public/browser access can inspect status and prepare proposals. Mutations remain
loopback-only. Read-only observations may additionally run from private/loopback
operator access when explicitly enabled, while public tunnels remain unable to
query private physical telemetry.
"""

from __future__ import annotations

from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
import os
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import parse_qs, urlparse

from .architecture_asset import render_architecture_svg
from . import demo_web
from .inneros_adapter import read_inneros_context_snapshot
from .operator_api import catalog_response, execute_response, observe_response, propose_response
from .product_runtime import ProductRuntimeBundle, build_product_runtime

MAX_BODY_BYTES = 64 * 1024


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


def render_operator_page(bundle: ProductRuntimeBundle) -> str:
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
        query = parse_qs(parsed.query)
        if parsed.path == "/":
            self._send_json_or_bytes(200, "text/html; charset=utf-8", render_operator_page(self.runtime_bundle).encode())
            return
        if parsed.path == "/judge":
            scenario = query.get("scenario", ["happy"])[0]
            self._send_json_or_bytes(200, "text/html; charset=utf-8", demo_web.render_demo_page(scenario).encode())
            return
        if parsed.path == "/api/actions":
            self._json(200, catalog_response(self.runtime_bundle))
            return
        if parsed.path == "/api/status":
            self._json(200, {"ok": True, "operator_runtime": self.runtime_bundle.status_payload(), "inneros_context": read_inneros_context_snapshot()})
            return
        if parsed.path == "/api/demo":
            scenario = query.get("scenario", ["happy"])[0]
            self._json(200, demo_web.demo_payload(scenario))
            return
        if parsed.path == "/assets/fieldops-architecture.svg":
            asset_path = Path(__file__).resolve().parents[2] / "docs" / "assets" / "fieldops-architecture.svg"
            body = asset_path.read_text(encoding="utf-8") if asset_path.exists() else render_architecture_svg()
            self._send_json_or_bytes(200, "image/svg+xml; charset=utf-8", body.encode())
            return
        self._json(404, {"ok": False, "error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        try:
            payload = _json_body(self)
        except ValueError as exc:
            self._json(400, {"ok": False, "error": "invalid_request", "message": str(exc)})
            return
        if parsed.path == "/api/propose":
            result = propose_response(self.runtime_bundle, payload)
            self._json(200 if result.get("ok") else 400, result)
            return
        if parsed.path == "/api/observe":
            if not _private_observation_allowed(self):
                self._json(403, {"ok": False, "status": "blocked", "error": "http_observation_not_private", "message": "Live physical observations are restricted to explicitly enabled private/loopback operator access."})
                return
            result = observe_response(self.runtime_bundle, payload)
            self._json(200 if result.get("ok") else 409, result)
            return
        if parsed.path == "/api/execute":
            if not _direct_local_execution_allowed(self):
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
