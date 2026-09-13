import json
from threading import Thread
from urllib.request import urlopen

from src.fieldops.demo_web import DemoHandler, ThreadingHTTPServer, demo_payload, render_demo_page


def test_demo_web_page_exposes_required_judge_surfaces():
    html = render_demo_page("happy")

    assert "InnerOS" in html and "FieldOps" in html
    assert "Judge Mode" in html
    assert "Approve & Execute" in html
    assert "Security Agent" in html
    assert "Energy Agent" in html
    assert "Facility / Network Agent" in html
    assert "Evidence Receipt" in html
    assert "Independent" in html
    assert "Technical trace" in html or "Technical Trace" in html


def test_demo_web_api_payload_contains_evidence_and_inneros_context():
    payload = demo_payload("happy")

    assert payload["status"] == "ok"
    assert payload["receipt"]["quality_gate"] == "passed"
    assert payload["inneros_context"]["read_only"] is True
    assert payload["inneros_context"]["mutation_allowed"] is False
    assert payload["inneros_context"]["operations"]["evidence_mode"] in {"LIVE REAL", "CAPTURED REAL"}


def test_credential_free_demo_uses_committed_real_operations_evidence():
    payload = demo_payload("happy")
    operations = payload["inneros_context"]["operations"]

    if operations["evidence_mode"] == "CAPTURED REAL":
        assert operations["energy"]["output_power_w"] == 677
        assert operations["energy"]["battery_capacity_percent"] == 100
        assert operations["facilities"]["wifi_24_clients_total"] == 37
        assert operations["facilities"]["wifi_5_clients"] == 10
        assert operations["facilities"]["alarm_intelbras_presence"] == "online"


def test_judge_console_http_smoke():
    server = ThreadingHTTPServer(("127.0.0.1", 0), DemoHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        with urlopen(f"http://{host}:{port}/", timeout=3) as response:
            html = response.read().decode("utf-8")
            assert response.status == 200
            assert "Judge Mode" in html
            assert "CAPTURED REAL" in html or "LIVE REAL" in html
        with urlopen(f"http://{host}:{port}/api/status", timeout=3) as response:
            payload = json.loads(response.read().decode("utf-8"))
            assert response.status == 200
            assert payload["inneros_context"]["read_only"] is True
            assert payload["inneros_context"]["operations"]["evidence_mode"] in {"LIVE REAL", "CAPTURED REAL"}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
