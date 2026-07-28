"""Source contracts for the physical-NIC MAC discovery opt-in."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SETTING = "hardware_discovery_sync_nic_macs"


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text()


def test_setting_is_default_off_and_ui_editable() -> None:
    model = _read("netbox_proxbox/models/plugin_settings.py")
    form = _read("netbox_proxbox/forms/settings.py")
    template = _read("netbox_proxbox/templates/netbox_proxbox/settings.html")

    model_block = model.split(f"{SETTING} = models.BooleanField(", 1)[1].split(
        "\n    )", 1
    )[0]
    assert "default=False" in model_block
    assert f"{SETTING} = forms.BooleanField(" in form
    assert f"form.{SETTING}" in template


def test_setting_is_exposed_to_backend_and_persisted_by_view() -> None:
    serializer = _read("netbox_proxbox/api/serializers/settings.py")
    view = _read("netbox_proxbox/views/settings.py")

    assert f'"{SETTING}",' in serializer
    assert view.count(f'"{SETTING}"') >= 3
    assert f"settings_obj.{SETTING} = form.cleaned_data.get(" in view


def test_setting_uses_idempotent_additive_migration() -> None:
    migration = _read(
        "netbox_proxbox/migrations/"
        "0076_pluginsettings_hardware_discovery_sync_nic_macs.py"
    )

    assert '"0075_fastapi_backend_key_target_fingerprint"' in migration
    assert "add_field_idempotent(" in migration
    assert f'field_name="{SETTING}"' in migration
    assert "default=False" in migration


def test_operator_docs_explain_both_required_opt_ins() -> None:
    hardware_docs = _read("docs/configuration/hardware-discovery.md")
    settings_docs = _read("docs/configuration/plugin-settings.md")
    normalized_hardware_docs = hardware_docs.replace("\n", " ")

    assert "Both checkboxes must be on" in normalized_hardware_docs
    assert "Existing MAC rows are left untouched" in normalized_hardware_docs
    assert SETTING in hardware_docs
    assert "Sync physical NIC MAC addresses" in settings_docs
