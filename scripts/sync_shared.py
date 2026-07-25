#!/usr/bin/env python3
"""One-way sync of the canonical shared/ package from packing-tool into this
repo. packing-tool/shared/ is the single source of truth (see
packing-tool/docs/superpowers/specs/2026-07-25-shared-unification-design.md)
— never hand-edit shopify-fulfillment-tool/shared/ directly.

Usage:
    python scripts/sync_shared.py
"""
import shutil
import sys
from pathlib import Path

THIS_REPO = Path(__file__).resolve().parent.parent
SOURCE = THIS_REPO.parent / "packing-tool" / "shared"
DEST = THIS_REPO / "shared"


def main() -> int:
    if not SOURCE.is_dir():
        print(f"Source not found: {SOURCE}", file=sys.stderr)
        print("Expected packing-tool as a sibling directory of this repo.", file=sys.stderr)
        return 1

    copied = []
    for src_file in sorted(SOURCE.rglob("*")):
        if "__pycache__" in src_file.parts:
            continue
        if not src_file.is_file():
            continue

        rel = src_file.relative_to(SOURCE)
        dest_file = DEST / rel
        dest_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_file, dest_file)
        copied.append(str(rel))

    print(f"Synced {len(copied)} file(s) from {SOURCE} to {DEST}:")
    for rel in copied:
        print(f"  {rel}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
