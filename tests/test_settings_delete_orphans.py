"""Source contracts for the destructive orphan-VM cleanup setting."""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def test_delete_orphans_model_and_migration_are_default_off():
    model = _read("netbox_proxbox/models/plugin_settings.py")
    migration = _read("netbox_proxbox/migrations/0046_pluginsettings_delete_orphans.py")

    assert "delete_orphans = models.BooleanField(" in model
    assert "default=False" in model
    assert '("netbox_proxbox", "0045_pluginsettings_branching_fields")' in migration
    assert 'ADD COLUMN IF NOT EXISTS "delete_orphans" boolean' in migration
    assert "NOT NULL DEFAULT FALSE" in migration
    assert 'DROP COLUMN IF EXISTS "delete_orphans"' in migration


def test_delete_orphans_is_exposed_in_settings_ui_api_and_docs():
    form = _read("netbox_proxbox/forms/settings.py")
    serializer = _read("netbox_proxbox/api/serializers/settings.py")
    view = _read("netbox_proxbox/views/settings.py")
    template = _read("netbox_proxbox/templates/netbox_proxbox/settings.html")
    config_docs = _read("docs/configuration/plugin-settings.md")
    api_docs = _read("docs/api/settings.md")

    assert "delete_orphans = forms.BooleanField(" in form
    assert 'label="Delete orphan VMs"' in form
    assert '"delete_orphans",' in serializer
    assert '"delete_orphans": settings_obj.delete_orphans' in view
    assert 'form.cleaned_data.get("delete_orphans", False)' in view
    assert '"delete_orphans",' in view
    assert "{% render_field form.delete_orphans %}" in template
    assert "PROXBOX_DELETE_ORPHANS" in config_docs
    assert "`delete_orphans`" in api_docs
