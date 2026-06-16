"""Coverage for tenant-scoped Proxmox endpoint allowlists."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
NETBOX_ROOT = REPO_ROOT.parent / "netbox" / "netbox"

for candidate in (REPO_ROOT, NETBOX_ROOT):
    candidate_str = str(candidate)
    if candidate.exists() and candidate_str not in sys.path:
        sys.path.insert(0, candidate_str)


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text()


def test_proxmox_endpoint_model_exposes_allowed_tenants() -> None:
    src = _read("netbox_proxbox/models/proxmox_endpoint.py")
    assert "allowed_tenants = models.ManyToManyField(" in src
    assert 'related_name="proxbox_proxmox_endpoints"' in src
    assert "NMS Cloud callers with any explicit endpoint grant" in src


def test_proxmox_endpoint_form_and_detail_surface_allowed_tenants() -> None:
    forms = _read("netbox_proxbox/forms/proxmox.py")
    detail = _read("netbox_proxbox/templates/netbox_proxbox/proxmoxendpoint.html")

    assert 'label=_("Allowed tenants")' in forms
    assert '"allowed_tenants"' in forms
    assert "Default visibility" in detail


def test_proxmox_endpoint_api_supports_allowed_tenants() -> None:
    serializer = _read("netbox_proxbox/api/serializers/endpoints.py")
    filtersets = _read("netbox_proxbox/filtersets.py")
    views = _read("netbox_proxbox/api/views.py")

    assert "allowed_tenants = TenantSerializer(nested=True, many=True, required=False)" in serializer
    assert 'validated_data.pop("allowed_tenants", None)' in serializer
    assert "instance.allowed_tenants.set(allowed_tenants)" in serializer
    assert "allowed_tenants__id__in" in filtersets
    assert "allowed_tenants__isnull" in filtersets
    assert '.prefetch_related("allowed_tenants")' in views


def test_proxmox_endpoint_migration_adds_allowed_tenants() -> None:
    migration = _read("netbox_proxbox/migrations/0052_proxmoxendpoint_allowed_tenants.py")
    assert 'name="allowed_tenants"' in migration
    assert 'to="tenancy.tenant"' in migration


def _require_harness() -> None:
    django = pytest.importorskip("django", reason="NetBox + Django harness not installed")
    pytest.importorskip("tenancy", reason="NetBox app modules not importable in this env")

    os.environ.setdefault("NETBOX_CONFIGURATION", "tests.netbox_test_configuration")
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "netbox.settings")

    from django.apps import apps

    if not apps.ready:
        django.setup()


@pytest.fixture
def proxmox_endpoint_fixture():  # type: ignore[no-untyped-def]
    _require_harness()

    from ipam.models import IPAddress
    from tenancy.models import Tenant

    from netbox_proxbox.choices import ProxmoxModeChoices
    from netbox_proxbox.models import ProxmoxEndpoint

    tenant_a = Tenant.objects.create(name="Tenant A", slug="tenant-a")
    tenant_b = Tenant.objects.create(name="Tenant B", slug="tenant-b")
    global_ip = IPAddress.objects.create(address="192.0.2.10/24")
    scoped_ip = IPAddress.objects.create(address="192.0.2.11/24")
    create_ip = IPAddress.objects.create(address="192.0.2.12/24")

    global_endpoint = ProxmoxEndpoint.objects.create(
        name="global-endpoint",
        ip_address=global_ip,
        port=8006,
        mode=ProxmoxModeChoices.PROXMOX_MODE_CLUSTER,
        username="root@pam",
        token_name="global-token",
        token_value="global-secret",
        verify_ssl=False,
    )
    scoped_endpoint = ProxmoxEndpoint.objects.create(
        name="scoped-endpoint",
        ip_address=scoped_ip,
        port=8006,
        mode=ProxmoxModeChoices.PROXMOX_MODE_CLUSTER,
        username="root@pam",
        token_name="scoped-token",
        token_value="scoped-secret",
        verify_ssl=False,
    )
    scoped_endpoint.allowed_tenants.add(tenant_a)

    return {
        "tenant_a": tenant_a,
        "tenant_b": tenant_b,
        "global_endpoint": global_endpoint,
        "scoped_endpoint": scoped_endpoint,
        "create_ip": create_ip,
    }


@pytest.mark.django_db
def test_allowed_tenants_filterset_matches_slug_and_global_flag(
    proxmox_endpoint_fixture,
) -> None:  # type: ignore[no-untyped-def]
    from netbox_proxbox.filtersets import ProxmoxEndpointFilterSet
    from netbox_proxbox.models import ProxmoxEndpoint

    tenant_a = proxmox_endpoint_fixture["tenant_a"]
    global_endpoint = proxmox_endpoint_fixture["global_endpoint"]
    scoped_endpoint = proxmox_endpoint_fixture["scoped_endpoint"]

    scoped_qs = ProxmoxEndpointFilterSet(
        {"allowed_tenants": [tenant_a.slug]},
        queryset=ProxmoxEndpoint.objects.all(),
    ).qs
    assert list(scoped_qs.values_list("pk", flat=True)) == [scoped_endpoint.pk]

    global_qs = ProxmoxEndpointFilterSet(
        {"allowed_tenants__isnull": True},
        queryset=ProxmoxEndpoint.objects.all(),
    ).qs
    assert list(global_qs.values_list("pk", flat=True)) == [global_endpoint.pk]


@pytest.mark.django_db
def test_allowed_tenants_serializer_writes_and_clears_m2m(
    proxmox_endpoint_fixture,
) -> None:  # type: ignore[no-untyped-def]
    from netbox_proxbox.api.serializers.endpoints import ProxmoxEndpointSerializer

    tenant_a = proxmox_endpoint_fixture["tenant_a"]
    tenant_b = proxmox_endpoint_fixture["tenant_b"]
    create_ip = proxmox_endpoint_fixture["create_ip"]
    scoped_endpoint = proxmox_endpoint_fixture["scoped_endpoint"]

    create_serializer = ProxmoxEndpointSerializer(
        data={
            "name": "created-endpoint",
            "ip_address": {"id": create_ip.pk},
            "port": 8006,
            "mode": "cluster",
            "username": "root@pam",
            "token_name": "created-token",
            "token_value": "created-secret",
            "verify_ssl": False,
            "allowed_tenants": [{"id": tenant_a.pk}, {"id": tenant_b.pk}],
        }
    )
    assert create_serializer.is_valid(), create_serializer.errors
    created = create_serializer.save()
    assert list(created.allowed_tenants.order_by("slug").values_list("slug", flat=True)) == [
        "tenant-a",
        "tenant-b",
    ]

    update_serializer = ProxmoxEndpointSerializer(
        scoped_endpoint,
        data={"allowed_tenants": []},
        partial=True,
    )
    assert update_serializer.is_valid(), update_serializer.errors
    updated = update_serializer.save()
    assert not updated.allowed_tenants.exists()
