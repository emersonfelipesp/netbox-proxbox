"""Provide NetBox API root views and model viewsets for the plugin."""

from __future__ import annotations

from typing import Any

from netbox.api.viewsets import NetBoxModelViewSet
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.routers import APIRootView

from .. import filtersets, models
from .serializers import (
    FastAPIEndpointSerializer,
    NetBoxEndpointSerializer,
    ProxmoxEndpointSerializer,
    VMBackupSerializer,
    VMSnapshotSerializer,
)


class ProxBoxRootView(APIRootView):
    """Plugin API root with a link to nested endpoint routes."""

    def get_view_name(self) -> str:
        """Human-readable title for the plugin API root schema."""
        return "ProxBox"

    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Augment the default API root payload with an absolute ``endpoints`` URL."""
        response = super().get(request, *args, **kwargs)
        base_url = request.build_absolute_uri("/").rstrip("/")
        response.data["endpoints"] = f"{base_url}/api/plugins/proxbox/endpoints/"
        return response


class ProxBoxEndpointsView(APIRootView):
    """Nested root for Proxmox / NetBox / FastAPI endpoint viewsets."""

    def get_view_name(self) -> str:
        """Title for the nested endpoints API root."""
        return "Endpoints"


class VMBackupViewSet(NetBoxModelViewSet):
    """REST API for VM backup rows synced from Proxmox."""
    queryset = models.VMBackup.objects.all()
    serializer_class = VMBackupSerializer
    filterset_class = filtersets.VMBackupFilterSet


class VMSnapshotViewSet(NetBoxModelViewSet):
    """REST API for VM snapshot rows synced from Proxmox."""
    queryset = models.VMSnapshot.objects.all()
    serializer_class = VMSnapshotSerializer
    filterset_class = filtersets.VMSnapshotFilterSet


class ProxmoxEndpointViewSet(NetBoxModelViewSet):
    """REST API for Proxmox VE API endpoint credentials and targets."""
    queryset = models.ProxmoxEndpoint.objects.select_related("ip_address")
    serializer_class = ProxmoxEndpointSerializer
    filterset_class = filtersets.ProxmoxEndpointFilterSet


class NetBoxEndpointViewSet(NetBoxModelViewSet):
    """REST API for remote NetBox API endpoint configuration."""
    queryset = models.NetBoxEndpoint.objects.all()
    serializer_class = NetBoxEndpointSerializer
    filterset_class = filtersets.NetBoxEndpointFilterSet


class FastAPIEndpointViewSet(NetBoxModelViewSet):
    """REST API for ProxBox FastAPI backend (HTTP/WebSocket) endpoints."""
    queryset = models.FastAPIEndpoint.objects.all()
    serializer_class = FastAPIEndpointSerializer
    filterset_class = filtersets.FastAPIEndpointFilterSet
