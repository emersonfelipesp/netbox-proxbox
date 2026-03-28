"""Public facade for Proxbox CLI documentation capture and command indexing."""

from __future__ import annotations

import json
import platform
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import TextIO

from proxbox_cli.docgen.engine import CaptureEngine, build_command_catalog
from proxbox_cli.docgen.specs import load_specs


def resolve_capture_paths(
    output: Path | None,
    raw_dir: Path | None,
    catalog_output: Path | None,
) -> tuple[Path, Path, Path]:
    """Resolve default artifact paths under `docs/generated/proxbox-cli/`."""
    docs_dir = _repo_root() / "docs"
    generated_dir = docs_dir / "generated" / "proxbox-cli"
    resolved_output = output or (docs_dir / "generated" / "proxbox-cli-command-capture.md")
    resolved_raw = raw_dir or (generated_dir / "raw")
    resolved_catalog = catalog_output or (generated_dir / "catalog.json")
    return resolved_output, resolved_raw, resolved_catalog


def generate_command_capture_docs(
    *,
    output: Path,
    raw_dir: Path,
    catalog_output: Path,
    log: TextIO | None = None,
) -> int:
    """Generate raw capture artifacts plus a command catalog for the MkDocs site."""
    logger = log or sys.stderr
    output.parent.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)
    catalog_output.parent.mkdir(parents=True, exist_ok=True)

    for existing in raw_dir.glob("*.json"):
        existing.unlink()

    meta = _build_meta()
    specs = load_specs()
    engine = CaptureEngine(log=logger)
    results = engine.capture_all(specs)
    engine.write_artifacts(results, raw_dir)

    (raw_dir / "index.json").write_text(
        json.dumps(
            {
                "meta": meta,
                "runs": [result.to_dict() for result in results],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    catalog_output.write_text(
        json.dumps(
            {
                "meta": meta,
                **build_command_catalog(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    output.write_text(_render_snapshot(meta, results), encoding="utf-8")

    print(f"Wrote {output}", file=logger)
    print(f"Wrote {len(results)} raw capture files under {raw_dir}", file=logger)
    print(f"Wrote {catalog_output}", file=logger)
    return 0


def _build_meta() -> dict[str, str]:
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "python": platform.python_version(),
        "platform": platform.platform(),
    }


def _render_snapshot(meta: dict[str, str], results: list) -> str:
    lines = [
        "# proxbox_cli command capture",
        "",
        "This file is machine-generated. Regenerate it with:",
        "",
        "```bash",
        "cd /path/to/netbox-proxbox",
        "python docs/generate_proxbox_cli_docs.py",
        "# or: pxb docs generate-capture",
        "```",
        "",
        "## Metadata",
        "",
        f"- Generated at: `{meta['generated_at']}`",
        f"- Python: `{meta['python']}`",
        f"- Platform: `{meta['platform']}`",
        "",
    ]

    current_section = ""
    for result in results:
        if result.section != current_section:
            current_section = result.section
            lines.extend([f"## {current_section}", ""])

        lines.extend(
            [
                f"### {result.title}",
                "",
                f"Command: `pxb {' '.join(result.argv)}`",
                "",
            ]
        )
        if result.notes:
            lines.extend([result.notes, ""])
        lines.extend(["```text", result.stdout or "(empty)", "```", ""])

    return "\n".join(lines)


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent
