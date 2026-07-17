"""Source contracts for the cloud customer network plugin settings."""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MIGRATION = "netbox_proxbox/migrations/0059_cloud_customer_network_settings.py"


def _read(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def test_cloud_customer_network_fields_exist_with_estate_agnostic_defaults():
    model = _read("netbox_proxbox/models/plugin_settings.py")
    migration = _read(MIGRATION)

    for field_name in (
        "cloud_network_lock_enabled",
        "cloud_customer_prefix_id",
        "cloud_customer_bridge",
        "cloud_customer_vlan_tag",
        "cloud_customer_gateway",
    ):
        assert f"{field_name} = models." in model
        assert f'field_name="{field_name}"' in migration

    assert "cloud_network_lock_enabled = models.BooleanField(" in model
    assert (
        "default=False"
        in model.split(
            "cloud_network_lock_enabled = models.BooleanField(",
            1,
        )[1][:180]
    )
    assert "cloud_customer_prefix_id = models.PositiveIntegerField(" in model
    assert (
        "null=True"
        in model.split(
            "cloud_customer_prefix_id = models.PositiveIntegerField(",
            1,
        )[1][:180]
    )
    assert "cloud_customer_bridge = models.CharField(" in model
    assert (
        'default="vmbr1"'
        in model.split(
            "cloud_customer_bridge = models.CharField(",
            1,
        )[1][:180]
    )
    assert "cloud_customer_vlan_tag = models.PositiveIntegerField(" in model
    assert (
        "null=True"
        in model.split(
            "cloud_customer_vlan_tag = models.PositiveIntegerField(",
            1,
        )[1][:180]
    )
    assert "cloud_customer_gateway = models.CharField(" in model
    assert (
        'default=""'
        in model.split(
            "cloud_customer_gateway = models.CharField(",
            1,
        )[1][:180]
    )

    assert "168.0.98" not in migration
    assert "2050" not in migration


def test_cloud_customer_network_is_wired_through_settings_surfaces():
    form = _read("netbox_proxbox/forms/settings.py")
    serializer = _read("netbox_proxbox/api/serializers/settings.py")
    view = _read("netbox_proxbox/views/settings.py")
    template = _read("netbox_proxbox/templates/netbox_proxbox/settings.html")
    config_docs = _read("docs/configuration/plugin-settings.md")
    api_docs = _read("docs/api/settings.md")
    command = _read(
        "netbox_proxbox/management/commands/ensure_cloud_customer_network.py"
    )

    for field_name in (
        "cloud_network_lock_enabled",
        "cloud_customer_prefix_id",
        "cloud_customer_bridge",
        "cloud_customer_vlan_tag",
        "cloud_customer_gateway",
    ):
        assert f"{field_name} = forms." in form
        assert f'"{field_name}",' in serializer
        assert f'"{field_name}": getattr(' in view
        assert f"settings_obj.{field_name} = form.cleaned_data.get(" in view
        assert f'"{field_name}",' in view
        assert f"form.{field_name}" in template
        assert field_name in config_docs
        assert field_name in api_docs
        assert field_name in command

    assert "Cloud customer network" in template
    assert "## Cloud-customer network" in config_docs
    assert "ensure_cloud_customer_network" in config_docs
