from __future__ import annotations

import types

import pytest

for module_name in ("click", "typer", "rich"):
    pytest.importorskip(module_name)

virtualization = pytest.importorskip("proxbox_cli.commands.virtualization")


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
