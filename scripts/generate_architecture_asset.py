#!/usr/bin/env python3
"""Generate the FieldOps architecture SVG used by docs and the demo UI."""

from __future__ import annotations

from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.fieldops.architecture_asset import render_architecture_svg


def main() -> None:
    output_path = REPO_ROOT / "docs" / "assets" / "fieldops-architecture.svg"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_architecture_svg(), encoding="utf-8")
    print(output_path)


if __name__ == "__main__":
    main()
