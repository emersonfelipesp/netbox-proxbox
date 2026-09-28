"""Real Django form and API behavior for node Device name templates."""

from __future__ import annotations

import pytest

from tests.test_proxmox_endpoint_allowed_tenants import _require_harness

pytestmark = pytest.mark.django_db


@pytest.fixture
def naming_models(pytestconfig, request):
    _require_harness(pytestconfig)
    request.getfixturevalue("db")
    from netbox_proxbox.models import (
        ProxboxPluginSettings,
        ProxmoxCluster,
        ProxmoxEndpoint,
        ProxmoxNode,
    )

    return ProxboxPluginSettings, ProxmoxCluster, ProxmoxEndpoint, ProxmoxNode


def _endpoint(Endpoint, *, name: str, template: str = ""):
    return Endpoint.objects.create(
        name=name,
        domain="pve.example.test",
        username="root@pam",
        node_device_name_template=template,
        enabled=False,
    )


def test_settings_form_rejects_overlength_real_cluster(naming_models) -> None:
    from netbox_proxbox.forms.proxmox import ProxmoxEndpointSettingsForm

    _, Cluster, Endpoint, Node = naming_models
    endpoint = _endpoint(Endpoint, name="pve")
    cluster = Cluster.objects.create(endpoint=endpoint, name="c" * 60)
    Node.objects.create(
        endpoint=endpoint,
        proxmox_cluster=cluster,
        name="node1",
        ip_address=".".join(("192", "0", "2", "10")),
    )

    form = ProxmoxEndpointSettingsForm(
        data={"node_device_name_template": "{node}.{cluster}"},
        instance=endpoint,
    )

    assert not form.is_valid()
    assert "66 characters" in str(form.errors["node_device_name_template"])


def test_endpoint_api_create_rejects_inherited_template_for_submitted_name(
    naming_models,
) -> None:
    from netbox_proxbox.api.serializers.endpoints import ProxmoxEndpointSerializer

    Settings, _, _, _ = naming_models
    settings = Settings.get_solo()
    settings.node_device_name_template = "{node}.{endpoint}"
    settings.save(update_fields=["node_device_name_template"])

    serializer = ProxmoxEndpointSerializer(
        data={
            "name": "e" * 60,
            "domain": "pve.example.test",
            "node_device_name_template": "",
        }
    )

    assert not serializer.is_valid()
    assert "node_device_name_template" in serializer.errors


def test_endpoint_api_rename_rejects_inherited_template_without_inventory(
    naming_models,
) -> None:
    from netbox_proxbox.api.serializers.endpoints import ProxmoxEndpointSerializer

    Settings, _, Endpoint, _ = naming_models
    settings = Settings.get_solo()
    settings.node_device_name_template = "{node}.{endpoint}"
    settings.save(update_fields=["node_device_name_template"])
    endpoint = _endpoint(Endpoint, name="short")

    serializer = ProxmoxEndpointSerializer(
        endpoint,
        data={"name": "e" * 60},
        partial=True,
    )

    assert not serializer.is_valid()
    assert "node_device_name_template" in serializer.errors


def test_global_api_rejects_inheriting_endpoint_without_inventory(
    naming_models,
) -> None:
    from netbox_proxbox.api.serializers.settings import (
        ProxboxPluginSettingsSerializer,
    )

    Settings, _, Endpoint, _ = naming_models
    settings = Settings.get_solo()
    _endpoint(Endpoint, name="e" * 60)

    serializer = ProxboxPluginSettingsSerializer(
        settings,
        data={"node_device_name_template": "{node}.{endpoint}"},
        partial=True,
    )

    assert not serializer.is_valid()
    assert "node_device_name_template" in serializer.errors
