"""Topology contract for the plugin's Django signal handlers.

FastAPIEndpoint persistence owns explicit-candidate adoption and schedules
pending automatic discovery after transaction commit. Its receiver stops stale
clients; downstream endpoint receivers authenticate an already stored key
before pushing configuration. This file pins only signal registration topology; real NetBox behavior lives in
``test_backend_key_adoption_django.py``.

The contract is verified statically against ``netbox_proxbox/signals.py`` so
the test runs without booting Django or NetBox.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SIGNALS_PATH = REPO_ROOT / "netbox_proxbox" / "signals.py"

EXPECTED_RECEIVERS: dict[str, str] = {
    "ensure_fastapi_endpoint_token": "netbox_proxbox.FastAPIEndpoint",
    "ensure_proxmox_endpoint_has_fastapi_token": "netbox_proxbox.ProxmoxEndpoint",
    "sync_netbox_endpoint_to_backend": "netbox_proxbox.NetBoxEndpoint",
}


def _registered_receivers(module: ast.Module) -> dict[str, dict[str, str]]:
    """Walk the module AST and pull (signal, sender) for every @receiver def."""
    found: dict[str, dict[str, str]] = {}
    for node in ast.walk(module):
        if not isinstance(node, ast.FunctionDef):
            continue
        for deco in node.decorator_list:
            if not isinstance(deco, ast.Call):
                continue
            if not (isinstance(deco.func, ast.Name) and deco.func.id == "receiver"):
                continue

            signal_name = ""
            if deco.args and isinstance(deco.args[0], ast.Name):
                signal_name = deco.args[0].id

            sender = ""
            for kw in deco.keywords:
                if kw.arg == "sender" and isinstance(kw.value, ast.Constant):
                    sender = str(kw.value.value)

            found[node.name] = {"signal": signal_name, "sender": sender}
    return found


def test_signal_handlers_are_registered_with_correct_senders():
    module = ast.parse(SIGNALS_PATH.read_text(encoding="utf-8"))
    receivers = _registered_receivers(module)

    for handler_name, expected_sender in EXPECTED_RECEIVERS.items():
        assert handler_name in receivers, (
            f"signal handler {handler_name!r} missing from signals.py — "
            "the read-only post-save contract is no longer enforced"
        )
        info = receivers[handler_name]
        assert info["signal"] == "post_save", (
            f"{handler_name} no longer uses post_save; pre_save runs before the row "
            "exists in the DB and would bypass the persistence boundary"
        )
        assert info["sender"] == expected_sender, (
            f"{handler_name} sender drifted to {info['sender']!r}; "
            f"expected {expected_sender!r}"
        )


def test_signals_module_only_uses_post_save_receivers():
    """No accidental ``pre_save`` / ``pre_delete`` handlers — they would fire
    before the row is committed and bypass the key-adoption boundary."""
    module = ast.parse(SIGNALS_PATH.read_text(encoding="utf-8"))
    for info in _registered_receivers(module).values():
        assert info["signal"] == "post_save", (
            f"All endpoint receivers must run on post_save, not {info['signal']!r}"
        )


def test_disabled_proxmox_save_requests_policy_only_backend_revocation():
    source = SIGNALS_PATH.read_text(encoding="utf-8")
    assert "policy_revocation_only = not bool" in source
    assert "allow_disabled_policy_update=policy_revocation_only" in source


def test_proxmox_backend_push_runs_only_after_commit_from_a_fresh_row():
    source = SIGNALS_PATH.read_text(encoding="utf-8")
    handler = source.split("def ensure_proxmox_endpoint_has_fastapi_token(", 1)[
        1
    ].split("@receiver(post_save", 1)[0]
    assert "transaction.on_commit(sync_committed_endpoint, using=using)" in handler
    assert "manager.filter(pk=endpoint_pk).first()" in handler
    assert "_after_commit=True" in handler
    assert handler.index("transaction.on_commit") < handler.index(
        "from netbox_proxbox.models import FastAPIEndpoint"
    )


def test_signal_delegates_confirmed_policy_recording_to_shared_push_helper():
    source = SIGNALS_PATH.read_text(encoding="utf-8")
    handler = source.split("def ensure_proxmox_endpoint_has_fastapi_token(", 1)[
        1
    ].split("@receiver(post_save", 1)[0]
    assert "sync_proxmox_endpoint_to_backend(" in handler
    backend_sync = (
        REPO_ROOT / "netbox_proxbox" / "views" / "backend_sync.py"
    ).read_text(encoding="utf-8")
    assert "_record_confirmed_packer_template_authorization(" in backend_sync
    assert "packer_template_builds_backend_authorized=authorized" in backend_sync
