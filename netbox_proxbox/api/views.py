"""Provide NetBox API root views and model viewsets for the plugin."""

from __future__ import annotations

from django.db.models import Q
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from netbox.api.authentication import IsAuthenticatedOrLoginNotRequired
from netbox.api.viewsets import NetBoxModelViewSet
from rest_framework import status as drf_status
from rest_framework.decorators import action
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.routers import APIRootView
from rest_framework.views import APIView
from utilities.permissions import get_permission_for_model

from netbox_proxbox.choices import ProxmoxVMTypeChoices
from netbox_proxbox.intent.firewall_common import (
    FirewallPushError,
    preview_firewall_object,
    push_firewall_object,
)
from netbox_proxbox.views.proxbox_access import permission_run_proxmox_action

from .. import filtersets, models
from .serializers import (
    BackupRoutineSerializer,
    CloudImageTemplateSerializer,
    DeletionRequestSerializer,
    FastAPIEndpointSerializer,
    FirecrackerHostPoolSerializer,
    FirecrackerHostSerializer,
    FirecrackerImageTemplateSerializer,
    FirecrackerMicroVMSerializer,
    GuestVMInterfaceAddressSerializer,
    GuestVMInterfaceSerializer,
    NetBoxEndpointSerializer,
    NodeSSHCredentialSerializer,
    PBSEndpointSerializer,
    PDMEndpointSerializer,
    PDMRemoteSerializer,
    ProxboxClusterGroupSyncStateSerializer,
    ProxboxClusterSyncStateSerializer,
    ProxboxClusterTypeSyncStateSerializer,
    ProxboxDeviceRoleSyncStateSerializer,
    ProxboxDeviceSyncStateSerializer,
    ProxboxDeviceTypeSyncStateSerializer,
    ProxboxIPAddressSyncStateSerializer,
    ProxboxInterfaceSyncStateSerializer,
    ProxboxManufacturerSyncStateSerializer,
    ProxboxPluginSettingsSerializer,
    ProxboxSiteSyncStateSerializer,
    ProxboxVirtualDiskSyncStateSerializer,
    ProxboxVirtualMachineSyncStateSerializer,
    ProxboxVLANSyncStateSerializer,
    ProxboxVMInterfaceSyncStateSerializer,
    ProxmoxApplyJobSerializer,
    ProxmoxClusterSerializer,
    ProxmoxEndpointSerializer,
    ProxmoxFirewallAliasSerializer,
    ProxmoxFirewallIPSetEntrySerializer,
    ProxmoxFirewallIPSetSerializer,
    ProxmoxFirewallOptionsSerializer,
    ProxmoxFirewallRuleSerializer,
    ProxmoxFirewallSecurityGroupSerializer,
    ProxmoxDatacenterCpuModelSerializer,
    ProxmoxMetricsInfluxDBSerializer,
    ProxmoxNodeSerializer,
    ProxmoxServiceCollectionSerializer,
    ProxmoxServiceSampleSerializer,
    ProxmoxServiceStatusSerializer,
    ProxmoxSdnBindingSerializer,
    ProxmoxSdnControllerSerializer,
    ProxmoxSdnFabricSerializer,
    ProxmoxSdnPrefixListSerializer,
    ProxmoxSdnRouteMapSerializer,
    ProxmoxSdnSubnetSerializer,
    ProxmoxSdnVNetSerializer,
    ProxmoxSdnZoneSerializer,
    ProxmoxStorageSerializer,
    ProxmoxVMCloudInitSerializer,
    ProxmoxVMTemplateSerializer,
    PVETemplateBuildRequestSerializer,
    PVETemplateBuildResponseSerializer,
    ReplicationSerializer,
    ScheduleSyncRequestSerializer,
    VMBackupSerializer,
    VMSnapshotSerializer,
    VMTaskHistorySerializer,
)
from netbox_proxbox.api.build_pve_template import (
    build_cloud_image_pipeline_via_backend,
    build_pve_template_via_backend,
)


class ProxBoxRootView(APIRootView):
    """Plugin API root with a link to nested endpoint routes."""

    def get_view_name(self) -> str:
        """Human-readable title for the plugin API root schema."""
        return "ProxBox"

    def get(self, request: Request, *args: object, **kwargs: object) -> Response:
        """Augment the default API root payload with all plugin endpoint URLs."""
        response = super().get(request, *args, **kwargs)
        base = f"{request.build_absolute_uri('/').rstrip('/')}/api/plugins/proxbox"
        response.data["endpoints"] = f"{base}/endpoints/"
        response.data["settings"] = f"{base}/settings/"
        response.data["home"] = f"{base}/home/"
        response.data["dashboard"] = f"{base}/dashboard/"
        response.data["resources"] = {
            "clusters": f"{base}/resources/clusters/",
            "nodes": f"{base}/resources/nodes/",
            "virtual_machines": f"{base}/resources/virtual-machines/",
            "lxc_containers": f"{base}/resources/lxc-containers/",
            "vm_templates": f"{base}/vm-templates/",
            "firecracker_microvms": f"{base}/resources/firecracker-microvms/",
            "interfaces": f"{base}/resources/interfaces/",
            "guest_vm_interfaces": f"{base}/guest-vm-interfaces/",
            "guest_vm_interface_addresses": (f"{base}/guest-vm-interface-addresses/"),
            "ip_addresses": f"{base}/resources/ip-addresses/",
            "virtual_disks": f"{base}/resources/virtual-disks/",
        }
        response.data["schedule_sync"] = f"{base}/sync/schedule/"
        response.data["logs"] = f"{base}/logs/"
        response.data["cloud_image_templates"] = f"{base}/cloud-image-templates/"
        response.data["metrics_influxdb"] = f"{base}/metrics-influxdb/"
        response.data["firecracker"] = {
            "host_pools": f"{base}/firecracker-host-pools/",
            "hosts": f"{base}/firecracker-hosts/",
            "image_templates": f"{base}/firecracker-image-templates/",
            "microvms": f"{base}/firecracker-microvms/",
        }
        response.data["sync_state"] = {
            "virtual_machines": f"{base}/sync-state/virtual-machines/",
            "devices": f"{base}/sync-state/devices/",
            "clusters": f"{base}/sync-state/clusters/",
            "ip_addresses": f"{base}/sync-state/ip-addresses/",
            "interfaces": f"{base}/sync-state/interfaces/",
            "vlans": f"{base}/sync-state/vlans/",
            "cluster_groups": f"{base}/sync-state/cluster-groups/",
            "virtual_disks": f"{base}/sync-state/virtual-disks/",
            "vm_interfaces": f"{base}/sync-state/vm-interfaces/",
            "device_roles": f"{base}/sync-state/device-roles/",
            "device_types": f"{base}/sync-state/device-types/",
            "manufacturers": f"{base}/sync-state/manufacturers/",
            "sites": f"{base}/sync-state/sites/",
            "cluster_types": f"{base}/sync-state/cluster-types/",
        }
        response.data["ha"] = {
            "summary": f"{base}/ha/summary/",
            "vm": f"{base}/ha/vm/",
        }
        return response


class ProxBoxEndpointsView(APIRootView):
    """Nested root for Proxmox / NetBox / FastAPI endpoint viewsets."""

    def get_view_name(self) -> str:
        """Title for the nested endpoints API root."""
        return "Endpoints"


class ProxboxPluginSettingsViewSet(NetBoxModelViewSet):
    """REST API for ProxBox plugin settings (singleton)."""

    queryset = models.ProxboxPluginSettings.objects.all().order_by("id")
    serializer_class = ProxboxPluginSettingsSerializer
    http_method_names = ["get", "patch", "head", "options"]

    def get_permissions(self):
        if self.request.method in ("GET", "HEAD", "OPTIONS"):
            return [IsAuthenticated()]
        return super().get_permissions()

    @action(detail=False, methods=["get"], url_path="runtime")
    def runtime(self, request: Request) -> Response:
        """Return the singleton settings row in the backend runtime shape."""
        settings_obj = models.ProxboxPluginSettings.get_solo()
        data = dict(self.get_serializer(settings_obj).data)
        encryption_key = settings_obj.encryption_key or ""
        data["encryption_key_configured"] = bool(encryption_key)
        data["encryption_key"] = (
            encryption_key if _user_can_read_runtime_secret(request.user) else ""
        )
        return Response(data)


def _user_can_read_runtime_secret(user: object) -> bool:
    """Return whether the API caller may read backend-only sensitive settings."""
    if getattr(user, "is_superuser", False):
        return True
    has_perm = getattr(user, "has_perm", None)
    return bool(
        callable(has_perm)
        and has_perm(get_permission_for_model(models.ProxboxPluginSettings, "change"))
    )


class VMBackupViewSet(NetBoxModelViewSet):
    """REST API for VM backup rows synced from Proxmox."""

    queryset = models.VMBackup.objects.select_related(
        "virtual_machine", "proxmox_storage", "proxmox_storage__cluster"
    )
    serializer_class = VMBackupSerializer
    filterset_class = filtersets.VMBackupFilterSet


class CloudImageTemplateViewSet(NetBoxModelViewSet):
    """REST API for tenant-scoped Cloud Portal cloud image templates."""

    queryset = models.CloudImageTemplate.objects.select_related(
        "cluster",
    ).prefetch_related("allowed_tenants", "tags")
    serializer_class = CloudImageTemplateSerializer
    filterset_class = filtersets.CloudImageTemplateFilterSet


class FirecrackerHostPoolViewSet(NetBoxModelViewSet):
    """REST API for Firecracker host pools."""

    queryset = models.FirecrackerHostPool.objects.prefetch_related(
        "allowed_tenants",
        "tags",
    )
    serializer_class = FirecrackerHostPoolSerializer
    filterset_class = filtersets.FirecrackerHostPoolFilterSet


class FirecrackerHostViewSet(NetBoxModelViewSet):
    """REST API for Firecracker host-agent VMs."""

    queryset = models.FirecrackerHost.objects.select_related(
        "pool",
        "host_vm",
        "proxmox_node",
    ).prefetch_related("tags")
    serializer_class = FirecrackerHostSerializer
    filterset_class = filtersets.FirecrackerHostFilterSet


class FirecrackerImageTemplateViewSet(NetBoxModelViewSet):
    """REST API for Firecracker kernel/rootfs image templates."""

    queryset = models.FirecrackerImageTemplate.objects.prefetch_related(
        "allowed_tenants",
        "tags",
    )
    serializer_class = FirecrackerImageTemplateSerializer
    filterset_class = filtersets.FirecrackerImageTemplateFilterSet


class FirecrackerMicroVMViewSet(NetBoxModelViewSet):
    """REST API for Firecracker micro-VM instances."""

    queryset = models.FirecrackerMicroVM.objects.select_related(
        "tenant",
        "host",
        "host__pool",
        "image",
    ).prefetch_related("tags")
    serializer_class = FirecrackerMicroVMSerializer
    filterset_class = filtersets.FirecrackerMicroVMFilterSet


class VMSnapshotViewSet(NetBoxModelViewSet):
    """REST API for VM snapshot rows synced from Proxmox."""

    queryset = models.VMSnapshot.objects.select_related(
        "virtual_machine", "proxmox_storage", "proxmox_storage__cluster"
    )
    serializer_class = VMSnapshotSerializer
    filterset_class = filtersets.VMSnapshotFilterSet


class VMTaskHistoryViewSet(NetBoxModelViewSet):
    """REST API for VM task history rows synced from Proxmox."""

    queryset = models.VMTaskHistory.objects.select_related("virtual_machine")
    serializer_class = VMTaskHistorySerializer
    filterset_class = filtersets.VMTaskHistoryFilterSet


class ProxmoxVMCloudInitViewSet(NetBoxModelViewSet):
    """REST API for Proxmox VM cloud-init rows (issue #363).

    proxbox-api writes ciuser/sshkeys/ipconfig0 here after each per-VM sync.
    The NetBox UI keeps the row read-only via disabled form fields; the API
    inherits NetBox's standard object-level permissions.
    """

    queryset = models.ProxmoxVMCloudInit.objects.select_related("virtual_machine")
    serializer_class = ProxmoxVMCloudInitSerializer
    filterset_class = filtersets.ProxmoxVMCloudInitFilterSet


class ProxmoxVMTemplateViewSet(NetBoxModelViewSet):
    """REST API for dedicated Proxmox VM template inventory."""

    queryset = models.ProxmoxVMTemplate.objects.select_related(
        "proxmox_endpoint",
        "cluster",
        "node",
        "source_vm",
    ).prefetch_related("cloned_vms", "tags")
    serializer_class = ProxmoxVMTemplateSerializer
    filterset_class = filtersets.ProxmoxVMTemplateFilterSet


class ProxmoxMetricsInfluxDBViewSet(NetBoxModelViewSet):
    """REST API for Proxmox cluster InfluxDB metrics endpoint metadata."""

    queryset = models.ProxmoxMetricsInfluxDB.objects.select_related(
        "endpoint",
        "proxmox_cluster",
    ).prefetch_related("tags")
    serializer_class = ProxmoxMetricsInfluxDBSerializer
    filterset_class = filtersets.ProxmoxMetricsInfluxDBFilterSet


class ProxmoxStorageViewSet(NetBoxModelViewSet):
    """REST API for Proxmox storage rows synced from Proxmox endpoints."""

    queryset = models.ProxmoxStorage.objects.select_related("cluster")
    serializer_class = ProxmoxStorageSerializer
    filterset_class = filtersets.ProxmoxStorageFilterSet


class GuestVMInterfaceViewSet(NetBoxModelViewSet):
    """REST API for guest OS VM interfaces reported by the QEMU guest agent."""

    queryset = models.GuestVMInterface.objects.select_related(
        "virtual_machine",
        "vm_interface",
    ).prefetch_related("addresses", "tags")
    serializer_class = GuestVMInterfaceSerializer
    filterset_class = filtersets.GuestVMInterfaceFilterSet


class GuestVMInterfaceAddressViewSet(NetBoxModelViewSet):
    """REST API for guest OS interface to shared IPAddress links."""

    queryset = models.GuestVMInterfaceAddress.objects.select_related(
        "guest_interface",
        "guest_interface__virtual_machine",
        "guest_interface__vm_interface",
        "ip_address",
    ).prefetch_related("tags")
    serializer_class = GuestVMInterfaceAddressSerializer
    filterset_class = filtersets.GuestVMInterfaceAddressFilterSet


class _ParentRestrictedSyncStateViewSetMixin:
    """Restrict sidecar rows by the caller's visibility to the parent object."""

    parent_field_name: str

    def get_queryset(self):
        queryset = super().get_queryset()
        request = getattr(self, "request", None)
        user = getattr(request, "user", None)
        parent_field = queryset.model._meta.get_field(self.parent_field_name)
        parent_model = parent_field.remote_field.model
        parent_queryset = parent_model.objects.all()
        if user is not None and hasattr(parent_queryset, "restrict"):
            parent_queryset = parent_queryset.restrict(user, "view")
        return queryset.filter(
            **{f"{self.parent_field_name}__in": parent_queryset.values("pk")}
        )


class _RelationRestrictedSyncStateViewSetMixin(_ParentRestrictedSyncStateViewSetMixin):
    """Restrict sidecar rows that would expose hidden writable relations."""

    restricted_relation_fields: tuple[str, ...] = ()

    def get_queryset(self):
        queryset = super().get_queryset()
        request = getattr(self, "request", None)
        user = getattr(request, "user", None)
        for field_name in self.restricted_relation_fields:
            relation_field = queryset.model._meta.get_field(field_name)
            relation_model = relation_field.remote_field.model
            relation_queryset = relation_model.objects.all()
            if user is not None and hasattr(relation_queryset, "restrict"):
                relation_queryset = relation_queryset.restrict(user, "view")
            queryset = queryset.filter(
                Q(**{f"{field_name}__isnull": True})
                | Q(**{f"{field_name}__in": relation_queryset.values("pk")})
            )
        return queryset


class ProxboxVirtualMachineSyncStateViewSet(
    _ParentRestrictedSyncStateViewSetMixin,
    NetBoxModelViewSet,
):
    """REST API for typed Proxbox VM custom-field sync state."""

    parent_field_name = "virtual_machine"
    queryset = models.ProxboxVirtualMachineSyncState.objects.select_related(
        "virtual_machine",
        "endpoint",
        "proxmox_node",
        "proxmox_node__endpoint",
        "proxmox_cluster",
        "proxmox_cluster__endpoint",
    )
    serializer_class = ProxboxVirtualMachineSyncStateSerializer
    filterset_class = filtersets.ProxboxVirtualMachineSyncStateFilterSet


class ProxboxDeviceSyncStateViewSet(
    _ParentRestrictedSyncStateViewSetMixin,
    NetBoxModelViewSet,
):
    """REST API for typed Proxbox device custom-field sync state."""

    parent_field_name = "device"
    queryset = models.ProxboxDeviceSyncState.objects.select_related(
        "device",
        "endpoint",
        "proxmox_node",
        "proxmox_node__endpoint",
        "proxmox_cluster",
        "proxmox_cluster__endpoint",
    )
    serializer_class = ProxboxDeviceSyncStateSerializer
    filterset_class = filtersets.ProxboxDeviceSyncStateFilterSet


class ProxboxClusterSyncStateViewSet(
    _ParentRestrictedSyncStateViewSetMixin,
    NetBoxModelViewSet,
):
    """REST API for typed Proxbox cluster custom-field sync state."""

    parent_field_name = "cluster"
    queryset = models.ProxboxClusterSyncState.objects.select_related(
        "cluster",
        "proxmox_cluster",
        "proxmox_cluster__endpoint",
    )
    serializer_class = ProxboxClusterSyncStateSerializer
    filterset_class = filtersets.ProxboxClusterSyncStateFilterSet


class ProxboxIPAddressSyncStateViewSet(
    _ParentRestrictedSyncStateViewSetMixin,
    NetBoxModelViewSet,
):
    """REST API for typed Proxbox IP address custom-field sync state."""

    parent_field_name = "ip_address"
    queryset = models.ProxboxIPAddressSyncState.objects.select_related("ip_address")
    serializer_class = ProxboxIPAddressSyncStateSerializer
    filterset_class = filtersets.ProxboxIPAddressSyncStateFilterSet


class ProxboxInterfaceSyncStateViewSet(
    _ParentRestrictedSyncStateViewSetMixin,
    NetBoxModelViewSet,
):
    """REST API for typed Proxbox interface custom-field sync state."""

    parent_field_name = "interface"
    queryset = models.ProxboxInterfaceSyncState.objects.select_related(
        "interface",
        "interface__device",
    )
    serializer_class = ProxboxInterfaceSyncStateSerializer
    filterset_class = filtersets.ProxboxInterfaceSyncStateFilterSet


class ProxboxVLANSyncStateViewSet(
    _ParentRestrictedSyncStateViewSetMixin,
    NetBoxModelViewSet,
):
    """REST API for typed Proxbox VLAN custom-field sync state."""

    parent_field_name = "vlan"
    queryset = models.ProxboxVLANSyncState.objects.select_related("vlan")
    serializer_class = ProxboxVLANSyncStateSerializer
    filterset_class = filtersets.ProxboxVLANSyncStateFilterSet


class ProxboxClusterGroupSyncStateViewSet(
    _ParentRestrictedSyncStateViewSetMixin,
    NetBoxModelViewSet,
):
    """REST API for typed Proxbox cluster-group custom-field sync state."""

    parent_field_name = "cluster_group"
    queryset = models.ProxboxClusterGroupSyncState.objects.select_related(
        "cluster_group",
    )
    serializer_class = ProxboxClusterGroupSyncStateSerializer
    filterset_class = filtersets.ProxboxClusterGroupSyncStateFilterSet


class ProxboxVirtualDiskSyncStateViewSet(
    _RelationRestrictedSyncStateViewSetMixin,
    NetBoxModelViewSet,
):
    """REST API for typed Proxbox virtual-disk custom-field sync state."""

    parent_field_name = "virtual_disk"
    restricted_relation_fields = ("proxbox_storage",)
    queryset = models.ProxboxVirtualDiskSyncState.objects.select_related(
        "virtual_disk",
        "virtual_disk__virtual_machine",
        "proxbox_storage",
        "proxbox_storage__cluster",
    )
    serializer_class = ProxboxVirtualDiskSyncStateSerializer
    filterset_class = filtersets.ProxboxVirtualDiskSyncStateFilterSet


class ProxboxVMInterfaceSyncStateViewSet(
    _RelationRestrictedSyncStateViewSetMixin,
    NetBoxModelViewSet,
):
    """REST API for typed Proxbox VM-interface custom-field sync state."""

    parent_field_name = "vm_interface"
    restricted_relation_fields = ("proxbox_bridge",)
    queryset = models.ProxboxVMInterfaceSyncState.objects.select_related(
        "vm_interface",
        "vm_interface__virtual_machine",
        "proxbox_bridge",
        "proxbox_bridge__device",
    )
    serializer_class = ProxboxVMInterfaceSyncStateSerializer
    filterset_class = filtersets.ProxboxVMInterfaceSyncStateFilterSet


class ProxboxDeviceRoleSyncStateViewSet(
    _ParentRestrictedSyncStateViewSetMixin,
    NetBoxModelViewSet,
):
    """REST API for typed Proxbox device-role custom-field sync state."""

    parent_field_name = "device_role"
    queryset = models.ProxboxDeviceRoleSyncState.objects.select_related("device_role")
    serializer_class = ProxboxDeviceRoleSyncStateSerializer
    filterset_class = filtersets.ProxboxDeviceRoleSyncStateFilterSet


class ProxboxDeviceTypeSyncStateViewSet(
    _ParentRestrictedSyncStateViewSetMixin,
    NetBoxModelViewSet,
):
    """REST API for typed Proxbox device-type custom-field sync state."""

    parent_field_name = "device_type"
    queryset = models.ProxboxDeviceTypeSyncState.objects.select_related("device_type")
    serializer_class = ProxboxDeviceTypeSyncStateSerializer
    filterset_class = filtersets.ProxboxDeviceTypeSyncStateFilterSet


class ProxboxManufacturerSyncStateViewSet(
    _ParentRestrictedSyncStateViewSetMixin,
    NetBoxModelViewSet,
):
    """REST API for typed Proxbox manufacturer custom-field sync state."""

    parent_field_name = "manufacturer"
    queryset = models.ProxboxManufacturerSyncState.objects.select_related(
        "manufacturer",
    )
    serializer_class = ProxboxManufacturerSyncStateSerializer
    filterset_class = filtersets.ProxboxManufacturerSyncStateFilterSet


class ProxboxSiteSyncStateViewSet(
    _ParentRestrictedSyncStateViewSetMixin,
    NetBoxModelViewSet,
):
    """REST API for typed Proxbox site custom-field sync state."""

    parent_field_name = "site"
    queryset = models.ProxboxSiteSyncState.objects.select_related("site")
    serializer_class = ProxboxSiteSyncStateSerializer
    filterset_class = filtersets.ProxboxSiteSyncStateFilterSet


class ProxboxClusterTypeSyncStateViewSet(
    _ParentRestrictedSyncStateViewSetMixin,
    NetBoxModelViewSet,
):
    """REST API for typed Proxbox cluster-type custom-field sync state."""

    parent_field_name = "cluster_type"
    queryset = models.ProxboxClusterTypeSyncState.objects.select_related(
        "cluster_type",
    )
    serializer_class = ProxboxClusterTypeSyncStateSerializer
    filterset_class = filtersets.ProxboxClusterTypeSyncStateFilterSet


class ProxmoxEndpointViewSet(NetBoxModelViewSet):
    """REST API for Proxmox VE API endpoint credentials and targets."""

    queryset = models.ProxmoxEndpoint.objects.select_related(
        "ip_address", "site", "tenant"
    ).prefetch_related("allowed_tenants")
    serializer_class = ProxmoxEndpointSerializer
    filterset_class = filtersets.ProxmoxEndpointFilterSet

    @extend_schema(
        request=PVETemplateBuildRequestSerializer,
        responses={
            201: PVETemplateBuildResponseSerializer,
            502: OpenApiTypes.OBJECT,
            503: OpenApiTypes.OBJECT,
        },
        operation_id="proxbox_proxmox_endpoint_build_pve_template",
    )
    @action(
        detail=True,
        methods=["post"],
        url_path="build-pve-template",
        url_name="build-pve-template",
        permission_classes=[IsAuthenticated],
    )
    def build_pve_template(self, request: Request, pk: int | None = None) -> Response:
        """Trigger a PVE-installer cloud-init template build via proxbox-api.

        Validates the request body against ``PVETemplateBuildRequestSerializer``,
        injects ``endpoint_id`` from the URL path, then proxies the call to
        the Cloud Image Build Pipeline compatibility endpoint on proxbox-api.
        The response is the upstream body verbatim — including the rendered
        build script and cloud-init snippets for the target host.
        """
        endpoint = self.get_object()
        serializer = PVETemplateBuildRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = dict(serializer.validated_data)
        payload["endpoint_id"] = endpoint.pk
        body, status_code = build_pve_template_via_backend(payload)
        return Response(body, status=status_code)

    @extend_schema(
        request=PVETemplateBuildRequestSerializer,
        responses={
            200: PVETemplateBuildResponseSerializer,
            201: PVETemplateBuildResponseSerializer,
            403: OpenApiTypes.OBJECT,
            502: OpenApiTypes.OBJECT,
            503: OpenApiTypes.OBJECT,
        },
        operation_id="proxbox_proxmox_endpoint_cloud_image_build_pipeline",
    )
    @action(
        detail=True,
        methods=["post"],
        url_path="cloud-image-build-pipeline",
        url_name="cloud-image-build-pipeline",
        permission_classes=[IsAuthenticated],
    )
    def cloud_image_build_pipeline(
        self,
        request: Request,
        pk: int | None = None,
    ) -> Response:
        """Trigger the Cloud Image Build Pipeline via proxbox-api."""
        endpoint = self.get_object()
        serializer = PVETemplateBuildRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = dict(serializer.validated_data)
        payload["endpoint_id"] = endpoint.pk
        body, status_code = build_cloud_image_pipeline_via_backend(payload)
        return Response(body, status=status_code)


class ProxmoxServiceMonitoringRefreshAPIView(APIView):
    """Queue an on-demand systemctl service collection for one endpoint."""

    permission_classes = [IsAuthenticated]
    http_method_names = ["post", "head", "options"]

    def post(self, request: Request, endpoint_id: int) -> Response:
        """Mirror the Services tab refresh button for API clients."""
        if not request.user.has_perm(
            get_permission_for_model(models.ProxmoxEndpoint, "change")
        ):
            return Response(
                {
                    "detail": "Missing permission to change Proxmox endpoints.",
                },
                status=drf_status.HTTP_403_FORBIDDEN,
            )

        try:
            endpoint = models.ProxmoxEndpoint.objects.restrict(
                request.user,
                "change",
            ).get(pk=endpoint_id)
        except models.ProxmoxEndpoint.DoesNotExist:
            return Response(
                {"detail": "Proxmox endpoint not found."},
                status=drf_status.HTTP_404_NOT_FOUND,
            )

        if not endpoint.service_monitoring_enabled:
            return Response(
                {"detail": "Service monitoring is disabled for this endpoint."},
                status=drf_status.HTTP_400_BAD_REQUEST,
            )

        from netbox_proxbox.services.endpoint_enabled import endpoint_is_enabled

        if not endpoint_is_enabled(endpoint):
            return Response(
                {
                    "detail": "Endpoint is disabled; disabled endpoints are never contacted."
                },
                status=drf_status.HTTP_400_BAD_REQUEST,
            )

        if not endpoint.service_monitoring_eligible:
            return Response(
                {
                    "detail": (
                        "Service monitoring requires allow_writes, API + SSH "
                        "access, complete endpoint SSH credentials, and "
                        "netbox-rpc enabled for this endpoint."
                    )
                },
                status=drf_status.HTTP_400_BAD_REQUEST,
            )

        from netbox_proxbox.integrations.rpc import collect_systemctl_services

        execution = collect_systemctl_services(
            endpoint,
            requested_by=request.user,
            trigger="on_demand",
        )
        if execution is None:
            return Response(
                {
                    "detail": (
                        "Service monitoring collection could not be queued. "
                        "Confirm netbox-rpc is installed and the procedure is enabled."
                    )
                },
                status=drf_status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response(
            {
                "status": "queued",
                "rpc_execution_id": getattr(execution, "pk", None),
            },
            status=drf_status.HTTP_202_ACCEPTED,
        )


class ProxmoxServiceCollectionViewSet(NetBoxModelViewSet):
    """Read-only REST API for service-monitoring collection history."""

    queryset = models.ProxmoxServiceCollection.objects.select_related("endpoint")
    serializer_class = ProxmoxServiceCollectionSerializer
    http_method_names = ["get", "head", "options"]


class ProxmoxServiceSampleViewSet(NetBoxModelViewSet):
    """Read-only REST API for raw service-monitoring samples."""

    queryset = models.ProxmoxServiceSample.objects.select_related(
        "collection",
        "collection__endpoint",
    )
    serializer_class = ProxmoxServiceSampleSerializer
    http_method_names = ["get", "head", "options"]


class ProxmoxServiceStatusViewSet(NetBoxModelViewSet):
    """Read-only REST API for latest projected service state."""

    queryset = models.ProxmoxServiceStatus.objects.select_related("endpoint")
    serializer_class = ProxmoxServiceStatusSerializer
    http_method_names = ["get", "head", "options"]


class NetBoxEndpointViewSet(NetBoxModelViewSet):
    """REST API for remote NetBox API endpoint configuration."""

    queryset = models.NetBoxEndpoint.objects.select_related("ip_address", "token")
    serializer_class = NetBoxEndpointSerializer
    filterset_class = filtersets.NetBoxEndpointFilterSet


class FastAPIEndpointViewSet(NetBoxModelViewSet):
    """REST API for ProxBox FastAPI backend (HTTP/WebSocket) endpoints."""

    queryset = models.FastAPIEndpoint.objects.select_related("ip_address")
    serializer_class = FastAPIEndpointSerializer
    filterset_class = filtersets.FastAPIEndpointFilterSet


class ProxmoxClusterViewSet(NetBoxModelViewSet):
    """REST API for Proxmox cluster tracking linked to NetBox clusters."""

    queryset = models.ProxmoxCluster.objects.select_related(
        "endpoint", "netbox_cluster"
    )
    serializer_class = ProxmoxClusterSerializer
    filterset_class = filtersets.ProxmoxClusterFilterSet


class ProxmoxNodeViewSet(NetBoxModelViewSet):
    """REST API for Proxmox node tracking linked to NetBox devices."""

    queryset = models.ProxmoxNode.objects.select_related(
        "endpoint", "proxmox_cluster", "netbox_device"
    )
    serializer_class = ProxmoxNodeSerializer
    filterset_class = filtersets.ProxmoxNodeFilterSet


class BackupRoutineViewSet(NetBoxModelViewSet):
    """REST API for Proxmox backup routine schedules synced from Proxmox."""

    queryset = models.BackupRoutine.objects.select_related(
        "endpoint",
        "node",
        "storage",
        "storage__cluster",
        "fleecing_storage",
        "fleecing_storage__cluster",
    )
    serializer_class = BackupRoutineSerializer
    filterset_class = filtersets.BackupRoutineFilterSet


class ReplicationViewSet(NetBoxModelViewSet):
    """REST API for Proxmox replication schedules synced from Proxmox."""

    queryset = models.Replication.objects.select_related(
        "virtual_machine", "proxmox_node"
    )
    serializer_class = ReplicationSerializer
    filterset_class = filtersets.ReplicationFilterSet


class NodeSSHCredentialViewSet(NetBoxModelViewSet):
    """REST API for per-node SSH credentials used by hardware discovery.

    Secrets are write-only on this viewset. Callers that need decrypted
    secrets (the proxbox-api orchestrator) use the dedicated NetBox API-token
    shim at ``/ssh-credentials/by-node/<node_id>/credentials/``.
    """

    queryset = models.NodeSSHCredential.objects.select_related("node")
    serializer_class = NodeSSHCredentialSerializer
    filterset_class = filtersets.NodeSSHCredentialFilterSet


class _ProxboxDashboardPermission(BasePermission):
    """Allow access if the user may view at least one Proxbox endpoint model.

    Unauthenticated users are allowed when ``LOGIN_REQUIRED`` is ``False``
    (matching ``ConditionalLoginRequiredMixin`` behaviour on the UI side).
    """

    def has_permission(self, request: Request, view: object) -> bool:  # type: ignore[override]
        from django.conf import settings as django_settings

        from netbox_proxbox.views.proxbox_access import (
            user_may_access_proxbox_dashboard,
        )

        if not request.user.is_authenticated:
            return not django_settings.LOGIN_REQUIRED
        return user_may_access_proxbox_dashboard(request.user)


def _nested(obj: object, request: Request) -> dict | None:
    if obj is None:
        return None
    try:
        url = request.build_absolute_uri(obj.get_absolute_url())
    except Exception:
        url = None
    return {"id": obj.pk, "name": str(obj), "url": url}


def _serialize_interfaces(interfaces: object, request: Request) -> list[dict]:
    result = []
    for iface in interfaces.all():
        result.append(
            {
                "id": iface.pk,
                "name": iface.name,
                "enabled": iface.enabled,
                "ip_addresses": [str(ip.address) for ip in iface.ip_addresses.all()],
            }
        )
    return result


def _serialize_device(
    device: object, request: Request, proxmox_node: object | None = None
) -> dict:
    result: dict = {
        "id": device.pk,
        "name": str(device.name),
        "url": request.build_absolute_uri(device.get_absolute_url()),
        "status": {"value": device.status, "label": device.get_status_display()},
        "device_type": str(device.device_type) if device.device_type else None,
        "manufacturer": (
            str(device.device_type.manufacturer)
            if device.device_type and device.device_type.manufacturer
            else None
        ),
        "role": _nested(device.role, request),
        "site": _nested(device.site, request),
        "tenant": _nested(device.tenant, request),
        "cluster": _nested(device.cluster, request),
        "interfaces": _serialize_interfaces(device.interfaces, request),
    }
    if proxmox_node is not None:
        result.update(
            {
                "online": proxmox_node.online,
                "ip_address": proxmox_node.ip_address or "",
                "cpu_usage_percent": proxmox_node.cpu_usage_percent,
                "max_cpu": proxmox_node.max_cpu,
                "memory_usage": proxmox_node.memory_usage,
                "memory_usage_percent": proxmox_node.memory_usage_percent,
                "max_memory": proxmox_node.max_memory,
            }
        )
    return result


def _serialize_vm(vm: object, request: Request) -> dict:
    return {
        "id": vm.pk,
        "name": str(vm.name),
        "url": request.build_absolute_uri(vm.get_absolute_url()),
        "site": _nested(vm.site, request),
        "cluster": _nested(vm.cluster, request),
        "role": _nested(vm.role, request),
        "tenant": _nested(vm.tenant, request),
        "platform": _nested(vm.platform, request),
        "interfaces": _serialize_interfaces(vm.interfaces, request),
    }


def _serialize_firecracker_microvm(microvm: object, request: Request) -> dict:
    """Serialize a Firecracker micro-VM in the Cloud resource-list shape."""
    try:
        url = request.build_absolute_uri(microvm.get_absolute_url())
    except Exception:
        url = None
    return {
        "id": microvm.pk,
        "instance_ref": microvm.instance_ref,
        "kind": "firecracker",
        "name": microvm.name,
        "url": url,
        "status": {
            "value": microvm.status,
            "label": microvm.get_status_display(),
        },
        "tenant": _nested(microvm.tenant, request),
        "host": _nested(microvm.host, request),
        "host_pool": _nested(microvm.host.pool, request) if microvm.host_id else None,
        "image": _nested(microvm.image, request),
        "network_mode": {
            "value": microvm.network_mode,
            "label": microvm.get_network_mode_display(),
        },
        "vcpus": microvm.vcpus,
        "memory_mib": microvm.memory_mib,
        "disk_mib": microvm.disk_mib,
        "guest_ip": str(microvm.guest_ip) if microvm.guest_ip else None,
        "mac_address": microvm.mac_address or None,
        "started_at": microvm.started_at.isoformat() if microvm.started_at else None,
        "stopped_at": microvm.stopped_at.isoformat() if microvm.stopped_at else None,
    }


def _serialize_cluster(cluster: object, request: Request) -> dict:
    return {
        "id": cluster.pk,
        "name": str(cluster.name),
        "url": request.build_absolute_uri(cluster.get_absolute_url()),
        "status": cluster.status,
        "type": _nested(cluster.type, request),
        "group": _nested(cluster.group, request),
        "site": _nested(cluster._site, request),
        "tenant": _nested(cluster.tenant, request),
        "device_count": cluster.device_count,
        "vm_count": cluster.vm_count,
    }


def _serialize_job(job: object, request: Request | None = None) -> dict:
    url = None
    if request is not None:
        try:
            url = request.build_absolute_uri(job.get_absolute_url())
        except Exception:
            pass
    return {
        "id": job.pk,
        "name": job.name,
        "status": job.status,
        "created": job.created.isoformat() if job.created else None,
        "url": url,
    }


class HomeAPIView(APIView):
    """API mirror of the Proxbox plugin home page (/plugins/proxbox/).

    Returns endpoint lists, FastAPI URL info, and an active job reference.
    Read-only GET endpoint.
    """

    permission_classes = [_ProxboxDashboardPermission]

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request: Request) -> Response:
        """Return the same data the plugin home page renders."""
        from netbox_proxbox.jobs import PROXBOX_SYNC_QUEUE_NAME, is_proxbox_sync_job
        from netbox_proxbox.schedule_hints import has_recurring_proxbox_sync_all
        from netbox_proxbox.utils import get_fastapi_url
        from netbox_proxbox.views.home_context import build_companion_endpoint_groups
        from core.choices import JobStatusChoices
        from core.models import Job

        proxmox_qs = models.ProxmoxEndpoint.objects.restrict(
            request.user, "view"
        ).order_by("id")
        netbox_qs = models.NetBoxEndpoint.objects.restrict(
            request.user, "view"
        ).order_by("id")
        fastapi_qs = models.FastAPIEndpoint.objects.restrict(
            request.user, "view"
        ).order_by("id")

        fastapi_info: dict = {}
        fastapi_obj = fastapi_qs.first()
        if fastapi_obj is not None:
            fastapi_info = get_fastapi_url(fastapi_obj) or {}

        from django.db.models import Q as DbQ
        from netbox_proxbox.jobs import LEGACY_PROXBOX_RQ_QUEUE

        # Find newest running/queued proxbox sync job visible to this user.
        # Pre-filter by queue or name to avoid scanning unrelated jobs.
        active_job = None
        for job in (
            Job.objects.restrict(request.user, "view")
            .filter(
                status__in=JobStatusChoices.ENQUEUED_STATE_CHOICES,
            )
            .filter(
                DbQ(queue_name__in=[PROXBOX_SYNC_QUEUE_NAME, LEGACY_PROXBOX_RQ_QUEUE])
                | DbQ(name="Proxbox Sync")
            )
            .order_by("-created")
            .iterator(chunk_size=32)
        ):
            if is_proxbox_sync_job(job):
                active_job = job
                break

        def _endpoint_dict(ep: object) -> dict:
            return {
                "id": ep.pk,
                "name": str(ep.name),
                "url": request.build_absolute_uri(ep.get_absolute_url()),
                "domain": getattr(ep, "domain", None),
                "ip_address": str(ep.ip_address) if ep.ip_address else None,
            }

        return Response(
            {
                "proxmox_endpoints": [_endpoint_dict(ep) for ep in proxmox_qs],
                "netbox_endpoints": [_endpoint_dict(ep) for ep in netbox_qs],
                "fastapi_endpoints": [_endpoint_dict(ep) for ep in fastapi_qs],
                "fastapi_url": fastapi_info.get("http_url", ""),
                "fastapi_websocket_url": fastapi_info.get("websocket_url", ""),
                "companion_endpoint_groups": build_companion_endpoint_groups(
                    request, absolute_urls=True
                ),
                "show_quick_full_sync_banner": not has_recurring_proxbox_sync_all(
                    request.user
                ),
                "active_proxbox_job": (
                    _serialize_job(active_job, request) if active_job else None
                ),
            }
        )


class DashboardAPIView(APIView):
    """API mirror of the Proxbox operational dashboard (/plugins/proxbox/dashboard/).

    Returns live cluster summaries, node status rows, and guest counts fetched
    from the proxbox-api backend. May be slow due to external HTTP calls.
    Read-only GET endpoint.
    """

    permission_classes = [_ProxboxDashboardPermission]
    _request_timeout = 8

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request: Request) -> Response:
        """Return the same aggregated data the dashboard page renders."""
        import requests as http_requests

        from netbox_proxbox.utils import get_backend_auth_headers, get_fastapi_url
        from netbox_proxbox.views import dashboard_data
        from netbox_proxbox.views.backend_sync import (
            resolve_backend_endpoint_id,
            sync_proxmox_endpoint_to_backend,
        )
        from netbox_proxbox.views.error_utils import (
            extract_proxmox_backend_error_detail,
            parse_requests_response_json,
        )
        from virtualization.models import Cluster

        proxmox_endpoints = list(
            models.ProxmoxEndpoint.objects.restrict(request.user, "view").filter(
                enabled=True
            )
        )
        fastapi_endpoint = (
            models.FastAPIEndpoint.objects.restrict(request.user, "view")
            .filter(enabled=True)
            .first()
        )

        fastapi_url = None
        backend_verify_ssl = True
        backend_headers: dict = {}
        if fastapi_endpoint:
            fastapi_info = get_fastapi_url(fastapi_endpoint) or {}
            fastapi_url = fastapi_info.get("http_url")
            backend_verify_ssl = bool(fastapi_info.get("verify_ssl", True))
            backend_headers = get_backend_auth_headers(fastapi_endpoint)

        dashboards: list[dict] = []
        for endpoint in proxmox_endpoints:
            entry: dict = {
                "endpoint": {
                    "id": endpoint.pk,
                    "name": str(endpoint.name),
                    "url": request.build_absolute_uri(endpoint.get_absolute_url()),
                    "domain": endpoint.domain,
                    "ip_address": (
                        str(endpoint.ip_address).split("/")[0]
                        if endpoint.ip_address
                        else None
                    ),
                },
                "cluster_summary": None,
                "guest_summary": None,
                "nodes": [],
                "netbox_cluster": None,
                "object_summaries": [],
                "detail": None,
            }

            if not fastapi_url:
                entry["detail"] = "No FastAPI backend URL is configured."
                dashboards.append(entry)
                continue

            sync_ok, sync_detail, _ = sync_proxmox_endpoint_to_backend(
                endpoint,
                base_url=fastapi_url,
                auth_headers=backend_headers,
                backend_verify_ssl=backend_verify_ssl,
                timeout=self._request_timeout,
            )
            if not sync_ok:
                entry["detail"] = sync_detail
                dashboards.append(entry)
                continue

            backend_endpoint_id, resolve_error = resolve_backend_endpoint_id(
                endpoint,
                base_url=fastapi_url,
                auth_headers=backend_headers,
                backend_verify_ssl=backend_verify_ssl,
                timeout=self._request_timeout,
            )
            if backend_endpoint_id is None:
                entry["detail"] = (
                    resolve_error
                    or "Failed to resolve Proxmox endpoint on ProxBox backend."
                )
                dashboards.append(entry)
                continue

            query_params: dict = {
                "source": "database",
                "proxmox_endpoint_ids": str(backend_endpoint_id),
            }

            def _fetch(route: str) -> tuple[object, str | None]:
                resp = http_requests.get(
                    f"{fastapi_url}{route}",
                    params=query_params,
                    headers=backend_headers,
                    verify=backend_verify_ssl,
                    timeout=self._request_timeout,
                    allow_redirects=False,
                )
                resp.raise_for_status()
                return parse_requests_response_json(resp, log_label=route)

            try:
                cluster_payload, cluster_err = _fetch("/proxmox/cluster/status")
                resources_payload, resources_err = _fetch("/proxmox/cluster/resources")
            except http_requests.exceptions.RequestException as exc:
                detail, _ = extract_proxmox_backend_error_detail(
                    exc,
                    proxmox_host=(
                        endpoint.domain or str(endpoint.ip_address).split("/")[0]
                    ),
                    proxmox_port=endpoint.port,
                    backend_url=f"{fastapi_url}/proxmox",
                )
                entry["detail"] = detail
                dashboards.append(entry)
                continue

            cluster_name = None
            cluster_node_names: set = set()
            if not cluster_err:
                cluster_name, cluster_node_names = dashboard_data.cluster_node_scope(
                    cluster_payload
                )

            local_node_rows = dashboard_data.build_local_node_rows(
                endpoint,
                cluster_name=cluster_name,
                cluster_node_names=cluster_node_names,
            )
            live_node_rows: list = []
            nodes_err = None
            try:
                nodes_payload, nodes_err = _fetch("/proxmox/nodes/")
                if not nodes_err:
                    live_node_rows = dashboard_data.build_live_node_rows(nodes_payload)
            except http_requests.exceptions.RequestException as exc:
                if not local_node_rows:
                    detail, _ = extract_proxmox_backend_error_detail(
                        exc,
                        proxmox_host=(
                            endpoint.domain or str(endpoint.ip_address).split("/")[0]
                        ),
                        proxmox_port=endpoint.port,
                        backend_url=f"{fastapi_url}/proxmox",
                    )
                    entry["detail"] = detail
                    dashboards.append(entry)
                    continue

            if cluster_err or resources_err:
                entry["detail"] = cluster_err or resources_err
                dashboards.append(entry)
                continue

            if nodes_err and not local_node_rows:
                entry["detail"] = nodes_err
                dashboards.append(entry)
                continue

            cluster_summary = dashboard_data.build_cluster_summary(cluster_payload)
            entry["guest_summary"] = dashboard_data.build_guest_summary(
                resources_payload
            )

            if local_node_rows:
                entry["nodes"] = dashboard_data.merge_node_rows(
                    local_node_rows, live_node_rows
                )
            else:
                entry["nodes"] = live_node_rows

            entry["cluster_summary"] = dashboard_data.cluster_summary_from_node_rows(
                cluster_summary, entry["nodes"]
            )

            cluster_name_display = (
                entry["cluster_summary"].get("name", "")
                if entry["cluster_summary"]
                else ""
            )
            netbox_cluster = (
                Cluster.objects.filter(name=cluster_name_display).first()
                if cluster_name_display and cluster_name_display != "—"
                else None
            )
            entry["netbox_cluster"] = _nested(netbox_cluster, request)
            entry["object_summaries"] = dashboard_data.build_object_summaries(
                endpoint, netbox_cluster
            )

            dashboards.append(entry)

        return Response({"dashboards": dashboards})


class NodesAPIView(APIView):
    """API mirror of the Proxbox nodes page (/plugins/proxbox/nodes/).

    Returns NetBox Device objects tagged 'proxbox' (synced Proxmox nodes).
    Read-only GET endpoint.
    """

    permission_classes = [IsAuthenticatedOrLoginNotRequired]

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request: Request) -> Response:
        """Return proxbox-tagged devices with their interfaces and IPs."""
        from dcim.models import Device
        from netbox_proxbox.models import ProxmoxNode
        from netbox_proxbox.utils import get_proxbox_tagged_object_ids

        tagged_ids = get_proxbox_tagged_object_ids(Device)[:100]
        if not tagged_ids:
            return Response({"count": 0, "results": []})

        devices = list(
            Device.objects.restrict(request.user, "view")
            .filter(id__in=tagged_ids)
            .select_related(
                "device_type__manufacturer", "role", "site", "tenant", "cluster"
            )
            .prefetch_related("interfaces__ip_addresses")
        )

        # Key by the authoritative FK to avoid collisions when multiple Proxmox endpoints
        # have nodes with the same name (e.g. the default "pve1" across clusters).
        device_ids = [d.pk for d in devices]
        nodes_by_device_id = {
            n.netbox_device_id: n
            for n in ProxmoxNode.objects.filter(netbox_device_id__in=device_ids)
        }

        results = [
            _serialize_device(d, request, proxmox_node=nodes_by_device_id.get(d.pk))
            for d in devices
        ]
        return Response({"count": len(results), "results": results})


class _ProxboxVMListAPIView(APIView):
    """Shared paginated VM resource list view, parameterized by ``vm_type``.

    Requests without ``limit`` or ``offset`` return the full filtered VM set for
    backwards compatibility. Requests with either parameter use DRF
    ``LimitOffsetPagination`` with a default page size of 1000 and max of 5000.
    """

    permission_classes = [IsAuthenticatedOrLoginNotRequired]
    vm_type: str
    vm_type_slug: str

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request: Request) -> Response:
        from virtualization.models import VirtualMachine
        from netbox_proxbox.utils import (
            filter_queryset_by_proxmox_vm_type,
            get_proxbox_tagged_object_ids,
            vm_type_select_related_fields,
        )

        tagged_ids = get_proxbox_tagged_object_ids(VirtualMachine)
        if not tagged_ids:
            return Response({"count": 0, "next": None, "previous": None, "results": []})

        base_qs = (
            VirtualMachine.objects.restrict(request.user, "view")
            .filter(id__in=tagged_ids)
            .select_related(*vm_type_select_related_fields(VirtualMachine))
            .prefetch_related("interfaces__ip_addresses")
        )

        qs = filter_queryset_by_proxmox_vm_type(
            base_qs,
            VirtualMachine,
            vm_type=self.vm_type,
            vm_type_slug=self.vm_type_slug,
        ).order_by("name")

        if "limit" not in request.query_params and "offset" not in request.query_params:
            results = [_serialize_vm(vm, request) for vm in qs]
            return Response(
                {
                    "count": len(results),
                    "next": None,
                    "previous": None,
                    "results": results,
                }
            )

        paginator = LimitOffsetPagination()
        paginator.default_limit = 1000
        paginator.max_limit = 5000
        page = paginator.paginate_queryset(qs, request, view=self)
        results = [_serialize_vm(vm, request) for vm in page]
        return paginator.get_paginated_response(results)


class VirtualMachinesAPIView(_ProxboxVMListAPIView):
    """API mirror of the Proxbox virtual machines page (/plugins/proxbox/virtual_machines/).

    Returns NetBox VirtualMachine objects tagged 'proxbox' with vm_type=qemu.
    Read-only GET endpoint.
    """

    vm_type = ProxmoxVMTypeChoices.QEMU
    vm_type_slug = "qemu-virtual-machine"


class LXCContainersAPIView(_ProxboxVMListAPIView):
    """API mirror of the Proxbox LXC containers page (/plugins/proxbox/lxc_containers/).

    Returns NetBox VirtualMachine objects tagged 'proxbox' with vm_type=lxc.
    Read-only GET endpoint.
    """

    vm_type = ProxmoxVMTypeChoices.LXC
    vm_type_slug = "lxc-container"


class FirecrackerMicroVMsAPIView(APIView):
    """API mirror for Firecracker micro-VM resources exposed to NMS Cloud."""

    permission_classes = [IsAuthenticatedOrLoginNotRequired]

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request: Request) -> Response:
        """Return Firecracker micro-VMs with Cloud-compatible metadata."""
        qs = (
            models.FirecrackerMicroVM.objects.restrict(request.user, "view")
            .select_related("tenant", "host", "host__pool", "image")
            .order_by("name")
        )

        if "limit" not in request.query_params and "offset" not in request.query_params:
            results = [
                _serialize_firecracker_microvm(microvm, request) for microvm in qs
            ]
            return Response(
                {
                    "count": len(results),
                    "next": None,
                    "previous": None,
                    "results": results,
                }
            )

        paginator = LimitOffsetPagination()
        paginator.default_limit = 1000
        paginator.max_limit = 5000
        page = paginator.paginate_queryset(qs, request, view=self)
        results = [_serialize_firecracker_microvm(microvm, request) for microvm in page]
        return paginator.get_paginated_response(results)


class InterfacesAPIView(APIView):
    """API mirror of the Proxbox interfaces page (/plugins/proxbox/interfaces/).

    Returns combined VM interfaces and node interfaces for proxbox-tagged objects,
    with summary counts. Read-only GET endpoint.
    """

    permission_classes = [IsAuthenticatedOrLoginNotRequired]

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request: Request) -> Response:
        """Return proxbox-tagged VM and node interfaces with up/down summary."""
        from dcim.models import Device
        from dcim.models import Interface as DCIMInterface
        from virtualization.models import VirtualMachine, VMInterface
        from netbox_proxbox.utils import get_proxbox_tagged_object_ids

        tagged_device_ids = get_proxbox_tagged_object_ids(Device)
        tagged_vm_ids = get_proxbox_tagged_object_ids(VirtualMachine)

        node_interfaces: list = []
        vm_interfaces: list = []
        interfaces_up = 0
        interfaces_down = 0

        if tagged_device_ids:
            node_interfaces = list(
                DCIMInterface.objects.restrict(request.user, "view")
                .filter(device_id__in=tagged_device_ids)
                .select_related("device")
                .prefetch_related("ip_addresses")
                .order_by("device__name", "name")
            )
            for iface in node_interfaces:
                if iface.enabled:
                    interfaces_up += 1
                else:
                    interfaces_down += 1

        if tagged_vm_ids:
            vm_interfaces = list(
                VMInterface.objects.restrict(request.user, "view")
                .filter(virtual_machine_id__in=tagged_vm_ids)
                .select_related("virtual_machine")
                .prefetch_related("ip_addresses")
                .order_by("virtual_machine__name", "name")
            )
            for iface in vm_interfaces:
                if iface.enabled:
                    interfaces_up += 1
                else:
                    interfaces_down += 1

        def _iface_dict(iface: object, parent_type: str) -> dict:
            parent = iface.device if parent_type == "device" else iface.virtual_machine
            return {
                "id": iface.pk,
                "name": iface.name,
                "enabled": iface.enabled,
                "parent_type": parent_type,
                "parent_name": str(parent) if parent else None,
                "ip_addresses": [str(ip.address) for ip in iface.ip_addresses.all()],
            }

        total = len(node_interfaces) + len(vm_interfaces)
        return Response(
            {
                "node_interfaces": [_iface_dict(i, "device") for i in node_interfaces],
                "vm_interfaces": [_iface_dict(i, "vm") for i in vm_interfaces],
                "summary": {
                    "total": total,
                    "up": interfaces_up,
                    "down": interfaces_down,
                },
            }
        )


class IPAddressesAPIView(APIView):
    """API mirror of the Proxbox IP addresses page (/plugins/proxbox/ip-addresses/).

    Returns IP addresses assigned to proxbox-tagged interfaces, split by node/VM.
    Read-only GET endpoint.
    """

    permission_classes = [IsAuthenticatedOrLoginNotRequired]

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request: Request) -> Response:
        """Return proxbox-tagged node and VM IP addresses with summary counts."""
        from dcim.models import Device
        from dcim.models import Interface as DCIMInterface
        from ipam.models import IPAddress
        from virtualization.models import VirtualMachine, VMInterface
        from netbox_proxbox.utils import get_proxbox_tagged_object_ids

        tagged_device_ids = get_proxbox_tagged_object_ids(Device)
        tagged_vm_ids = get_proxbox_tagged_object_ids(VirtualMachine)

        node_ips: list = []
        vm_ips: list = []

        if tagged_device_ids:
            node_iface_ids = list(
                DCIMInterface.objects.filter(
                    device_id__in=tagged_device_ids
                ).values_list("id", flat=True)
            )
            node_ips = list(
                IPAddress.objects.restrict(request.user, "view")
                .filter(
                    assigned_object_type__app_label="dcim",
                    assigned_object_type__model="interface",
                    assigned_object_id__in=node_iface_ids,
                )
                .prefetch_related("assigned_object")
                .order_by("address")
            )

        if tagged_vm_ids:
            vm_iface_ids = list(
                VMInterface.objects.filter(
                    virtual_machine_id__in=tagged_vm_ids
                ).values_list("id", flat=True)
            )
            vm_ips = list(
                IPAddress.objects.restrict(request.user, "view")
                .filter(
                    assigned_object_type__app_label="virtualization",
                    assigned_object_type__model="vminterface",
                    assigned_object_id__in=vm_iface_ids,
                )
                .prefetch_related("assigned_object")
                .order_by("address")
            )

        def _ip_dict(ip: object) -> dict:
            assigned = ip.assigned_object
            ct = ip.assigned_object_type
            return {
                "id": ip.pk,
                "address": str(ip.address),
                "assigned_object_type": (f"{ct.app_label}.{ct.model}" if ct else None),
                "assigned_object_id": ip.assigned_object_id,
                "assigned_object_name": str(assigned) if assigned else None,
            }

        return Response(
            {
                "node_ips": [_ip_dict(ip) for ip in node_ips],
                "vm_ips": [_ip_dict(ip) for ip in vm_ips],
                "summary": {
                    "node_count": len(node_ips),
                    "vm_count": len(vm_ips),
                    "total": len(node_ips) + len(vm_ips),
                },
            }
        )


class VirtualDisksAPIView(APIView):
    """API mirror of the Proxbox virtual disks page (/plugins/proxbox/virtual-disks/).

    Returns VirtualDisk objects whose parent VM is tagged 'proxbox'.
    Read-only GET endpoint.
    """

    permission_classes = [IsAuthenticatedOrLoginNotRequired]

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request: Request) -> Response:
        """Return virtual disks for proxbox-tagged VMs."""
        from virtualization.models import VirtualDisk, VirtualMachine
        from netbox_proxbox.utils import get_proxbox_tagged_object_ids

        tagged_vm_ids = get_proxbox_tagged_object_ids(VirtualMachine)
        if not tagged_vm_ids:
            return Response({"count": 0, "results": []})

        disks = list(
            VirtualDisk.objects.restrict(request.user, "view")
            .filter(virtual_machine_id__in=tagged_vm_ids)
            .select_related("virtual_machine")
            .order_by("virtual_machine__name", "name")
        )
        results = [
            {
                "id": d.pk,
                "name": d.name,
                "size": d.size,
                "virtual_machine": {
                    "id": d.virtual_machine.pk,
                    "name": str(d.virtual_machine.name),
                    "url": request.build_absolute_uri(
                        d.virtual_machine.get_absolute_url()
                    ),
                },
            }
            for d in disks
        ]
        return Response({"count": len(results), "results": results})


class ClustersAPIView(APIView):
    """API mirror of the Proxbox clusters page (/plugins/proxbox/clusters/).

    Returns NetBox Cluster objects tagged 'proxbox' (synced Proxmox clusters).
    Read-only GET endpoint.
    """

    permission_classes = [IsAuthenticatedOrLoginNotRequired]

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request: Request) -> Response:
        """Return proxbox-tagged clusters with their type, group, site, tenant, and counts."""
        from virtualization.models import Cluster
        from netbox_proxbox.utils import get_proxbox_tagged_object_ids

        tagged_ids = get_proxbox_tagged_object_ids(Cluster)[:100]
        if not tagged_ids:
            return Response({"count": 0, "results": []})

        from django.db.models import Count

        clusters = list(
            Cluster.objects.restrict(request.user, "view")
            .filter(id__in=tagged_ids)
            .select_related("type", "group", "_site", "tenant")
            .annotate(
                device_count=Count("devices", distinct=True),
                vm_count=Count("virtual_machines", distinct=True),
            )
        )
        results = [_serialize_cluster(c, request) for c in clusters]
        return Response({"count": len(results), "results": results})


class ScheduleSyncAPIView(APIView):
    """API mirror of the Proxbox schedule sync page (/plugins/proxbox/sync/schedule/).

    GET returns the list of active Proxbox scheduled/pending sync jobs.
    POST creates a new sync job.

    Both methods require ``core.add_job`` permission, matching the UI view's
    ``ContentTypePermissionRequiredMixin`` behaviour.
    """

    permission_classes = [IsAuthenticatedOrLoginNotRequired]

    def _check_enqueue_permission(self, request: Request) -> Response | None:
        """Return a 403 Response if the user cannot enqueue sync jobs, else None."""
        from netbox_proxbox.views.proxbox_access import permission_enqueue_proxbox_sync

        if not request.user.has_perm(permission_enqueue_proxbox_sync()):
            return Response(
                {"detail": "You do not have permission to enqueue sync jobs."},
                status=403,
            )
        return None

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request: Request) -> Response:
        """Return active Proxbox sync jobs (scheduled, pending, running, etc.)."""
        from netbox_proxbox.views.schedule_helpers import get_scheduled_jobs_list

        denied = self._check_enqueue_permission(request)
        if denied is not None:
            return denied

        scheduled_jobs = get_scheduled_jobs_list(request)
        return Response(
            {"count": len(scheduled_jobs), "scheduled_jobs": scheduled_jobs}
        )

    @extend_schema(
        request=ScheduleSyncRequestSerializer,
        responses={201: OpenApiTypes.OBJECT},
    )
    def post(self, request: Request) -> Response:
        """Enqueue a Proxbox sync job. Requires core.add_job permission."""
        from netbox_proxbox.choices import ScheduleIntervalUnitChoices, SyncTypeChoices
        from netbox_proxbox.jobs import PROXBOX_SYNC_QUEUE_NAME, ProxboxSyncJob
        from utilities.datetime import local_now

        denied = self._check_enqueue_permission(request)
        if denied is not None:
            return denied

        serializer = ScheduleSyncRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"errors": serializer.errors}, status=400)

        data = serializer.validated_data
        sync_types: list = data["sync_types"]
        valid_slugs = {c[0] for c in SyncTypeChoices.CHOICES}
        invalid = [s for s in sync_types if s not in valid_slugs]
        if invalid:
            return Response(
                {"errors": {"sync_types": [f"Invalid sync type(s): {invalid}"]}},
                status=400,
            )
        if SyncTypeChoices.ALL in sync_types and len(sync_types) > 1:
            return Response(
                {
                    "errors": {
                        "sync_types": ['Cannot combine "all" with other sync types.']
                    }
                },
                status=400,
            )

        schedule_at = data.get("schedule_at")
        if schedule_at and schedule_at < local_now():
            return Response(
                {"errors": {"schedule_at": ["Scheduled time must be in the future."]}},
                status=400,
            )

        interval_value = data.get("interval_value")
        interval_unit = data.get("interval_unit")
        interval: int | None = None
        if interval_value and interval_unit:
            interval = ScheduleIntervalUnitChoices.to_minutes(
                interval_value, interval_unit
            )
        if interval and not schedule_at:
            schedule_at = local_now()

        proxmox_endpoint_ids = [
            str(pk) for pk in data.get("proxmox_endpoint_ids") or []
        ]
        if proxmox_endpoint_ids:
            proxmox_endpoint_ids = [
                str(pk)
                for pk in models.ProxmoxEndpoint.objects.filter(
                    pk__in=proxmox_endpoint_ids,
                    enabled=True,
                ).values_list("pk", flat=True)
            ]
        netbox_endpoint_ids = [str(pk) for pk in data.get("netbox_endpoint_ids") or []]
        job_name = (data.get("job_name") or "").strip()

        enqueue_kwargs: dict = dict(
            instance=None,
            user=request.user,
            schedule_at=schedule_at,
            interval=interval,
            queue_name=PROXBOX_SYNC_QUEUE_NAME,
            sync_types=sync_types,
            proxmox_endpoint_ids=proxmox_endpoint_ids,
            netbox_endpoint_ids=netbox_endpoint_ids,
        )
        if job_name:
            enqueue_kwargs["name"] = job_name

        job = ProxboxSyncJob.enqueue(**enqueue_kwargs)

        job_id = getattr(job, "pk", None) or getattr(job, "id", None)
        return Response(
            {
                "ok": True,
                "job_id": job_id,
                "message": (
                    f"Sync job scheduled for {schedule_at.strftime('%Y-%m-%d %H:%M %Z')}."
                    if schedule_at
                    else "Sync job queued for immediate execution."
                ),
            },
            status=201,
        )


class BackendLogsAPIView(APIView):
    """API mirror of the Proxbox backend logs page (/plugins/proxbox/logs/).

    Returns the FastAPI backend log endpoint URLs and the configured log file path.
    Actual log content is served directly by the FastAPI backend.
    Read-only GET endpoint.
    """

    permission_classes = [IsAuthenticatedOrLoginNotRequired]

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request: Request) -> Response:
        """Return backend log URLs and the configured log file path."""
        from netbox_proxbox.models import FastAPIEndpoint, ProxboxPluginSettings
        from netbox_proxbox.utils import get_fastapi_url
        from netbox_proxbox.views.logs import DEFAULT_BACKEND_LOG_FILE_PATH

        endpoint = (
            FastAPIEndpoint.objects.restrict(request.user, "view")
            .filter(enabled=True)
            .first()
        )
        fastapi_info = get_fastapi_url(endpoint) if endpoint is not None else {}
        settings_obj = ProxboxPluginSettings.get_solo()

        fastapi_url = fastapi_info.get("http_url", "")
        return Response(
            {
                "fastapi_url": fastapi_url,
                "fastapi_websocket_url": fastapi_info.get("websocket_url", ""),
                "logs_api_url": f"{fastapi_url}/admin/logs" if fastapi_url else "",
                "sse_stream_url": (
                    f"{fastapi_url}/admin/logs/stream" if fastapi_url else ""
                ),
                "backend_log_file_path": (
                    settings_obj.backend_log_file_path or DEFAULT_BACKEND_LOG_FILE_PATH
                ),
            }
        )


# ── Firewall ViewSets ─────────────────────────────────────────────────────────


class _FirewallPushActionMixin:
    """DRF action for pushing one firewall object to Proxmox."""

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    @action(detail=True, methods=["post"], url_path="push")
    def push(self, request: Request, pk: int | str | None = None) -> Response:
        """Push this firewall object to the linked Proxmox endpoint."""
        if not request.user.has_perm(permission_run_proxmox_action()):
            return Response(
                {
                    "status": "error",
                    "reason": "permission_denied",
                    "detail": "Missing core.run_proxmox_action permission.",
                },
                status=drf_status.HTTP_403_FORBIDDEN,
            )

        obj = self.get_object()
        actor = _actor_from_request(request)
        try:
            result = push_firewall_object(obj, actor=actor)
        except FirewallPushError as exc:
            return Response(
                {
                    "status": "error",
                    "reason": exc.reason,
                    "detail": exc.detail,
                    "response": exc.response,
                },
                status=exc.status_code,
            )
        return Response(result.to_response(), status=drf_status.HTTP_200_OK)

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    @action(detail=True, methods=["get"], url_path="preview")
    def preview(self, request: Request, pk: int | str | None = None) -> Response:
        """Return NetBox state, live Proxmox state, and differing fields."""
        del pk
        if not request.user.has_perm(permission_run_proxmox_action()):
            return Response(
                {
                    "status": "error",
                    "reason": "permission_denied",
                    "detail": "Missing core.run_proxmox_action permission.",
                },
                status=drf_status.HTTP_403_FORBIDDEN,
            )
        result = preview_firewall_object(self.get_object())
        return Response(result.to_response(), status=drf_status.HTTP_200_OK)


def _actor_from_request(request: Request) -> str:
    user = getattr(request, "user", None)
    get_username = getattr(user, "get_username", None)
    if callable(get_username):
        return str(get_username())
    return str(getattr(user, "username", "") or getattr(user, "pk", "") or "netbox")


class ProxmoxFirewallSecurityGroupViewSet(_FirewallPushActionMixin, NetBoxModelViewSet):
    """REST API for Proxmox firewall security groups."""

    queryset = models.ProxmoxFirewallSecurityGroup.objects.select_related("endpoint")
    serializer_class = ProxmoxFirewallSecurityGroupSerializer
    filterset_class = filtersets.ProxmoxFirewallSecurityGroupFilterSet


class ProxmoxFirewallRuleViewSet(_FirewallPushActionMixin, NetBoxModelViewSet):
    """REST API for Proxmox firewall rules."""

    queryset = models.ProxmoxFirewallRule.objects.select_related(
        "endpoint", "proxmox_node", "virtual_machine", "security_group"
    )
    serializer_class = ProxmoxFirewallRuleSerializer
    filterset_class = filtersets.ProxmoxFirewallRuleFilterSet

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    @action(detail=False, methods=["post"], url_path="push")
    def bulk_push(self, request: Request) -> Response:
        """Push selected firewall rules to Proxmox."""
        if not request.user.has_perm(permission_run_proxmox_action()):
            return Response(
                {
                    "status": "error",
                    "reason": "permission_denied",
                    "detail": "Missing core.run_proxmox_action permission.",
                },
                status=drf_status.HTTP_403_FORBIDDEN,
            )
        ids = request.data.get("ids") or request.data.get("pk") or []
        if not isinstance(ids, list):
            ids = [ids]
        actor = _actor_from_request(request)
        results = []
        for rule in self.get_queryset().filter(pk__in=ids):
            try:
                results.append(push_firewall_object(rule, actor=actor).to_response())
            except FirewallPushError as exc:
                results.append(
                    {
                        "id": rule.pk,
                        "status": "error",
                        "reason": exc.reason,
                        "detail": exc.detail,
                    }
                )
        return Response(
            {"status": "completed", "count": len(results), "results": results},
            status=drf_status.HTTP_200_OK,
        )


class ProxmoxFirewallIPSetViewSet(_FirewallPushActionMixin, NetBoxModelViewSet):
    """REST API for Proxmox firewall IP sets."""

    queryset = models.ProxmoxFirewallIPSet.objects.select_related(
        "endpoint", "virtual_machine"
    )
    serializer_class = ProxmoxFirewallIPSetSerializer
    filterset_class = filtersets.ProxmoxFirewallIPSetFilterSet


class ProxmoxFirewallIPSetEntryViewSet(_FirewallPushActionMixin, NetBoxModelViewSet):
    """REST API for Proxmox firewall IP set entries."""

    queryset = models.ProxmoxFirewallIPSetEntry.objects.select_related("ipset")
    serializer_class = ProxmoxFirewallIPSetEntrySerializer
    filterset_class = filtersets.ProxmoxFirewallIPSetEntryFilterSet


class ProxmoxFirewallAliasViewSet(_FirewallPushActionMixin, NetBoxModelViewSet):
    """REST API for Proxmox firewall aliases."""

    queryset = models.ProxmoxFirewallAlias.objects.select_related(
        "endpoint", "virtual_machine"
    )
    serializer_class = ProxmoxFirewallAliasSerializer
    filterset_class = filtersets.ProxmoxFirewallAliasFilterSet


class ProxmoxFirewallOptionsViewSet(_FirewallPushActionMixin, NetBoxModelViewSet):
    """REST API for Proxmox firewall options snapshots."""

    queryset = models.ProxmoxFirewallOptions.objects.select_related(
        "endpoint", "proxmox_node", "virtual_machine"
    )
    serializer_class = ProxmoxFirewallOptionsSerializer
    filterset_class = filtersets.ProxmoxFirewallOptionsFilterSet


# ── SDN ViewSets ──────────────────────────────────────────────────────────────


class ProxmoxSdnFabricViewSet(NetBoxModelViewSet):
    """REST API for Proxmox SDN fabrics."""

    queryset = models.ProxmoxSdnFabric.objects.select_related("endpoint")
    serializer_class = ProxmoxSdnFabricSerializer
    filterset_class = filtersets.ProxmoxSdnFabricFilterSet


class ProxmoxSdnControllerViewSet(NetBoxModelViewSet):
    """REST API for Proxmox SDN controllers."""

    queryset = models.ProxmoxSdnController.objects.select_related("endpoint")
    serializer_class = ProxmoxSdnControllerSerializer
    filterset_class = filtersets.ProxmoxSdnControllerFilterSet


class ProxmoxSdnZoneViewSet(NetBoxModelViewSet):
    """REST API for Proxmox SDN zones."""

    queryset = models.ProxmoxSdnZone.objects.select_related("endpoint")
    serializer_class = ProxmoxSdnZoneSerializer
    filterset_class = filtersets.ProxmoxSdnZoneFilterSet


class ProxmoxSdnVNetViewSet(NetBoxModelViewSet):
    """REST API for Proxmox SDN VNets."""

    queryset = models.ProxmoxSdnVNet.objects.select_related("endpoint", "l2vpn")
    serializer_class = ProxmoxSdnVNetSerializer
    filterset_class = filtersets.ProxmoxSdnVNetFilterSet


class ProxmoxSdnSubnetViewSet(NetBoxModelViewSet):
    """REST API for Proxmox SDN subnets."""

    queryset = models.ProxmoxSdnSubnet.objects.select_related("endpoint", "prefix")
    serializer_class = ProxmoxSdnSubnetSerializer
    filterset_class = filtersets.ProxmoxSdnSubnetFilterSet


class ProxmoxSdnBindingViewSet(NetBoxModelViewSet):
    """REST API for Proxmox SDN binding/status records."""

    queryset = models.ProxmoxSdnBinding.objects.select_related("endpoint")
    serializer_class = ProxmoxSdnBindingSerializer
    filterset_class = filtersets.ProxmoxSdnBindingFilterSet


class ProxmoxSdnRouteMapViewSet(NetBoxModelViewSet):
    """REST API for Proxmox SDN route maps."""

    queryset = models.ProxmoxSdnRouteMap.objects.select_related("endpoint")
    serializer_class = ProxmoxSdnRouteMapSerializer
    filterset_class = filtersets.ProxmoxSdnRouteMapFilterSet


class ProxmoxSdnPrefixListViewSet(NetBoxModelViewSet):
    """REST API for Proxmox SDN prefix lists."""

    queryset = models.ProxmoxSdnPrefixList.objects.select_related("endpoint")
    serializer_class = ProxmoxSdnPrefixListSerializer
    filterset_class = filtersets.ProxmoxSdnPrefixListFilterSet


# ── Datacenter ViewSets ───────────────────────────────────────────────────────


class ProxmoxDatacenterCpuModelViewSet(NetBoxModelViewSet):
    """REST API for Proxmox datacenter custom CPU models."""

    queryset = models.ProxmoxDatacenterCpuModel.objects.select_related("endpoint")
    serializer_class = ProxmoxDatacenterCpuModelSerializer
    filterset_class = filtersets.ProxmoxDatacenterCpuModelFilterSet


# ── PBS / PDM / Intent ViewSets ───────────────────────────────────────────────


class PBSEndpointViewSet(NetBoxModelViewSet):
    """REST API for Proxmox Backup Server endpoint inventory."""

    queryset = models.PBSEndpoint.objects.select_related(
        "ip_address",
        "site",
        "tenant",
    )
    serializer_class = PBSEndpointSerializer


class PDMEndpointViewSet(NetBoxModelViewSet):
    """REST API for Proxmox Datacenter Manager endpoint inventory."""

    queryset = models.PDMEndpoint.objects.select_related(
        "ip_address",
        "site",
        "tenant",
    ).prefetch_related(
        "proxmox_endpoints",
        "pbs_endpoints",
    )
    serializer_class = PDMEndpointSerializer


class PDMRemoteViewSet(NetBoxModelViewSet):
    """REST API for PDM remote discovery records."""

    queryset = models.PDMRemote.objects.select_related(
        "pdm_endpoint",
        "linked_proxmox_endpoint",
        "linked_pbs_endpoint",
    )
    serializer_class = PDMRemoteSerializer


class DeletionRequestViewSet(NetBoxModelViewSet):
    """Read-only REST API for Proxmox deletion requests (four-eyes approval workflow).

    Write access is intentionally disabled — all state transitions must go through
    the UI-side approval workflow to preserve the four-eyes safety model.
    """

    queryset = models.DeletionRequest.objects.select_related(
        "requested_by",
        "authorizer",
    )
    serializer_class = DeletionRequestSerializer
    # Safety invariant: read-only gate for four-eyes approval; see AGENTS.md §"LLM Agent Safety Guardrails".
    http_method_names = ["get", "head", "options"]


class ProxmoxApplyJobViewSet(NetBoxModelViewSet):
    """Read-only REST API for NetBox→Proxmox intent apply runs.

    Write access is intentionally disabled — apply jobs are created exclusively
    through the intent branch-merge workflow.
    """

    queryset = models.ProxmoxApplyJob.objects.select_related("user")
    serializer_class = ProxmoxApplyJobSerializer
    # Safety invariant: apply jobs are created only through the intent branch-merge workflow; never via API write.
    http_method_names = ["get", "head", "options"]
