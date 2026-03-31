"""Queue a targeted Proxbox sync for a single NetBox virtual machine."""

from __future__ import annotations

from django.contrib import messages
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from django.views import View
from virtualization.models import VirtualMachine

from netbox_proxbox.choices import SyncTypeChoices
from netbox_proxbox.jobs import PROXBOX_SYNC_QUEUE_NAME, ProxboxSyncJob
from netbox_proxbox.views.proxbox_access import permission_enqueue_proxbox_sync
from utilities.views import (
    ContentTypePermissionRequiredMixin,
    TokenConditionalLoginRequiredMixin,
    register_model_view,
)

__all__ = ("VirtualMachineSyncNowView",)


@register_model_view(VirtualMachine, "proxbox_sync_now", path="proxbox-sync-now")
class VirtualMachineSyncNowView(
    TokenConditionalLoginRequiredMixin,
    ContentTypePermissionRequiredMixin,
    View,
):
    """POST: enqueue VM + disk sync job targeting exactly one NetBox VM id."""

    http_method_names = ["post"]

    def get_required_permission(self):
        return permission_enqueue_proxbox_sync()

    def post(self, request, pk):
        vm = get_object_or_404(
            VirtualMachine.objects.restrict(request.user, "view"),
            pk=pk,
        )
        ProxboxSyncJob.enqueue(
            instance=None,
            user=request.user,
            queue_name=PROXBOX_SYNC_QUEUE_NAME,
            name=str(_("Proxbox Sync: Virtual machine {}")).format(vm.pk),
            sync_types=[
                SyncTypeChoices.VIRTUAL_MACHINES,
                SyncTypeChoices.VIRTUAL_MACHINES_DISKS,
            ],
            netbox_vm_ids=[str(vm.pk)],
        )
        messages.success(
            request,
            _("A sync job for this virtual machine has been queued."),
        )
        return HttpResponseRedirect(vm.get_absolute_url())
