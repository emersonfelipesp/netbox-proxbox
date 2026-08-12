"""Load named JSON examples from the semantic MCP bridge guide."""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MCP_GUIDE_PATH = REPO_ROOT / "docs" / "api" / "semantic-mcp-bridge.md"
_EXAMPLE_PATTERN = re.compile(
    r"<!-- mcp-example:([a-z0-9-]+) -->\s*```json\s*(.*?)\s*```",
    re.DOTALL,
)


def load_mcp_guide_examples() -> dict[str, object]:
    """Return every uniquely named JSON block from the MCP guide."""
    matches = _EXAMPLE_PATTERN.findall(MCP_GUIDE_PATH.read_text())
    examples: dict[str, object] = {}
    for name, raw_json in matches:
        if name in examples:
            raise AssertionError(f"Duplicate MCP guide example name: {name}")
        examples[name] = json.loads(raw_json)
    return examples
