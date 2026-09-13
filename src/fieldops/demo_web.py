"""Small no-dependency web UI for presenting the FieldOps demo."""

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


def _receipt_rows(payload: dict[str, object]) -> str:
    receipt = payload.get("receipt")
    if not isinstance(receipt, dict):
        return '<div class="status warn">Awaiting approval or remediation</div>'
    rows = [
        ("Correlation", receipt.get("correlation_id")),
        ("Route", receipt.get("route")),
        ("Action", receipt.get("requested_action")),
        ("Executor", receipt.get("executor")),
        ("Verifier", receipt.get("verifier")),
        ("Quality Gate", receipt.get("quality_gate")),
    ]
    return "".join(
        f"<dt>{escape(str(label))}</dt><dd>{escape(str(value))}</dd>" for label, value in rows
    )


def render_demo_page(scenario: str = "happy") -> str:
    payload = demo_payload(scenario)
    status = escape(str(payload.get("status", "unknown")))
    quality = "blocked"
    receipt = payload.get("receipt")
    if isinstance(receipt, dict):
        quality = escape(str(receipt.get("quality_gate", "unknown")))
    context = payload.get("inneros_context", {})
    hostname = escape(str(context.get("hostname", "unknown"))) if isinstance(context, dict) else "unknown"

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>InnerOS FieldOps Demo</title>
  <style>
    :root {{
      color-scheme: light;
      --ink: #102033;
      --muted: #526173;
      --line: #d7e1ea;
      --panel: #ffffff;
      --soft: #f4f8fb;
      --accent: #1a7f64;
      --warn: #b45309;
      --shadow: 0 18px 50px rgba(16, 32, 51, .10);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #eef4f7;
      color: var(--ink);
      line-height: 1.5;
    }}
    header {{
      background: #102033;
      color: white;
      padding: 30px 5vw 28px;
      border-bottom: 5px solid var(--accent);
    }}
    header h1 {{
      margin: 0;
      font-size: 34px;
      letter-spacing: 0;
    }}
    header p {{
      margin: 8px 0 0;
      max-width: 860px;
      color: #c9d8e5;
      font-size: 16px;
    }}
    main {{
      max-width: 1180px;
      margin: 0 auto;
      padding: 24px 20px 38px;
    }}
    .toolbar {{
      display: flex;
      gap: 12px;
      align-items: center;
      flex-wrap: wrap;
      margin-bottom: 18px;
    }}
    select, button {{
      height: 42px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: white;
      color: var(--ink);
      padding: 0 12px;
      font: inherit;
    }}
    button {{
      background: var(--accent);
      color: white;
      border-color: var(--accent);
      font-weight: 700;
      cursor: pointer;
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 14px;
    }}
    .card {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
      padding: 18px;
      min-height: 154px;
    }}
    .card h2 {{
      margin: 0 0 8px;
      font-size: 18px;
      letter-spacing: 0;
    }}
    .card p {{
      margin: 0;
      color: var(--muted);
      font-size: 14px;
    }}
    .status {{
      display: inline-flex;
      align-items: center;
      min-height: 30px;
      margin-top: 14px;
      padding: 4px 10px;
      border-radius: 999px;
      background: #e9f7f2;
      color: #0f684f;
      font-size: 13px;
      font-weight: 700;
    }}
    .status.warn {{
      background: #fff7ed;
      color: var(--warn);
    }}
    .wide {{
      display: grid;
      grid-template-columns: 1.1fr .9fr;
      gap: 16px;
      margin-top: 16px;
    }}
    .diagram, .receipt {{
      background: white;
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
      padding: 18px;
    }}
    .diagram img {{
      width: 100%;
      display: block;
      border: 1px solid #e6edf4;
      border-radius: 8px;
      background: var(--soft);
    }}
    dl {{
      display: grid;
      grid-template-columns: 140px 1fr;
      gap: 8px 14px;
      margin: 0;
    }}
    dt {{
      color: var(--muted);
      font-size: 13px;
    }}
    dd {{
      margin: 0;
      font-weight: 700;
      overflow-wrap: anywhere;
    }}
    pre {{
      max-height: 300px;
      overflow: auto;
      background: #0f172a;
      color: #d9f99d;
      border-radius: 8px;
      padding: 14px;
      font-size: 12px;
    }}
    @media (max-width: 900px) {{
      .grid, .wide {{ grid-template-columns: 1fr; }}
      header h1 {{ font-size: 28px; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>InnerOS FieldOps</h1>
    <p>Governed field operations for agents: request, approval, bounded execution, independent verification and replayable evidence.</p>
  </header>
  <main>
    <form class="toolbar" id="demo-form">
      <label for="scenario">Scenario</label>
      <select id="scenario" name="scenario">
        {"".join(f'<option value="{escape(item)}" {"selected" if item == scenario else ""}>{escape(item)}</option>' for item in SCENARIOS)}
      </select>
      <button type="submit">Run Demo</button>
      <span class="status">Status: <strong id="status">&nbsp;{status}</strong></span>
      <span class="status">Quality: <strong id="quality">&nbsp;{quality}</strong></span>
    </form>
    <section class="grid" aria-label="FieldOps execution stages">
      <article class="card"><h2>Request</h2><p>A human, agent or incident proposes one bounded operational outcome.</p><span class="status">Captured</span></article>
      <article class="card"><h2>Human Approval</h2><p>Risky actions require explicit approval before execution can begin.</p><span class="status">Required</span></article>
      <article class="card"><h2>Execution</h2><p>The edge executor changes only the approved target and action type.</p><span class="status">Bounded</span></article>
      <article class="card"><h2>Independent Verification</h2><p>An independent verifier observes the resulting state before success is accepted.</p><span class="status">Mandatory</span></article>
    </section>
    <section class="wide">
      <div class="diagram">
        <h2>Architecture</h2>
        <img src="/assets/fieldops-architecture.svg" alt="InnerOS FieldOps architecture diagram">
      </div>
      <div class="receipt">
        <h2>Evidence Receipt</h2>
        <dl id="receipt">{_receipt_rows(payload)}</dl>
        <h2>Runtime Boundary</h2>
        <p>Host: <strong>{hostname}</strong></p>
        <p>Read-only context adapter. Governed action boundary remains separate.</p>
      </div>
    </section>
    <section class="receipt" style="margin-top:16px">
      <h2>Live Trace</h2>
      <pre id="trace">{escape(json.dumps(payload, indent=2, sort_keys=True))}</pre>
    </section>
  </main>
  <script>
    const form = document.getElementById('demo-form');
    form.addEventListener('submit', async (event) => {{
      event.preventDefault();
      const scenario = document.getElementById('scenario').value;
      const res = await fetch(`/api/demo?scenario=${{encodeURIComponent(scenario)}}`);
      const data = await res.json();
      document.getElementById('status').textContent = ' ' + data.status;
      document.getElementById('quality').textContent = ' ' + (data.receipt?.quality_gate || 'blocked');
      document.getElementById('trace').textContent = JSON.stringify(data, null, 2);
    }});
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
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def run_server(host: str = "127.0.0.1", port: int = 8765) -> None:
    server = ThreadingHTTPServer((host, port), DemoHandler)
    print(f"InnerOS FieldOps demo UI listening on http://{host}:{port}")
    server.serve_forever()
