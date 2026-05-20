"""Provide NetBox CRUD views for backup routine records."""

from netbox.views import generic
from utilities.views import register_model_view

from netbox_proxbox.filtersets import BackupRoutineFilterSet
from netbox_proxbox.forms import BackupRoutineFilterForm, BackupRoutineForm
from netbox_proxbox.models import BackupRoutine
from netbox_proxbox.tables import BackupRoutineTable


__all__ = (
    "BackupRoutineView",
    "BackupRoutineListView",
    "BackupRoutineEditView",
    "BackupRoutineDeleteView",
    "BackupRoutineBulkDeleteView",
)


@register_model_view(BackupRoutine, "list", path="", detail=False)
class BackupRoutineListView(generic.ObjectListView):
    """Global list of backup routines with export and bulk delete actions."""

    queryset = BackupRoutine.objects.select_related("endpoint", "node", "storage")
    table = BackupRoutineTable
    filterset = BackupRoutineFilterSet
    filterset_form = BackupRoutineFilterForm
    template_name = "netbox_proxbox/backup_routine_list.html"
    actions = {
        "bulk_delete": {"delete"},
        "export": {"view"},
    }


@register_model_view(BackupRoutine)
class BackupRoutineView(generic.ObjectView):
    """Detail view for one backup routine with four cards: General, Retention, Note Template, Advanced."""

    queryset = BackupRoutine.objects.select_related(
        "endpoint", "node", "storage", "fleecing_storage"
    )
    template_name = "netbox_proxbox/backup_routine.html"


@register_model_view(BackupRoutine, "add", detail=False)
@register_model_view(BackupRoutine, "edit")
class BackupRoutineEditView(generic.ObjectEditView):
    """Create or edit a backup routine record."""

    queryset = BackupRoutine.objects.all()
    form = BackupRoutineForm
    default_return_url = "plugins:netbox_proxbox:backuproutine_list"


@register_model_view(BackupRoutine, "delete")
class BackupRoutineDeleteView(generic.ObjectDeleteView):
    """Delete a single backup routine."""

    queryset = BackupRoutine.objects.all()
    default_return_url = "plugins:netbox_proxbox:backuproutine_list"


@register_model_view(BackupRoutine, "bulk_delete", detail=False)
class BackupRoutineBulkDeleteView(generic.BulkDeleteView):
    """Bulk delete backup routines from the global list."""

    queryset = BackupRoutine.objects.select_related("endpoint", "node", "storage")
    filterset = BackupRoutineFilterSet
    table = BackupRoutineTable
    default_return_url = "plugins:netbox_proxbox:backuproutine_list"
