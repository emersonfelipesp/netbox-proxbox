"""Define NetBox filtersets for the plugin's list views and API queries."""

import django_filters
from django.db.models import Q, QuerySet
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from netbox.filtersets import NetBoxModelFilterSet
from tenancy.models import Tenant
from utilities.filtersets import register_filterset
from utilities.filters import MultiValueNumberFilter
from virtualization.models import Cluster

from .choices import CloudImageOSFamilyChoices
from .models import (
    BackupRoutine,
    CloudImageTemplate,
    FastAPIEndpoint,
    NetBoxEndpoint,
    NodeSSHCredential,
    ProxmoxCluster,
    ProxmoxEndpoint,
    ProxmoxNode,
    ProxmoxStorage,
    ProxmoxVMCloudInit,
    Replication,
    VMBackup,
    VMSnapshot,
    VMTaskHistory,
)


class ProxboxModelFilterSet(NetBoxModelFilterSet):
    """NetBoxModelFilterSet with OpenAPI type hints for tag filters.

    drf-spectacular cannot resolve TaggableManager field paths, so we
    annotate tag filters explicitly to suppress schema-generation warnings
    and produce correct OpenAPI types.
    """

    _TAG_FILTER_SCHEMA_MAP = {
        "tag": OpenApiTypes.STR,
        "tag__n": OpenApiTypes.STR,
        "tag_id": OpenApiTypes.INT,
        "tag_id__n": OpenApiTypes.INT,
    }

    @classmethod
    def get_filters(cls):
        filters = super().get_filters()
        for name, openapi_type in cls._TAG_FILTER_SCHEMA_MAP.items():
            if name in filters:
                extend_schema_field(openapi_type)(filters[name])
        return filters


@register_filterset
class CloudImageTemplateFilterSet(ProxboxModelFilterSet):
    """Filter cloud image templates exposed through the Cloud Portal."""

    cluster_id = django_filters.ModelMultipleChoiceFilter(
        field_name="cluster",
        queryset=Cluster.objects.all(),
    )
    cluster = django_filters.ModelMultipleChoiceFilter(
        field_name="cluster__name",
        to_field_name="name",
        queryset=Cluster.objects.all(),
    )
    os_family = django_filters.MultipleChoiceFilter(
        choices=CloudImageOSFamilyChoices,
    )
    allowed_tenants_id = django_filters.ModelMultipleChoiceFilter(
        field_name="allowed_tenants",
        queryset=Tenant.objects.all(),
    )
    allowed_tenants = django_filters.ModelMultipleChoiceFilter(
        field_name="allowed_tenants__slug",
        to_field_name="slug",
        queryset=Tenant.objects.all(),
    )
    allowed_tenants__id__in = MultiValueNumberFilter(
        field_name="allowed_tenants__id",
        lookup_expr="in",
    )
    allowed_tenants__isnull = django_filters.BooleanFilter(
        field_name="allowed_tenants",
        lookup_expr="isnull",
    )

    class Meta:
        model = CloudImageTemplate
        fields = (
            "id",
            "name",
            "slug",
            "cluster",
            "cluster_id",
            "source_vmid",
            "os_family",
            "os_release",
            "default_ciuser",
            "allowed_tenants",
            "allowed_tenants_id",
            "allowed_tenants__id__in",
            "allowed_tenants__isnull",
            "is_active",
        )

    def search(self, queryset: QuerySet, name: str, value: str) -> QuerySet:
        """Match cloud image name, slug, cluster, release, or source VMID."""
        if not value.strip():
            return queryset
        query = (
            Q(name__icontains=value)
            | Q(slug__icontains=value)
            | Q(cluster__name__icontains=value)
            | Q(os_release__icontains=value)
        )
        if value.isdigit():
            query |= Q(source_vmid=int(value))
        return queryset.filter(query)


@register_filterset
class ProxmoxEndpointFilterSet(ProxboxModelFilterSet):
    """Filter Proxmox VE endpoint records for list and API views."""

    class Meta:
        model = ProxmoxEndpoint
        fields = (
            "id",
            "name",
            "domain",
            "ip_address",
            "mode",
            "environment",
            "site",
            "tenant",
        )

    def search(self, queryset: QuerySet, name: str, value: str) -> QuerySet:
        """Match the search term against endpoint name or domain."""
        if not value.strip():
            return queryset
        return queryset.filter(Q(name__icontains=value) | Q(domain__icontains=value))


@register_filterset
class NetBoxEndpointFilterSet(ProxboxModelFilterSet):
    """Filter remote NetBox API endpoint records."""

    class Meta:
        model = NetBoxEndpoint
        fields = ("id", "name", "domain", "ip_address")

    def search(self, queryset: QuerySet, name: str, value: str) -> QuerySet:
        """Match the search term against endpoint name or domain."""
        if not value.strip():
            return queryset
        return queryset.filter(Q(name__icontains=value) | Q(domain__icontains=value))


@register_filterset
class FastAPIEndpointFilterSet(ProxboxModelFilterSet):
    """Filter ProxBox FastAPI backend endpoint records."""

    class Meta:
        model = FastAPIEndpoint
        fields = ("id", "name", "domain", "ip_address")

    def search(self, queryset: QuerySet, name: str, value: str) -> QuerySet:
        """Match the search term against endpoint name or domain."""
        if not value.strip():
            return queryset
        return queryset.filter(Q(name__icontains=value) | Q(domain__icontains=value))


@register_filterset
class NodeSSHCredentialFilterSet(ProxboxModelFilterSet):
    """Filter per-node SSH credential rows."""

    class Meta:
        model = NodeSSHCredential
        fields = ("id", "node", "username", "auth_method", "port", "sudo_required")

    def search(self, queryset: QuerySet, name: str, value: str) -> QuerySet:
        """Match username, Proxmox node name, or linked NetBox device name."""
        if not value.strip():
            return queryset
        return queryset.filter(
            Q(username__icontains=value)
            | Q(node__name__icontains=value)
            | Q(node__netbox_device__name__icontains=value)
        )


@register_filterset
class VMBackupFilterSet(ProxboxModelFilterSet):
    """Filter VM backup records synced from Proxmox."""

    class Meta:
        model = VMBackup
        fields = (
            "id",
            "proxmox_storage",
            "virtual_machine",
            "subtype",
            "format",
            "creation_time",
            "size",
            "used",
            "encrypted",
            "volume_id",
            "vmid",
        )

    def search(self, queryset: QuerySet, name: str, value: str) -> QuerySet:
        """Match VM name, storage, or volume id (case-insensitive)."""
        if not value.strip():
            return queryset
        return queryset.filter(
            Q(virtual_machine__name__icontains=value)
            | Q(proxmox_storage__name__icontains=value)
            | Q(storage__icontains=value)
            | Q(volume_id__icontains=value)
        )


@register_filterset
class VMSnapshotFilterSet(ProxboxModelFilterSet):
    """Filter VM snapshot records synced from Proxmox."""

    class Meta:
        model = VMSnapshot
        fields = (
            "id",
            "proxmox_storage",
            "virtual_machine",
            "subtype",
            "status",
            "name",
            "description",
            "vmid",
            "node",
            "parent",
            "snaptime",
        )

    def search(self, queryset: QuerySet, name: str, value: str) -> QuerySet:
        """Match VM name, snapshot name, node, or description."""
        if not value.strip():
            return queryset
        return queryset.filter(
            Q(virtual_machine__name__icontains=value)
            | Q(proxmox_storage__name__icontains=value)
            | Q(name__icontains=value)
            | Q(node__icontains=value)
            | Q(description__icontains=value)
        )


@register_filterset
class VMTaskHistoryFilterSet(ProxboxModelFilterSet):
    """Filter VM task history records synced from Proxmox."""

    class Meta:
        model = VMTaskHistory
        fields = (
            "id",
            "virtual_machine",
            "vm_type",
            "upid",
            "node",
            "pid",
            "pstart",
            "task_id",
            "task_type",
            "username",
            "start_time",
            "end_time",
            "description",
            "status",
            "task_state",
            "exitstatus",
        )

    def search(self, queryset: QuerySet, name: str, value: str) -> QuerySet:
        """Match VM name, task metadata, user name, or task result text."""
        if not value.strip():
            return queryset
        return queryset.filter(
            Q(virtual_machine__name__icontains=value)
            | Q(vm_type__icontains=value)
            | Q(upid__icontains=value)
            | Q(node__icontains=value)
            | Q(task_id__icontains=value)
            | Q(task_type__icontains=value)
            | Q(username__icontains=value)
            | Q(description__icontains=value)
            | Q(status__icontains=value)
            | Q(task_state__icontains=value)
            | Q(exitstatus__icontains=value)
        )


@register_filterset
class ProxmoxVMCloudInitFilterSet(ProxboxModelFilterSet):
    """Filter Proxmox VM cloud-init rows reflected from Proxmox (issue #363)."""

    class Meta:
        model = ProxmoxVMCloudInit
        fields = (
            "id",
            "virtual_machine",
            "ciuser",
            "ipconfig0",
            "sshkeys_truncated",
        )

    def search(self, queryset: QuerySet, name: str, value: str) -> QuerySet:
        """Match VM name or cloud-init fields case-insensitively."""
        if not value.strip():
            return queryset
        return queryset.filter(
            Q(virtual_machine__name__icontains=value)
            | Q(ciuser__icontains=value)
            | Q(ipconfig0__icontains=value)
        )


@register_filterset
class ProxmoxStorageFilterSet(ProxboxModelFilterSet):
    """Filter Proxmox storage rows synced by the plugin."""

    class Meta:
        model = ProxmoxStorage
        fields = (
            "id",
            "cluster",
            "cluster__name",
            "name",
            "storage_type",
            "content",
            "path",
            "nodes",
            "shared",
            "enabled",
            "server",
            "port",
            "format",
            "datastore",
            "pool",
        )

    def search(self, queryset: QuerySet, name: str, value: str) -> QuerySet:
        """Match storage name, cluster, or storage path."""
        if not value.strip():
            return queryset
        return queryset.filter(
            Q(name__icontains=value)
            | Q(cluster__name__icontains=value)
            | Q(path__icontains=value)
        )


@register_filterset
class ProxmoxClusterFilterSet(ProxboxModelFilterSet):
    """Filter Proxmox cluster records tracked by the plugin."""

    class Meta:
        model = ProxmoxCluster
        fields = ("id", "endpoint", "netbox_cluster", "name", "mode", "quorate")

    def search(self, queryset: QuerySet, name: str, value: str) -> QuerySet:
        """Match cluster name or cluster ID."""
        if not value.strip():
            return queryset
        return queryset.filter(
            Q(name__icontains=value) | Q(cluster_id__icontains=value)
        )


@register_filterset
class ProxmoxNodeFilterSet(ProxboxModelFilterSet):
    """Filter Proxmox node records tracked by the plugin."""

    class Meta:
        model = ProxmoxNode
        fields = (
            "id",
            "endpoint",
            "proxmox_cluster",
            "netbox_device",
            "name",
            "ip_address",
            "online",
            "local",
        )

    def search(self, queryset: QuerySet, name: str, value: str) -> QuerySet:
        """Match node name, IP address, or SSL fingerprint."""
        if not value.strip():
            return queryset
        return queryset.filter(
            Q(name__icontains=value)
            | Q(ip_address__icontains=value)
            | Q(ssl_fingerprint__icontains=value)
        )


@register_filterset
class BackupRoutineFilterSet(ProxboxModelFilterSet):
    """Filter backup routine records synced from Proxmox."""

    class Meta:
        model = BackupRoutine
        fields = (
            "id",
            "endpoint",
            "job_id",
            "enabled",
            "node",
            "storage",
            "status",
            "keep_last",
            "keep_daily",
            "keep_weekly",
            "keep_monthly",
        )

    def search(self, queryset: QuerySet, name: str, value: str) -> QuerySet:
        """Match job ID or comment."""
        if not value.strip():
            return queryset
        return queryset.filter(Q(job_id__icontains=value) | Q(comment__icontains=value))


@register_filterset
class ReplicationFilterSet(ProxboxModelFilterSet):
    """Filter Replication records synced from Proxmox."""

    class Meta:
        model = Replication
        fields = (
            "id",
            "endpoint",
            "replication_id",
            "virtual_machine",
            "proxmox_node",
            "guest",
            "target",
            "job_type",
            "schedule",
            "disable",
            "source",
            "jobnum",
            "remove_job",
            "status",
        )

    def search(self, queryset: QuerySet, name: str, value: str) -> QuerySet:
        """Match replication ID, VM name, target, comment, or source."""
        if not value.strip():
            return queryset
        return queryset.filter(
            Q(replication_id__icontains=value)
            | Q(virtual_machine__name__icontains=value)
            | Q(target__icontains=value)
            | Q(comment__icontains=value)
            | Q(source__icontains=value)
        )
