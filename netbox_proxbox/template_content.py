"""NetBox plugin template hooks (see PluginConfig template_extensions)."""

from __future__ import annotations

from core.choices import JobStatusChoices
from core.models import Job
from django.utils.safestring import mark_safe
from netbox.plugins import PluginTemplateExtension
from utilities.permissions import get_permission_for_model
from virtualization.models import VirtualMachine

from netbox_proxbox.jobs import is_proxbox_sync_job
from netbox_proxbox.models import (
    ProxmoxCluster,
    ProxmoxNode,
    ProxmoxStorage,
    VMBackup,
    VMSnapshot,
    VMTaskHistory,
)
from netbox_proxbox.views.proxbox_access import permission_enqueue_proxbox_sync

__all__ = (
    "ProxboxJobTemplateExtension",
    "ProxboxVirtualMachineTemplateExtension",
    "ProxmoxClusterTemplateExtension",
    "ProxmoxNodeTemplateExtension",
    "ProxmoxStorageTemplateExtension",
    "VMBackupTemplateExtension",
    "VMSnapshotTemplateExtension",
    "VMTaskHistoryTemplateExtension",
    "template_extensions",
)


class _SyncNowButtonExtension(PluginTemplateExtension):
    """Base that renders a sync-now button on a model detail page.

    Subclasses set class attributes to parameterise the behaviour:

    * ``button_template`` – path to the Django template for the button.
    * ``context_key``      – key used to pass the page object into the template.
    * ``model_class``      – optional model type; when set, ``isinstance`` is checked first.
    * ``tracking_attr``    – optional relation name (e.g. ``"proxmox_node_tracking"``);
      when set the first related object must exist and its URL is used for the
      action.  When *None* the page object's own URL is used.
    """

    button_template: str
    context_key: str
    model_class: type | None = None
    tracking_attr: str | None = None

    def buttons(self) -> str:
        obj = self.context["object"]
        if self.model_class is not None and not isinstance(obj, self.model_class):
            return ""
        user = self.context["request"].user
        if not user.has_perm(permission_enqueue_proxbox_sync()):
            return ""
        if self.tracking_attr is not None:
            tracking = getattr(obj, self.tracking_attr).first()
            if not tracking:
                return ""
            action_url = f"{tracking.get_absolute_url()}proxbox-sync-now/"
        else:
            action_url = f"{obj.get_absolute_url()}proxbox-sync-now/"
        return self.render(
            self.button_template,
            {self.context_key: obj, "action_url": action_url},
        )


class ProxboxJobTemplateExtension(PluginTemplateExtension):
    """Inject Run now / Cancel controls on core Job detail for Proxbox Sync jobs."""

    models = ["core.job"]

    def alerts(self) -> str:
        """Load job log DOM helpers for any Proxbox job; live poll only while non-terminal."""
        obj = self.context["object"]
        if not isinstance(obj, Job):
            return ""
        if not is_proxbox_sync_job(obj):
            return ""
        parts = [self.render("netbox_proxbox/inc/job_log_assets.html")]
        if obj.status in JobStatusChoices.ENQUEUED_STATE_CHOICES:
            parts.append(
                self.render(
                    "netbox_proxbox/inc/job_live_poll_alert.html",
                    {"job": obj},
                )
            )
        return mark_safe("".join(parts))

    def buttons(self) -> str:
        """Render Run now and Cancel buttons on Proxbox Sync job detail pages.

        Run now: shown for terminal jobs (re-run) and scheduled jobs (run immediately
        without cancelling the original).
        Cancel: shown for all enqueued states (pending, scheduled, running).
        Both buttons appear together for scheduled jobs.
        """
        obj = self.context["object"]
        if not isinstance(obj, Job) or not is_proxbox_sync_job(obj):
            return ""
        user = self.context["request"].user
        parts: list[str] = []

        show_run_now = (
            obj.status in JobStatusChoices.TERMINAL_STATE_CHOICES
            or obj.status == JobStatusChoices.STATUS_SCHEDULED
        )
        if show_run_now and user.has_perm(permission_enqueue_proxbox_sync()):
            parts.append(
                self.render(
                    "netbox_proxbox/inc/job_run_now_button.html",
                    {"job": obj},
                )
            )

        if obj.status in JobStatusChoices.ENQUEUED_STATE_CHOICES:
            if user.has_perm(get_permission_for_model(Job, "delete")):
                parts.append(
                    self.render(
                        "netbox_proxbox/inc/job_cancel_button.html",
                        {"job": obj},
                    )
                )

        return mark_safe("".join(parts)) if parts else ""

    def left_page(self) -> str:
        """Show last Proxbox sync runtime and stage summary on Job detail."""
        obj = self.context["object"]
        if not isinstance(obj, Job) or not is_proxbox_sync_job(obj):
            return ""
        return self.render(
            "netbox_proxbox/inc/job_runtime_panel.html",
            {"job": obj},
        )


class ProxboxVirtualMachineTemplateExtension(PluginTemplateExtension):
    """Inject Sync Now action on VirtualMachine detail pages."""

    models = ["virtualization.virtualmachine"]

    def buttons(self) -> str:
        """Handle buttons."""
        obj = self.context["object"]
        if not isinstance(obj, VirtualMachine):
            return ""
        user = self.context["request"].user
        if not user.has_perm(permission_enqueue_proxbox_sync()):
            return ""
        return self.render(
            "netbox_proxbox/inc/vm_sync_now_button.html",
            {
                "vm": obj,
                "action_url": f"{obj.get_absolute_url()}proxbox-sync-now/",
            },
        )

    def console_button(self) -> str:
        """Handle console button."""
        obj = self.context["object"]
        if not isinstance(obj, VirtualMachine):
            return ""
        user = self.context["request"].user
        if not user.has_perm(permission_enqueue_proxbox_sync()):
            return ""

        vmid = obj.custom_field_data.get("proxmox_vm_id") or obj.custom_field_data.get(
            "cf_proxmox_vm_id"
        )
        vm_type_obj = getattr(obj, "virtual_machine_type", None)
        if vm_type_obj and hasattr(vm_type_obj, "slug"):
            slug = str(vm_type_obj.slug).lower()
            if "lxc" in slug:
                vm_type = "lxc"
            elif "qemu" in slug:
                vm_type = "qemu"
            else:
                cf = getattr(obj, "custom_field_data", {}) or {}
                vm_type = str(
                    cf.get("proxmox_vm_type") or cf.get("cf_proxmox_vm_type") or "qemu"
                )
        else:
            cf = getattr(obj, "custom_field_data", {}) or {}
            vm_type = str(
                cf.get("proxmox_vm_type") or cf.get("cf_proxmox_vm_type") or "qemu"
            )

        node = ""
        if hasattr(obj, "device") and obj.device:
            node = obj.device.name
        else:
            node = obj.custom_field_data.get(
                "proxmox_node"
            ) or obj.custom_field_data.get("cf_proxmox_node", "")

        endpoint_url = ""
        if obj.cluster:
            proxbox_cluster = obj.cluster.proxmox_cluster_tracking.first()
            if proxbox_cluster and proxbox_cluster.endpoint:
                endpoint_url = proxbox_cluster.endpoint.url

        if not all([vmid, node, endpoint_url]):
            return ""

        if vm_type == "lxc":
            console_url = (
                f"{endpoint_url}/?console=lxc&xtermjs=1&vmid={vmid}"
                f"&vmname={obj.name}&node={node}&cmd="
            )
        else:
            console_url = (
                f"{endpoint_url}/?console=kvm&novnc=1&vmid={vmid}"
                f"&vmname={obj.name}&node={node}&resize=off&cmd="
            )

        return self.render(
            "netbox_proxbox/inc/vm_console_button.html",
            {"console_url": console_url},
        )


class ProxmoxClusterTemplateExtension(_SyncNowButtonExtension):
    """Inject Sync Now action on virtualization.Cluster detail pages."""

    models = ["virtualization.cluster"]
    button_template = "netbox_proxbox/inc/cluster_sync_now_button.html"
    context_key = "cluster"
    tracking_attr = "proxmox_cluster_tracking"


class ProxmoxNodeTemplateExtension(_SyncNowButtonExtension):
    """Inject Sync Now action on dcim.Device detail pages for Proxmox nodes."""

    models = ["dcim.device"]
    button_template = "netbox_proxbox/inc/node_sync_now_button.html"
    context_key = "device"
    tracking_attr = "proxmox_node_tracking"


class ProxmoxStorageTemplateExtension(_SyncNowButtonExtension):
    """Inject Sync Now action on ProxmoxStorage detail pages."""

    models = ["netbox_proxbox.proxmoxstorage"]
    button_template = "netbox_proxbox/inc/storage_sync_now_button.html"
    context_key = "storage"
    model_class = ProxmoxStorage


class VMBackupTemplateExtension(_SyncNowButtonExtension):
    """Inject Sync Now action on VMBackup detail pages."""

    models = ["netbox_proxbox.vmbackup"]
    button_template = "netbox_proxbox/inc/vm_backup_sync_now_button.html"
    context_key = "backup"
    model_class = VMBackup


class VMSnapshotTemplateExtension(_SyncNowButtonExtension):
    """Inject Sync Now action on VMSnapshot detail pages."""

    models = ["netbox_proxbox.vmsnapshot"]
    button_template = "netbox_proxbox/inc/vm_snapshot_sync_now_button.html"
    context_key = "snapshot"
    model_class = VMSnapshot


class VMTaskHistoryTemplateExtension(_SyncNowButtonExtension):
    """Inject Sync Now action on VMTaskHistory detail pages."""

    models = ["netbox_proxbox.vmtaskhistory"]
    button_template = "netbox_proxbox/inc/task_history_sync_now_button.html"
    context_key = "task_history"
    model_class = VMTaskHistory


template_extensions = [
    ProxboxJobTemplateExtension,
    ProxboxVirtualMachineTemplateExtension,
    ProxmoxClusterTemplateExtension,
    ProxmoxNodeTemplateExtension,
    ProxmoxStorageTemplateExtension,
    VMBackupTemplateExtension,
    VMSnapshotTemplateExtension,
    VMTaskHistoryTemplateExtension,
]
