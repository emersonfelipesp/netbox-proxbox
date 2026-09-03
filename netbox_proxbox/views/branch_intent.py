"""NetBox CRUD views for plugin-owned branch intent safety gates."""

from netbox.object_actions import BulkDelete, BulkExport
from netbox.views import generic
from utilities.views import register_model_view

from netbox_proxbox.filtersets import ProxboxBranchIntentFilterSet
from netbox_proxbox.forms import (
    ProxboxBranchIntentFilterForm,
    ProxboxBranchIntentForm,
)
from netbox_proxbox.models import ProxboxBranchIntent
from netbox_proxbox.tables import ProxboxBranchIntentTable


@register_model_view(ProxboxBranchIntent, "list", path="", detail=False)
class ProxboxBranchIntentListView(generic.ObjectListView):
    """List branch intent rows."""

    queryset = ProxboxBranchIntent.objects.all()
    table = ProxboxBranchIntentTable
    filterset = ProxboxBranchIntentFilterSet
    filterset_form = ProxboxBranchIntentFilterForm
    actions = (BulkExport, BulkDelete)


@register_model_view(ProxboxBranchIntent)
class ProxboxBranchIntentView(generic.ObjectView):
    """Display one branch intent row."""

    queryset = ProxboxBranchIntent.objects.all()


@register_model_view(ProxboxBranchIntent, "add", detail=False)
@register_model_view(ProxboxBranchIntent, "edit")
class ProxboxBranchIntentEditView(generic.ObjectEditView):
    """Create or edit branch intent gates."""

    queryset = ProxboxBranchIntent.objects.all()
    form = ProxboxBranchIntentForm
    default_return_url = "plugins:netbox_proxbox:proxboxbranchintent_list"


@register_model_view(ProxboxBranchIntent, "delete")
class ProxboxBranchIntentDeleteView(generic.ObjectDeleteView):
    """Delete a branch intent row."""

    queryset = ProxboxBranchIntent.objects.all()
    default_return_url = "plugins:netbox_proxbox:proxboxbranchintent_list"


@register_model_view(ProxboxBranchIntent, "bulk_delete", detail=False)
class ProxboxBranchIntentBulkDeleteView(generic.BulkDeleteView):
    """Delete selected branch intent rows."""

    queryset = ProxboxBranchIntent.objects.all()
    filterset = ProxboxBranchIntentFilterSet
    table = ProxboxBranchIntentTable
    default_return_url = "plugins:netbox_proxbox:proxboxbranchintent_list"
