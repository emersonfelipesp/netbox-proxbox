"""NetBox CRUD views for hardware-discovery SSH credentials."""

from netbox.object_actions import AddObject, BulkDelete, BulkExport, BulkImport
from netbox.views import generic
from django.views.decorators.debug import sensitive_variables
from utilities.views import register_model_view

from netbox_proxbox.filtersets import NodeSSHCredentialFilterSet
from netbox_proxbox.forms import NodeSSHCredentialFilterForm, NodeSSHCredentialForm
from netbox_proxbox.models import NodeSSHCredential
from netbox_proxbox.tables import NodeSSHCredentialTable


@sensitive_variables()
def _credential_payloads(request: object) -> list[object]:
    return [request.POST]  # type: ignore[attr-defined]


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
    actions = (AddObject, BulkImport, BulkExport, BulkDelete)


@register_model_view(NodeSSHCredential, "add", detail=False)
@register_model_view(NodeSSHCredential, "edit")
class NodeSSHCredentialEditView(generic.ObjectEditView):
    """Create or edit a per-node SSH credential."""

    queryset = NodeSSHCredential.objects.select_related("node")
    form = NodeSSHCredentialForm

    @sensitive_variables()
    def post(self, request: object, *args: object, **kwargs: object) -> object:
        """Own the provider transaction outside NetBox's edit atomic block."""
        from netbox_proxbox.integrations.openbao_node_request import (
            node_credential_request_boundary,
        )

        owner = self.get_object(**kwargs)
        owners = [] if owner.pk is None else [owner]
        with node_credential_request_boundary(
            owners,
            _credential_payloads(request),
            actor=request.user,
            request=request,
            allow_new=owner.pk is None,
        ):
            return super().post(request, *args, **kwargs)


@register_model_view(NodeSSHCredential, "delete")
class NodeSSHCredentialDeleteView(generic.ObjectDeleteView):
    """Delete a per-node SSH credential."""

    queryset = NodeSSHCredential.objects.select_related("node")

    @sensitive_variables()
    def post(self, request: object, *args: object, **kwargs: object) -> object:
        """Own provider cleanup outside the generic deletion path."""
        from netbox_proxbox.integrations.openbao_node_request import (
            node_credential_request_boundary,
        )

        owner = self.get_object(**kwargs)
        with node_credential_request_boundary(
            [owner], [], actor=request.user, request=request
        ):
            return super().post(request, *args, **kwargs)


@register_model_view(NodeSSHCredential, "bulk_delete", detail=False)
class NodeSSHCredentialBulkDeleteView(generic.BulkDeleteView):
    """Bulk-delete per-node SSH credentials."""

    queryset = NodeSSHCredential.objects.select_related("node")
    table = NodeSSHCredentialTable

    def _selected_owners(self, request: object) -> list[NodeSSHCredential]:
        if request.POST.get("_all"):  # type: ignore[attr-defined]
            queryset = NodeSSHCredential.objects.all()
            if self.filterset is not None:
                queryset = self.filterset(  # type: ignore[operator]
                    request.GET,
                    queryset,
                    request=request,  # type: ignore[attr-defined]
                ).qs
            pks = queryset.values_list("pk", flat=True)
        else:
            pks = request.POST.getlist("pk")  # type: ignore[attr-defined]
        return list(self.queryset.filter(pk__in=pks).order_by("pk"))

    @sensitive_variables()
    def post(self, request: object, **kwargs: object) -> object:
        """Own all selected cleanup inside one outer provider transaction."""
        from netbox_proxbox.integrations.openbao_node_request import (
            node_credential_request_boundary,
        )

        owners = self._selected_owners(request)
        with node_credential_request_boundary(
            owners, [], actor=request.user, request=request
        ):
            return super().post(request, **kwargs)
