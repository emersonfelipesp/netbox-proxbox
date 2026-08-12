"""Contracts for the netbox-sdk semantic plugin bridge advertisement."""

from __future__ import annotations

import ast
import importlib.util
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BRIDGE_PATH = REPO_ROOT / "netbox_proxbox" / "api" / "mcp_bridge.py"
VIEWS_PATH = REPO_ROOT / "netbox_proxbox" / "api" / "views.py"
URLS_PATH = REPO_ROOT / "netbox_proxbox" / "api" / "urls.py"
CANONICAL_FIXTURE_PATH = REPO_ROOT / "tests" / "fixtures" / "proxbox_bridge_v1.json"
SERIALIZERS_PATH = (
    REPO_ROOT / "netbox_proxbox" / "api" / "serializers" / "resource_views.py"
)
PAIRED_SDK_GATE_PATH = REPO_ROOT / "tests" / "validate_paired_netbox_sdk_bridge.py"
PAIRED_SDK_ACTIVATION_PATH = (
    REPO_ROOT / "tests" / "fixtures" / "netbox_sdk_bridge_activation.json"
)
CI_WORKFLOW_PATHS = (
    REPO_ROOT / ".gitea" / "workflows" / "ci.yml",
    REPO_ROOT / ".github" / "workflows" / "ci.yml",
    REPO_ROOT / ".github" / "workflows" / "django-tests.yml",
)


def _load_bridge_module():
    spec = importlib.util.spec_from_file_location("_proxbox_mcp_bridge", BRIDGE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_manifest_uses_bridge_v1_and_fixed_existing_sync_endpoint() -> None:
    manifest = _load_bridge_module().build_mcp_bridge_manifest()

    assert manifest["schema_version"] == "1"
    assert manifest["plugin"] == "proxbox"
    assert [tool["name"] for tool in manifest["tools"]] == [
        "list_sync_jobs",
        "schedule_sync",
    ]
    assert {tool["path"] for tool in manifest["tools"]} == {"sync/schedule/"}
    assert [tool["method"] for tool in manifest["tools"]] == ["GET", "POST"]
    assert [tool["effect"] for tool in manifest["tools"]] == [
        "read",
        "destructive",
    ]


def test_generated_manifest_matches_proxbox_owned_contract_snapshot() -> None:
    fixture = json.loads(CANONICAL_FIXTURE_PATH.read_text())

    assert _load_bridge_module().build_mcp_bridge_manifest() == fixture


def test_manifest_inputs_are_strict_and_schedule_schema_matches_existing_serializer() -> (
    None
):
    bridge = _load_bridge_module()
    manifest = bridge.build_mcp_bridge_manifest()
    tools = {tool["name"]: tool for tool in manifest["tools"]}

    assert tools["list_sync_jobs"]["inputSchema"] == {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }
    schedule_schema = tools["schedule_sync"]["inputSchema"]
    assert schedule_schema["additionalProperties"] is False
    assert schedule_schema["required"] == ["sync_stages"]
    assert set(schedule_schema["properties"]) == {
        "sync_stages",
        "job_name",
        "schedule_at",
        "recurrence",
        "proxmox_endpoint_ids",
    }
    assert schedule_schema["properties"]["sync_stages"]["items"]["enum"] == (
        bridge.SYNC_TYPE_VALUES
    )
    assert len(bridge.SYNC_TYPE_VALUES) == 13
    assert "all" not in bridge.SYNC_TYPE_VALUES
    recurrence = schedule_schema["properties"]["recurrence"]
    assert recurrence["minProperties"] == recurrence["maxProperties"] == 1
    assert recurrence["additionalProperties"] is False
    assert set(recurrence["properties"]) == set(bridge.INTERVAL_UNIT_VALUES)
    for unit, unit_schema in recurrence["properties"].items():
        assert unit_schema["minimum"] == 1
        assert unit_schema["maximum"] == bridge.INTERVAL_VALUE_MAXIMUMS[unit]
        assert (
            unit_schema["maximum"] * bridge.INTERVAL_MINUTE_MULTIPLIERS[unit]
            <= bridge.MAX_PERSISTED_INTERVAL_MINUTES
        )
    assert schedule_schema["properties"]["proxmox_endpoint_ids"]["minItems"] == 1
    endpoint_item = schedule_schema["properties"]["proxmox_endpoint_ids"]["items"]
    assert endpoint_item == {
        "type": "integer",
        "minimum": 1,
        "maximum": bridge.MAX_POSITIVE_SIGNED_64_BIT_INTEGER,
        "description": (
            "Use an integer JSON literal for IDs above "
            f"{bridge.MAX_EXACT_JSON_FLOAT_INTEGER}; decimal-form numbers are "
            "accepted only while exactly representable by IEEE 754."
        ),
    }
    assert (
        "full sync is the exact complete stage list"
        in tools["schedule_sync"]["description"]
    )
    assert (
        "may delete stale NetBox inventory records"
        in (tools["schedule_sync"]["description"])
    )
    assert (
        "Recurrence contains exactly one bounded unit/value member"
        in (tools["schedule_sync"]["description"])
    )
    assert (
        "explicit Proxmox endpoint scope must contain at least one ID"
        in (tools["schedule_sync"]["description"])
    )
    for invariant_pass in ("cluster/node", "firewall", "datacenter", "VM-template"):
        assert invariant_pass in tools["schedule_sync"]["description"]


def test_manifest_stays_inside_the_paired_sdk_schema_subset() -> None:
    """The consumer rejects these keywords instead of partially evaluating them."""
    encoded = json.dumps(_load_bridge_module().build_mcp_bridge_manifest())
    for unsupported in (
        '"$ref"',
        '"allOf"',
        '"anyOf"',
        '"if"',
        '"not"',
        '"oneOf"',
        '"pattern"',
    ):
        assert unsupported not in encoded


def test_manifest_annotations_keep_read_and_write_semantics_explicit() -> None:
    manifest = _load_bridge_module().build_mcp_bridge_manifest()
    tools = {tool["name"]: tool for tool in manifest["tools"]}

    assert tools["list_sync_jobs"]["annotations"] == {
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
    assert tools["schedule_sync"]["annotations"] == {
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": True,
    }


def test_manifest_api_view_and_root_advertisement_are_registered() -> None:
    views_source = VIEWS_PATH.read_text()
    urls_source = URLS_PATH.read_text()
    views_module = ast.parse(views_source, filename=str(VIEWS_PATH))

    manifest_view = next(
        node
        for node in views_module.body
        if isinstance(node, ast.ClassDef) and node.name == "PluginMCPManifestAPIView"
    )
    assert any(
        isinstance(base, ast.Name) and base.id == "APIView"
        for base in manifest_view.bases
    )
    assert "if mcp_bridge_is_active():" in views_source
    assert 'response.data["mcp"]' in views_source
    assert '"schema_version": "1"' in views_source
    assert '"manifest": f"{base}/mcp/"' in views_source
    assert "mcp_bridge_activation_record()" in views_source
    assert '"The semantic MCP consumer bridge is not activated."' in views_source
    assert (
        'path("mcp/", PluginMCPManifestAPIView.as_view(), name="api-mcp-manifest")'
        in ("".join(urls_source.splitlines()))
    )


def test_bridge_does_not_embed_fastmcp_or_duplicate_credentials() -> None:
    source = BRIDGE_PATH.read_text()

    assert "FastMCP" not in source
    assert "import netbox_sdk" not in source
    assert "from netbox_sdk" not in source
    assert "token" not in source.casefold()
    assert "credential" not in source.casefold()


def test_explicit_cross_repository_gate_imports_the_real_sdk_model() -> None:
    source = PAIRED_SDK_GATE_PATH.read_text()

    assert 'importlib.import_module("netbox_sdk.plugin_bridge")' in source
    assert "manifest_model.model_validate" in source
    assert "bridge_module.validate_plugin_tool_arguments" in source
    assert "--sdk-root" in source
    assert "--expected-commit" in source
    assert "--expected-version" in source
    assert "--expected-module-origin" in source
    assert "module_file" in source
    assert "_sdk_git_commit" in source
    assert "9007199254740992.0" not in source
    assert "9_007_199_254_740_992.0" in source
    assert '"9999-12-31T23:59:60Z"' in source
    assert '"9999-12-31T23:59:59-23:59"' in source
    assert "pytest.importorskip" not in source


def test_paired_sdk_ci_activation_remains_fail_closed_until_exact_release() -> None:
    bridge = _load_bridge_module()
    activation = json.loads(PAIRED_SDK_ACTIVATION_PATH.read_text())
    assert activation == {
        "schema_version": 1,
        "state": "blocked",
        "expected_version": None,
        "expected_commit": None,
        "module_origin": "netbox_sdk/plugin_bridge.py",
        "required_contracts": [
            "lossless-json-integer-identity",
            "bounded-rfc3339-normalization",
        ],
        "reason": (
            "No released netbox-sdk version has passed the immutable paired bridge "
            "gate yet."
        ),
    }
    assert bridge.mcp_bridge_activation_record() == activation
    assert bridge.mcp_bridge_is_active() is False
    workflows = "\n".join(path.read_text() for path in CI_WORKFLOW_PATHS)
    assert "validate_paired_netbox_sdk_bridge.py" not in workflows


def test_sdk_activation_requires_exactly_one_complete_immutable_identity() -> None:
    bridge = _load_bridge_module()
    bridge.MCP_BRIDGE_ACTIVATION_STATE = "active"

    bridge.MCP_BRIDGE_EXPECTED_SDK_VERSION = "1.2.3"
    assert bridge.mcp_bridge_is_active() is True

    bridge.MCP_BRIDGE_EXPECTED_SDK_COMMIT = "a" * 40
    assert bridge.mcp_bridge_is_active() is False

    bridge.MCP_BRIDGE_EXPECTED_SDK_VERSION = None
    assert bridge.mcp_bridge_is_active() is True

    bridge.MCP_BRIDGE_EXPECTED_SDK_COMMIT = "A" * 40
    assert bridge.mcp_bridge_is_active() is False

    bridge.MCP_BRIDGE_EXPECTED_SDK_COMMIT = "a" * 40
    bridge.MCP_BRIDGE_EXPECTED_MODULE_ORIGIN = "another/module.py"
    assert bridge.mcp_bridge_is_active() is False


def test_runtime_serializer_declares_every_strict_bridge_v1_constraint() -> None:
    source = SERIALIZERS_PATH.read_text()

    assert "max_length=200" in source
    assert source.count("max_value=MAX_POSITIVE_SIGNED_64_BIT_INTEGER") == 2
    assert "math.isfinite(data)" in source
    assert "data.is_integer()" in source
    assert "isinstance(data, Decimal)" in source
    assert source.count("abs(data) > MAX_EXACT_JSON_FLOAT_INTEGER") == 2
    assert "interval_value = _StrictJSONIntegerField(" in source
    assert "ScheduleSyncRecurrenceSerializer" in source
    assert "MAX_PERSISTED_INTERVAL_MINUTES" in source
    assert "_StrictRFC3339DateTimeField" in source
    assert "job_name = _StrictJSONStringField(" in source
    assert source.count("min_length=1") >= 2
    assert 'errors[field_name] = ["Unknown field."]' in source
    assert 'errors[field_name] = ["Duplicate values are not allowed."]' in source
    assert "except OverflowError:" in source
    assert "[SyncTypeChoices.ALL]" in source
