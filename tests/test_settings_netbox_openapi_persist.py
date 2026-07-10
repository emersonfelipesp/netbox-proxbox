"""Source contracts for the netbox_openapi_persist (in-memory schema) setting."""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _read(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def test_netbox_openapi_persist_model_and_migration_default_on():
    model = _read("netbox_proxbox/models/plugin_settings.py")
    migration = _read(
        "netbox_proxbox/migrations/0057_proxboxpluginsettings_netbox_openapi_persist.py"
    )

    assert "netbox_openapi_persist = models.BooleanField(" in model
    # The model field defaults to on (persist to disk).
    field_block = model.split("netbox_openapi_persist = models.BooleanField(", 1)[1][
        :120
    ]
    assert "default=True" in field_block

    assert '("netbox_proxbox", "0056_proxmoxendpoint_access_methods")' in migration
    assert "add_field_idempotent(" in migration
    assert 'field_name="netbox_openapi_persist"' in migration
    assert "default=True" in migration


def test_netbox_openapi_persist_exposed_in_ui_api_and_docs():
    form = _read("netbox_proxbox/forms/settings.py")
    serializer = _read("netbox_proxbox/api/serializers/settings.py")
    view = _read("netbox_proxbox/views/settings.py")
    template = _read("netbox_proxbox/templates/netbox_proxbox/settings.html")
    config_docs = _read("docs/configuration/plugin-settings.md")
    api_docs = _read("docs/api/settings.md")

    assert "netbox_openapi_persist = forms.BooleanField(" in form
    assert '"netbox_openapi_persist",' in serializer
    assert '"netbox_openapi_persist": getattr(' in view
    # Save path reads the form value (default True); tolerate ruff line-wrapping.
    assert "settings_obj.netbox_openapi_persist = form.cleaned_data.get(" in view
    assert '"netbox_openapi_persist", True' in view
    # Persisted in the model save() update_fields list.
    assert '"netbox_openapi_persist",' in view
    assert "{% render_field form.netbox_openapi_persist %}" in template
    assert "PROXBOX_NETBOX_OPENAPI_PERSIST" in config_docs
    assert "`netbox_openapi_persist`" in api_docs
