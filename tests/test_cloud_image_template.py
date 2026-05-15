"""Source contracts for CloudImageTemplate catalog support."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text()


def test_cloud_image_template_model_defines_catalog_fields_and_permission():
    src = _read("netbox_proxbox/models/cloud_image_template.py")
    assert "class CloudImageTemplate(NetBoxModel)" in src
    for field in (
        "name",
        "slug",
        "description",
        "cluster",
        "source_vmid",
        "os_family",
        "os_release",
        "default_ciuser",
        "allowed_tenants",
        "is_active",
    ):
        assert field in src
    assert '"provision_cloud_vm"' in src
    assert 'unique_together = ("cluster", "source_vmid")' in src
    assert "tenancy.Tenant" in src
    assert "virtualization.Cluster" in src


def test_cloud_image_template_migration_exists_on_current_develop_head():
    src = _read("netbox_proxbox/migrations/0044_cloud_image_template.py")
    assert '("netbox_proxbox", "0043_pluginsettings_warn_plaintext")' in src
    assert 'name="CloudImageTemplate"' in src
    assert '"provision_cloud_vm"' in src
    assert '"unique_together": {("cluster", "source_vmid")}' in src


def test_cloud_image_template_ui_surface_is_registered():
    urls = _read("netbox_proxbox/urls.py")
    views = _read("netbox_proxbox/views/cloud_image_templates.py")
    nav = _read("netbox_proxbox/navigation.py")

    assert '"cloud-image-templates/<int:pk>/"' in urls
    assert 'get_model_urls("netbox_proxbox", "cloudimagetemplate")' in urls
    assert "@register_model_view(CloudImageTemplate)" in views
    assert '@register_model_view(CloudImageTemplate, "add", detail=False)' in views
    assert "CloudImageTemplateTable" in views
    assert "cloudimagetemplate_list" in nav
    assert "cloudimagetemplate_add" in nav


def test_cloud_image_template_api_surface_is_registered():
    urls = _read("netbox_proxbox/api/urls.py")
    views = _read("netbox_proxbox/api/views.py")
    serializer = _read("netbox_proxbox/api/serializers/cloud_image_template.py")
    filtersets = _read("netbox_proxbox/filtersets.py")

    assert '"cloud-image-templates"' in urls
    assert "CloudImageTemplateViewSet" in views
    assert "CloudImageTemplateSerializer" in serializer
    assert "NestedCloudImageTemplateSerializer" in serializer
    assert "allowed_tenants__id__in" in filtersets
    assert "allowed_tenants__isnull" in filtersets


def test_cloud_image_template_api_serializer_supports_writable_tenant_scope():
    serializer = _read("netbox_proxbox/api/serializers/cloud_image_template.py")

    assert "def create(self, validated_data)" in serializer
    assert "def update(self, instance, validated_data)" in serializer
    assert 'validated_data.pop("allowed_tenants", None)' in serializer
    assert "instance.allowed_tenants.set(allowed_tenants)" in serializer


def test_cloud_image_template_templates_exist():
    detail = (
        REPO_ROOT / "netbox_proxbox/templates/netbox_proxbox/cloudimagetemplate.html"
    )
    listing = (
        REPO_ROOT
        / "netbox_proxbox/templates/netbox_proxbox/cloudimagetemplate_list.html"
    )
    assert detail.exists()
    assert listing.exists()
    assert "Tenant Scope" in detail.read_text()
    assert "Add Cloud Image" in listing.read_text()
