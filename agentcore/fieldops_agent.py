"""AgentCore-oriented entrypoint for InnerOS FieldOps.

This module intentionally keeps deployment concerns thin: the same bounded
Strands Agent used by the local demo is constructed here, while secrets and AWS
identity are supplied by the runtime environment.
"""

from __future__ import annotations

from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.fieldops.strands_runtime import build_fieldops_agent, invoke_fieldops_demo_tool


agent = build_fieldops_agent()


def handler(event: dict[str, Any] | None = None, context: Any | None = None) -> dict[str, Any]:
    """Minimal deployable handler for smoke tests and managed runtimes."""

    scenario = "happy"
    if event and isinstance(event.get("scenario"), str):
        scenario = event["scenario"]
    return invoke_fieldops_demo_tool(scenario=scenario)
