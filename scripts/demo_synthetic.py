#!/usr/bin/env python3
"""Run a safe end-to-end InnerOS FieldOps demonstration."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.fieldops.demo_runner import SCENARIOS, run_demo
from src.fieldops.providers import ProviderConfigError, load_provider_config


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a credential-free InnerOS FieldOps synthetic demo."
    )
    parser.add_argument(
        "--scenario",
        choices=SCENARIOS,
        default="happy",
        help="Synthetic path to exercise.",
    )
    parser.add_argument(
        "--provider",
        choices=["local", "bedrock"],
        default=None,
        help="Override FIELDOPS_MODEL_PROVIDER for routing evidence only.",
    )
    args = parser.parse_args()

    try:
        provider = load_provider_config()
        if args.provider:
            provider = load_provider_config(
                {**provider.to_env_overlay(), "FIELDOPS_MODEL_PROVIDER": args.provider}
            )
    except ProviderConfigError as exc:
        parser.exit(2, f"configuration error: {exc}\n")

    output = run_demo(args.scenario, provider)
    print(json.dumps(output, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
