"""
SSE Stream Contract Tests

Verifies that the plugin's SSE parsing code handles all event formats
that the backend can produce. These tests ensure the contract between
netbox-proxbox (plugin) and proxbox-api (backend) is maintained.
"""

from __future__ import annotations

import importlib
import json

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


class TestIterSSEFrames:
    """Test _iter_sse_frames function for SSE parsing."""

    def test_parse_step_event_with_json_data(self, backend_proxy_module):
        """Step events should parse JSON data payloads correctly."""
        bp = backend_proxy_module
        lines = [
            "event: step",
            'data: {"step": "devices", "status": "syncing", "message": "Creating device pve01"}',
            "",
        ]
        frames = list(bp._iter_sse_frames(lines))
        assert len(frames) == 1
        event, data = frames[0]
        assert event == "step"
        assert data["step"] == "devices"
        assert data["status"] == "syncing"
        assert "Creating device pve01" in data["message"]

    def test_parse_multiple_events_separated_by_blank_lines(self, backend_proxy_module):
        """Multiple SSE events should be separated by blank lines."""
        bp = backend_proxy_module
        lines = [
            "event: step",
            'data: {"step": "devices"}',
            "",
            "event: step",
            'data: {"step": "virtual-machines"}',
            "",
            "event: complete",
            'data: {"ok": true}',
            "",
        ]
        frames = list(bp._iter_sse_frames(lines))
        assert len(frames) == 3
        assert frames[0][0] == "step"
        assert frames[0][1]["step"] == "devices"
        assert frames[1][0] == "step"
        assert frames[1][1]["step"] == "virtual-machines"
        assert frames[2][0] == "complete"

    def test_parse_complete_event_with_ok_true(self, backend_proxy_module):
        """Complete events with ok=true should be recognized."""
        bp = backend_proxy_module
        lines = [
            "event: complete",
            'data: {"ok": true, "message": "Sync completed successfully"}',
            "",
        ]
        frames = list(bp._iter_sse_frames(lines))
        assert len(frames) == 1
        event, data = frames[0]
        assert event == "complete"
        assert data["ok"] is True
        assert "Sync completed successfully" in data["message"]

    def test_parse_complete_event_with_ok_false(self, backend_proxy_module):
        """Complete events with ok=false should parse error info."""
        bp = backend_proxy_module
        lines = [
            "event: complete",
            'data: {"ok": false, "message": "Sync failed", "errors": [{"detail": "Connection refused"}]}',
            "",
        ]
        frames = list(bp._iter_sse_frames(lines))
        assert len(frames) == 1
        event, data = frames[0]
        assert event == "complete"
        assert data["ok"] is False
        assert "Sync failed" in data["message"]
        assert len(data["errors"]) == 1
        assert "Connection refused" in data["errors"][0]["detail"]

    def test_parse_error_event(self, backend_proxy_module):
        """Error events should be distinct from complete events."""
        bp = backend_proxy_module
        lines = [
            "event: error",
            'data: {"step": "devices", "status": "failed", "error": "Backend unreachable"}',
            "",
        ]
        frames = list(bp._iter_sse_frames(lines))
        assert len(frames) == 1
        event, data = frames[0]
        assert event == "error"
        assert data["step"] == "devices"
        assert data["status"] == "failed"
        assert "Backend unreachable" in data["error"]

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

    def test_parse_event_with_multiple_data_lines(self, backend_proxy_module):
        """SSE allows multiple data lines that should be joined."""
        bp = backend_proxy_module
        lines = [
            "event: step",
            "data: line one",
            "data: line two",
            "data: line three",
            "",
        ]
        frames = list(bp._iter_sse_frames(lines))
        assert len(frames) == 1
        event, data = frames[0]
        assert event == "step"
        assert data == {"raw": "line one\nline two\nline three"}

    def test_ignore_comment_lines(self, backend_proxy_module):
        """SSE comment lines (starting with :) should be ignored."""
        bp = backend_proxy_module
        lines = [
            ": this is a comment",
            "event: step",
            'data: {"step": "devices"}',
            "",
        ]
        frames = list(bp._iter_sse_frames(lines))
        assert len(frames) == 1
        assert frames[0][0] == "step"

    def test_default_event_name_is_message(self, backend_proxy_module):
        """Events without explicit event name should default to 'message'."""
        bp = backend_proxy_module
        lines = [
            'data: {"step": "devices"}',
            "",
        ]
        frames = list(bp._iter_sse_frames(lines))
        assert len(frames) == 1
        event, data = frames[0]
        assert event == "message"

    def test_handle_none_lines_gracefully(self, backend_proxy_module):
        """None lines in the iterator should be skipped."""
        bp = backend_proxy_module
        lines = [
            "event: step",
            'data: {"step": "devices"}',
            None,
            "",
        ]
        frames = list(bp._iter_sse_frames(lines))
        assert len(frames) == 1

    @pytest.mark.parametrize(
        "event_name,payload",
        [
            (
                "discovery",
                '{"event":"discovery","phase":"devices","count":2,"items":[{"name":"pve1"},{"name":"pve2"}]}',
            ),
            (
                "substep",
                '{"event":"substep","phase":"devices","substep":"ensure_cluster","status":"processing"}',
            ),
            (
                "item_progress",
                '{"event":"item_progress","phase":"devices","status":"completed","progress":{"current":1,"total":2,"percent":50}}',
            ),
            (
                "phase_summary",
                '{"event":"phase_summary","phase":"devices","status":"completed","result":{"created":2,"failed":0}}',
            ),
            (
                "error_detail",
                '{"event":"error_detail","phase":"devices","category":"validation","message":"failed","suggestion":"check role"}',
            ),
        ],
    )
    def test_parse_new_detailed_event_types(
        self, backend_proxy_module, event_name, payload
    ):
        """Parser should preserve new detailed event types emitted by backend."""
        bp = backend_proxy_module
        lines = [f"event: {event_name}", f"data: {payload}", ""]
        frames = list(bp._iter_sse_frames(lines))
        assert len(frames) == 1
        event, data = frames[0]
        assert event == event_name
        assert data["event"] == event_name
        assert data["phase"] == "devices"


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


class TestHTTPTimeoutForSyncPath:
    """Test http_timeout_for_sync_path function."""

    def test_normal_path_returns_default_timeout(self, backend_proxy_module):
        """Normal sync paths should return default timeout."""
        bp = backend_proxy_module
        assert bp.http_timeout_for_sync_path("dcim/devices/create") == 5
        # VM sync paths use extended timeout due to large interface/IP/VLAN sync
        assert (
            bp.http_timeout_for_sync_path("virtualization/virtual-machines/create")
            == (5, 3600)
        )

    def test_backup_path_returns_long_timeout(self, backend_proxy_module):
        """Backup sync path should return long timeout."""
        bp = backend_proxy_module
        timeout = bp.http_timeout_for_sync_path(
            "virtualization/virtual-machines/backups/all/create"
        )
        assert timeout == (5, 3600), f"Expected long timeout for backups, got {timeout}"

    def test_snapshot_path_returns_long_timeout(self, backend_proxy_module):
        """Snapshot sync path should return long timeout."""
        bp = backend_proxy_module
        timeout = bp.http_timeout_for_sync_path(
            "virtualization/virtual-machines/snapshots/all/create"
        )
        assert timeout == (5, 3600), (
            f"Expected long timeout for snapshots, got {timeout}"
        )
