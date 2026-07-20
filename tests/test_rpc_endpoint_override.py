"""Per-endpoint netbox-rpc enablement override (non-enforcing).

Covers the resolution semantics of ``ProxmoxEndpoint.effective_rpc_enabled()``
(netbox-rpc installation is required first; when installed, the per-endpoint
override wins via ``is not None``; otherwise inherit the global netbox-rpc
``RpcPluginSettings.enabled``)
plus source contracts pinning the model field, constants, form, serializer,
migration, view context, and Settings-tab UI wiring.

netbox-proxbox integrates with netbox-rpc *optionally* and must never depend on
the NMS stack; netbox-rpc is not modified by this feature.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _read(rel: str) -> str:
    return (REPO_ROOT / rel).read_text(encoding="utf-8")


def _resolve_rpc_like_model(
    endpoint_rpc_enabled: bool | None,
    global_enabled: bool,
    *,
    rpc_installed: bool = True,
) -> bool:
    """Mirror of ``ProxmoxEndpoint.effective_rpc_enabled()`` body."""
    if not rpc_installed:
        return False
    if endpoint_rpc_enabled is not None:
        return bool(endpoint_rpc_enabled)
    return bool(global_enabled)


# --- resolution semantics -----------------------------------------------------


def test_per_endpoint_true_wins_over_global_false() -> None:
    assert _resolve_rpc_like_model(True, global_enabled=False) is True


def test_per_endpoint_false_wins_over_global_true() -> None:
    # An explicit per-endpoint False must be respected (is not None), not treated
    # as "unset".
    assert _resolve_rpc_like_model(False, global_enabled=True) is False


def test_unset_inherits_global_enabled() -> None:
    assert _resolve_rpc_like_model(None, global_enabled=True) is True
    assert _resolve_rpc_like_model(None, global_enabled=False) is False


def test_netbox_rpc_absent_resolves_false_when_unset() -> None:
    assert (
        _resolve_rpc_like_model(None, global_enabled=True, rpc_installed=False) is False
    )


def test_netbox_rpc_absent_disables_even_explicit_true_override() -> None:
    assert (
        _resolve_rpc_like_model(True, global_enabled=False, rpc_installed=False)
        is False
    )


# --- source contracts ---------------------------------------------------------


def test_model_defines_rpc_enabled_and_effective_resolution() -> None:
    src = _read("netbox_proxbox/models/proxmox_endpoint.py")
    assert "rpc_enabled = models.BooleanField(" in src
    block = src.split("rpc_enabled = models.BooleanField(", 1)[1][:200]
    assert "null=True" in block and "blank=True" in block
    method = src.split("def effective_rpc_enabled", 1)[1]
    assert "self.rpc_enabled is not None" in method
    # Optional, guarded, function-local netbox-rpc import (never top-level).
    assert "from netbox_rpc.models import RpcPluginSettings" in method
    assert "except ImportError" in method
    assert method.index("from netbox_rpc.models") < method.index(
        "if self.rpc_enabled is not None"
    )
    assert "RpcPluginSettings.get_solo().enabled" in method
    top = src.split("class ", 1)[0]
    assert "import netbox_rpc" not in top and "from netbox_rpc" not in top
    # No NMS dependency anywhere in this model module.
    assert "netbox_nms" not in src and "nms_backend" not in src


def test_constants_expose_rpc_field_groups() -> None:
    src = _read("netbox_proxbox/constants.py")
    assert "RPC_FIELD_GROUPS" in src
    assert '"rpc_enabled"' in src
    assert "RPC_FIELDS" in src


def test_settings_form_includes_rpc_enabled() -> None:
    src = _read("netbox_proxbox/forms/proxmox.py")
    assert "RPC_FIELDS" in src
    assert '"rpc_enabled"' in src
    assert "NullBooleanSelect" in src


def test_serializer_exposes_rpc_fields() -> None:
    src = _read("netbox_proxbox/api/serializers/endpoints.py")
    assert '"rpc_enabled"' in src
    assert '"effective_rpc_enabled"' in src
    assert "def get_effective_rpc_enabled" in src
    assert "obj.effective_rpc_enabled()" in src


def test_migration_adds_rpc_enabled_field() -> None:
    src = _read("netbox_proxbox/migrations/0059_proxmoxendpoint_rpc_enabled.py")
    assert "add_field_idempotent" in src
    assert 'model_name="proxmoxendpoint"' in src
    assert 'field_name="rpc_enabled"' in src
    assert '"0058_encrypt_primary_endpoint_secrets"' in src


def test_settings_view_passes_rpc_field_groups() -> None:
    src = _read("netbox_proxbox/views/endpoints/proxmox.py")
    assert "RPC_FIELD_GROUPS" in src
    assert '"rpc_field_groups": RPC_FIELD_GROUPS' in src


def test_settings_template_has_rpc_tab() -> None:
    src = _read("netbox_proxbox/templates/netbox_proxbox/proxmoxendpoint_settings.html")
    assert 'id="proxbox-settings-rpc"' in src
    assert 'data-bs-target="#proxbox-settings-rpc"' in src
    assert "rpc_field_groups" in src
