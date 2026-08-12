"""Executable documentation contracts for the semantic MCP bridge."""

from __future__ import annotations

import importlib.util
import math
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from tests.mcp_bridge_examples import MCP_GUIDE_PATH, load_mcp_guide_examples

REPO_ROOT = Path(__file__).resolve().parents[1]
BRIDGE_PATH = REPO_ROOT / "netbox_proxbox" / "api" / "mcp_bridge.py"

EXPECTED_EXAMPLES = {
    "api-root-discovery",
    "plugin-list-tools-input",
    "list-sync-jobs-input",
    "list-sync-jobs-output",
    "schedule-immediate-input",
    "schedule-future-scoped-input",
    "schedule-recurring-input",
    "schedule-sync-output",
    "validation-error-output",
}

_RFC3339_DATE_TIME_RE = re.compile(
    r"^\d{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])"
    r"[Tt](?:[01]\d|2[0-3]):[0-5]\d:(?:[0-5]\d|60)(?:\.\d+)?"
    r"(?:[Zz]|[+-](?:[01]\d|2[0-3]):[0-5]\d)$"
)


def _load_bridge_module():
    spec = importlib.util.spec_from_file_location("_proxbox_mcp_docs", BRIDGE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _matches_json_type(value: object, expected: str) -> bool:
    if expected == "null":
        return value is None
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return (
            isinstance(value, int)
            and not isinstance(value, bool)
            or isinstance(value, float)
            and math.isfinite(value)
            and value.is_integer()
        )
    if expected == "boolean":
        return isinstance(value, bool)
    raise AssertionError(f"Unsupported JSON Schema type in bridge fixture: {expected}")


def _json_values_equal(left: object, right: object) -> bool:
    """Match JSON Schema equality, including integer/number equivalence."""
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        return left == right
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(
            _json_values_equal(a, b) for a, b in zip(left, right, strict=True)
        )
    if isinstance(left, dict) and isinstance(right, dict):
        return set(left) == set(right) and all(
            _json_values_equal(left[key], right[key]) for key in left
        )
    return type(left) is type(right) and left == right


def _assert_schema_accepts(
    value: object, schema: dict[str, Any], path: str = "$"
) -> None:
    """Validate the bridge-v1 JSON Schema subset used by the manifest."""
    if "const" in schema:
        assert value == schema["const"], f"{path} does not match const"

    expected_types = schema.get("type")
    if expected_types is not None:
        if isinstance(expected_types, str):
            expected_types = [expected_types]
        assert any(
            _matches_json_type(value, expected) for expected in expected_types
        ), f"{path} has the wrong JSON type"

    if "enum" in schema:
        assert value in schema["enum"], f"{path} is outside the enum"
    is_json_number = isinstance(value, (int, float)) and not isinstance(value, bool)
    if is_json_number and "minimum" in schema:
        assert value >= schema["minimum"], f"{path} is below minimum"
    if is_json_number and "maximum" in schema:
        assert value <= schema["maximum"], f"{path} is above maximum"
    if isinstance(value, str):
        if "maxLength" in schema:
            assert len(value) <= schema["maxLength"], f"{path} is too long"
        if schema.get("format") == "date-time":
            assert _RFC3339_DATE_TIME_RE.fullmatch(value), (
                f"{path} is not an RFC 3339 date-time"
            )
            normalized = value.replace("t", "T").replace("z", "Z")
            normalized = re.sub(r":60(?=(?:\.\d+)?(?:Z|[+-]))", ":59", normalized)
            datetime.fromisoformat(normalized)
    if isinstance(value, list):
        if "minItems" in schema:
            assert len(value) >= schema["minItems"], f"{path} has too few items"
        if schema.get("uniqueItems"):
            for index, item in enumerate(value):
                assert not any(
                    _json_values_equal(item, earlier) for earlier in value[:index]
                ), f"{path} contains duplicate items"
        item_schema = schema.get("items")
        if item_schema is not None:
            for index, item in enumerate(value):
                _assert_schema_accepts(item, item_schema, f"{path}[{index}]")
    if isinstance(value, dict):
        properties = schema.get("properties", {})
        if "minProperties" in schema:
            assert len(value) >= schema["minProperties"], (
                f"{path} has too few properties"
            )
        if "maxProperties" in schema:
            assert len(value) <= schema["maxProperties"], (
                f"{path} has too many properties"
            )
        missing = set(schema.get("required", [])) - set(value)
        assert not missing, f"{path} is missing required properties: {sorted(missing)}"
        if schema.get("additionalProperties") is False:
            unknown = set(value) - set(properties)
            assert not unknown, f"{path} has unknown properties: {sorted(unknown)}"
        for key, item in value.items():
            if key in properties:
                _assert_schema_accepts(item, properties[key], f"{path}.{key}")


def _assert_schema_rejects(value: object, schema: dict[str, Any]) -> None:
    """Require a mutation to fail the paired SDK-supported schema model."""
    with pytest.raises((AssertionError, ValueError)):
        _assert_schema_accepts(value, schema)


def test_guide_has_the_complete_named_example_set() -> None:
    assert set(load_mcp_guide_examples()) == EXPECTED_EXAMPLES


def test_documented_examples_conform_to_the_generated_manifest() -> None:
    examples = load_mcp_guide_examples()
    manifest = _load_bridge_module().build_mcp_bridge_manifest()
    tools = {tool["name"]: tool for tool in manifest["tools"]}

    assert examples["api-root-discovery"] == {
        "mcp": {
            "schema_version": manifest["schema_version"],
            "manifest": "/api/plugins/proxbox/mcp/",
        }
    }
    assert examples["plugin-list-tools-input"] == {"plugin": "proxbox"}
    _assert_schema_accepts(
        examples["list-sync-jobs-input"]["arguments"],
        tools["list_sync_jobs"]["inputSchema"],
    )
    _assert_schema_accepts(
        examples["list-sync-jobs-output"]["body"],
        tools["list_sync_jobs"]["outputSchema"],
    )
    for name in (
        "schedule-immediate-input",
        "schedule-future-scoped-input",
        "schedule-recurring-input",
    ):
        _assert_schema_accepts(
            examples[name]["arguments"],
            tools["schedule_sync"]["inputSchema"],
            path=f"{name}.arguments",
        )
    _assert_schema_accepts(
        examples["schedule-sync-output"]["body"],
        tools["schedule_sync"]["outputSchema"],
    )
    assert set(examples["validation-error-output"]) == {"errors"}


def test_sdk_supported_schema_subset_rejects_bridge_argument_mutations() -> None:
    bridge = _load_bridge_module()
    schedule_schema = next(
        tool
        for tool in bridge.build_mcp_bridge_manifest()["tools"]
        if tool["name"] == "schedule_sync"
    )["inputSchema"]
    base = {"sync_stages": ["virtual-machines"]}
    mutations = (
        {"sync_stages": ["all"]},
        {"sync_stages": ["storage", "storage"]},
        {**base, "netbox_endpoint_ids": [3]},
        {**base, "interval_value": 2, "interval_unit": "hours"},
        {**base, "recurrence": {}},
        {**base, "recurrence": {"minutes": 1, "hours": 1}},
        {**base, "recurrence": {"months": 1}},
        {**base, "recurrence": {"hours": True}},
        {**base, "recurrence": {"hours": 1.5}},
        {**base, "proxmox_endpoint_ids": [7.5]},
        {**base, "proxmox_endpoint_ids": [7, 7.0]},
        {
            **base,
            "proxmox_endpoint_ids": [bridge.MAX_POSITIVE_SIGNED_64_BIT_INTEGER + 1],
        },
        {
            **base,
            "recurrence": {"weeks": bridge.INTERVAL_VALUE_MAXIMUMS["weeks"] + 1},
        },
        {**base, "schedule_at": "2099-01-15T03:00:00"},
        {**base, "schedule_at": "2099-02-30T03:00:00Z"},
        {**base, "schedule_at": "2099-01-15T03:00:00+24:00"},
        {**base, "schedule_at": True},
    )
    for mutation in mutations:
        _assert_schema_rejects(mutation, schedule_schema)

    _assert_schema_accepts(
        {**base, "schedule_at": "2099-12-31T23:59:60Z"}, schedule_schema
    )
    _assert_schema_accepts(
        {**base, "recurrence": {"hours": 6.0}, "proxmox_endpoint_ids": [7.0]},
        schedule_schema,
    )


def test_llm_and_project_docs_link_the_authoritative_guide() -> None:
    expected_links = {
        "README.md": "api/semantic-mcp-bridge/",
        "AGENTS.md": "docs/api/semantic-mcp-bridge.md",
        "CLAUDE.md": "docs/api/semantic-mcp-bridge.md",
        "netbox_proxbox/CLAUDE.md": "docs/api/semantic-mcp-bridge.md",
        "netbox_proxbox/api/CLAUDE.md": "docs/api/semantic-mcp-bridge.md",
        "docs/api/index.md": "semantic-mcp-bridge.md",
        "docs/features/api-integration.md": "semantic-mcp-bridge.md",
        "docs/features/scheduled-sync.md": "semantic-mcp-bridge.md",
        "docs/developer/authentication.md": "semantic-mcp-bridge.md",
        "mkdocs.yml": "api/semantic-mcp-bridge.md",
    }
    for relative_path, expected in expected_links.items():
        content = (REPO_ROOT / relative_path).read_text()
        assert expected in content, f"{relative_path} must link the MCP guide"


def test_llm_context_states_the_actionable_safety_contract() -> None:
    llm_context = (REPO_ROOT / "llms.txt").read_text()
    required_phrases = (
        "## Semantic MCP Bridge (bridge v1)",
        "server-wide mutation gating",
        "core.add_job",
        "destructive and non-idempotent",
        "does not delete Proxmox guests or infrastructure",
        "Unknown properties are rejected",
        "Never send `[]` as a placeholder",
        "Never auto-retry",
        "generic descriptor protocol",
        "signed-64-bit positive",
        "endpoint/configuration preflight",
        'internal `["all"]` identity',
        "`plugin_list_tools`",
        "`plugin_call_tool`",
        "tests/fixtures/proxbox_bridge_v1.json",
        "tests/fixtures/netbox_sdk_bridge_activation.json",
        "No released SDK identity is currently activated",
        "9007199254740991",
        "docs/api/semantic-mcp-bridge.md",
    )
    for phrase in required_phrases:
        assert phrase in llm_context


def test_guide_covers_operations_compatibility_and_verification() -> None:
    guide = MCP_GUIDE_PATH.read_text()
    required_sections = (
        "## Architecture",
        "## Discovery",
        "## Authentication and authorization",
        "## Tool catalog",
        "## Safe agent interaction sequence",
        "## Errors and fail-closed behavior",
        "## Trust boundary and security notes",
        "## Compatibility and versioning",
        "## Verification and traceability",
        "## Troubleshooting",
    )
    for section in required_sections:
        assert section in guide
    for phrase in (
        "descriptor protocol:",
        "not a second SDK authority",
        "9223372036854775807",
        "9007199254740991",
        "mathematically integral JSON number",
        "Stage selection and invariant reconciliation",
        "Consumer activation is currently blocked",
        "--expected-module-origin",
        "tests/fixtures/netbox_sdk_bridge_activation.json",
        "tests/validate_paired_netbox_sdk_bridge.py",
    ):
        assert phrase in guide
