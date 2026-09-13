from src.fieldops import judge_runtime


def test_judge_runtime_preserves_strands_evidence(monkeypatch):
    monkeypatch.setattr(
        judge_runtime,
        "invoke_fieldops_demo_tool",
        lambda scenario="happy": {
            "parsed": {
                "status": "ok",
                "scenario": scenario,
                "receipt": {"quality_gate": "passed"},
            },
            "agent_class": "Agent",
            "agent_module": "strands.agent.agent",
            "invoked_tool": "execute_fieldops_demo",
            "tool_status": "success",
            "tool_use_id": "tool-123",
        },
    )
    monkeypatch.setattr(
        judge_runtime,
        "read_inneros_context_snapshot",
        lambda: {"read_only": True, "operations": {"evidence_mode": "CAPTURED REAL"}},
    )

    payload = judge_runtime.run_judge_demo("happy")

    assert payload["status"] == "ok"
    assert payload["receipt"]["quality_gate"] == "passed"
    assert payload["strands_runtime"]["active"] is True
    assert payload["strands_runtime"]["agent_class"] == "Agent"
    assert payload["strands_runtime"]["agent_module"] == "strands.agent.agent"
    assert payload["strands_runtime"]["invoked_tool"] == "execute_fieldops_demo"
    assert payload["strands_runtime"]["bedrock_inference_claimed"] is False
    assert payload["inneros_context"]["read_only"] is True
