import pytest

pytest.importorskip("strands")

from src.fieldops.strands_runtime import (  # noqa: E402
    build_fieldops_agent,
    invoke_fieldops_demo_tool,
)


def test_real_strands_agent_can_invoke_bounded_fieldops_tool():
    result = invoke_fieldops_demo_tool("happy")

    assert result["agent_class"] == "Agent"
    assert result["tool_status"] == "success"
    assert result["parsed"]["status"] == "ok"
    assert result["parsed"]["receipt"]["quality_gate"] == "passed"
    assert result["parsed"]["receipt"]["executor"] == "inneros-edge-01"


def test_real_strands_agent_exposes_readonly_context_tool():
    agent = build_fieldops_agent()
    result = agent.tool.read_inneros_readonly_context()

    assert result["status"] == "success"
    assert '"read_only": true' in result["content"][0]["text"]
    assert '"mutation_allowed": false' in result["content"][0]["text"]
