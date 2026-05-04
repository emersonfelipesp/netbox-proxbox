"""Queue a targeted Proxbox sync for a single NetBox virtual machine."""

from __future__ import annotations

from django.contrib import messages
from django.http import HttpRequest
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from django.views import View
from utilities.views import (
    ContentTypePermissionRequiredMixin,
    TokenConditionalLoginRequiredMixin,
    register_model_view,
)
from virtualization.models import VirtualMachine

from netbox_proxbox.choices import SyncTypeChoices
from netbox_proxbox.jobs import (
    PROXBOX_SYNC_QUEUE_NAME,
    ProxboxSyncJob,
)
from netbox_proxbox.models import ProxmoxEndpoint
from netbox_proxbox.views.proxbox_access import permission_enqueue_proxbox_sync

__all__ = ("VirtualMachineSyncNowView",)

_VM_SYNC_NOW_SYNC_TYPES: tuple[str, ...] = (
    SyncTypeChoices.VIRTUAL_MACHINES,
    SyncTypeChoices.VIRTUAL_MACHINES_BACKUPS,
    SyncTypeChoices.VIRTUAL_MACHINES_SNAPSHOTS,
)


@register_model_view(VirtualMachine, "proxbox_sync_now", path="proxbox-sync-now")
class VirtualMachineSyncNowView(
    TokenConditionalLoginRequiredMixin,
    ContentTypePermissionRequiredMixin,
    View,
):
    """POST: enqueue a targeted per-VM sync job."""

    http_method_names = ["post"]

    def get_required_permission(self) -> str:
        """Return required permission."""
        return permission_enqueue_proxbox_sync()

    def post(self, request: HttpRequest, pk: int | str) -> HttpResponseRedirect:
        """Handle post."""
        vm = get_object_or_404(
            VirtualMachine.objects.restrict(request.user, "view"),
            pk=pk,
        )
        ProxboxSyncJob.enqueue(
            instance=None,
            user=request.user,
            queue_name=PROXBOX_SYNC_QUEUE_NAME,
            name=str(_("Proxbox Sync: Virtual machine {}")).format(vm.pk),
            sync_types=list(_VM_SYNC_NOW_SYNC_TYPES),
            netbox_vm_ids=[str(vm.pk)],
            proxmox_endpoint_ids=list(
                ProxmoxEndpoint.objects.values_list("pk", flat=True)
            ),
        )
        messages.success(
            request,
            _("A sync job for this virtual machine has been queued."),
        )
        return HttpResponseRedirect(vm.get_absolute_url())
