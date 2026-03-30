"""Enqueue Proxbox sync operations as NetBox background jobs (RQ)."""

from __future__ import annotations

from typing import Any, ClassVar

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.utils.html import format_html
from django.utils.text import format_lazy
from django.utils.translation import gettext_lazy as _
from django.views import View

from netbox_proxbox.choices import SyncTypeChoices
from netbox_proxbox.jobs import PROXBOX_SYNC_QUEUE_NAME, ProxboxSyncJob
from netbox_proxbox.views.proxbox_access import permission_enqueue_proxbox_sync
from utilities.views import (
    ContentTypePermissionRequiredMixin,
    TokenConditionalLoginRequiredMixin,
)


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

    def post(self, request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
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
        return redirect("plugins:netbox_proxbox:home")


class SyncDevicesView(_ProxboxSyncEnqueueView):
    """POST: queue device sync."""

    sync_types = [SyncTypeChoices.DEVICES]
    action_label = _("Devices")


class SyncVirtualMachinesView(_ProxboxSyncEnqueueView):
    """POST: queue virtual machine sync."""

    sync_types = [SyncTypeChoices.VIRTUAL_MACHINES]
    action_label = _("Virtual machines")


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


sync_devices = SyncDevicesView.as_view()
sync_virtual_machines = SyncVirtualMachinesView.as_view()
sync_full_update = SyncFullUpdateView.as_view()
sync_vm_backups = SyncVmBackupsView.as_view()
sync_vm_snapshots = SyncVmSnapshotsView.as_view()
sync_virtual_disks = SyncVirtualDisksView.as_view()
