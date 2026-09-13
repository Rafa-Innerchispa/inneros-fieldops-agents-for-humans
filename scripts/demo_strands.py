#!/usr/bin/env python3
"""Run the real Strands Agent wrapper for the safe FieldOps demo."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.fieldops.demo_runner import SCENARIOS
from src.fieldops.strands_runtime import invoke_fieldops_demo_tool


def main() -> None:
    parser = argparse.ArgumentParser(description="Invoke FieldOps through a real Strands Agent.")
    parser.add_argument(
        "--scenario",
        choices=SCENARIOS,
        default="happy",
        help="Synthetic scenario to call through the Strands tool.",
    )
    args = parser.parse_args()
    result = invoke_fieldops_demo_tool(scenario=args.scenario)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
