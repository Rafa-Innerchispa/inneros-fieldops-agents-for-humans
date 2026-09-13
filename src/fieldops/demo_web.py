"""No-dependency judge console for the InnerOS FieldOps hackathon demo."""

from __future__ import annotations

from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .architecture_asset import render_architecture_svg
from .demo_runner import SCENARIOS, run_demo
from .inneros_adapter import read_inneros_context_snapshot


def demo_payload(scenario: str = "happy") -> dict[str, object]:
    """Return the API payload used by the browser and E2E smoke tests."""

    payload = run_demo(scenario)
    payload["inneros_context"] = read_inneros_context_snapshot()
    return payload


def status_payload() -> dict[str, object]:
    """Return read-only infrastructure telemetry for periodic UI refresh."""

    return {"inneros_context": read_inneros_context_snapshot()}


def _value(value: object, suffix: str = "", fallback: str = "--") -> str:
    if value is None or value == "":
        return fallback
    return f"{value}{suffix}"


def _operations(payload: dict[str, object]) -> tuple[dict[str, object], dict[str, object], str, bool]:
    context = payload.get("inneros_context")
    if not isinstance(context, dict):
        return {}, {}, "UNAVAILABLE", False
    operations = context.get("operations")
    if not isinstance(operations, dict):
        return {}, {}, "UNAVAILABLE", False
    energy = operations.get("energy") if isinstance(operations.get("energy"), dict) else {}
    facilities = operations.get("facilities") if isinstance(operations.get("facilities"), dict) else {}
    return energy, facilities, str(operations.get("evidence_mode", "UNAVAILABLE")), bool(operations.get("live"))


def _receipt_rows(payload: dict[str, object]) -> str:
    receipt = payload.get("receipt")
    if not isinstance(receipt, dict):
        return '<div class="empty">No receipt yet. Execution is blocked or awaiting approval.</div>'
    rows = [
        ("Correlation", receipt.get("correlation_id")),
        ("Route", receipt.get("route")),
        ("Action", receipt.get("requested_action")),
        ("Executor", receipt.get("executor")),
        ("Verifier", receipt.get("verifier")),
        ("Quality Gate", receipt.get("quality_gate")),
    ]
    return "".join(
        f"<div class='receipt-row'><span>{escape(str(label))}</span><strong>{escape(str(value))}</strong></div>"
        for label, value in rows
    )


def render_demo_page(scenario: str = "happy") -> str:
    payload = demo_payload(scenario)
    energy, facilities, evidence_mode, live = _operations(payload)
    context = payload.get("inneros_context") if isinstance(payload.get("inneros_context"), dict) else {}
    receipt = payload.get("receipt") if isinstance(payload.get("receipt"), dict) else {}
    provider = payload.get("provider") if isinstance(payload.get("provider"), dict) else {}
    quality = str(receipt.get("quality_gate", "blocked"))
    hostname = str(context.get("hostname", "unknown"))
    evidence_class = "live" if live else "captured"
    wifi24 = facilities.get("wifi_24_clients_total")
    if wifi24 is None:
        p = facilities.get("wifi_24_clients_primary")
        s = facilities.get("wifi_24_clients_secondary")
        if isinstance(p, (int, float)) or isinstance(s, (int, float)):
            wifi24 = int(p or 0) + int(s or 0)
    access_points = facilities.get("access_points") if isinstance(facilities.get("access_points"), list) else []
    hottest_ap = None
    for ap in access_points:
        if not isinstance(ap, dict):
            continue
        if hottest_ap is None or int(ap.get("radio_24_utilization_percent") or 0) > int(hottest_ap.get("radio_24_utilization_percent") or 0):
            hottest_ap = ap
    hot_name = str((hottest_ap or {}).get("name", "Network"))
    hot_util = (hottest_ap or {}).get("radio_24_utilization_percent")
    high_retry = facilities.get("high_retry_client") if isinstance(facilities.get("high_retry_client"), dict) else {}

    initial_json = json.dumps(payload, separators=(",", ":")).replace("</", "<\\/")
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>InnerOS FieldOps — Judge Console</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg:#05090f; --panel:#0b131d; --panel2:#101b28; --line:#203246;
      --text:#edf7ff; --muted:#8ea4b8; --cyan:#42d7ff; --green:#59e39a;
      --amber:#ffcc66; --red:#ff6d7a; --violet:#a991ff;
    }}
    *{{box-sizing:border-box}} body{{margin:0;background:radial-gradient(circle at 20% -10%,#123047 0,#05090f 42%);color:var(--text);font-family:Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif}}
    button,select{{font:inherit}} .shell{{max-width:1440px;margin:auto;padding:24px}}
    header{{display:flex;justify-content:space-between;align-items:flex-start;gap:20px;padding:12px 0 22px;border-bottom:1px solid var(--line)}}
    .brand h1{{margin:0;font-size:34px;letter-spacing:-1px}} .brand p{{margin:7px 0 0;color:var(--muted);max-width:800px}}
    .brand b{{color:var(--cyan)}} .badges{{display:flex;gap:8px;flex-wrap:wrap;justify-content:flex-end}}
    .badge{{border:1px solid var(--line);background:#0a1520;border-radius:999px;padding:6px 10px;font-size:12px;font-weight:800;letter-spacing:.4px}}
    .badge.live{{color:var(--green);border-color:#2d6d50}} .badge.captured{{color:var(--amber);border-color:#725d31}} .badge.route{{color:var(--cyan)}}
    .hero{{display:grid;grid-template-columns:1.4fr .6fr;gap:16px;margin:20px 0}}
    .panel{{background:linear-gradient(180deg,rgba(16,27,40,.96),rgba(8,16,25,.98));border:1px solid var(--line);border-radius:16px;padding:18px;box-shadow:0 18px 45px rgba(0,0,0,.22)}}
    .panel h2,.panel h3{{margin:0}} .eyebrow{{font-size:11px;color:var(--cyan);font-weight:900;text-transform:uppercase;letter-spacing:1.4px}}
    .mission{{font-size:26px;line-height:1.2;margin:9px 0 14px;max-width:820px}} .muted{{color:var(--muted)}}
    .controls{{display:flex;gap:9px;flex-wrap:wrap;margin-top:14px}} button,select{{border-radius:10px;border:1px solid var(--line);background:#0b1824;color:var(--text);padding:10px 13px}}
    button{{cursor:pointer;font-weight:800}} button.primary{{background:linear-gradient(135deg,#007e9e,#155fa8);border-color:#2aa9d0}} button.danger{{border-color:#7b3c44;color:#ffc5cb}} button.ghost{{color:var(--muted)}}
    .score{{display:grid;grid-template-columns:repeat(2,1fr);gap:10px;margin-top:12px}} .metric{{background:#08121c;border:1px solid var(--line);border-radius:12px;padding:13px}}
    .metric strong{{display:block;font-size:24px}} .metric span{{font-size:12px;color:var(--muted)}}
    .systems{{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin:16px 0}}
    .capability-heading{{display:flex;justify-content:space-between;align-items:end;gap:18px;margin:22px 0 10px}}
    .capability-heading h2{{margin:4px 0 0}} .capability-heading p{{margin:0;max-width:720px;text-align:right;color:var(--muted);font-size:13px}}
    .capabilities{{display:grid;grid-template-columns:repeat(2,1fr);gap:16px;margin:0 0 16px}}
    .capability-card .system-title{{margin-bottom:9px}} .capability-card .kv strong{{text-align:right}}
    .system-card{{position:relative;overflow:hidden}} .system-card::after{{content:"";position:absolute;inset:auto -40px -80px auto;width:160px;height:160px;border-radius:50%;background:rgba(66,215,255,.07)}}
    .system-title{{display:flex;align-items:center;justify-content:space-between;margin-bottom:13px}} .system-title h3{{font-size:17px}}
    .kv{{display:grid;grid-template-columns:1fr auto;gap:8px 14px;font-size:13px;padding:7px 0;border-bottom:1px solid rgba(32,50,70,.65)}} .kv:last-child{{border-bottom:0}} .kv span{{color:var(--muted)}}
    .state-good{{color:var(--green)}} .state-warn{{color:var(--amber)}} .state-bad{{color:var(--red)}}
    .pipeline{{display:grid;grid-template-columns:repeat(5,1fr);gap:9px;margin-top:14px}} .step{{padding:12px;border:1px solid var(--line);border-radius:12px;background:#07111a;min-height:92px}}
    .step b{{display:block;margin-bottom:5px}} .step small{{color:var(--muted)}} .step.done{{border-color:#276849}} .step.active{{border-color:#237fa3;box-shadow:inset 0 0 0 1px rgba(66,215,255,.18)}}
    .bottom{{display:grid;grid-template-columns:.9fr 1.1fr;gap:16px;margin-top:16px}} .receipt-row{{display:grid;grid-template-columns:120px 1fr;gap:12px;padding:8px 0;border-bottom:1px solid var(--line);font-size:13px}} .receipt-row span{{color:var(--muted)}} .receipt-row strong{{overflow-wrap:anywhere}}
    .timeline{{display:flex;flex-direction:column;gap:9px;margin-top:12px}} .event{{display:grid;grid-template-columns:78px 1fr;gap:10px;align-items:start}} .event time{{font-size:11px;color:var(--muted);padding-top:2px}} .event div{{border-left:2px solid var(--cyan);padding-left:10px;font-size:13px}}
    .trace{{max-height:280px;overflow:auto;background:#03070b;border:1px solid #182637;border-radius:12px;padding:13px;font:11px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;color:#bfe9ce;white-space:pre-wrap}}
    .empty{{color:var(--muted);padding:14px 0}} .architecture{{width:100%;border:1px solid var(--line);border-radius:12px;margin-top:12px;background:#07111a}}
    footer{{color:#657b8e;font-size:12px;text-align:center;padding:24px 0 8px}}
    @media(max-width:980px){{.hero,.bottom{{grid-template-columns:1fr}}.systems{{grid-template-columns:1fr}}.pipeline{{grid-template-columns:1fr}}.shell{{padding:15px}}header{{flex-direction:column}}.badges{{justify-content:flex-start}}}}
  </style>
</head>
<body>
<div class="shell">
  <header>
    <div class="brand">
      <div class="eyebrow">AWS Agents for Humans · Professional Agents</div>
      <h1>InnerOS <b>FieldOps</b></h1>
      <p>The agent that closes the loop: understand a real-world problem, keep people in control, execute a bounded action, verify the physical result, and preserve evidence.</p>
    </div>
    <div class="badges">
      <span class="badge {evidence_class}" id="evidence-badge">{escape(evidence_mode)}</span>
      <span class="badge route" id="route-badge">{escape(str(provider.get('route', 'local-first')))}</span>
      <span class="badge">Edge: {escape(hostname)}</span>
    </div>
  </header>

  <section class="hero">
    <div class="panel">
      <div class="eyebrow">Judge Mode</div>
      <div class="mission">“A camera service is unavailable. Restore it safely and prove that it came back.”</div>
      <div class="muted">Security Agent interprets the incident. A consequential action cannot run until a human approves it. Verification is independent from execution.</div>
      <div class="controls">
        <button class="primary" data-scenario="happy">Approve & Execute</button>
        <button class="danger" data-scenario="denied">Deny Action</button>
        <button class="ghost" data-scenario="failed-verification">Simulate Failed Verification</button>
        <select id="scenario">{"".join(f'<option value="{escape(item)}">{escape(item)}</option>' for item in SCENARIOS)}</select>
      </div>
      <div class="pipeline" id="pipeline">
        <div class="step done"><b>01 · Observe</b><small>Incident + infrastructure context</small></div>
        <div class="step done"><b>02 · Understand</b><small>Strands chooses bounded FieldOps tool</small></div>
        <div class="step active"><b>03 · Approve</b><small>Human control for consequential action</small></div>
        <div class="step"><b>04 · Act</b><small>Allowlisted executor only</small></div>
        <div class="step"><b>05 · Verify</b><small>Independent state check + receipt</small></div>
      </div>
    </div>
    <aside class="panel">
      <div class="eyebrow">Execution Status</div>
      <div class="score">
        <div class="metric"><strong id="status">{escape(str(payload.get('status', 'unknown')))}</strong><span>workflow status</span></div>
        <div class="metric"><strong id="quality">{escape(quality)}</strong><span>quality gate</span></div>
        <div class="metric"><strong>Strands</strong><span>agent orchestration</span></div>
        <div class="metric"><strong>Fail-closed</strong><span>unsafe action policy</span></div>
      </div>
    </aside>
  </section>

  <section class="systems">
    <article class="panel system-card">
      <div class="system-title"><h3>Security Agent</h3><span class="badge">GOVERNED</span></div>
      <div class="kv"><span>Incident</span><strong>Camera service unavailable</strong></div>
      <div class="kv"><span>Action</span><strong>Bounded service restart</strong></div>
      <div class="kv"><span>Approval</span><strong class="state-warn">Required</strong></div>
      <div class="kv"><span>Verification</span><strong>Independent</strong></div>
    </article>
    <article class="panel system-card">
      <div class="system-title"><h3>Energy Agent</h3><span class="badge {evidence_class}">{escape(evidence_mode)}</span></div>
      <div class="kv"><span>Inverter</span><strong>{escape(_value(energy.get('status'), fallback='Xmart online'))}</strong></div>
      <div class="kv"><span>Output</span><strong id="solar-power">{escape(_value(energy.get('output_power_w'), ' W'))}</strong></div>
      <div class="kv"><span>Battery</span><strong id="solar-battery">{escape(_value(energy.get('battery_capacity_percent'), '%'))}</strong></div>
      <div class="kv"><span>Load</span><strong id="solar-load">{escape(_value(energy.get('load_percent'), '%'))}</strong></div>
      <div class="kv"><span>PV charging</span><strong>{escape(_value(energy.get('pv_charging_power_w'), ' W'))}</strong></div>
    </article>
    <article class="panel system-card">
      <div class="system-title"><h3>Facility / Network Agent</h3><span class="badge {evidence_class}">{escape(evidence_mode)}</span></div>
      <div class="kv"><span>2.4 GHz clients</span><strong id="wifi24">{escape(_value(wifi24))}</strong></div>
      <div class="kv"><span>5 GHz clients</span><strong id="wifi5">{escape(_value(facilities.get('wifi_5_clients')))}</strong></div>
      <div class="kv"><span>Hot AP</span><strong>{escape(hot_name)}</strong></div>
      <div class="kv"><span>2.4 utilization</span><strong class="state-warn">{escape(_value(hot_util, '%'))}</strong></div>
      <div class="kv"><span>Problem client</span><strong>{escape(str(high_retry.get('name', 'none')))}</strong></div>
    </article>
  </section>

  <div class="capability-heading">
    <div>
      <div class="eyebrow">Connected Physical Capabilities</div>
      <h2>One governed boundary, more than one kind of hardware</h2>
    </div>
    <p>Verified InnerOS integrations are shown as supporting evidence rather than extra judge workflows, keeping the end-to-end story focused.</p>
  </div>
  <section class="capabilities">
    <article class="panel capability-card">
      <div class="system-title"><h3>Lighting / DMX</h3><span class="badge live">VERIFIED REAL</span></div>
      <div class="kv"><span>Runtime</span><strong>InnerOS AG-59</strong></div>
      <div class="kv"><span>Transport</span><strong>Art-Net / DMX</strong></div>
      <div class="kv"><span>Control surface</span><strong>Allowlisted scenes only</strong></div>
      <div class="kv"><span>Safety</span><strong>No raw channels from the agent</strong></div>
      <div class="kv"><span>Hardware proof</span><strong class="state-good">Scene + blackout verified</strong></div>
    </article>
    <article class="panel capability-card">
      <div class="system-title"><h3>Telephony / VoiceOps</h3><span class="badge captured">READ-ONLY VERIFIED</span></div>
      <div class="kv"><span>PBX</span><strong>Grandstream UCM6104</strong></div>
      <div class="kv"><span>Control planes</span><strong>SIP + AMI + CGI adapters</strong></div>
      <div class="kv"><span>Network proof</span><strong class="state-good">PBX services reachable</strong></div>
      <div class="kv"><span>Remote path</span><strong>Private tunnel architecture</strong></div>
      <div class="kv"><span>Outbound calls</span><strong class="state-warn">LOCKED pending route verification</strong></div>
    </article>
  </section>

  <section class="bottom">
    <article class="panel">
      <div class="eyebrow">Evidence Receipt</div>
      <h2>Proof, not promises</h2>
      <div id="receipt">{_receipt_rows(payload)}</div>
      <div class="timeline" id="timeline">
        <div class="event"><time>STEP 1</time><div>Request captured with a correlation ID.</div></div>
        <div class="event"><time>STEP 2</time><div>Policy checks approval before executor invocation.</div></div>
        <div class="event"><time>STEP 3</time><div>Independent verifier decides whether the quality gate passes.</div></div>
      </div>
    </article>
    <article class="panel">
      <div class="eyebrow">Architecture + Live Trace</div>
      <h2>Sovereign execution, cloud-compatible orchestration</h2>
      <img class="architecture" src="/assets/fieldops-architecture.svg" alt="InnerOS FieldOps architecture diagram">
      <details style="margin-top:12px"><summary>Technical trace</summary><pre class="trace" id="trace">{escape(json.dumps(payload, indent=2, sort_keys=True))}</pre></details>
    </article>
  </section>
  <footer>InnerOS FieldOps · Local-first execution · Human approval · Independent verification · Auditable evidence</footer>
</div>
<script>
  let current = {initial_json};
  const esc = (v) => String(v ?? '--');
  function receiptRows(data) {{
    if (!data.receipt) return '<div class="empty">No receipt yet. Execution is blocked or awaiting approval.</div>';
    const rows = [['Correlation','correlation_id'],['Route','route'],['Action','requested_action'],['Executor','executor'],['Verifier','verifier'],['Quality Gate','quality_gate']];
    return rows.map(([label,key]) => `<div class="receipt-row"><span>${{label}}</span><strong>${{esc(data.receipt[key])}}</strong></div>`).join('');
  }}
  function paint(data) {{
    current = data;
    document.getElementById('status').textContent = esc(data.status);
    document.getElementById('quality').textContent = esc(data.receipt?.quality_gate || 'blocked');
    document.getElementById('receipt').innerHTML = receiptRows(data);
    document.getElementById('trace').textContent = JSON.stringify(data, null, 2);
    const steps = [...document.querySelectorAll('.step')];
    steps.forEach(s => s.classList.remove('done','active'));
    steps[0].classList.add('done'); steps[1].classList.add('done');
    if (data.status === 'blocked') {{ steps[2].classList.add('active'); }}
    else if (data.receipt?.quality_gate === 'passed') {{ steps.forEach(s => s.classList.add('done')); }}
    else {{ steps[2].classList.add('done'); steps[3].classList.add('done'); steps[4].classList.add('active'); }}
  }}
  async function runScenario(scenario) {{
    document.getElementById('scenario').value = scenario;
    const res = await fetch(`/api/demo?scenario=${{encodeURIComponent(scenario)}}`);
    paint(await res.json());
  }}
  document.querySelectorAll('[data-scenario]').forEach(btn => btn.addEventListener('click', () => runScenario(btn.dataset.scenario)));
  document.getElementById('scenario').addEventListener('change', e => runScenario(e.target.value));
  async function refreshStatus() {{
    try {{
      const res = await fetch('/api/status'); const data = await res.json();
      const ops = data.inneros_context?.operations || {{}}; const energy = ops.energy || {{}}; const f = ops.facilities || {{}};
      document.getElementById('evidence-badge').textContent = ops.evidence_mode || 'UNAVAILABLE';
      document.getElementById('solar-power').textContent = energy.output_power_w == null ? '--' : `${{energy.output_power_w}} W`;
      document.getElementById('solar-battery').textContent = energy.battery_capacity_percent == null ? '--' : `${{energy.battery_capacity_percent}}%`;
      document.getElementById('solar-load').textContent = energy.load_percent == null ? '--' : `${{energy.load_percent}}%`;
      const wifi24 = f.wifi_24_clients_total ?? ((Number(f.wifi_24_clients_primary)||0)+(Number(f.wifi_24_clients_secondary)||0));
      document.getElementById('wifi24').textContent = wifi24 || '--';
      document.getElementById('wifi5').textContent = f.wifi_5_clients ?? '--';
    }} catch (_) {{}}
  }}
  setInterval(refreshStatus, 5000);
</script>
</body>
</html>
"""


class DemoHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        scenario = query.get("scenario", ["happy"])[0]
        if scenario not in SCENARIOS:
            scenario = "happy"
        if parsed.path == "/":
            self._send(200, "text/html; charset=utf-8", render_demo_page(scenario).encode())
            return
        if parsed.path == "/api/demo":
            body = json.dumps(demo_payload(scenario), indent=2, sort_keys=True).encode()
            self._send(200, "application/json; charset=utf-8", body)
            return
        if parsed.path == "/api/status":
            body = json.dumps(status_payload(), indent=2, sort_keys=True).encode()
            self._send(200, "application/json; charset=utf-8", body)
            return
        if parsed.path == "/assets/fieldops-architecture.svg":
            asset_path = Path(__file__).resolve().parents[2] / "docs" / "assets" / "fieldops-architecture.svg"
            body = asset_path.read_text(encoding="utf-8") if asset_path.exists() else render_architecture_svg()
            self._send(200, "image/svg+xml; charset=utf-8", body.encode())
            return
        self._send(404, "text/plain; charset=utf-8", b"not found")

    def log_message(self, format: str, *args: object) -> None:
        return

    def _send(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def run_server(host: str = "127.0.0.1", port: int = 8765) -> None:
    server = ThreadingHTTPServer((host, port), DemoHandler)
    print(f"InnerOS FieldOps judge console listening on http://{host}:{port}")
    server.serve_forever()
