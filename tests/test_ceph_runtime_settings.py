"""Source contracts for the bounded Ceph runtime timing settings."""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MIGRATION = "netbox_proxbox/migrations/0077_ceph_runtime_timing_settings.py"
FIELDS = (
    "ceph_task_timeout",
    "ceph_task_poll_interval",
    "ceph_run_lease_seconds",
)


def _read(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def test_ceph_runtime_settings_have_idempotent_schema_and_bounded_models() -> None:
    model = _read("netbox_proxbox/models/plugin_settings.py")
    migration = _read(MIGRATION)

    assert (
        '"0076_pluginsettings_hardware_discovery_sync_nic_macs"' in migration
    )
    assert migration.count("add_field_idempotent(") == 3
    for field_name in FIELDS:
        assert f"{field_name} = models.DecimalField(" in model
        assert f'field_name="{field_name}"' in migration

    assert 'default=Decimal("300.00")' in model
    assert 'default=Decimal("1.00")' in model
    assert 'default=Decimal("360.00")' in model
    assert 'MinValueValidator(Decimal("0.10"))' in model
    assert model.count('MaxValueValidator(Decimal("3600.00"))') == 2
    assert 'MaxValueValidator(Decimal("60.00"))' in model


def test_ceph_runtime_settings_are_wired_through_every_operator_surface() -> None:
    form = _read("netbox_proxbox/forms/settings.py")
    serializer = _read("netbox_proxbox/api/serializers/settings.py")
    view = _read("netbox_proxbox/views/settings.py")
    template = _read("netbox_proxbox/templates/netbox_proxbox/settings.html")
    config_docs = _read("docs/configuration/plugin-settings.md")
    api_docs = _read("docs/api/settings.md")

    for field_name in FIELDS:
        assert f"{field_name} = forms.DecimalField(" in form
        assert f'"{field_name}",' in serializer
        assert f'"{field_name}": settings_obj.{field_name}' in view
        assert f"settings_obj.{field_name} = form.cleaned_data[" in view
        assert view.count(f'"{field_name}"') >= 3
        assert f"form.{field_name}" in template
        assert field_name in config_docs
        assert field_name in api_docs

    assert "Ceph Control Plane" in template
    assert "## Ceph control-plane timing" in config_docs


def test_ceph_runtime_settings_document_cross_service_resolution_contract() -> None:
    config_docs = _read("docs/configuration/plugin-settings.md")
    api_docs = _read("docs/api/settings.md")

    for variable in (
        "PROXBOX_CEPH_TASK_TIMEOUT",
        "PROXBOX_CEPH_TASK_POLL_INTERVAL",
        "PROXBOX_CEPH_RUN_LEASE_SECONDS",
    ):
        assert variable in config_docs
        assert variable in api_docs
    assert "environment override" in config_docs
    assert "immutable" in config_docs
    normalized_config_docs = config_docs.lower()
    assert "finite out-of-range environment values are" in normalized_config_docs
    assert "clamped" in normalized_config_docs
    assert "polling interval to at most" in config_docs
    assert "JSON numbers" in config_docs
    assert '"ceph_task_timeout": 300.0' in api_docs
    assert '"ceph_task_timeout": "300.00"' not in api_docs
    assert "| `ceph_task_timeout` | number |" in api_docs
    assert "decimal string" not in api_docs
