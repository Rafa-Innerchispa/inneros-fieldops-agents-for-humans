#!/usr/bin/env python3
"""Print the real FieldOps product runtime binding status without mutating devices."""

from __future__ import annotations

import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.fieldops.operator_api import catalog_response
from src.fieldops.product_runtime import build_product_runtime


def main() -> None:
    bundle = build_product_runtime()
    print(json.dumps(catalog_response(bundle), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
