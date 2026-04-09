"""Provide NetBox API root views and model viewsets for the plugin."""

from __future__ import annotations

from netbox.api.viewsets import NetBoxModelViewSet
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.routers import APIRootView

from .. import filtersets, models
from .serializers import (
    BackupRoutineSerializer,
    FastAPIEndpointSerializer,
    NetBoxEndpointSerializer,
    ProxboxPluginSettingsSerializer,
    ProxmoxClusterSerializer,
    ProxmoxEndpointSerializer,
    ProxmoxNodeSerializer,
    ProxmoxStorageSerializer,
    ReplicationSerializer,
    VMBackupSerializer,
    VMSnapshotSerializer,
    VMTaskHistorySerializer,
)


class ProxBoxRootView(APIRootView):
    """Plugin API root with a link to nested endpoint routes."""

    def get_view_name(self) -> str:
        """Human-readable title for the plugin API root schema."""
        return "ProxBox"

    def get(self, request: Request, *args: object, **kwargs: object) -> Response:
        """Augment the default API root payload with an absolute ``endpoints`` URL."""
        response = super().get(request, *args, **kwargs)
        base_url = request.build_absolute_uri("/").rstrip("/")
        response.data["endpoints"] = f"{base_url}/api/plugins/proxbox/endpoints/"
        response.data["settings"] = f"{base_url}/api/plugins/proxbox/settings/"
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


class VMBackupViewSet(NetBoxModelViewSet):
    """REST API for VM backup rows synced from Proxmox."""

    queryset = models.VMBackup.objects.select_related(
        "virtual_machine", "proxmox_storage", "proxmox_storage__cluster"
    )
    serializer_class = VMBackupSerializer
    filterset_class = filtersets.VMBackupFilterSet


class VMSnapshotViewSet(NetBoxModelViewSet):
    """REST API for VM snapshot rows synced from Proxmox."""

    queryset = models.VMSnapshot.objects.select_related(
        "virtual_machine", "proxmox_storage", "proxmox_storage__cluster"
    )
    serializer_class = VMSnapshotSerializer
    filterset_class = filtersets.VMSnapshotFilterSet


class VMTaskHistoryViewSet(NetBoxModelViewSet):
    """REST API for VM task history rows synced from Proxmox."""

    http_method_names = ["get", "post", "patch", "head", "options"]
    queryset = models.VMTaskHistory.objects.select_related("virtual_machine")
    serializer_class = VMTaskHistorySerializer
    filterset_class = filtersets.VMTaskHistoryFilterSet

    def perform_create(self, serializer: object) -> None:
        """Upsert by Proxmox UPID so task reconciliation can replay safely."""
        validated = serializer.validated_data
        # validated_data is a list for bulk POSTs and a dict for single POSTs.
        if isinstance(validated, dict):
            upid = validated.get("upid")
            if upid:
                existing = models.VMTaskHistory.objects.filter(upid=upid).first()
                if existing is not None:
                    serializer.instance = existing
        serializer.save()


class ProxmoxStorageViewSet(NetBoxModelViewSet):
    """REST API for Proxmox storage rows synced from Proxmox endpoints."""

    queryset = models.ProxmoxStorage.objects.select_related("cluster")
    serializer_class = ProxmoxStorageSerializer
    filterset_class = filtersets.ProxmoxStorageFilterSet


class ProxmoxEndpointViewSet(NetBoxModelViewSet):
    """REST API for Proxmox VE API endpoint credentials and targets."""

    queryset = models.ProxmoxEndpoint.objects.select_related("ip_address")
    serializer_class = ProxmoxEndpointSerializer
    filterset_class = filtersets.ProxmoxEndpointFilterSet


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
