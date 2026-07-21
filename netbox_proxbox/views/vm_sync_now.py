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
from netbox_proxbox.models import ProxmoxCluster, ProxmoxEndpoint
from netbox_proxbox.views.proxbox_access import permission_enqueue_proxbox_sync

__all__ = ("VirtualMachineSyncNowView",)

_VM_SYNC_NOW_SYNC_TYPES: tuple[str, ...] = (
    SyncTypeChoices.VIRTUAL_MACHINES,
    SyncTypeChoices.VIRTUAL_MACHINES_BACKUPS,
    SyncTypeChoices.VIRTUAL_MACHINES_SNAPSHOTS,
)


def _endpoint_ids_for_vm(vm: VirtualMachine) -> list[int]:
    """Return the Proxmox endpoint id(s) that can host ``vm``.

    A targeted per-VM sync only needs the endpoint the VM actually lives on.
    Passing every enabled endpoint made the job run cluster/node preflight
    against the whole estate for a single VM (a reporter with 8 endpoints saw
    all 8 synced before their one VM was touched).

    The VM's NetBox cluster maps to a ``ProxmoxCluster``, which carries the
    owning endpoint. If that cannot be resolved -- the VM has no cluster, or the
    cluster has no reflected Proxmox counterpart yet -- fall back to all enabled
    endpoints so a first-ever sync can still discover the VM.
    """
    if vm.cluster_id:
        endpoint_ids = list(
            ProxmoxCluster.objects.filter(netbox_cluster_id=vm.cluster_id)
            .exclude(endpoint__isnull=True)
            .filter(endpoint__enabled=True)
            .values_list("endpoint_id", flat=True)
            .distinct()
        )
        if endpoint_ids:
            return endpoint_ids

    return list(
        ProxmoxEndpoint.objects.filter(enabled=True).values_list("pk", flat=True)
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
            proxmox_endpoint_ids=_endpoint_ids_for_vm(vm),
        )
        messages.success(
            request,
            _("A sync job for this virtual machine has been queued."),
        )
        return HttpResponseRedirect(vm.get_absolute_url())
