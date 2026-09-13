from src.fieldops.demo_web import demo_payload, render_demo_page


def test_demo_web_page_exposes_required_review_surfaces():
    html = render_demo_page("happy")

    assert "InnerOS FieldOps" in html
    assert "Human Approval" in html
    assert "Independent Verification" in html
    assert "Evidence Receipt" in html
    assert "Live Trace" in html


def test_demo_web_api_payload_contains_evidence_and_inneros_context():
    payload = demo_payload("happy")

    assert payload["status"] == "ok"
    assert payload["receipt"]["quality_gate"] == "passed"
    assert payload["inneros_context"]["read_only"] is True
    assert payload["inneros_context"]["mutation_allowed"] is False
