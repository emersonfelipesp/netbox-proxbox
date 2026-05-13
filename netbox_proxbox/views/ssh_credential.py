"""NetBox CRUD views for hardware-discovery SSH credentials."""

from netbox.views import generic
from utilities.views import register_model_view

from netbox_proxbox.filtersets import NodeSSHCredentialFilterSet
from netbox_proxbox.forms import NodeSSHCredentialFilterForm, NodeSSHCredentialForm
from netbox_proxbox.models import NodeSSHCredential
from netbox_proxbox.tables import NodeSSHCredentialTable


@register_model_view(NodeSSHCredential)
class NodeSSHCredentialView(generic.ObjectView):
    """Detail view for one per-node SSH credential."""

    queryset = NodeSSHCredential.objects.select_related("node")


@register_model_view(NodeSSHCredential, "list", path="", detail=False)
class NodeSSHCredentialListView(generic.ObjectListView):
    """Filterable list of per-node SSH credentials."""

    queryset = NodeSSHCredential.objects.select_related("node")
    table = NodeSSHCredentialTable
    filterset = NodeSSHCredentialFilterSet
    filterset_form = NodeSSHCredentialFilterForm


@register_model_view(NodeSSHCredential, "add", detail=False)
@register_model_view(NodeSSHCredential, "edit")
class NodeSSHCredentialEditView(generic.ObjectEditView):
    """Create or edit a per-node SSH credential."""

    queryset = NodeSSHCredential.objects.select_related("node")
    form = NodeSSHCredentialForm


@register_model_view(NodeSSHCredential, "delete")
class NodeSSHCredentialDeleteView(generic.ObjectDeleteView):
    """Delete a per-node SSH credential."""

    queryset = NodeSSHCredential.objects.select_related("node")


@register_model_view(NodeSSHCredential, "bulk_delete", detail=False)
class NodeSSHCredentialBulkDeleteView(generic.BulkDeleteView):
    """Bulk-delete per-node SSH credentials."""

    queryset = NodeSSHCredential.objects.select_related("node")
    table = NodeSSHCredentialTable
