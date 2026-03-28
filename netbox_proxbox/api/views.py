from extras import filtersets as extras_filtersets
from extras.models import JournalEntry
from netbox.api.viewsets import NetBoxModelViewSet
from rest_framework.routers import APIRootView

from .. import filtersets, models
from .serializers import (
    FastAPIEndpointSerializer,
    JournalEntrySerializer,
    NetBoxEndpointSerializer,
    ProxmoxEndpointSerializer,
    SyncProcessSerializer,
    VMBackupSerializer,
)


class ProxBoxRootView(APIRootView):
    def get_view_name(self):
        return "ProxBox"

    def get(self, request, *args, **kwargs):
        response = super().get(request, *args, **kwargs)
        base_url = request.build_absolute_uri("/").rstrip("/")
        response.data["endpoints"] = f"{base_url}/api/plugins/proxbox/endpoints/"
        return response


class ProxBoxEndpointsView(APIRootView):
    def get_view_name(self):
        return "Endpoints"


class VMBackupViewSet(NetBoxModelViewSet):
    queryset = models.VMBackup.objects.all()
    serializer_class = VMBackupSerializer
    filterset_class = filtersets.VMBackupFilterSet


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


class JournalEntryViewSet(NetBoxModelViewSet):
    queryset = JournalEntry.objects.all()
    serializer_class = JournalEntrySerializer
    filterset_class = extras_filtersets.JournalEntryFilterSet
