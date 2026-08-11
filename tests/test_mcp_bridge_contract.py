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


def test_generated_manifest_matches_canonical_sdk_compatibility_fixture() -> None:
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
    assert schedule_schema["required"] == ["sync_types"]
    assert set(schedule_schema["properties"]) == {
        "sync_types",
        "job_name",
        "schedule_at",
        "interval_value",
        "interval_unit",
        "proxmox_endpoint_ids",
        "netbox_endpoint_ids",
    }
    assert schedule_schema["properties"]["interval_unit"]["enum"] == [
        *bridge.INTERVAL_UNIT_VALUES,
        None,
    ]
    assert schedule_schema["properties"]["sync_types"]["items"]["enum"] == (
        bridge.SYNC_TYPE_VALUES
    )
    assert schedule_schema["properties"]["proxmox_endpoint_ids"]["minItems"] == 1
    assert schedule_schema["properties"]["netbox_endpoint_ids"]["minItems"] == 1
    assert (
        '"all" sync type must be selected by itself'
        in tools["schedule_sync"]["description"]
    )
    assert (
        "may delete stale NetBox inventory records"
        in (tools["schedule_sync"]["description"])
    )
    assert (
        "Recurrence value and unit must be set together"
        in (tools["schedule_sync"]["description"])
    )
    assert (
        "Explicit endpoint scopes must contain at least one ID"
        in (tools["schedule_sync"]["description"])
    )


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
    assert 'response.data["mcp"]' in views_source
    assert '"schema_version": "1"' in views_source
    assert '"manifest": f"{base}/mcp/"' in views_source
    assert (
        'path("mcp/", PluginMCPManifestAPIView.as_view(), name="api-mcp-manifest")'
        in ("".join(urls_source.splitlines()))
    )


def test_bridge_does_not_embed_fastmcp_or_duplicate_credentials() -> None:
    source = BRIDGE_PATH.read_text()

    assert "FastMCP" not in source
    assert "netbox_sdk" not in source
    assert "token" not in source.casefold()
    assert "credential" not in source.casefold()
