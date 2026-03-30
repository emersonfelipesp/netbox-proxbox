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
    SyncProcessSerializer,
    VMBackupSerializer,
    VMSnapshotSerializer,
)


class ProxBoxRootView(APIRootView):
    """Plugin API root with a link to nested endpoint routes."""

    def get_view_name(self) -> str:
        return "ProxBox"

    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        response = super().get(request, *args, **kwargs)
        base_url = request.build_absolute_uri("/").rstrip("/")
        response.data["endpoints"] = f"{base_url}/api/plugins/proxbox/endpoints/"
        return response


class ProxBoxEndpointsView(APIRootView):
    """Nested root for Proxmox / NetBox / FastAPI endpoint viewsets."""

    def get_view_name(self) -> str:
        return "Endpoints"


class VMBackupViewSet(NetBoxModelViewSet):
    queryset = models.VMBackup.objects.all()
    serializer_class = VMBackupSerializer
    filterset_class = filtersets.VMBackupFilterSet


class VMSnapshotViewSet(NetBoxModelViewSet):
    queryset = models.VMSnapshot.objects.all()
    serializer_class = VMSnapshotSerializer
    filterset_class = filtersets.VMSnapshotFilterSet


class SyncProcessViewSet(NetBoxModelViewSet):
    queryset = models.SyncProcess.objects.all()
    serializer_class = SyncProcessSerializer
    filterset_class = filtersets.SyncProcessFilterSet


class ProxmoxEndpointViewSet(NetBoxModelViewSet):
    queryset = models.ProxmoxEndpoint.objects.all()
    serializer_class = ProxmoxEndpointSerializer
    filterset_class = filtersets.ProxmoxEndpointFilterSet


class NetBoxEndpointViewSet(NetBoxModelViewSet):
    queryset = models.NetBoxEndpoint.objects.all()
    serializer_class = NetBoxEndpointSerializer
    filterset_class = filtersets.NetBoxEndpointFilterSet


class FastAPIEndpointViewSet(NetBoxModelViewSet):
    queryset = models.FastAPIEndpoint.objects.all()
    serializer_class = FastAPIEndpointSerializer
    filterset_class = filtersets.FastAPIEndpointFilterSet
