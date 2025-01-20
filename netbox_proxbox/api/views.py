from netbox.api.viewsets import NetBoxModelViewSet

from .. import filtersets, models
from .serializers import (
    ProxmoxEndpointSerializer,
    NetBoxEndpointSerializer,
    FastAPIEndpointSerializer,
)


class ProxmoxEndpointViewSet(NetBoxModelViewSet):
    queryset = models.ProxmoxEndpoint.objects.all()
    serializer_class = ProxmoxEndpointSerializer


class NetBoxEndpointViewSet(NetBoxModelViewSet):
    queryset = models.NetBoxEndpoint.objects.all()
    serializer_class = NetBoxEndpointSerializer


class FastAPIEndpointViewSet(NetBoxModelViewSet):
    queryset = models.FastAPIEndpoint.objects.all()
    serializer_class = FastAPIEndpointSerializer

    