"""MkDocs hook for Proxbox CLI generated reference pages."""

from __future__ import annotations

import json
from pathlib import Path
import re
import sys

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_GENERATED_DIR = _REPO_ROOT / "docs" / "generated" / "proxbox-cli"
_RAW_DIR = _GENERATED_DIR / "raw"
_INDEX_FILE = _RAW_DIR / "index.json"
_CATALOG_FILE = _GENERATED_DIR / "catalog.json"
_EXAMPLES_DIR = _REPO_ROOT / "docs" / "reference" / "proxbox-cli" / "command-examples"
_CATALOG_DIR = _REPO_ROOT / "docs" / "reference" / "proxbox-cli" / "command-catalog"


def on_config(config, **kwargs):  # noqa: ANN001, D401
    """Build CLI-generated pages before MkDocs scans the docs tree."""
    _build_command_examples()
    _build_command_catalog()
    return config


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _build_command_examples() -> None:
    _EXAMPLES_DIR.mkdir(parents=True, exist_ok=True)

    if not _INDEX_FILE.exists():
        (_EXAMPLES_DIR / "index.md").write_text(
            "\n".join(
                [
                    "# Proxbox CLI Command Examples",
                    "",
                    '!!! warning "Not yet generated"',
                    "    Run `python docs/generate_proxbox_cli_docs.py` or `pxb docs generate-capture` first.",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        return

    index = json.loads(_INDEX_FILE.read_text(encoding="utf-8"))
    meta = index.get("meta", {})
    runs = index.get("runs", [])

    sections: dict[str, list[dict]] = {}
    for run in runs:
        sections.setdefault(run["section"], []).append(run)

    section_lines = [
        "# Proxbox CLI Command Examples",
        "",
        "Machine-generated help captures for representative `pxb` commands.",
        "",
        '!!! info "Generated"',
        f"    Last updated: `{meta.get('generated_at', 'unknown')}`",
        "",
        "## Sections",
        "",
    ]

    for section in sections:
        slug = _slug(section)
        section_lines.append(
            f"- [{section}](./{slug}.md) — {len(sections[section])} captures"
        )
        _write_example_section(section, sections[section], meta)

    section_lines.append("")
    (_EXAMPLES_DIR / "index.md").write_text("\n".join(section_lines), encoding="utf-8")


def _write_example_section(section: str, runs: list[dict], meta: dict) -> None:
    lines = [
        f"# {section}",
        "",
        "Representative command help output captured automatically from the local checkout.",
        "",
        f"Generated: `{meta.get('generated_at', 'unknown')}`",
        "",
    ]
    for run in runs:
        command = "pxb " + " ".join(run.get("argv", []))
        lines.extend(
            [
                f"## {run['title']}",
                "",
                f"Command: `{command}`",
                "",
            ]
        )
        notes = (run.get("notes") or "").strip()
        if notes:
            lines.extend([notes, ""])
        lines.extend(["```text", run.get("stdout") or "(empty)", "```", ""])

    (_EXAMPLES_DIR / f"{_slug(section)}.md").write_text(
        "\n".join(lines), encoding="utf-8"
    )


def _build_command_catalog() -> None:
    _CATALOG_DIR.mkdir(parents=True, exist_ok=True)

    if not _CATALOG_FILE.exists():
        (_CATALOG_DIR / "index.md").write_text(
            "\n".join(
                [
                    "# Proxbox CLI Command Reference",
                    "",
                    '!!! warning "Not yet generated"',
                    "    Run `python docs/generate_proxbox_cli_docs.py` or `pxb docs generate-capture` first.",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        return

    catalog = json.loads(_CATALOG_FILE.read_text(encoding="utf-8"))
    commands = catalog.get("commands", [])

    lines = [
        "# Proxbox CLI Command Reference",
        "",
        "Machine-generated command inventory for the `proxbox_cli` package.",
        "",
        '!!! info "Generated"',
        f"    Last updated: `{catalog.get('meta', {}).get('generated_at', 'unknown')}`",
        f"    Command groups: `{catalog.get('group_count', 0)}`",
        f"    Leaf commands: `{catalog.get('command_count', 0)}`",
        "",
        "| Command | Kind | Summary | Example |",
        "|---------|------|---------|---------|",
    ]

    for item in commands:
        command = item.get("command", "")
        kind = item.get("kind", "")
        summary = _table_escape(item.get("summary", ""))
        example = item.get("example", "")
        lines.append(f"| `{command}` | `{kind}` | {summary} | `{example}` |")

    lines.append("")
    (_CATALOG_DIR / "index.md").write_text("\n".join(lines), encoding="utf-8")


def _table_escape(value: str) -> str:
    return value.replace("\n", " ").replace("|", "\\|")
