"""Source-contract test for the plugin's Django signal handlers.

These signals automatically generate API tokens and register FastAPI/NetBox
endpoint records with the proxbox-api backend after a NetBox-side save. They
are easy to break by accident — for example by swapping ``post_save`` for a
``pre_save`` signal, dropping the ``@receiver`` decorator, or changing the
sender to a non-string class reference (which then fails to import at app load
time inside NetBox).

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
            "endpoint creation no longer auto-bootstraps the backend"
        )
        info = receivers[handler_name]
        assert info["signal"] == "post_save", (
            f"{handler_name} no longer uses post_save; pre_save runs before the row "
            "exists in the DB and would break token generation"
        )
        assert info["sender"] == expected_sender, (
            f"{handler_name} sender drifted to {info['sender']!r}; "
            f"expected {expected_sender!r}"
        )


def test_signals_module_only_uses_post_save_receivers():
    """No accidental ``pre_save`` / ``pre_delete`` handlers — they would fire
    before the row is committed and break the bootstrap flow."""
    module = ast.parse(SIGNALS_PATH.read_text(encoding="utf-8"))
    for info in _registered_receivers(module).values():
        assert info["signal"] == "post_save", (
            "All endpoint-bootstrap receivers must run on post_save, not "
            f"{info['signal']!r}"
        )
