"""NetBox views for endpoint-owned application services."""

from netbox.object_actions import AddObject, BulkDelete
from netbox.views import generic
from django.core.exceptions import PermissionDenied
from utilities.views import register_model_view

from netbox_proxbox.filtersets import (
    ProxmoxEndpointServiceFilterSet,
    ServiceSSHCredentialFilterSet,
)
from netbox_proxbox.forms import (
    ProxmoxEndpointServiceFilterForm,
    ProxmoxEndpointServiceForm,
)
from netbox_proxbox.models import (
    ProxmoxEndpoint,
    ProxmoxEndpointService,
    ServiceSSHCredential,
)
from netbox_proxbox.tables import (
    ProxmoxEndpointServiceTable,
    ServiceSSHCredentialTable,
)
from netbox_proxbox.views.confirmed_cleanup import (
    ConfirmedCleanupBulkDeleteMixin,
    ConfirmedCleanupDeleteMixin,
)


@register_model_view(ProxmoxEndpointService)
class ProxmoxEndpointServiceView(generic.ObjectView):
    queryset = ProxmoxEndpointService.objects.select_related("endpoint")

    def get_extra_context(self, request, instance) -> dict[str, object]:
        """Expose credential metadata only when the actor may view it."""
        credential = (
            ServiceSSHCredential.objects.restrict(request.user, "view")
            .filter(service=instance)
            .first()
        )
        return {"service_ssh_credential": credential}


@register_model_view(ProxmoxEndpointService, "list", path="", detail=False)
class ProxmoxEndpointServiceListView(generic.ObjectListView):
    queryset = ProxmoxEndpointService.objects.select_related("endpoint")
    table = ProxmoxEndpointServiceTable
    filterset = ProxmoxEndpointServiceFilterSet
    filterset_form = ProxmoxEndpointServiceFilterForm
    actions = (AddObject, BulkDelete)


class _EndpointChangeRequiredMixin:
    """Limit service mutations to parents the actor may change."""

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        endpoints = ProxmoxEndpoint.objects.restrict(request.user, "change")
        return queryset.filter(endpoint__in=endpoints)


class _CredentialEndpointChangeRequiredMixin:
    """Limit credential deletion to services whose endpoint the actor may change."""

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        endpoints = ProxmoxEndpoint.objects.restrict(request.user, "change")
        return queryset.filter(service__endpoint__in=endpoints)


class _ServiceCleanupMixin:
    """Clean service-owned provider state within the confirmed delete scope."""

    def cleanup_boundary(self, request, objects):
        from netbox_proxbox.integrations.openbao_service import (
            service_cleanup_boundary,
        )

        return service_cleanup_boundary(objects, actor=request.user, request=request)

    def cleanup_objects(self, request, objects) -> None:
        from netbox_proxbox.integrations.openbao_service import cleanup_service_state

        for service in objects:
            cleanup_service_state(service, actor=request.user)


class _ServiceCredentialCleanupMixin:
    """Clean credential assignments within the confirmed delete scope."""

    def cleanup_boundary(self, request, objects):
        from netbox_proxbox.integrations.openbao_service import (
            service_cleanup_boundary,
        )

        return service_cleanup_boundary(
            [owner.service for owner in objects],
            actor=request.user,
            request=request,
        )

    def cleanup_objects(self, request, objects) -> None:
        from netbox_proxbox.integrations.openbao_service import (
            cleanup_service_credential,
        )

        for owner in objects:
            cleanup_service_credential(owner, actor=request.user)


@register_model_view(ProxmoxEndpointService, "add", detail=False)
@register_model_view(ProxmoxEndpointService, "edit")
class ProxmoxEndpointServiceEditView(
    _EndpointChangeRequiredMixin, generic.ObjectEditView
):
    queryset = ProxmoxEndpointService.objects.select_related("endpoint")
    form = ProxmoxEndpointServiceForm


@register_model_view(ProxmoxEndpointService, "delete")
class ProxmoxEndpointServiceDeleteView(
    _ServiceCleanupMixin,
    ConfirmedCleanupDeleteMixin,
    _EndpointChangeRequiredMixin,
    generic.ObjectDeleteView,
):
    queryset = ProxmoxEndpointService.objects.select_related("endpoint")


@register_model_view(ProxmoxEndpointService, "bulk_delete", detail=False)
class ProxmoxEndpointServiceBulkDeleteView(
    _ServiceCleanupMixin,
    ConfirmedCleanupBulkDeleteMixin,
    _EndpointChangeRequiredMixin,
    generic.BulkDeleteView,
):
    queryset = ProxmoxEndpointService.objects.select_related("endpoint")
    table = ProxmoxEndpointServiceTable

    def validate_cleanup_selection(self, request, primary_keys) -> None:
        """Reject the whole selection when any parent is outside change scope."""
        if primary_keys:
            requested = ProxmoxEndpointService.objects.filter(pk__in=primary_keys)
            allowed = self.get_queryset(request).filter(pk__in=primary_keys)
            if requested.count() != allowed.count():
                raise PermissionDenied(
                    "You do not have permission to change every owning Proxmox endpoint."
                )


@register_model_view(ServiceSSHCredential)
class ServiceSSHCredentialView(generic.ObjectView):
    queryset = ServiceSSHCredential.objects.select_related(
        "service", "service__endpoint"
    )


@register_model_view(ServiceSSHCredential, "list", path="", detail=False)
class ServiceSSHCredentialListView(generic.ObjectListView):
    queryset = ServiceSSHCredential.objects.select_related(
        "service", "service__endpoint"
    )
    table = ServiceSSHCredentialTable
    filterset = ServiceSSHCredentialFilterSet
    actions = (BulkDelete,)


@register_model_view(ServiceSSHCredential, "delete")
class ServiceSSHCredentialDeleteView(
    _ServiceCredentialCleanupMixin,
    ConfirmedCleanupDeleteMixin,
    _CredentialEndpointChangeRequiredMixin,
    generic.ObjectDeleteView,
):
    queryset = ServiceSSHCredential.objects.select_related(
        "service", "service__endpoint"
    )


@register_model_view(ServiceSSHCredential, "bulk_delete", detail=False)
class ServiceSSHCredentialBulkDeleteView(
    _ServiceCredentialCleanupMixin,
    ConfirmedCleanupBulkDeleteMixin,
    _CredentialEndpointChangeRequiredMixin,
    generic.BulkDeleteView,
):
    queryset = ServiceSSHCredential.objects.select_related(
        "service", "service__endpoint"
    )
    table = ServiceSSHCredentialTable

    def validate_cleanup_selection(self, request, primary_keys) -> None:
        """Reject the whole selection when any owning endpoint is outside change scope."""
        if primary_keys:
            requested = ServiceSSHCredential.objects.filter(pk__in=primary_keys)
            allowed = self.get_queryset(request).filter(pk__in=primary_keys)
            if requested.count() != allowed.count():
                raise PermissionDenied(
                    "You do not have permission to change every owning Proxmox endpoint."
                )
