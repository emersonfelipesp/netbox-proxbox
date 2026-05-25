#!/usr/bin/env python3
"""Generate Proxbox CLI command-capture artifacts for the MkDocs site."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from proxbox_cli.docgen_capture import generate_command_capture_docs, resolve_capture_paths


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Proxbox CLI docs artifacts.")
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--raw-dir", type=Path, default=None)
    parser.add_argument("--catalog-output", type=Path, default=None)
    args = parser.parse_args()

    output, raw_dir, catalog_output = resolve_capture_paths(
        args.output,
        args.raw_dir,
        args.catalog_output,
    )
    return generate_command_capture_docs(
        output=output,
        raw_dir=raw_dir,
        catalog_output=catalog_output,
    )


if __name__ == "__main__":
    raise SystemExit(main())
