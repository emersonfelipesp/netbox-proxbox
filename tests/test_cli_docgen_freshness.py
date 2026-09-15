"""Semantic freshness checks for generated Proxbox CLI documentation."""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

import pytest

for module_name in ("click", "typer", "rich"):
    pytest.importorskip(module_name)

from proxbox_cli.docgen.engine import CaptureEngine  # noqa: E402
from proxbox_cli.docgen.specs import load_specs  # noqa: E402
from proxbox_cli.docgen_capture import generate_command_capture_docs  # noqa: E402
from docs import hooks  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[1]
_TRACKED_ROOT = _REPO_ROOT / "docs" / "generated"
_TRACKED_REFERENCE = _REPO_ROOT / "docs" / "reference" / "proxbox-cli"
_VOLATILE_KEYS = {"elapsed_seconds", "meta"}
_ANSI_ESCAPE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
GeneratedDocs = tuple[Path, Path, Path]


def _semantic_json(value: Any) -> Any:
    """Remove environment and duration metadata from generated JSON."""
    if isinstance(value, dict):
        return {
            key: _semantic_json(item)
            for key, item in value.items()
            if key not in _VOLATILE_KEYS
        }
    if isinstance(value, list):
        return [_semantic_json(item) for item in value]
    if isinstance(value, str):
        return _ANSI_ESCAPE.sub("", value)
    return value


def _load_semantic_json(path: Path) -> Any:
    """Load one generated JSON artifact without volatile fields."""
    return _semantic_json(json.loads(path.read_text(encoding="utf-8")))


def _load_semantic_markdown(path: Path) -> str:
    """Load generated Markdown without environment metadata."""
    volatile = (
        "- Generated at:",
        "- Python:",
        "- Platform:",
        "Generated:",
        "    Last updated:",
    )
    text = _ANSI_ESCAPE.sub("", path.read_text(encoding="utf-8"))
    return "\n".join(
        line for line in text.splitlines() if not line.startswith(volatile)
    )


def _capture_root_help(
    monkeypatch: pytest.MonkeyPatch, environment: dict[str, str]
) -> bytes:
    """Capture root help under one simulated parent terminal environment."""
    for name in ("TERM", "COLUMNS", "NO_COLOR", "FORCE_COLOR"):
        monkeypatch.delenv(name, raising=False)
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    return CaptureEngine().capture(load_specs()[0]).stdout.encode()


def _generate_into(directory: Path) -> GeneratedDocs:
    """Generate all primary CLI documentation artifacts in a temporary tree."""
    output = directory / "proxbox-cli-command-capture.md"
    raw_dir = directory / "proxbox-cli" / "raw"
    catalog = directory / "proxbox-cli" / "catalog.json"
    assert (
        generate_command_capture_docs(
            output=output, raw_dir=raw_dir, catalog_output=catalog
        )
        == 0
    )
    return output, raw_dir, catalog


@pytest.fixture(scope="module")
def generated_docs(tmp_path_factory: pytest.TempPathFactory) -> GeneratedDocs:
    """Generate one shared temporary documentation tree."""
    return _generate_into(tmp_path_factory.mktemp("cli-docgen"))


def _build_derived_docs(
    monkeypatch: pytest.MonkeyPatch, generated: GeneratedDocs
) -> tuple[Path, Path]:
    """Render derived reference pages from temporary primary artifacts."""
    output, raw_dir, catalog = generated
    root = output.parent / "reference" / "proxbox-cli"
    monkeypatch.setattr(hooks, "_INDEX_FILE", raw_dir / "index.json")
    monkeypatch.setattr(hooks, "_CATALOG_FILE", catalog)
    monkeypatch.setattr(hooks, "_EXAMPLES_DIR", root / "command-examples")
    monkeypatch.setattr(hooks, "_CATALOG_DIR", root / "command-catalog")
    hooks._build_command_examples()
    hooks._build_command_catalog()
    return hooks._EXAMPLES_DIR, hooks._CATALOG_DIR


def _assert_markdown_directories_equal(generated: Path, tracked: Path) -> None:
    """Compare generated Markdown directory contents without volatile lines."""
    generated_files = {path.name for path in generated.glob("*.md")}
    assert generated_files == {path.name for path in tracked.glob("*.md")}
    for name in generated_files:
        assert _load_semantic_markdown(generated / name) == _load_semantic_markdown(
            tracked / name
        )


def test_cli_docs_are_semantically_current(generated_docs: GeneratedDocs) -> None:
    output, raw_dir, catalog = generated_docs
    tracked_raw = _TRACKED_ROOT / "proxbox-cli" / "raw"
    assert _load_semantic_markdown(output) == _load_semantic_markdown(
        _TRACKED_ROOT / output.name
    )
    assert _load_semantic_json(catalog) == _load_semantic_json(
        _TRACKED_ROOT / "proxbox-cli" / "catalog.json"
    )
    assert {path.name for path in raw_dir.glob("*.json")} == {
        path.name for path in tracked_raw.glob("*.json")
    }
    for path in raw_dir.glob("*.json"):
        assert _load_semantic_json(path) == _load_semantic_json(tracked_raw / path.name)


def test_cli_derived_pages_are_semantically_current(
    generated_docs: GeneratedDocs, monkeypatch: pytest.MonkeyPatch
) -> None:
    generated_examples, generated_catalog = _build_derived_docs(
        monkeypatch, generated_docs
    )
    _assert_markdown_directories_equal(
        generated_examples, _TRACKED_REFERENCE / "command-examples"
    )
    _assert_markdown_directories_equal(
        generated_catalog, _TRACKED_REFERENCE / "command-catalog"
    )


def test_cli_capture_is_identical_across_terminal_environments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configured = {
        "TERM": "xterm-256color",
        "COLUMNS": "200",
        "NO_COLOR": "1",
        "FORCE_COLOR": "1",
    }
    with monkeypatch.context() as first:
        expected = _capture_root_help(first, configured)
    with monkeypatch.context() as second:
        actual = _capture_root_help(second, {})
    assert actual == expected
    assert b"\x1b[" not in actual
