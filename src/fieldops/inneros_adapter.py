"""Read-only InnerOS context adapter for FieldOps demos.

The adapter deliberately avoids mutation. It gives a Strands or UI demo enough
live context to prove it is running inside an InnerOS environment, while keeping
actual action requests behind the governed FieldOps boundary.
"""

from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
import socket
from typing import Mapping

DEFAULT_COORDINATION_ROOTS = (
    "/home/rlopez/inneros/inneros_core/HUB",
    "/home/rlopez/inneros/inneros_core/runtime",
)


def _split_roots(value: str) -> list[str]:
    return [item for item in (part.strip() for part in value.split(":")) if item]


def read_inneros_context_snapshot(
    source: Mapping[str, str] | None = None,
) -> dict[str, object]:
    """Return non-secret, read-only runtime context for evidence."""

    env = source or os.environ
    roots = _split_roots(env.get("FIELDOPS_INNEROS_COORDINATION_ROOTS", ""))
    if not roots:
        roots = list(DEFAULT_COORDINATION_ROOTS)
    live_status_path = env.get("FIELDOPS_INNEROS_STATUS_PATH", "").strip()
    live_status_preview = None
    live_status_exists = False
    if live_status_path:
        path = Path(live_status_path)
        live_status_exists = path.exists()
        if live_status_exists and path.is_file():
            live_status_preview = path.read_text(encoding="utf-8", errors="replace")[:1200]

    return {
        "adapter": "inneros-readonly-v1",
        "arbitrary_shell": False,
        "arbitrary_network": False,
        "governed_action_boundary": "fieldops.workflow.run_action",
        "hostname": socket.gethostname(),
        "mcp_profile": env.get("FIELDOPS_INNEROS_MCP_PROFILE", "not-configured"),
        "mcp_url_configured": bool(env.get("FIELDOPS_INNEROS_MCP_URL")),
        "mutation_allowed": False,
        "read_only": True,
        "roots": [
            {
                "path": root,
                "exists": Path(root).exists(),
            }
            for root in roots
        ],
        "status_path": live_status_path or None,
        "status_path_exists": live_status_exists,
        "status_preview": live_status_preview,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    }
