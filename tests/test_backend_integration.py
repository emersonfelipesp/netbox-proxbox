"""
Backend Integration Tests

Tests that verify the plugin correctly handles responses from the proxbox-api backend.
These tests mock the backend responses and verify the plugin handles all expected
HTTP status codes, error formats, and query parameter passing.
"""

from __future__ import annotations

import importlib
import importlib.util
import sys
import types
from pathlib import Path

import pytest


@pytest.fixture
def backend_proxy_module(monkeypatch):
    """Load backend proxy helpers with the minimum NetBox stubs."""
    repo_root = Path(__file__).resolve().parents[1]

    netbox_module = types.ModuleType("netbox")
    netbox_plugins = types.ModuleType("netbox.plugins")
    netbox_plugins.PluginConfig = type("PluginConfig", (), {})
    monkeypatch.setitem(sys.modules, "netbox", netbox_module)
    monkeypatch.setitem(sys.modules, "netbox.plugins", netbox_plugins)

    nbp_root = types.ModuleType("netbox_proxbox")
    nbp_root.__path__ = [str(repo_root / "netbox_proxbox")]
    monkeypatch.setitem(sys.modules, "netbox_proxbox", nbp_root)

    nbp_views = types.ModuleType("netbox_proxbox.views")
    nbp_views.__path__ = [str(repo_root / "netbox_proxbox" / "views")]
    monkeypatch.setitem(sys.modules, "netbox_proxbox.views", nbp_views)

    nbp_schemas = types.ModuleType("netbox_proxbox.schemas")
    nbp_schemas.__path__ = [str(repo_root / "netbox_proxbox" / "schemas")]
    monkeypatch.setitem(sys.modules, "netbox_proxbox.schemas", nbp_schemas)

    nbp_services = types.ModuleType("netbox_proxbox.services")
    nbp_services.__path__ = [str(repo_root / "netbox_proxbox" / "services")]
    monkeypatch.setitem(sys.modules, "netbox_proxbox.services", nbp_services)

    models_stub = types.ModuleType("netbox_proxbox.models")
    models_stub.FastAPIEndpoint = type("FastAPIEndpoint", (), {})
    monkeypatch.setitem(sys.modules, "netbox_proxbox.models", models_stub)

    sys.modules.pop("netbox_proxbox.services.backend_proxy", None)
    sys.modules.pop("netbox_proxbox.utils", None)
    sys.modules.pop("netbox_proxbox.views.error_utils", None)
    sys.modules.pop("netbox_proxbox.schemas.backend_proxy", None)
    sys.modules.pop("netbox_proxbox.schemas._base", None)

    return importlib.import_module("netbox_proxbox.services.backend_proxy")


class TestHTTPTimeoutForSyncPath:
    """Test http_timeout_for_sync_path function."""

    def test_normal_path_returns_default_timeout(self, backend_proxy_module):
        """Normal sync paths should return default timeout."""
        bp = backend_proxy_module
        assert bp.http_timeout_for_sync_path("dcim/devices/create") == 5

    def test_vm_sync_path_returns_long_timeout(self, backend_proxy_module):
        """VM sync paths use extended timeout due to large interface/IP/VLAN sync."""
        bp = backend_proxy_module
        assert (
            bp.http_timeout_for_sync_path("virtualization/virtual-machines/create")
            == (5, 3600)
        )

    def test_backup_path_returns_long_timeout(self, backend_proxy_module):
        """Backup sync path should return long timeout (covered by VM marker)."""
        bp = backend_proxy_module
        timeout = bp.http_timeout_for_sync_path(
            "virtualization/virtual-machines/backups/all/create"
        )
        assert timeout == (5, 3600)

    def test_snapshot_path_returns_long_timeout(self, backend_proxy_module):
        """Snapshot sync path should return long timeout (covered by VM marker)."""
        bp = backend_proxy_module
        timeout = bp.http_timeout_for_sync_path(
            "virtualization/virtual-machines/snapshots/all/create"
        )
        assert timeout == (5, 3600)

    def test_full_update_path_returns_long_timeout(self, backend_proxy_module):
        """Full-update sync path should return long timeout."""
        bp = backend_proxy_module
        timeout = bp.http_timeout_for_sync_path("full-update")
        assert timeout == (5, 3600)


class TestSSEErrorFrames:
    """Test sse_error_frames generator for error handling."""

    def test_error_frames_format(self, backend_proxy_module):
        """Error frames should produce properly formatted SSE lines."""
        bp = backend_proxy_module
        lines = list(bp.sse_error_frames("Connection refused"))
        assert len(lines) == 4
        assert lines[0] == "event: error\n"
        assert lines[2] == "event: complete\n"

    def test_error_frames_contain_json_data(self, backend_proxy_module):
        """Error frame data should be valid JSON."""
        import json

        bp = backend_proxy_module
        lines = list(bp.sse_error_frames("Test error", final_message="Test failure"))
        error_line = lines[1]
        assert error_line.startswith("data: ")
        error_json = error_line[6:].strip()
        error_data = json.loads(error_json)
        assert error_data["step"] == "stream"
        assert error_data["status"] == "failed"
        assert "Test error" in error_data["error"]

        complete_line = lines[3]
        assert complete_line.startswith("data: ")
        complete_json = complete_line[6:].strip()
        complete_data = json.loads(complete_json)
        assert complete_data["ok"] is False
        assert "Test failure" in complete_data["message"]


class TestRequestBackendResource:
    """Test request_backend_resource for HTTPS and verification handling."""

    def test_https_requests_use_configured_scheme_and_verify_ssl(
        self,
        backend_proxy_module,
        monkeypatch,
    ):
        bp = backend_proxy_module
        calls = []

        class _Response:
            def __init__(self):
                self.status_code = 200

            def raise_for_status(self):
                return None

            def json(self):
                return {"queued": True}

        def fake_get(url, **kwargs):
            calls.append(
                {
                    "url": url,
                    "verify": kwargs.get("verify"),
                    "stream": kwargs.get("stream"),
                    "timeout": kwargs.get("timeout"),
                }
            )
            return _Response()

        monkeypatch.setattr(bp.requests, "get", fake_get)

        context = bp.BackendRequestContext(
            http_url="https://proxbox.local:8800",
            ip_address_url="https://10.0.0.5:8800",
            verify_ssl=True,
            headers={"Authorization": "Bearer backend-token"},
        )

        payload, status = bp.request_backend_resource(context, "proxmox/version")

        assert status == 202
        assert calls == [
            {
                "url": "https://proxbox.local:8800/proxmox/version",
                "verify": True,
                "stream": None,
                "timeout": 5,
            }
        ]
        assert payload["requested_urls"] == [
            "https://proxbox.local:8800/proxmox/version"
        ]


def test_proxbox_config_ready_skips_runtime_registration_without_pydantic(
    monkeypatch, caplog
):
    repo_root = Path(__file__).resolve().parents[1]

    netbox_module = types.ModuleType("netbox")
    netbox_plugins = types.ModuleType("netbox.plugins")

    class PluginConfig:
        def ready(self):
            return None

    netbox_plugins.PluginConfig = PluginConfig
    monkeypatch.setitem(sys.modules, "netbox", netbox_module)
    monkeypatch.setitem(sys.modules, "netbox.plugins", netbox_plugins)

    original_find_spec = importlib.util.find_spec

    def fake_find_spec(name, package=None):
        if name in {"pydantic", "pydantic_core"}:
            return None
        return original_find_spec(name, package)

    monkeypatch.setattr(importlib.util, "find_spec", fake_find_spec)

    sys.modules.pop("netbox_proxbox", None)
    spec = importlib.util.spec_from_file_location(
        "netbox_proxbox", repo_root / "netbox_proxbox" / "__init__.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["netbox_proxbox"] = module
    spec.loader.exec_module(module)

    with caplog.at_level("WARNING"):
        module.ProxboxConfig().ready()

    assert "Skipping ProxBox job and view registration" in caplog.text


class TestIterSSEFrames:
    """Test _iter_sse_frames function for SSE parsing."""

    def test_parse_step_event_with_json_data(self, backend_proxy_module):
        """Step events should parse JSON data payloads correctly."""
        bp = backend_proxy_module
        lines = [
            "event: step",
            'data: {"step": "devices", "status": "syncing"}',
            "",
        ]
        frames = list(bp._iter_sse_frames(lines))
        assert len(frames) == 1
        event, data = frames[0]
        assert event == "step"
        assert data["step"] == "devices"

    def test_handle_malformed_json_gracefully(self, backend_proxy_module):
        """Malformed JSON in data lines should not crash the parser."""
        bp = backend_proxy_module
        lines = [
            "event: step",
            "data: {invalid json}",
            "",
        ]
        frames = list(bp._iter_sse_frames(lines))
        assert len(frames) == 1
        event, data = frames[0]
        assert event == "step"
        assert "raw" in data
        assert "{invalid json}" in data["raw"]
