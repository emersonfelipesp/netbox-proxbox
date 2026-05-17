"""NetBox filtersets for netbox-packer list views and API queries."""

from __future__ import annotations

import django_filters
from django.db.models import Q, QuerySet
from netbox.filtersets import NetBoxModelFilterSet
from tenancy.models import Tenant
from virtualization.models import Cluster

from netbox_packer.choices import (
    PackerBuildStatusChoices,
    PackerBuilderTypeChoices,
    PackerOSFamilyChoices,
    PackerProvisionerRecipeChoices,
)
from netbox_packer.models import (
    PackerImageBuild,
    PackerImageDefinition,
    PackerPluginSettings,
)
from netbox_proxbox.models import ProxmoxEndpoint


class PackerImageDefinitionFilterSet(NetBoxModelFilterSet):
    """Filter reusable image definitions."""

    proxmox_endpoint = django_filters.ModelMultipleChoiceFilter(
        queryset=ProxmoxEndpoint.objects.all(),
    )
    target_cluster = django_filters.ModelMultipleChoiceFilter(
        queryset=Cluster.objects.all(),
    )
    os_family = django_filters.MultipleChoiceFilter(
        choices=PackerOSFamilyChoices,
    )
    builder_type = django_filters.MultipleChoiceFilter(
        choices=PackerBuilderTypeChoices,
    )
    provisioner_recipe = django_filters.MultipleChoiceFilter(
        choices=PackerProvisionerRecipeChoices,
    )
    tenant = django_filters.ModelMultipleChoiceFilter(
        field_name="allowed_tenants",
        queryset=Tenant.objects.all(),
    )

    class Meta:
        model = PackerImageDefinition
        fields = (
            "id",
            "name",
            "slug",
            "enabled",
            "builder_type",
            "proxmox_endpoint",
            "target_cluster",
            "target_node",
            "os_family",
            "provisioner_recipe",
            "tenant",
        )

    def search(
        self,
        queryset: QuerySet[PackerImageDefinition],
        name: str,
        value: str,
    ) -> QuerySet[PackerImageDefinition]:
        """Match image definition name or description."""
        if not value.strip():
            return queryset
        return queryset.filter(
            Q(name__icontains=value) | Q(description__icontains=value)
        )


class PackerImageBuildFilterSet(NetBoxModelFilterSet):
    """Filter image build executions."""

    status = django_filters.MultipleChoiceFilter(
        choices=PackerBuildStatusChoices,
    )
    proxmox_endpoint = django_filters.ModelMultipleChoiceFilter(
        queryset=ProxmoxEndpoint.objects.all(),
    )
    os_family = django_filters.MultipleChoiceFilter(
        field_name="definition__os_family",
        choices=PackerOSFamilyChoices,
    )
    tenant = django_filters.ModelMultipleChoiceFilter(
        field_name="definition__allowed_tenants",
        queryset=Tenant.objects.all(),
    )

    class Meta:
        model = PackerImageBuild
        fields = (
            "id",
            "definition",
            "status",
            "backend_build_id",
            "proxmox_endpoint",
            "target_node",
            "output_vmid",
            "image_version",
            "created_by",
            "netbox_job_id",
            "cloud_image_template",
            "os_family",
            "tenant",
        )

    def search(
        self,
        queryset: QuerySet[PackerImageBuild],
        name: str,
        value: str,
    ) -> QuerySet[PackerImageBuild]:
        """Match build output, backend identifier, or error text."""
        if not value.strip():
            return queryset
        return queryset.filter(
            Q(output_name__icontains=value)
            | Q(backend_build_id__icontains=value)
            | Q(error__icontains=value)
        )


class PackerPluginSettingsFilterSet(NetBoxModelFilterSet):
    class Meta:
        model = PackerPluginSettings
        fields = ("singleton_key",)
