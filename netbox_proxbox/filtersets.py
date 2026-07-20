"""Define NetBox filtersets for the plugin's list views and API queries."""

import django_filters
from dcim.models import Device, DeviceRole, DeviceType, Interface, Manufacturer, Site
from django.db.models import Q, QuerySet
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from ipam.models import IPAddress, VLAN
from netbox.filtersets import NetBoxModelFilterSet
from tenancy.models import Tenant
from utilities.filtersets import register_filterset
from utilities.filters import MultiValueNumberFilter
from virtualization.models import (
    Cluster,
    ClusterGroup,
    ClusterType,
    VirtualDisk,
    VirtualMachine,
    VMInterface,
)

from .choices import (
    CloudImageOSFamilyChoices,
    FirecrackerHostStatusChoices,
    FirecrackerMicroVMStatusChoices,
    FirecrackerNetworkModeChoices,
)
from .models import (
    BackupRoutine,
    CloudImageTemplate,
    FastAPIEndpoint,
    FirecrackerHost,
    FirecrackerHostPool,
    FirecrackerImageTemplate,
    FirecrackerMicroVM,
    GuestVMInterface,
    GuestVMInterfaceAddress,
    NetBoxEndpoint,
    NodeSSHCredential,
    ProxmoxCluster,
    ProxmoxEndpoint,
    ProxmoxFirewallAlias,
    ProxmoxFirewallIPSet,
    ProxmoxFirewallIPSetEntry,
    ProxmoxFirewallOptions,
    ProxmoxFirewallRule,
    ProxmoxFirewallSecurityGroup,
    ProxmoxMetricsInfluxDB,
    ProxboxClusterGroupSyncState,
    ProxboxClusterSyncState,
    ProxboxClusterTypeSyncState,
    ProxboxDeviceRoleSyncState,
    ProxboxDeviceSyncState,
    ProxboxDeviceTypeSyncState,
    ProxboxIPAddressSyncState,
    ProxboxInterfaceSyncState,
    ProxboxManufacturerSyncState,
    ProxboxSiteSyncState,
    ProxboxVirtualDiskSyncState,
    ProxboxVirtualMachineSyncState,
    ProxboxVLANSyncState,
    ProxboxVMInterfaceSyncState,
    ProxmoxSdnBinding,
    ProxmoxSdnController,
    ProxmoxSdnFabric,
    ProxmoxSdnRouteMap,
    ProxmoxSdnPrefixList,
    ProxmoxSdnSubnet,
    ProxmoxSdnVNet,
    ProxmoxSdnZone,
    ProxmoxDatacenterCpuModel,
    ProxmoxNode,
    ProxmoxStorage,
    ProxmoxVMCloudInit,
    ProxmoxVMTemplate,
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


class ProxboxSyncStateFilterSet(ProxboxModelFilterSet):
    """FilterSet base for sync-state sidecars with relation visibility guards."""

    def _filter_visible_relation_id(
        self,
        queryset: QuerySet,
        field_name: str,
        value: list[int],
    ) -> QuerySet:
        if not value:
            return queryset

        relation_field = queryset.model._meta.get_field(field_name)
        relation_model = relation_field.remote_field.model
        relation_queryset = relation_model.objects.all()
        user = getattr(self.request, "user", None)
        if user is not None and hasattr(relation_queryset, "restrict"):
            relation_queryset = relation_queryset.restrict(user, "view")

        visible_relation_ids = relation_queryset.filter(pk__in=value).values("pk")
        return queryset.filter(**{f"{field_name}__in": visible_relation_ids})


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
class FirecrackerHostPoolFilterSet(ProxboxModelFilterSet):
    """Filter Firecracker host pools exposed to Cloud provisioning."""

    default_network_mode = django_filters.MultipleChoiceFilter(
        choices=FirecrackerNetworkModeChoices,
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
        model = FirecrackerHostPool
        fields = (
            "id",
            "name",
            "slug",
            "default_network_mode",
            "allowed_tenants",
            "allowed_tenants_id",
            "allowed_tenants__id__in",
            "allowed_tenants__isnull",
            "is_active",
        )

    def search(self, queryset: QuerySet, name: str, value: str) -> QuerySet:
        if not value.strip():
            return queryset
        return queryset.filter(Q(name__icontains=value) | Q(slug__icontains=value))


@register_filterset
class FirecrackerHostFilterSet(ProxboxModelFilterSet):
    """Filter Firecracker host-agent VMs."""

    pool_id = django_filters.ModelMultipleChoiceFilter(
        field_name="pool",
        queryset=FirecrackerHostPool.objects.all(),
    )
    pool = django_filters.ModelMultipleChoiceFilter(
        field_name="pool__slug",
        to_field_name="slug",
        queryset=FirecrackerHostPool.objects.all(),
    )
    status = django_filters.MultipleChoiceFilter(choices=FirecrackerHostStatusChoices)

    class Meta:
        model = FirecrackerHost
        fields = (
            "id",
            "pool",
            "pool_id",
            "name",
            "status",
            "host_vm",
            "proxmox_node",
            "kvm_available",
            "supports_nat",
            "supports_bridge",
        )

    def search(self, queryset: QuerySet, name: str, value: str) -> QuerySet:
        if not value.strip():
            return queryset
        return queryset.filter(
            Q(name__icontains=value)
            | Q(pool__name__icontains=value)
            | Q(agent_base_url__icontains=value)
        )


@register_filterset
class FirecrackerImageTemplateFilterSet(ProxboxModelFilterSet):
    """Filter Firecracker image templates exposed through Cloud provisioning."""

    os_family = django_filters.MultipleChoiceFilter(choices=CloudImageOSFamilyChoices)
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
        model = FirecrackerImageTemplate
        fields = (
            "id",
            "name",
            "slug",
            "architecture",
            "os_family",
            "os_release",
            "allowed_tenants",
            "allowed_tenants_id",
            "allowed_tenants__id__in",
            "allowed_tenants__isnull",
            "is_active",
        )

    def search(self, queryset: QuerySet, name: str, value: str) -> QuerySet:
        if not value.strip():
            return queryset
        return queryset.filter(
            Q(name__icontains=value)
            | Q(slug__icontains=value)
            | Q(os_release__icontains=value)
            | Q(architecture__icontains=value)
        )


@register_filterset
class FirecrackerMicroVMFilterSet(ProxboxModelFilterSet):
    """Filter provisioned Firecracker micro-VMs."""

    status = django_filters.MultipleChoiceFilter(
        choices=FirecrackerMicroVMStatusChoices,
    )
    network_mode = django_filters.MultipleChoiceFilter(
        choices=FirecrackerNetworkModeChoices,
    )
    tenant_id = django_filters.ModelMultipleChoiceFilter(
        field_name="tenant",
        queryset=Tenant.objects.all(),
    )
    tenant = django_filters.ModelMultipleChoiceFilter(
        field_name="tenant__slug",
        to_field_name="slug",
        queryset=Tenant.objects.all(),
    )
    host_id = django_filters.ModelMultipleChoiceFilter(
        field_name="host",
        queryset=FirecrackerHost.objects.all(),
    )
    image_id = django_filters.ModelMultipleChoiceFilter(
        field_name="image",
        queryset=FirecrackerImageTemplate.objects.all(),
    )

    class Meta:
        model = FirecrackerMicroVM
        fields = (
            "id",
            "microvm_id",
            "name",
            "tenant",
            "tenant_id",
            "host",
            "host_id",
            "image",
            "image_id",
            "status",
            "network_mode",
        )

    def search(self, queryset: QuerySet, name: str, value: str) -> QuerySet:
        if not value.strip():
            return queryset
        query = (
            Q(name__icontains=value)
            | Q(tenant__name__icontains=value)
            | Q(host__name__icontains=value)
            | Q(image__name__icontains=value)
        )
        try:
            query |= Q(microvm_id=value)
        except (TypeError, ValueError):
            pass
        return queryset.filter(query)


@register_filterset
class ProxmoxEndpointFilterSet(ProxboxModelFilterSet):
    """Filter Proxmox VE endpoint records for list and API views."""

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
            "allowed_tenants",
            "allowed_tenants_id",
            "allowed_tenants__id__in",
            "allowed_tenants__isnull",
            "enabled",
            "ssh_credential_source",
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
        fields = ("id", "name", "domain", "ip_address", "enabled")

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
        fields = ("id", "name", "domain", "ip_address", "enabled")

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
class GuestVMInterfaceFilterSet(ProxboxModelFilterSet):
    """Filter guest OS VM interface rows."""

    virtual_machine = django_filters.ModelMultipleChoiceFilter(
        queryset=VirtualMachine.objects.all(),
    )
    virtual_machine_id = django_filters.ModelMultipleChoiceFilter(
        field_name="virtual_machine",
        queryset=VirtualMachine.objects.all(),
        label="Virtual machine (ID)",
    )
    vm_interface = django_filters.ModelMultipleChoiceFilter(
        queryset=VMInterface.objects.all(),
    )
    vm_interface_id = django_filters.ModelMultipleChoiceFilter(
        field_name="vm_interface",
        queryset=VMInterface.objects.all(),
        label="Core VM interface (ID)",
    )
    # Exact match: the backend reconcile scopes by ``virtual_machine_id`` +
    # exact ``name`` and trusts the server-side filter, so ``name`` must not be
    # ``icontains`` here. Free-text UI search goes through ``search()`` (the
    # ``q`` param), and NetBox still auto-generates ``name__ic`` for list views.
    name = django_filters.CharFilter()
    mac_address = django_filters.CharFilter(lookup_expr="icontains")

    class Meta:
        model = GuestVMInterface
        fields = (
            "id",
            "virtual_machine",
            "virtual_machine_id",
            "vm_interface",
            "vm_interface_id",
            "name",
            "mac_address",
            "enabled",
            "mtu",
        )

    def search(self, queryset: QuerySet, name: str, value: str) -> QuerySet:
        """Match guest interface name, MAC address, VM name, or core interface."""
        if not value.strip():
            return queryset
        return queryset.filter(
            Q(name__icontains=value)
            | Q(mac_address__icontains=value)
            | Q(virtual_machine__name__icontains=value)
            | Q(vm_interface__name__icontains=value)
        )


@register_filterset
class GuestVMInterfaceAddressFilterSet(ProxboxModelFilterSet):
    """Filter guest interface to shared IPAddress links."""

    guest_interface = django_filters.ModelMultipleChoiceFilter(
        queryset=GuestVMInterface.objects.all(),
    )
    guest_interface_id = django_filters.ModelMultipleChoiceFilter(
        field_name="guest_interface",
        queryset=GuestVMInterface.objects.all(),
        label="Guest VM interface (ID)",
    )
    ip_address = django_filters.ModelMultipleChoiceFilter(
        queryset=IPAddress.objects.all(),
    )
    ip_address_id = django_filters.ModelMultipleChoiceFilter(
        field_name="ip_address",
        queryset=IPAddress.objects.all(),
        label="IP address (ID)",
    )
    virtual_machine = django_filters.ModelMultipleChoiceFilter(
        field_name="guest_interface__virtual_machine",
        queryset=VirtualMachine.objects.all(),
    )
    vm_interface = django_filters.ModelMultipleChoiceFilter(
        field_name="guest_interface__vm_interface",
        queryset=VMInterface.objects.all(),
    )

    class Meta:
        model = GuestVMInterfaceAddress
        fields = (
            "id",
            "guest_interface",
            "guest_interface_id",
            "ip_address",
            "ip_address_id",
            "virtual_machine",
            "vm_interface",
        )

    def search(self, queryset: QuerySet, name: str, value: str) -> QuerySet:
        """Match IP address, guest interface, VM, or core interface name."""
        if not value.strip():
            return queryset
        return queryset.filter(
            Q(ip_address__address__icontains=value)
            | Q(guest_interface__name__icontains=value)
            | Q(guest_interface__virtual_machine__name__icontains=value)
            | Q(guest_interface__vm_interface__name__icontains=value)
        )


@register_filterset
class ProxboxVirtualMachineSyncStateFilterSet(ProxboxSyncStateFilterSet):
    """Filter typed VM sync-state sidecars."""

    virtual_machine = MultiValueNumberFilter(
        field_name="virtual_machine",
        method="_filter_visible_relation_id",
    )
    virtual_machine_id = MultiValueNumberFilter(
        field_name="virtual_machine",
        method="_filter_visible_relation_id",
        label="Virtual machine (ID)",
    )
    endpoint = MultiValueNumberFilter(
        field_name="endpoint",
        method="_filter_visible_relation_id",
    )
    endpoint_id = MultiValueNumberFilter(
        field_name="endpoint",
        method="_filter_visible_relation_id",
        label="Endpoint (ID)",
    )
    proxmox_node = MultiValueNumberFilter(
        field_name="proxmox_node",
        method="_filter_visible_relation_id",
    )
    proxmox_node_id = MultiValueNumberFilter(
        field_name="proxmox_node",
        method="_filter_visible_relation_id",
        label="Proxmox node (ID)",
    )
    proxmox_cluster = MultiValueNumberFilter(
        field_name="proxmox_cluster",
        method="_filter_visible_relation_id",
    )
    proxmox_cluster_id = MultiValueNumberFilter(
        field_name="proxmox_cluster",
        method="_filter_visible_relation_id",
        label="Proxmox cluster (ID)",
    )

    class Meta:
        model = ProxboxVirtualMachineSyncState
        fields = (
            "id",
            "virtual_machine",
            "virtual_machine_id",
            "endpoint",
            "endpoint_id",
            "proxmox_node",
            "proxmox_node_id",
            "proxmox_cluster",
            "proxmox_cluster_id",
            "proxmox_vm_id",
            "proxmox_vm_type",
            "proxmox_status",
            "proxmox_endpoint_raw_id",
            "proxmox_last_updated",
        )

    def search(self, queryset: QuerySet, name: str, value: str) -> QuerySet:
        if not value.strip():
            return queryset
        query = (
            Q(virtual_machine__name__icontains=value)
            | Q(proxmox_node_name__icontains=value)
            | Q(proxmox_cluster_name__icontains=value)
            | Q(proxmox_status__icontains=value)
            | Q(proxmox_vmid__icontains=value)
        )
        if value.isdigit():
            query |= Q(proxmox_vm_id=int(value))
        return queryset.filter(query)


@register_filterset
class ProxboxDeviceSyncStateFilterSet(ProxboxSyncStateFilterSet):
    """Filter typed device sync-state sidecars."""

    device = MultiValueNumberFilter(
        field_name="device",
        method="_filter_visible_relation_id",
    )
    device_id = MultiValueNumberFilter(
        field_name="device",
        method="_filter_visible_relation_id",
        label="Device (ID)",
    )
    endpoint = MultiValueNumberFilter(
        field_name="endpoint",
        method="_filter_visible_relation_id",
    )
    endpoint_id = MultiValueNumberFilter(
        field_name="endpoint",
        method="_filter_visible_relation_id",
        label="Endpoint (ID)",
    )
    proxmox_node = MultiValueNumberFilter(
        field_name="proxmox_node",
        method="_filter_visible_relation_id",
    )
    proxmox_node_id = MultiValueNumberFilter(
        field_name="proxmox_node",
        method="_filter_visible_relation_id",
        label="Proxmox node (ID)",
    )
    proxmox_cluster = MultiValueNumberFilter(
        field_name="proxmox_cluster",
        method="_filter_visible_relation_id",
    )
    proxmox_cluster_id = MultiValueNumberFilter(
        field_name="proxmox_cluster",
        method="_filter_visible_relation_id",
        label="Proxmox cluster (ID)",
    )

    class Meta:
        model = ProxboxDeviceSyncState
        fields = (
            "id",
            "device",
            "device_id",
            "endpoint",
            "endpoint_id",
            "proxmox_node",
            "proxmox_node_id",
            "proxmox_cluster",
            "proxmox_cluster_id",
            "proxmox_vmid",
            "hardware_chassis_serial",
            "proxmox_last_updated",
        )

    def search(self, queryset: QuerySet, name: str, value: str) -> QuerySet:
        if not value.strip():
            return queryset
        return queryset.filter(
            Q(device__name__icontains=value)
            | Q(proxmox_node_name__icontains=value)
            | Q(proxmox_cluster_name__icontains=value)
            | Q(proxmox_vmid__icontains=value)
            | Q(hardware_chassis_serial__icontains=value)
        )


@register_filterset
class ProxboxClusterSyncStateFilterSet(ProxboxSyncStateFilterSet):
    """Filter typed cluster sync-state sidecars."""

    cluster = MultiValueNumberFilter(
        field_name="cluster",
        method="_filter_visible_relation_id",
    )
    cluster_id = MultiValueNumberFilter(
        field_name="cluster",
        method="_filter_visible_relation_id",
        label="Cluster (ID)",
    )
    proxmox_cluster = MultiValueNumberFilter(
        field_name="proxmox_cluster",
        method="_filter_visible_relation_id",
    )
    proxmox_cluster_id = MultiValueNumberFilter(
        field_name="proxmox_cluster",
        method="_filter_visible_relation_id",
        label="Proxmox cluster (ID)",
    )

    class Meta:
        model = ProxboxClusterSyncState
        fields = (
            "id",
            "cluster",
            "cluster_id",
            "proxmox_cluster",
            "proxmox_cluster_id",
            "proxmox_cluster_name",
            "proxmox_cluster_status",
            "proxmox_cluster_raw_id",
            "proxmox_last_updated",
        )

    def search(self, queryset: QuerySet, name: str, value: str) -> QuerySet:
        if not value.strip():
            return queryset
        query = (
            Q(cluster__name__icontains=value)
            | Q(proxmox_cluster_name__icontains=value)
            | Q(proxmox_cluster_status__icontains=value)
        )
        if value.isdigit():
            query |= Q(proxmox_cluster_raw_id=int(value))
        return queryset.filter(query)


@register_filterset
class ProxboxIPAddressSyncStateFilterSet(ProxboxSyncStateFilterSet):
    """Filter typed IP address sync-state sidecars."""

    ip_address = MultiValueNumberFilter(
        field_name="ip_address",
        method="_filter_visible_relation_id",
    )
    ip_address_id = MultiValueNumberFilter(
        field_name="ip_address",
        method="_filter_visible_relation_id",
        label="IP address (ID)",
    )

    class Meta:
        model = ProxboxIPAddressSyncState
        fields = (
            "id",
            "ip_address",
            "ip_address_id",
            "proxmox_interface",
            "proxmox_mac",
            "proxmox_last_updated",
        )

    def search(self, queryset: QuerySet, name: str, value: str) -> QuerySet:
        if not value.strip():
            return queryset
        return queryset.filter(
            Q(ip_address__address__icontains=value)
            | Q(proxmox_interface__icontains=value)
            | Q(proxmox_mac__icontains=value)
            | Q(proxmox_ip_addresses__icontains=value)
        )


@register_filterset
class ProxboxInterfaceSyncStateFilterSet(ProxboxSyncStateFilterSet):
    """Filter typed device-interface sync-state sidecars."""

    interface = MultiValueNumberFilter(
        field_name="interface",
        method="_filter_visible_relation_id",
    )
    interface_id = MultiValueNumberFilter(
        field_name="interface",
        method="_filter_visible_relation_id",
        label="Interface (ID)",
    )

    class Meta:
        model = ProxboxInterfaceSyncState
        fields = (
            "id",
            "interface",
            "interface_id",
            "nic_speed_gbps",
            "nic_duplex",
            "nic_link",
            "proxmox_last_updated",
        )

    def search(self, queryset: QuerySet, name: str, value: str) -> QuerySet:
        if not value.strip():
            return queryset
        return queryset.filter(
            Q(interface__name__icontains=value)
            | Q(interface__device__name__icontains=value)
            | Q(nic_duplex__icontains=value)
        )


@register_filterset
class ProxboxVLANSyncStateFilterSet(ProxboxSyncStateFilterSet):
    """Filter typed VLAN sync-state sidecars."""

    vlan = MultiValueNumberFilter(
        field_name="vlan",
        method="_filter_visible_relation_id",
    )
    vlan_id = MultiValueNumberFilter(
        field_name="vlan",
        method="_filter_visible_relation_id",
        label="VLAN (ID)",
    )

    class Meta:
        model = ProxboxVLANSyncState
        fields = ("id", "vlan", "vlan_id", "proxmox_vlan_id", "proxmox_last_updated")

    def search(self, queryset: QuerySet, name: str, value: str) -> QuerySet:
        if not value.strip():
            return queryset
        query = Q(vlan__name__icontains=value)
        if value.isdigit():
            query |= Q(proxmox_vlan_id=int(value)) | Q(vlan__vid=int(value))
        return queryset.filter(query)


@register_filterset
class ProxboxClusterGroupSyncStateFilterSet(ProxboxSyncStateFilterSet):
    """Filter typed cluster-group sync-state sidecars."""

    cluster_group = MultiValueNumberFilter(
        field_name="cluster_group",
        method="_filter_visible_relation_id",
    )
    cluster_group_id = MultiValueNumberFilter(
        field_name="cluster_group",
        method="_filter_visible_relation_id",
        label="Cluster group (ID)",
    )

    class Meta:
        model = ProxboxClusterGroupSyncState
        fields = (
            "id",
            "cluster_group",
            "cluster_group_id",
            "proxmox_cluster_name",
            "proxmox_cluster_status",
            "proxmox_last_updated",
        )

    def search(self, queryset: QuerySet, name: str, value: str) -> QuerySet:
        if not value.strip():
            return queryset
        return queryset.filter(
            Q(cluster_group__name__icontains=value)
            | Q(proxmox_cluster_name__icontains=value)
            | Q(proxmox_cluster_status__icontains=value)
        )


@register_filterset
class ProxboxVirtualDiskSyncStateFilterSet(ProxboxSyncStateFilterSet):
    """Filter typed virtual-disk sync-state sidecars."""

    virtual_disk = MultiValueNumberFilter(
        field_name="virtual_disk",
        method="_filter_visible_relation_id",
    )
    virtual_disk_id = MultiValueNumberFilter(
        field_name="virtual_disk",
        method="_filter_visible_relation_id",
        label="Virtual disk (ID)",
    )
    proxbox_storage = MultiValueNumberFilter(
        field_name="proxbox_storage",
        method="_filter_visible_relation_id",
    )
    proxbox_storage_id = MultiValueNumberFilter(
        field_name="proxbox_storage",
        method="_filter_visible_relation_id",
        label="Proxbox storage (ID)",
    )

    class Meta:
        model = ProxboxVirtualDiskSyncState
        fields = (
            "id",
            "virtual_disk",
            "virtual_disk_id",
            "proxbox_storage",
            "proxbox_storage_id",
            "proxbox_storage_raw_id",
            "proxmox_last_updated",
        )

    def search(self, queryset: QuerySet, name: str, value: str) -> QuerySet:
        if not value.strip():
            return queryset
        query = Q(virtual_disk__name__icontains=value) | Q(
            proxbox_storage__name__icontains=value
        )
        if value.isdigit():
            query |= Q(proxbox_storage_raw_id=int(value))
        return queryset.filter(query)


@register_filterset
class ProxboxVMInterfaceSyncStateFilterSet(ProxboxSyncStateFilterSet):
    """Filter typed VM-interface sync-state sidecars."""

    vm_interface = MultiValueNumberFilter(
        field_name="vm_interface",
        method="_filter_visible_relation_id",
    )
    vm_interface_id = MultiValueNumberFilter(
        field_name="vm_interface",
        method="_filter_visible_relation_id",
        label="VM interface (ID)",
    )
    proxbox_bridge = MultiValueNumberFilter(
        field_name="proxbox_bridge",
        method="_filter_visible_relation_id",
    )
    proxbox_bridge_id = MultiValueNumberFilter(
        field_name="proxbox_bridge",
        method="_filter_visible_relation_id",
        label="Proxbox bridge (ID)",
    )

    class Meta:
        model = ProxboxVMInterfaceSyncState
        fields = (
            "id",
            "vm_interface",
            "vm_interface_id",
            "proxbox_bridge",
            "proxbox_bridge_id",
            "proxbox_bridge_raw_id",
            "proxmox_last_updated",
        )

    def search(self, queryset: QuerySet, name: str, value: str) -> QuerySet:
        if not value.strip():
            return queryset
        query = (
            Q(vm_interface__name__icontains=value)
            | Q(vm_interface__virtual_machine__name__icontains=value)
            | Q(proxbox_bridge__name__icontains=value)
            | Q(proxbox_bridge__device__name__icontains=value)
        )
        if value.isdigit():
            query |= Q(proxbox_bridge_raw_id=int(value))
        return queryset.filter(query)


@register_filterset
class ProxboxDeviceRoleSyncStateFilterSet(ProxboxSyncStateFilterSet):
    """Filter typed device-role sync-state sidecars."""

    device_role = MultiValueNumberFilter(
        field_name="device_role",
        method="_filter_visible_relation_id",
    )
    device_role_id = MultiValueNumberFilter(
        field_name="device_role",
        method="_filter_visible_relation_id",
        label="Device role (ID)",
    )

    class Meta:
        model = ProxboxDeviceRoleSyncState
        fields = ("id", "device_role", "device_role_id", "proxmox_last_updated")

    def search(self, queryset: QuerySet, name: str, value: str) -> QuerySet:
        if not value.strip():
            return queryset
        return queryset.filter(Q(device_role__name__icontains=value))


@register_filterset
class ProxboxDeviceTypeSyncStateFilterSet(ProxboxSyncStateFilterSet):
    """Filter typed device-type sync-state sidecars."""

    device_type = MultiValueNumberFilter(
        field_name="device_type",
        method="_filter_visible_relation_id",
    )
    device_type_id = MultiValueNumberFilter(
        field_name="device_type",
        method="_filter_visible_relation_id",
        label="Device type (ID)",
    )

    class Meta:
        model = ProxboxDeviceTypeSyncState
        fields = ("id", "device_type", "device_type_id", "proxmox_last_updated")

    def search(self, queryset: QuerySet, name: str, value: str) -> QuerySet:
        if not value.strip():
            return queryset
        return queryset.filter(
            Q(device_type__model__icontains=value)
            | Q(device_type__manufacturer__name__icontains=value)
        )


@register_filterset
class ProxboxManufacturerSyncStateFilterSet(ProxboxSyncStateFilterSet):
    """Filter typed manufacturer sync-state sidecars."""

    manufacturer = MultiValueNumberFilter(
        field_name="manufacturer",
        method="_filter_visible_relation_id",
    )
    manufacturer_id = MultiValueNumberFilter(
        field_name="manufacturer",
        method="_filter_visible_relation_id",
        label="Manufacturer (ID)",
    )

    class Meta:
        model = ProxboxManufacturerSyncState
        fields = ("id", "manufacturer", "manufacturer_id", "proxmox_last_updated")

    def search(self, queryset: QuerySet, name: str, value: str) -> QuerySet:
        if not value.strip():
            return queryset
        return queryset.filter(Q(manufacturer__name__icontains=value))


@register_filterset
class ProxboxSiteSyncStateFilterSet(ProxboxSyncStateFilterSet):
    """Filter typed site sync-state sidecars."""

    site = MultiValueNumberFilter(
        field_name="site",
        method="_filter_visible_relation_id",
    )
    site_id = MultiValueNumberFilter(
        field_name="site",
        method="_filter_visible_relation_id",
        label="Site (ID)",
    )

    class Meta:
        model = ProxboxSiteSyncState
        fields = ("id", "site", "site_id", "proxmox_last_updated")

    def search(self, queryset: QuerySet, name: str, value: str) -> QuerySet:
        if not value.strip():
            return queryset
        return queryset.filter(Q(site__name__icontains=value))


@register_filterset
class ProxboxClusterTypeSyncStateFilterSet(ProxboxSyncStateFilterSet):
    """Filter typed cluster-type sync-state sidecars."""

    cluster_type = MultiValueNumberFilter(
        field_name="cluster_type",
        method="_filter_visible_relation_id",
    )
    cluster_type_id = MultiValueNumberFilter(
        field_name="cluster_type",
        method="_filter_visible_relation_id",
        label="Cluster type (ID)",
    )

    class Meta:
        model = ProxboxClusterTypeSyncState
        fields = ("id", "cluster_type", "cluster_type_id", "proxmox_last_updated")

    def search(self, queryset: QuerySet, name: str, value: str) -> QuerySet:
        if not value.strip():
            return queryset
        return queryset.filter(Q(cluster_type__name__icontains=value))


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
            "location",
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
class ProxmoxVMTemplateFilterSet(ProxboxModelFilterSet):
    """Filter dedicated Proxmox VM template records."""

    class Meta:
        model = ProxmoxVMTemplate
        fields = (
            "id",
            "proxmox_endpoint",
            "cluster",
            "node",
            "source_vm",
            "vmid",
            "name",
            "node_name",
            "proxmox_type",
            "status",
            "cloud_init_enabled",
        )

    def search(self, queryset: QuerySet, name: str, value: str) -> QuerySet:
        """Match template name, VMID, node, type, or status."""
        if not value.strip():
            return queryset
        query = (
            Q(name__icontains=value)
            | Q(node_name__icontains=value)
            | Q(proxmox_type__icontains=value)
            | Q(status__icontains=value)
        )
        if value.isdigit():
            query |= Q(vmid=int(value))
        return queryset.filter(query)


@register_filterset
class ProxmoxMetricsInfluxDBFilterSet(ProxboxModelFilterSet):
    """Filter Proxmox cluster InfluxDB metrics endpoint metadata."""

    class Meta:
        model = ProxmoxMetricsInfluxDB
        fields = ("id", "endpoint", "proxmox_cluster", "enabled", "name")

    def search(self, queryset: QuerySet, name: str, value: str) -> QuerySet:
        """Match metrics endpoint name, InfluxDB URL, organization, or bucket."""
        if not value.strip():
            return queryset
        return queryset.filter(
            Q(name__icontains=value)
            | Q(influx_url__icontains=value)
            | Q(org__icontains=value)
            | Q(bucket__icontains=value)
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


@register_filterset
class ProxmoxFirewallSecurityGroupFilterSet(ProxboxModelFilterSet):
    """Filter Proxmox firewall security groups."""

    class Meta:
        model = ProxmoxFirewallSecurityGroup
        fields = ("id", "endpoint", "name", "status")

    def search(self, queryset: QuerySet, name: str, value: str) -> QuerySet:
        if not value.strip():
            return queryset
        return queryset.filter(Q(name__icontains=value) | Q(comment__icontains=value))


@register_filterset
class ProxmoxFirewallRuleFilterSet(ProxboxModelFilterSet):
    """Filter Proxmox firewall rules."""

    class Meta:
        model = ProxmoxFirewallRule
        fields = (
            "id",
            "endpoint",
            "zone",
            "proxmox_node",
            "virtual_machine",
            "security_group",
            "rule_type",
            "action",
            "enable",
            "status",
        )

    def search(self, queryset: QuerySet, name: str, value: str) -> QuerySet:
        if not value.strip():
            return queryset
        return queryset.filter(
            Q(action__icontains=value)
            | Q(source__icontains=value)
            | Q(dest__icontains=value)
            | Q(comment__icontains=value)
            | Q(macro__icontains=value)
        )


@register_filterset
class ProxmoxFirewallIPSetFilterSet(ProxboxModelFilterSet):
    """Filter Proxmox firewall IP sets."""

    class Meta:
        model = ProxmoxFirewallIPSet
        fields = ("id", "endpoint", "scope", "virtual_machine", "name", "status")

    def search(self, queryset: QuerySet, name: str, value: str) -> QuerySet:
        if not value.strip():
            return queryset
        return queryset.filter(Q(name__icontains=value) | Q(comment__icontains=value))


@register_filterset
class ProxmoxFirewallIPSetEntryFilterSet(ProxboxModelFilterSet):
    """Filter Proxmox firewall IP set entries."""

    class Meta:
        model = ProxmoxFirewallIPSetEntry
        fields = ("id", "ipset", "cidr", "nomatch")

    def search(self, queryset: QuerySet, name: str, value: str) -> QuerySet:
        if not value.strip():
            return queryset
        return queryset.filter(Q(cidr__icontains=value) | Q(comment__icontains=value))


@register_filterset
class ProxmoxFirewallAliasFilterSet(ProxboxModelFilterSet):
    """Filter Proxmox firewall aliases."""

    class Meta:
        model = ProxmoxFirewallAlias
        fields = ("id", "endpoint", "scope", "virtual_machine", "name", "status")

    def search(self, queryset: QuerySet, name: str, value: str) -> QuerySet:
        if not value.strip():
            return queryset
        return queryset.filter(
            Q(name__icontains=value)
            | Q(cidr__icontains=value)
            | Q(comment__icontains=value)
        )


@register_filterset
class ProxmoxFirewallOptionsFilterSet(ProxboxModelFilterSet):
    """Filter Proxmox firewall options."""

    class Meta:
        model = ProxmoxFirewallOptions
        fields = (
            "id",
            "endpoint",
            "zone",
            "proxmox_node",
            "virtual_machine",
            "enable",
            "status",
        )

    def search(self, queryset: QuerySet, name: str, value: str) -> QuerySet:
        if not value.strip():
            return queryset
        return queryset.filter(
            Q(policy_in__icontains=value) | Q(policy_out__icontains=value)
        )


@register_filterset
class ProxmoxSdnFabricFilterSet(ProxboxModelFilterSet):
    """Filter Proxmox SDN fabrics."""

    class Meta:
        model = ProxmoxSdnFabric
        fields = (
            "id",
            "endpoint",
            "cluster_name",
            "fabric_name",
            "fabric_type",
            "status",
        )

    def search(self, queryset: QuerySet, name: str, value: str) -> QuerySet:
        if not value.strip():
            return queryset
        return queryset.filter(
            Q(fabric_name__icontains=value) | Q(cluster_name__icontains=value)
        )


@register_filterset
class ProxmoxSdnControllerFilterSet(ProxboxModelFilterSet):
    """Filter Proxmox SDN controllers."""

    class Meta:
        model = ProxmoxSdnController
        fields = (
            "id",
            "endpoint",
            "cluster_name",
            "controller_name",
            "controller_type",
            "status",
        )

    def search(self, queryset: QuerySet, name: str, value: str) -> QuerySet:
        if not value.strip():
            return queryset
        return queryset.filter(
            Q(controller_name__icontains=value) | Q(cluster_name__icontains=value)
        )


@register_filterset
class ProxmoxSdnZoneFilterSet(ProxboxModelFilterSet):
    """Filter Proxmox SDN zones."""

    class Meta:
        model = ProxmoxSdnZone
        fields = ("id", "endpoint", "cluster_name", "zone_name", "zone_type", "status")

    def search(self, queryset: QuerySet, name: str, value: str) -> QuerySet:
        if not value.strip():
            return queryset
        return queryset.filter(
            Q(zone_name__icontains=value) | Q(cluster_name__icontains=value)
        )


@register_filterset
class ProxmoxSdnVNetFilterSet(ProxboxModelFilterSet):
    """Filter Proxmox SDN VNets."""

    class Meta:
        model = ProxmoxSdnVNet
        fields = (
            "id",
            "endpoint",
            "cluster_name",
            "zone_name",
            "vnet_name",
            "vnet_type",
            "tag",
            "status",
        )

    def search(self, queryset: QuerySet, name: str, value: str) -> QuerySet:
        if not value.strip():
            return queryset
        return queryset.filter(
            Q(vnet_name__icontains=value)
            | Q(zone_name__icontains=value)
            | Q(cluster_name__icontains=value)
        )


@register_filterset
class ProxmoxSdnSubnetFilterSet(ProxboxModelFilterSet):
    """Filter Proxmox SDN subnets."""

    class Meta:
        model = ProxmoxSdnSubnet
        fields = (
            "id",
            "endpoint",
            "cluster_name",
            "zone_name",
            "vnet_name",
            "subnet",
            "status",
        )

    def search(self, queryset: QuerySet, name: str, value: str) -> QuerySet:
        if not value.strip():
            return queryset
        return queryset.filter(
            Q(subnet__icontains=value)
            | Q(vnet_name__icontains=value)
            | Q(cluster_name__icontains=value)
        )


@register_filterset
class ProxmoxSdnBindingFilterSet(ProxboxModelFilterSet):
    """Filter Proxmox SDN binding/status rows."""

    class Meta:
        model = ProxmoxSdnBinding
        fields = (
            "id",
            "endpoint",
            "cluster_name",
            "source_type",
            "source_name",
            "target_type",
            "status",
        )

    def search(self, queryset: QuerySet, name: str, value: str) -> QuerySet:
        if not value.strip():
            return queryset
        return queryset.filter(
            Q(source_name__icontains=value)
            | Q(target_type__icontains=value)
            | Q(cluster_name__icontains=value)
        )


@register_filterset
class ProxmoxSdnRouteMapFilterSet(ProxboxModelFilterSet):
    """Filter Proxmox SDN route maps."""

    class Meta:
        model = ProxmoxSdnRouteMap
        fields = ("id", "endpoint", "cluster_name", "name", "action", "status")

    def search(self, queryset: QuerySet, name: str, value: str) -> QuerySet:
        if not value.strip():
            return queryset
        return queryset.filter(
            Q(name__icontains=value) | Q(cluster_name__icontains=value)
        )


@register_filterset
class ProxmoxSdnPrefixListFilterSet(ProxboxModelFilterSet):
    """Filter Proxmox SDN prefix lists."""

    class Meta:
        model = ProxmoxSdnPrefixList
        fields = ("id", "endpoint", "cluster_name", "name", "action", "status")

    def search(self, queryset: QuerySet, name: str, value: str) -> QuerySet:
        if not value.strip():
            return queryset
        return queryset.filter(
            Q(name__icontains=value)
            | Q(cidr__icontains=value)
            | Q(cluster_name__icontains=value)
        )


@register_filterset
class ProxmoxDatacenterCpuModelFilterSet(ProxboxModelFilterSet):
    """Filter Proxmox datacenter custom CPU models."""

    class Meta:
        model = ProxmoxDatacenterCpuModel
        fields = ("id", "endpoint", "cluster_name", "cputype", "base_cputype", "status")

    def search(self, queryset: QuerySet, name: str, value: str) -> QuerySet:
        if not value.strip():
            return queryset
        return queryset.filter(
            Q(cputype__icontains=value)
            | Q(base_cputype__icontains=value)
            | Q(cluster_name__icontains=value)
        )
