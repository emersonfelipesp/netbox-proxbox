"""
Backend Integration Tests

Tests that verify the plugin correctly handles responses from the proxbox-api backend.
These tests mock the backend responses and verify the plugin handles all expected
HTTP status codes, error formats, and query parameter passing.
"""

from __future__ import annotations

import importlib

import pytest

from tests.conftest import load_plugin_module


@pytest.fixture
def backend_proxy_module(monkeypatch, fastapi_endpoint):
    """Load Django/NetBox stubs then import ``backend_proxy``."""
    load_plugin_module(
        "netbox_proxbox.views.sync",
        monkeypatch=monkeypatch,
        fastapi_endpoint=fastapi_endpoint,
    )
    return importlib.import_module("netbox_proxbox.services.backend_proxy")


class TestHTTPTimeoutForSyncPath:
    """Test http_timeout_for_sync_path function."""

    def test_normal_path_returns_default_timeout(self, backend_proxy_module):
        """Normal sync paths should return default timeout."""
        bp = backend_proxy_module
        assert bp.http_timeout_for_sync_path("dcim/devices/create") == 5
        assert (
            bp.http_timeout_for_sync_path("virtualization/virtual-machines/create") == 5
        )

    def test_backup_path_returns_long_timeout(self, backend_proxy_module):
        """Backup sync path should return long timeout."""
        bp = backend_proxy_module
        timeout = bp.http_timeout_for_sync_path(
            "virtualization/virtual-machines/backups/all/create"
        )
        assert timeout == (5, 3600)

    def test_snapshot_path_returns_long_timeout(self, backend_proxy_module):
        """Snapshot sync path should return long timeout."""
        bp = backend_proxy_module
        timeout = bp.http_timeout_for_sync_path(
            "virtualization/virtual-machines/snapshots/all/create"
        )
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
