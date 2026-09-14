#!/usr/bin/env python3
"""Run the real FieldOps Operator Console with the Strands judge view attached."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.fieldops import demo_web, operator_web
from src.fieldops.judge_runtime import run_judge_demo


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the InnerOS FieldOps Operator Console")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8777)
    args = parser.parse_args()

    # The old synthetic/Strands evidence view remains available at /judge, but
    # the root surface is now the real operator product console.
    demo_web.demo_payload = run_judge_demo
    operator_web.run_server(args.host, args.port)


if __name__ == "__main__":
    main()
