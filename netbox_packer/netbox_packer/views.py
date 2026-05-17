"""Views for the netbox-packer UI surface."""

from __future__ import annotations

from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views import View
from netbox.views import generic
from utilities.permissions import get_permission_for_model
from utilities.views import (
    ConditionalLoginRequiredMixin,
    ContentTypePermissionRequiredMixin,
    ViewTab,
    register_model_view,
)

from core.models import Job
from netbox_packer import filtersets, forms, tables
from netbox_packer.models import (
    PackerImageBuild,
    PackerImageDefinition,
    PackerPluginSettings,
)

PHASE4_BUILD_MESSAGE = "Build queueing wired in PHASE4"
PHASE4_CANCEL_MESSAGE = "Cancel wired in PHASE4"


class PackerHomeView(ConditionalLoginRequiredMixin, generic.ObjectListView):
    """Plugin home landing renders the image definition list."""

    queryset = (
        PackerImageDefinition.objects.select_related(
            "proxmox_endpoint",
            "target_cluster",
        )
        .prefetch_related("allowed_tenants", "tags")
        .all()
    )
    table = tables.PackerImageDefinitionTable
    filterset = filtersets.PackerImageDefinitionFilterSet
    filterset_form = forms.PackerImageDefinitionFilterForm
    template_name = "netbox_packer/packerimagedefinition_list.html"


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


@register_model_view(PackerPluginSettings)
class PackerPluginSettingsView(generic.ObjectView):
    queryset = PackerPluginSettings.objects.all()


@register_model_view(PackerPluginSettings, "edit")
class PackerPluginSettingsEditView(generic.ObjectEditView):
    queryset = PackerPluginSettings.objects.all()
    form = forms.PackerPluginSettingsForm
    template_name = "netbox_packer/packerpluginsettings_edit.html"


class PackerSettingsSingletonRedirectView(
    ConditionalLoginRequiredMixin,
    ContentTypePermissionRequiredMixin,
    View,
):
    """Always edit the singleton settings row."""

    def get_required_permission(self) -> str:
        return "netbox_packer.change_packerpluginsettings"

    def get(self, request: HttpRequest, *args: object, **kwargs: object) -> HttpResponse:
        obj = PackerPluginSettings.get_solo()
        return redirect("plugins:netbox_packer:packerpluginsettings_edit", pk=obj.pk)


settings_singleton_redirect = PackerSettingsSingletonRedirectView.as_view()


# ---------------------------------------------------------------------------
# Image definitions
# ---------------------------------------------------------------------------


@register_model_view(PackerImageDefinition)
class PackerImageDefinitionView(generic.ObjectView):
    queryset = (
        PackerImageDefinition.objects.select_related(
            "proxmox_endpoint",
            "target_cluster",
        )
        .prefetch_related("allowed_tenants", "tags")
        .all()
    )
    template_name = "netbox_packer/packerimagedefinition.html"

    def get_extra_context(
        self,
        request: HttpRequest,
        instance: PackerImageDefinition,
    ) -> dict[str, object]:
        return {
            "build_form": forms.PackerImageBuildSubmitForm(definition=instance),
            "build_url": reverse(
                "plugins:netbox_packer:packerimagedefinition_build",
                args=[instance.pk],
            ),
        }


@register_model_view(PackerImageDefinition, "list", path="", detail=False)
class PackerImageDefinitionListView(generic.ObjectListView):
    queryset = (
        PackerImageDefinition.objects.select_related(
            "proxmox_endpoint",
            "target_cluster",
        )
        .prefetch_related("allowed_tenants", "tags")
        .all()
    )
    table = tables.PackerImageDefinitionTable
    filterset = filtersets.PackerImageDefinitionFilterSet
    filterset_form = forms.PackerImageDefinitionFilterForm
    template_name = "netbox_packer/packerimagedefinition_list.html"


@register_model_view(PackerImageDefinition, "add", detail=False)
@register_model_view(PackerImageDefinition, "edit")
class PackerImageDefinitionEditView(generic.ObjectEditView):
    queryset = PackerImageDefinition.objects.all()
    form = forms.PackerImageDefinitionForm
    template_name = "netbox_packer/packerimagedefinition_edit.html"


@register_model_view(PackerImageDefinition, "delete")
class PackerImageDefinitionDeleteView(generic.ObjectDeleteView):
    queryset = PackerImageDefinition.objects.all()


@register_model_view(PackerImageDefinition, "builds", path="builds")
class PackerImageDefinitionBuildsView(generic.ObjectChildrenView):
    queryset = PackerImageDefinition.objects.all()
    child_model = PackerImageBuild
    table = tables.PackerImageBuildTable
    filterset = filtersets.PackerImageBuildFilterSet
    template_name = "generic/object_children.html"
    actions = {}
    tab = ViewTab(
        label="Builds",
        badge=lambda obj: obj.builds.count(),
        permission="netbox_packer.view_packerimagebuild",
    )

    def get_children(
        self,
        request: HttpRequest,
        parent: PackerImageDefinition,
    ):
        return parent.builds.select_related(
            "definition",
            "proxmox_endpoint",
            "created_by",
            "cloud_image_template",
        )


@register_model_view(PackerImageDefinition, "build", path="build")
class PackerImageBuildSubmitView(
    ConditionalLoginRequiredMixin,
    ContentTypePermissionRequiredMixin,
    View,
):
    """POST-only PHASE3 build action placeholder."""

    http_method_names = ["post"]
    additional_permissions = [
        get_permission_for_model(PackerImageBuild, "add"),
    ]

    def get_required_permission(self) -> str:
        return get_permission_for_model(Job, "add")

    def post(self, request: HttpRequest, pk: int | str) -> HttpResponse:
        definition = get_object_or_404(
            PackerImageDefinition.objects.restrict(request.user, "view"),
            pk=pk,
        )
        form = forms.PackerImageBuildSubmitForm(request.POST, definition=definition)
        if not form.is_valid():
            return HttpResponse(form.errors.as_json(), status=400)
        return HttpResponse(
            f'<div class="alert alert-info">{PHASE4_BUILD_MESSAGE}</div>',
            status=202,
        )


# ---------------------------------------------------------------------------
# Image builds
# ---------------------------------------------------------------------------


@register_model_view(PackerImageBuild)
class PackerImageBuildView(generic.ObjectView):
    queryset = PackerImageBuild.objects.select_related(
        "definition",
        "proxmox_endpoint",
        "created_by",
        "cloud_image_template",
    )
    template_name = "netbox_packer/packerimagebuild.html"


@register_model_view(PackerImageBuild, "list", path="", detail=False)
class PackerImageBuildListView(generic.ObjectListView):
    queryset = PackerImageBuild.objects.select_related(
        "definition",
        "proxmox_endpoint",
        "created_by",
        "cloud_image_template",
    )
    table = tables.PackerImageBuildTable
    filterset = filtersets.PackerImageBuildFilterSet
    filterset_form = forms.PackerImageBuildFilterForm
    template_name = "netbox_packer/packerimagebuild_list.html"
    actions = {}


@register_model_view(PackerImageBuild, "logs", path="logs")
class PackerImageBuildLogsView(PackerImageBuildView):
    tab = ViewTab(
        label="Logs",
        permission="netbox_packer.view_packerimagebuild",
    )


@register_model_view(PackerImageBuild, "cancel", path="cancel")
class PackerImageBuildCancelView(
    ConditionalLoginRequiredMixin,
    ContentTypePermissionRequiredMixin,
    View,
):
    """POST-only PHASE3 cancel action placeholder."""

    http_method_names = ["post"]
    additional_permissions = [
        get_permission_for_model(PackerImageBuild, "change"),
    ]

    def get_required_permission(self) -> str:
        return get_permission_for_model(Job, "delete")

    def post(self, request: HttpRequest, pk: int | str) -> HttpResponse:
        get_object_or_404(
            PackerImageBuild.objects.restrict(request.user, "view"),
            pk=pk,
        )
        return HttpResponse(
            f'<div class="alert alert-info">{PHASE4_CANCEL_MESSAGE}</div>',
            status=202,
        )
