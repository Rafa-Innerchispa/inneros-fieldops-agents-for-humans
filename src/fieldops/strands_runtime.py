"""Actual Strands Agents SDK runtime for bounded FieldOps tools."""

from __future__ import annotations

import json
from typing import Any, Callable

from .demo_runner import run_demo
from .inneros_adapter import read_inneros_context_snapshot


class StrandsRuntimeError(RuntimeError):
    """Raised when the optional Strands SDK is not installed."""


def _load_strands() -> tuple[type[Any], Callable[[Callable[..., Any]], Any]]:
    try:
        from strands import Agent, tool
    except ImportError as exc:  # pragma: no cover - exercised only without optional dep
        raise StrandsRuntimeError(
            "Install the optional Strands runtime with: python -m pip install -e '.[strands]'"
        ) from exc
    return Agent, tool


def build_fieldops_tools() -> list[Any]:
    """Create real Strands tools over the safe FieldOps boundaries."""

    _, tool = _load_strands()

    @tool
    def execute_fieldops_demo(scenario: str = "happy") -> str:
        """Run a credential-free approved FieldOps demo and return evidence JSON."""

        return json.dumps(run_demo(scenario), sort_keys=True)

    @tool
    def read_inneros_readonly_context() -> str:
        """Return non-secret InnerOS runtime context without mutating anything."""

        return json.dumps(read_inneros_context_snapshot(), sort_keys=True)

    return [execute_fieldops_demo, read_inneros_readonly_context]


def build_fieldops_agent() -> Any:
    """Instantiate an actual Strands Agent with bounded FieldOps tools."""

    Agent, _ = _load_strands()
    return Agent(tools=build_fieldops_tools())


def _content_text(tool_result: Any) -> str:
    if isinstance(tool_result, dict):
        content = tool_result.get("content", [])
        if isinstance(content, list):
            chunks = []
            for item in content:
                if isinstance(item, dict) and isinstance(item.get("text"), str):
                    chunks.append(item["text"])
            return "\n".join(chunks)
    return str(tool_result)


def normalize_tool_result(tool_result: Any) -> dict[str, Any]:
    """Normalize Strands direct-tool output for tests and evidence."""

    text = _content_text(tool_result)
    parsed: Any = None
    if text:
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = None
    return {
        "tool_status": tool_result.get("status") if isinstance(tool_result, dict) else None,
        "tool_use_id": tool_result.get("toolUseId") if isinstance(tool_result, dict) else None,
        "content_text": text,
        "parsed": parsed,
    }


def invoke_fieldops_demo_tool(scenario: str = "happy") -> dict[str, Any]:
    """Build the agent and call the FieldOps tool through Strands direct invocation."""

    agent = build_fieldops_agent()
    raw = agent.tool.execute_fieldops_demo(scenario=scenario)
    normalized = normalize_tool_result(raw)
    normalized.update(
        {
            "agent_class": agent.__class__.__name__,
            "agent_module": agent.__class__.__module__,
            "invoked_tool": "execute_fieldops_demo",
            "scenario": scenario,
        }
    )
    return normalized
