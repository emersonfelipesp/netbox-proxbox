"""Views for netbox-pbs.

Read-only enforcement story (advisor check 3): the five PBS objects
reflected from PBS (Node, Datastore, BackupGroup, Snapshot, JobStatus)
register **only** ``ObjectListView`` and ``ObjectView``. They never
register ``edit``, ``delete``, ``bulk_edit``, ``bulk_delete``, or
``bulk_import``, so NetBox's plugin URL system never builds those routes
and the templates never render those buttons. PBSEndpoint is the one
writable model — operators create it manually so the sync (PR C3) can
reach it.
"""

from __future__ import annotations

from django.views.generic import TemplateView

from netbox.views import generic
from utilities.views import ConditionalLoginRequiredMixin, register_model_view

from netbox_pbs.filtersets import (
    PBSBackupGroupFilterSet,
    PBSDatastoreFilterSet,
    PBSEndpointFilterSet,
    PBSJobStatusFilterSet,
    PBSNodeFilterSet,
    PBSSnapshotFilterSet,
)
from netbox_pbs.forms import (
    PBSBackupGroupFilterForm,
    PBSDatastoreFilterForm,
    PBSEndpointBulkEditForm,
    PBSEndpointFilterForm,
    PBSEndpointForm,
    PBSEndpointImportForm,
    PBSJobStatusFilterForm,
    PBSNodeFilterForm,
    PBSSnapshotFilterForm,
)
from netbox_pbs.models import (
    PBSBackupGroup,
    PBSDatastore,
    PBSEndpoint,
    PBSJobStatus,
    PBSNode,
    PBSSnapshot,
)
from netbox_pbs.tables import (
    PBSBackupGroupTable,
    PBSDatastoreTable,
    PBSEndpointTable,
    PBSJobStatusTable,
    PBSNodeTable,
    PBSSnapshotTable,
)


# Read-only action set used by every reflected-model list view.
_READ_ONLY_ACTIONS = {"export": {"view"}}


class PBSHomeView(ConditionalLoginRequiredMixin, TemplateView):
    """Placeholder home page for the netbox-pbs plugin."""

    template_name = "netbox_pbs/home.html"


# ----- PBSEndpoint: full CRUD ------------------------------------------------


@register_model_view(PBSEndpoint, "list", path="", detail=False)
class PBSEndpointListView(generic.ObjectListView):
    """Global list of PBS endpoints."""

    queryset = PBSEndpoint.objects.all()
    table = PBSEndpointTable
    filterset = PBSEndpointFilterSet
    filterset_form = PBSEndpointFilterForm
    actions = {
        "add": {"add"},
        "bulk_edit": {"change"},
        "bulk_delete": {"delete"},
        "bulk_import": {"add"},
        "export": {"view"},
    }


@register_model_view(PBSEndpoint)
class PBSEndpointView(generic.ObjectView):
    """Detail view for a PBS endpoint."""

    queryset = PBSEndpoint.objects.all()


@register_model_view(PBSEndpoint, "add", detail=False)
@register_model_view(PBSEndpoint, "edit")
class PBSEndpointEditView(generic.ObjectEditView):
    """Create or edit a PBS endpoint."""

    queryset = PBSEndpoint.objects.all()
    form = PBSEndpointForm
    default_return_url = "plugins:netbox_pbs:pbsendpoint_list"


@register_model_view(PBSEndpoint, "delete")
class PBSEndpointDeleteView(generic.ObjectDeleteView):
    """Delete a single PBS endpoint."""

    queryset = PBSEndpoint.objects.all()
    default_return_url = "plugins:netbox_pbs:pbsendpoint_list"


@register_model_view(PBSEndpoint, "bulk_delete", detail=False)
class PBSEndpointBulkDeleteView(generic.BulkDeleteView):
    """Bulk delete PBS endpoints."""

    queryset = PBSEndpoint.objects.all()
    filterset = PBSEndpointFilterSet
    table = PBSEndpointTable
    default_return_url = "plugins:netbox_pbs:pbsendpoint_list"


@register_model_view(PBSEndpoint, "bulk_edit", path="edit", detail=False)
class PBSEndpointBulkEditView(generic.BulkEditView):
    """Bulk edit PBS endpoints."""

    queryset = PBSEndpoint.objects.all()
    filterset = PBSEndpointFilterSet
    table = PBSEndpointTable
    form = PBSEndpointBulkEditForm
    default_return_url = "plugins:netbox_pbs:pbsendpoint_list"


@register_model_view(PBSEndpoint, "bulk_import", path="import", detail=False)
class PBSEndpointBulkImportView(generic.BulkImportView):
    """CSV import for PBS endpoint rows."""

    queryset = PBSEndpoint.objects.all()
    model_form = PBSEndpointImportForm
    default_return_url = "plugins:netbox_pbs:pbsendpoint_list"


# ----- PBSNode: read-only list + detail --------------------------------------


@register_model_view(PBSNode, "list", path="", detail=False)
class PBSNodeListView(generic.ObjectListView):
    """Read-only list of PBS nodes mirrored from PBS."""

    queryset = PBSNode.objects.all()
    table = PBSNodeTable
    filterset = PBSNodeFilterSet
    filterset_form = PBSNodeFilterForm
    actions = _READ_ONLY_ACTIONS


@register_model_view(PBSNode)
class PBSNodeView(generic.ObjectView):
    """Detail view for a PBS node."""

    queryset = PBSNode.objects.all()


# ----- PBSDatastore: read-only list + detail ---------------------------------


@register_model_view(PBSDatastore, "list", path="", detail=False)
class PBSDatastoreListView(generic.ObjectListView):
    """Read-only list of PBS datastores mirrored from PBS."""

    queryset = PBSDatastore.objects.all()
    table = PBSDatastoreTable
    filterset = PBSDatastoreFilterSet
    filterset_form = PBSDatastoreFilterForm
    actions = _READ_ONLY_ACTIONS


@register_model_view(PBSDatastore)
class PBSDatastoreView(generic.ObjectView):
    """Detail view for a PBS datastore."""

    queryset = PBSDatastore.objects.all()


# ----- PBSBackupGroup: read-only list + detail -------------------------------


@register_model_view(PBSBackupGroup, "list", path="", detail=False)
class PBSBackupGroupListView(generic.ObjectListView):
    """Read-only list of PBS backup groups mirrored from PBS."""

    queryset = PBSBackupGroup.objects.all()
    table = PBSBackupGroupTable
    filterset = PBSBackupGroupFilterSet
    filterset_form = PBSBackupGroupFilterForm
    actions = _READ_ONLY_ACTIONS


@register_model_view(PBSBackupGroup)
class PBSBackupGroupView(generic.ObjectView):
    """Detail view for a PBS backup group."""

    queryset = PBSBackupGroup.objects.all()


# ----- PBSSnapshot: read-only list + detail ----------------------------------


@register_model_view(PBSSnapshot, "list", path="", detail=False)
class PBSSnapshotListView(generic.ObjectListView):
    """Read-only list of PBS snapshots mirrored from PBS."""

    queryset = PBSSnapshot.objects.all()
    table = PBSSnapshotTable
    filterset = PBSSnapshotFilterSet
    filterset_form = PBSSnapshotFilterForm
    actions = _READ_ONLY_ACTIONS


@register_model_view(PBSSnapshot)
class PBSSnapshotView(generic.ObjectView):
    """Detail view for a PBS snapshot."""

    queryset = PBSSnapshot.objects.all()


# ----- PBSJobStatus: read-only list + detail ---------------------------------


@register_model_view(PBSJobStatus, "list", path="", detail=False)
class PBSJobStatusListView(generic.ObjectListView):
    """Read-only list of PBS scheduled-job statuses mirrored from PBS."""

    queryset = PBSJobStatus.objects.all()
    table = PBSJobStatusTable
    filterset = PBSJobStatusFilterSet
    filterset_form = PBSJobStatusFilterForm
    actions = _READ_ONLY_ACTIONS


@register_model_view(PBSJobStatus)
class PBSJobStatusView(generic.ObjectView):
    """Detail view for a PBS scheduled-job status."""

    queryset = PBSJobStatus.objects.all()
