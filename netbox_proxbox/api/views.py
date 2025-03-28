from netbox.api.viewsets import NetBoxModelViewSet

from .. import filtersets, models
from .serializers import (
    ProxmoxEndpointSerializer,
    NetBoxEndpointSerializer,
    FastAPIEndpointSerializer,
    SyncProcessSerializer,
)


class SyncProcessViewSet(NetBoxModelViewSet):
    queryset = models.SyncProcess.objects.all()
    serializer_class = SyncProcessSerializer
    filterset_class = filtersets.SyncProcessFilterSet

class ProxmoxEndpointViewSet(NetBoxModelViewSet):
    queryset = models.ProxmoxEndpoint.objects.all()
    serializer_class = ProxmoxEndpointSerializer

class NetBoxEndpointViewSet(NetBoxModelViewSet):
    queryset = models.NetBoxEndpoint.objects.all()
    serializer_class = NetBoxEndpointSerializer
    
    def get_object(self):
        # If there is already an existing NetBoxEndpoint object, return the first object
        if models.NetBoxEndpoint.objects.exists():
            return models.NetBoxEndpoint.objects.first()
        return super().get_object()


class FastAPIEndpointViewSet(NetBoxModelViewSet):
    queryset = models.FastAPIEndpoint.objects.all()
    serializer_class = FastAPIEndpointSerializer

    