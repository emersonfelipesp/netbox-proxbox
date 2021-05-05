from rest_framework import mixins, viewsets

from netbox_proxbox.models import ProxmoxVM
from netbox_proxbox.filters import ProxmoxVMFilter

from .serializers import ProxmoxVMSerializer


class ProxmoxVMView(
    # class takes care of creating and saving a new model instance. Responds to HTTP POST.
    mixins.CreateModelMixin,

    # class will handle deletion of model instances. Responds to HTTP DELETE.
    mixins.DestroyModelMixin,

    # class allows returning a list of instances in API response. Used with HTTP GET.
    mixins.ListModelMixin,

    # class handles retrieval of a single model instance. Used with HTTP GET.
    mixins.RetrieveModelMixin,

    # class enables edits, both merge and replace. Used with HTTP PUT and PATCH.
    mixins.UpdateModelMixin,

    # ViewSet class that lets us combine multiple different views into one view.
    # It allows one entry in URL conf for adding, editing, deleting, etc. objects.
    viewsets.GenericViewSet,
):
    """Create, check status of, update, and delete ProxmoxVM object."""

    # gets all ProxmoxVM objects to use in API calls
    queryset = ProxmoxVM.objects.all()

    # specificies a filter class that can be used to apply search queries when retrieving objects via API
    filterset_class = ProxmoxVMFilter

    # serializer class built to render the ProxmoxVM model into json representation
    serializer_class = ProxmoxVMSerializer