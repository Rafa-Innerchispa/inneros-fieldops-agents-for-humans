#!/usr/bin/env python3
"""Run the existing FieldOps Judge Console through the real Strands runtime."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.fieldops import demo_web
from src.fieldops.judge_runtime import run_judge_demo


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Strands-backed FieldOps Judge Console")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8777)
    args = parser.parse_args()

    demo_web.demo_payload = run_judge_demo
    demo_web.run_server(args.host, args.port)


if __name__ == "__main__":
    main()
