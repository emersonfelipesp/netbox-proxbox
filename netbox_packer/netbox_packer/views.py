"""Views for the netbox-packer UI surface."""

from __future__ import annotations

from django.contrib import messages
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
from netbox_packer.choices import PackerBuildStatusChoices
from netbox_packer.jobs import PackerImageBuildJob
from netbox_packer.models import (
    PackerImageBuild,
    PackerImageDefinition,
    PackerPluginSettings,
)
from netbox_packer.services.http_client import (
    ImageFactoryBackendError,
    cancel_image_build,
)


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

    def get(
        self, request: HttpRequest, *args: object, **kwargs: object
    ) -> HttpResponse:
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
    """POST-only view that creates a PackerImageBuild and enqueues the job."""

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

        # --- PHASE6: feature gate checks ---
        settings = PackerPluginSettings.get_solo()

        if not settings.image_factory_enabled:
            messages.error(request, "Image factory is disabled in Packer plugin settings.")
            return HttpResponse("Image factory disabled.", status=403)

        if not definition.proxmox_endpoint.allow_writes:
            messages.error(
                request,
                f"Proxmox endpoint '{definition.proxmox_endpoint}' does not allow writes.",
            )
            return HttpResponse("Proxmox endpoint writes disabled.", status=403)

        from netbox_packer.choices import PackerBuilderTypeChoices

        if (
            definition.builder_type == PackerBuilderTypeChoices.PROXMOX_ISO
            and not settings.image_factory_allow_iso_builds
        ):
            messages.error(request, "ISO-based image builds are not enabled in Packer plugin settings.")
            return HttpResponse("ISO builds disabled.", status=403)

        running_count = PackerImageBuild.objects.filter(
            status=PackerBuildStatusChoices.RUNNING
        ).count()
        if running_count >= settings.image_factory_max_concurrent_builds:
            messages.error(
                request,
                f"Maximum concurrent image builds ({settings.image_factory_max_concurrent_builds}) reached.",
            )
            return HttpResponse("Too many concurrent builds.", status=429)

        # --- Create build record ---
        cd = form.cleaned_data
        build = PackerImageBuild.objects.create(
            definition=definition,
            proxmox_endpoint=definition.proxmox_endpoint,
            target_node=definition.target_node,
            output_vmid=cd["output_vmid"],
            output_name=cd["output_name"],
            image_version=cd["image_version"],
            status=PackerBuildStatusChoices.PENDING,
            created_by=request.user,
        )

        # --- Enqueue job ---
        job = PackerImageBuildJob.enqueue(
            instance=build,
            user=request.user,
            job_timeout=settings.image_factory_default_job_timeout,
            force=cd["force"],
            dry_run=cd["dry_run"],
        )

        build.netbox_job_id = job.pk
        build.save(update_fields=["netbox_job_id"])

        messages.success(request, f"Packer image build queued (build #{build.pk}).")
        return redirect(
            reverse("plugins:netbox_packer:packerimagebuild", args=[build.pk])
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
    """POST-only view that cancels a running or pending Packer image build."""

    http_method_names = ["post"]
    additional_permissions = [
        get_permission_for_model(PackerImageBuild, "change"),
    ]

    def get_required_permission(self) -> str:
        return get_permission_for_model(Job, "delete")

    def post(self, request: HttpRequest, pk: int | str) -> HttpResponse:
        build = get_object_or_404(
            PackerImageBuild.objects.restrict(request.user, "view"),
            pk=pk,
        )

        if build.status not in (
            PackerBuildStatusChoices.PENDING,
            PackerBuildStatusChoices.RUNNING,
        ):
            messages.warning(request, f"Build #{build.pk} is not cancellable (status: {build.status}).")
            return redirect(
                reverse("plugins:netbox_packer:packerimagebuild", args=[build.pk])
            )

        # Cancel backend build if one was started.
        if build.backend_build_id:
            try:
                cancel_image_build(backend_build_id=build.backend_build_id)
            except ImageFactoryBackendError as exc:
                messages.warning(
                    request,
                    f"Backend cancel call failed (build may still stop): {exc}",
                )

        build.status = PackerBuildStatusChoices.CANCELLED
        build.save(update_fields=["status", "last_updated"])

        messages.success(request, f"Build #{build.pk} cancelled.")
        return redirect(
            reverse("plugins:netbox_packer:packerimagebuild", args=[build.pk])
        )
