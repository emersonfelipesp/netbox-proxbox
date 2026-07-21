"""Source contracts for the legacy custom-fields deprecation setting.

``custom_fields_enabled`` defaults to False so the typed sync-state models are
the sole source of truth for the Proxmox-to-NetBox linkage; the legacy
reflection custom fields are only written/read/reconciled when an operator
opts back in.
"""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def test_custom_fields_enabled_model_and_migration_are_default_off():
    model = _read("netbox_proxbox/models/plugin_settings.py")
    migration = _read(
        "netbox_proxbox/migrations/0071_settings_custom_fields_enabled.py"
    )

    assert "custom_fields_enabled = models.BooleanField(" in model
    assert "default=False" in model
    assert "0070_proxmox_metrics_influxdb" in migration
    assert '"custom_fields_enabled"' in migration
    assert "models.BooleanField(" in migration
    assert "default=False" in migration


def test_custom_fields_enabled_is_exposed_in_settings_ui_api_and_docs():
    form = _read("netbox_proxbox/forms/settings.py")
    serializer = _read("netbox_proxbox/api/serializers/settings.py")
    view = _read("netbox_proxbox/views/settings.py")
    template = _read("netbox_proxbox/templates/netbox_proxbox/settings.html")
    config_docs = _read("docs/configuration/plugin-settings.md")
    api_docs = _read("docs/api/settings.md")

    assert "custom_fields_enabled = forms.BooleanField(" in form
    assert 'label="Enable legacy custom fields (deprecated)"' in form
    assert '"custom_fields_enabled",' in serializer
    assert '"custom_fields_enabled": settings_obj.custom_fields_enabled' in view
    assert '"custom_fields_enabled", False' in view
    assert "{% render_field form.custom_fields_enabled %}" in template
    assert "custom_fields_enabled" in config_docs
    assert "`custom_fields_enabled`" in api_docs
