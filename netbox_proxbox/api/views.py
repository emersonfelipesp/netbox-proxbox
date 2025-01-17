from netbox.api.viewsets import NetBoxModelViewSet

from .. import filtersets, models
from .serializers import ProxmoxEndpointSerializer

class ProxmoxEndpointViewSet(NetBoxModelViewSet):
    queryset = models.ProxmoxEndpoint.objects.all()
    serializer_class = ProxmoxEndpointSerializer
    
    