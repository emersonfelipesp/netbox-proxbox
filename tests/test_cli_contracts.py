"""Tests for test_cli_contracts."""

from __future__ import annotations

import types

import pytest

for module_name in ("click", "typer", "rich"):
    pytest.importorskip(module_name)

virtualization = pytest.importorskip("proxbox_cli.commands.virtualization")
proxmox_endpoints = pytest.importorskip("proxbox_cli.commands.proxmox_endpoints")


def test_backups_sync_all_uses_backend_query_name_for_delete_stale(monkeypatch):
    calls: list[tuple[str, dict | None]] = []

    class FakeClient:
        async def get(self, path: str, query: dict | None = None):
            calls.append((path, query))
            return types.SimpleNamespace(
                status=200, is_ok=lambda: True, json=lambda: {}
            )

    monkeypatch.setattr(virtualization, "_get_client", lambda: FakeClient())
    monkeypatch.setattr(virtualization, "print_response", lambda *args, **kwargs: None)

    virtualization.vms_backups_sync_all(delete_stale=True)

    assert calls == [
        (
            "/virtualization/virtual-machines/backups/all/create",
            {"delete_nonexistent_backup": "true"},
        )
    ]


def test_viewer_generate_sends_typed_query_parameters(monkeypatch):
    calls: list[tuple[str, dict | None]] = []

    class FakeClient:
        async def post(self, path: str, *, query: dict | None = None):
            calls.append((path, query))
            return types.SimpleNamespace(
                status=200, is_ok=lambda: True, json=lambda: {}
            )

    monkeypatch.setattr(proxmox_endpoints, "_get_client", lambda: FakeClient())
    monkeypatch.setattr(
        proxmox_endpoints, "print_response", lambda *args, **kwargs: None
    )

    proxmox_endpoints.viewer_generate(
        persist=False,
        workers=4,
        retry_count=3,
        retry_backoff=0.5,
        checkpoint_every=25,
        source_url="https://viewer.example.test/",
        version_tag="pve-9.0",
    )

    assert calls == [
        (
            "/proxmox/viewer/generate",
            {
                "persist": "false",
                "workers": 4,
                "retry_count": 3,
                "retry_backoff": 0.5,
                "checkpoint_every": 25,
                "source_url": "https://viewer.example.test/",
                "version_tag": "pve-9.0",
            },
        )
    ]
