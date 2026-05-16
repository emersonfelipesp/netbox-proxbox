"""Views for the standalone netbox-pbs plugin."""

from __future__ import annotations

from django.shortcuts import redirect
from django.views import View
from netbox.views import generic
from utilities.views import (
    ConditionalLoginRequiredMixin,
    ContentTypePermissionRequiredMixin,
    register_model_view,
)

from netbox_pbs import filtersets, forms, tables
from netbox_pbs.models import (
    PBSDatastore,
    PBSJob,
    PBSPluginSettings,
    PBSServer,
    PBSSnapshot,
)


class PBSHomeView(ConditionalLoginRequiredMixin, generic.ObjectListView):
    """Plugin home landing shows configured PBS servers."""

    queryset = PBSServer.objects.all()
    table = tables.PBSServerTable
    filterset = filtersets.PBSServerFilterSet
    filterset_form = forms.PBSServerFilterForm
    template_name = "netbox_pbs/home.html"


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


@register_model_view(PBSPluginSettings)
class PBSPluginSettingsView(generic.ObjectView):
    queryset = PBSPluginSettings.objects.all()


@register_model_view(PBSPluginSettings, "edit")
class PBSPluginSettingsEditView(generic.ObjectEditView):
    queryset = PBSPluginSettings.objects.all()
    form = forms.PBSPluginSettingsForm


class SettingsSingletonRedirectView(
    ConditionalLoginRequiredMixin,
    ContentTypePermissionRequiredMixin,
    View,
):
    """UI helper: always edit the singleton settings row."""

    def get_required_permission(self) -> str:
        return "netbox_pbs.change_pbspluginsettings"

    def get(self, request, *args, **kwargs):
        obj = PBSPluginSettings.get_solo()
        return redirect("plugins:netbox_pbs:pbspluginsettings_edit", pk=obj.pk)


settings_singleton_redirect = SettingsSingletonRedirectView.as_view()


# ---------------------------------------------------------------------------
# Servers
# ---------------------------------------------------------------------------


@register_model_view(PBSServer)
class PBSServerView(generic.ObjectView):
    queryset = PBSServer.objects.all()


@register_model_view(PBSServer, "list", path="", detail=False)
class PBSServerListView(generic.ObjectListView):
    queryset = PBSServer.objects.all()
    table = tables.PBSServerTable
    filterset = filtersets.PBSServerFilterSet
    filterset_form = forms.PBSServerFilterForm


@register_model_view(PBSServer, "add", detail=False)
@register_model_view(PBSServer, "edit")
class PBSServerEditView(generic.ObjectEditView):
    queryset = PBSServer.objects.all()
    form = forms.PBSServerForm


@register_model_view(PBSServer, "delete")
class PBSServerDeleteView(generic.ObjectDeleteView):
    queryset = PBSServer.objects.all()


@register_model_view(PBSServer, "bulk_delete", detail=False)
class PBSServerBulkDeleteView(generic.BulkDeleteView):
    queryset = PBSServer.objects.all()
    filterset = filtersets.PBSServerFilterSet
    table = tables.PBSServerTable


# ---------------------------------------------------------------------------
# Read-only inventory models
# ---------------------------------------------------------------------------


@register_model_view(PBSDatastore)
class PBSDatastoreView(generic.ObjectView):
    queryset = PBSDatastore.objects.select_related("server")


@register_model_view(PBSDatastore, "list", path="", detail=False)
class PBSDatastoreListView(generic.ObjectListView):
    queryset = PBSDatastore.objects.select_related("server")
    table = tables.PBSDatastoreTable
    filterset = filtersets.PBSDatastoreFilterSet
    filterset_form = forms.PBSDatastoreFilterForm
    actions = {}


@register_model_view(PBSSnapshot)
class PBSSnapshotView(generic.ObjectView):
    queryset = PBSSnapshot.objects.select_related("server")


@register_model_view(PBSSnapshot, "list", path="", detail=False)
class PBSSnapshotListView(generic.ObjectListView):
    queryset = PBSSnapshot.objects.select_related("server")
    table = tables.PBSSnapshotTable
    filterset = filtersets.PBSSnapshotFilterSet
    filterset_form = forms.PBSSnapshotFilterForm
    actions = {}


@register_model_view(PBSJob)
class PBSJobView(generic.ObjectView):
    queryset = PBSJob.objects.select_related("server")


@register_model_view(PBSJob, "list", path="", detail=False)
class PBSJobListView(generic.ObjectListView):
    queryset = PBSJob.objects.select_related("server")
    table = tables.PBSJobTable
    filterset = filtersets.PBSJobFilterSet
    filterset_form = forms.PBSJobFilterForm
    actions = {}
