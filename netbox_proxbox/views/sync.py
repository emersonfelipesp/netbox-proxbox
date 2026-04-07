"""Enqueue Proxbox sync operations as NetBox background jobs (RQ)."""

from __future__ import annotations

from typing import ClassVar

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.utils.html import format_html
from django.utils.text import format_lazy
from django.utils.translation import gettext_lazy as _
from django.views import View
from utilities.views import (
    ContentTypePermissionRequiredMixin,
    TokenConditionalLoginRequiredMixin,
)

from netbox_proxbox.choices import SyncTypeChoices
from netbox_proxbox.jobs import PROXBOX_SYNC_QUEUE_NAME, ProxboxSyncJob
from netbox_proxbox.views.proxbox_access import permission_enqueue_proxbox_sync


class _ProxboxSyncEnqueueView(
    TokenConditionalLoginRequiredMixin,
    ContentTypePermissionRequiredMixin,
    View,
):
    """POST: enqueue ``ProxboxSyncJob`` for a fixed sync type set."""

    http_method_names = ["post", "head", "options"]
    sync_types: ClassVar[list[str]] = [SyncTypeChoices.ALL]
    action_label: ClassVar = ""

    def get_required_permission(self) -> str:
        return permission_enqueue_proxbox_sync()

    def _job_name(self) -> str:
        if self.action_label:
            return str(format_lazy("{}: {}", _("Proxbox Sync"), self.action_label))
        return str(_("Proxbox Sync"))

    def post(
        self, request: HttpRequest, *args: object, **kwargs: object
    ) -> HttpResponse:
        try:
            job = ProxboxSyncJob.enqueue(
                instance=None,
                user=request.user,
                queue_name=PROXBOX_SYNC_QUEUE_NAME,
                name=self._job_name(),
                sync_types=list(self.sync_types),
            )
            messages.success(
                request,
                format_html(
                    '{} <a href="{}">{}</a>',
                    _(
                        "A Proxbox sync job has been queued. Open the job to follow progress."
                    ),
                    job.get_absolute_url(),
                    _("View job"),
                ),
            )
        except Exception as e:
            messages.error(
                request,
                format_html(
                    "{} <strong>{}</strong>",
                    _("Failed to enqueue sync job:"),
                    str(e),
                ),
            )
        return redirect("plugins:netbox_proxbox:home")


class SyncDevicesView(_ProxboxSyncEnqueueView):
    """POST: queue device sync."""

    sync_types = [SyncTypeChoices.DEVICES]
    action_label = _("Devices")


class SyncVirtualMachinesView(_ProxboxSyncEnqueueView):
    """POST: queue virtual machine + virtual disk sync."""

    sync_types = [
        SyncTypeChoices.VIRTUAL_MACHINES,
        SyncTypeChoices.VIRTUAL_MACHINES_DISKS,
    ]
    action_label = _("Virtual machines")


class SyncStorageView(_ProxboxSyncEnqueueView):
    """POST: queue storage sync."""

    sync_types = [SyncTypeChoices.STORAGE]
    action_label = _("Storage")


class SyncFullUpdateView(_ProxboxSyncEnqueueView):
    """POST: queue full multi-stage sync."""

    sync_types = [SyncTypeChoices.ALL]
    action_label = _("Full update")


class SyncVmBackupsView(_ProxboxSyncEnqueueView):
    """POST: queue VM backup sync."""

    sync_types = [SyncTypeChoices.VIRTUAL_MACHINES_BACKUPS]
    action_label = _("VM backups")


class SyncVirtualDisksView(_ProxboxSyncEnqueueView):
    """POST: queue virtual disk sync."""

    sync_types = [SyncTypeChoices.VIRTUAL_MACHINES_DISKS]
    action_label = _("Virtual disks")


class SyncVmSnapshotsView(_ProxboxSyncEnqueueView):
    """POST: queue VM snapshot sync."""

    sync_types = [SyncTypeChoices.VIRTUAL_MACHINES_SNAPSHOTS]
    action_label = _("VM snapshots")


class SyncNetworkInterfacesView(_ProxboxSyncEnqueueView):
    """POST: queue network interfaces sync (VM + node interfaces)."""

    sync_types = [SyncTypeChoices.NETWORK_INTERFACES]
    action_label = _("Network Interfaces")


class SyncIPAddressesView(_ProxboxSyncEnqueueView):
    """POST: queue IP addresses sync (depends on interfaces being synced first)."""

    sync_types = [SyncTypeChoices.IP_ADDRESSES]
    action_label = _("IP Addresses")


class SyncBackupRoutinesView(_ProxboxSyncEnqueueView):
    """POST: queue backup routines sync."""

    sync_types = [SyncTypeChoices.BACKUP_ROUTINES]
    action_label = _("Backup Routines")


class SyncReplicationsView(_ProxboxSyncEnqueueView):
    """POST: queue replications sync."""

    sync_types = [SyncTypeChoices.REPLICATIONS]
    action_label = _("Replications")


class _ProxboxSelectedSyncView(
    TokenConditionalLoginRequiredMixin,
    ContentTypePermissionRequiredMixin,
    View,
):
    """POST: enqueue a selected-object batch sync job."""

    http_method_names = ["post", "head", "options"]
    batch_object_type: ClassVar[str] = ""
    batch_object_label: ClassVar[str] = ""

    def get_required_permission(self) -> str:
        return permission_enqueue_proxbox_sync()

    def _selected_ids(self, request: HttpRequest) -> list[str]:
        return [str(value) for value in request.POST.getlist("pk") if str(value)]

    def _job_name(self) -> str:
        if self.batch_object_label:
            return str(
                format_lazy("{}: {}", _("Proxbox Sync"), self.batch_object_label)
            )
        return str(_("Proxbox Sync"))

    def post(
        self, request: HttpRequest, *args: object, **kwargs: object
    ) -> HttpResponse:
        selected_ids = self._selected_ids(request)
        if not selected_ids:
            messages.warning(request, _("Select at least one object to sync."))
            return redirect("plugins:netbox_proxbox:home")

        try:
            job = ProxboxSyncJob.enqueue(
                instance=None,
                user=request.user,
                queue_name=PROXBOX_SYNC_QUEUE_NAME,
                name=self._job_name(),
                sync_types=[SyncTypeChoices.ALL],
                batch_object_type=self.batch_object_type,
                batch_object_ids=selected_ids,
            )
            messages.success(
                request,
                format_html(
                    '{} <a href="{}">{}</a>',
                    _(
                        "A selected-object Proxbox sync job has been queued. Open the job to follow progress."
                    ),
                    job.get_absolute_url(),
                    _("View job"),
                ),
            )
        except Exception as e:
            messages.error(
                request,
                format_html(
                    "{} <strong>{}</strong>",
                    _("Failed to enqueue sync job:"),
                    str(e),
                ),
            )
        return redirect("plugins:netbox_proxbox:home")


class SyncSelectedVirtualMachinesView(_ProxboxSelectedSyncView):
    """POST: queue batch sync for selected virtual machines."""

    batch_object_type = "virtual-machine"
    batch_object_label = _("Virtual machines")


class SyncSelectedVMBackupsView(_ProxboxSelectedSyncView):
    """POST: queue batch sync for selected VM backups."""

    batch_object_type = "vm-backup"
    batch_object_label = _("VM backups")


class SyncSelectedVMSnapshotsView(_ProxboxSelectedSyncView):
    """POST: queue batch sync for selected VM snapshots."""

    batch_object_type = "vm-snapshot"
    batch_object_label = _("VM snapshots")


class SyncSelectedStorageView(_ProxboxSelectedSyncView):
    """POST: queue batch sync for selected Proxmox storage rows."""

    batch_object_type = "proxmox-storage"
    batch_object_label = _("Storage")


class SyncSelectedVMTaskHistoryView(_ProxboxSelectedSyncView):
    """POST: queue batch sync for selected VM task history rows."""

    batch_object_type = "vm-task-history"
    batch_object_label = _("VM task history")


sync_devices = SyncDevicesView.as_view()
sync_storage = SyncStorageView.as_view()
sync_virtual_machines = SyncVirtualMachinesView.as_view()
sync_full_update = SyncFullUpdateView.as_view()
sync_vm_backups = SyncVmBackupsView.as_view()
sync_vm_snapshots = SyncVmSnapshotsView.as_view()
sync_virtual_disks = SyncVirtualDisksView.as_view()
sync_network_interfaces = SyncNetworkInterfacesView.as_view()
sync_ip_addresses = SyncIPAddressesView.as_view()
sync_backup_routines = SyncBackupRoutinesView.as_view()
sync_replications = SyncReplicationsView.as_view()
sync_selected_virtual_machines = SyncSelectedVirtualMachinesView.as_view()
sync_selected_vm_backups = SyncSelectedVMBackupsView.as_view()
sync_selected_vm_snapshots = SyncSelectedVMSnapshotsView.as_view()
sync_selected_storage = SyncSelectedStorageView.as_view()
sync_selected_vm_task_history = SyncSelectedVMTaskHistoryView.as_view()
