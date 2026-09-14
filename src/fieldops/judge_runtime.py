"""Judge-facing FieldOps runtime backed by the actual Strands Agents SDK."""

from __future__ import annotations

from typing import Any

from .governance import READ_ONLY_CAPABILITIES, action_catalog_payload
from .inneros_adapter import read_inneros_context_snapshot
from .strands_runtime import invoke_fieldops_demo_tool


class JudgeRuntimeError(RuntimeError):
    """Raised when the Strands-backed judge path does not return valid evidence."""


def run_judge_demo(scenario: str = "happy") -> dict[str, object]:
    """Execute the bounded demo through a real ``strands.Agent`` tool surface.

    This deliberately uses direct Strands tool invocation rather than model inference,
    so the judge workflow remains deterministic and credential-free while AWS Bedrock
    account access is being resolved. The returned evidence records the actual Agent
    class/module and tool status used for the request.
    """

    normalized = invoke_fieldops_demo_tool(scenario=scenario)
    parsed = normalized.get("parsed")
    if not isinstance(parsed, dict):
        raise JudgeRuntimeError("Strands tool invocation did not return a FieldOps evidence payload")

    payload: dict[str, Any] = dict(parsed)
    payload["strands_runtime"] = {
        "active": True,
        "agent_class": normalized.get("agent_class"),
        "agent_module": normalized.get("agent_module"),
        "invoked_tool": normalized.get("invoked_tool"),
        "tool_status": normalized.get("tool_status"),
        "tool_use_id": normalized.get("tool_use_id"),
        "mode": "direct_bounded_tool_invocation",
        "bedrock_inference_claimed": False,
    }
    payload["inneros_context"] = read_inneros_context_snapshot()
    payload["governed_actions"] = action_catalog_payload()
    payload["read_only_capabilities"] = dict(READ_ONLY_CAPABILITIES)
    payload["governance_contract"] = {
        "mutation_path": ["observe", "propose", "approve", "execute", "verify", "evidence"],
        "central_policy_authoritative": True,
        "executor_ack_is_not_success": True,
        "unknown_mutations_fail_closed": True,
    }
    return payload
