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
        """Render Run now (finished jobs only) and Cancel (pending/scheduled/running) as permitted."""
        obj = self.context["object"]
        if not isinstance(obj, Job) or not is_proxbox_sync_job(obj):
            return ""
        user = self.context["request"].user
        parts: list[str] = []

        if obj.status in JobStatusChoices.TERMINAL_STATE_CHOICES:
            if user.has_perm(permission_enqueue_proxbox_sync()):
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
        vm_type = obj.custom_field_data.get(
            "proxmox_vm_type"
        ) or obj.custom_field_data.get("cf_proxmox_vm_type", "qemu")

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


class ProxmoxClusterTemplateExtension(PluginTemplateExtension):
    """Inject Sync Now action on virtualization.Cluster detail pages."""

    models = ["virtualization.cluster"]

    def buttons(self) -> str:
        """Handle buttons."""
        obj = self.context["object"]
        user = self.context["request"].user
        if not user.has_perm(permission_enqueue_proxbox_sync()):
            return ""
        proxbox_cluster = obj.proxmox_cluster_tracking.first()
        if not proxbox_cluster:
            return ""
        return self.render(
            "netbox_proxbox/inc/cluster_sync_now_button.html",
            {
                "cluster": obj,
                "action_url": f"{proxbox_cluster.get_absolute_url()}proxbox-sync-now/",
            },
        )


class ProxmoxNodeTemplateExtension(PluginTemplateExtension):
    """Inject Sync Now action on dcim.Device detail pages for Proxmox nodes."""

    models = ["dcim.device"]

    def buttons(self) -> str:
        """Handle buttons."""
        obj = self.context["object"]
        user = self.context["request"].user
        if not user.has_perm(permission_enqueue_proxbox_sync()):
            return ""
        proxbox_node = obj.proxmox_node_tracking.first()
        if not proxbox_node:
            return ""
        return self.render(
            "netbox_proxbox/inc/node_sync_now_button.html",
            {
                "device": obj,
                "action_url": f"{proxbox_node.get_absolute_url()}proxbox-sync-now/",
            },
        )


class ProxmoxStorageTemplateExtension(PluginTemplateExtension):
    """Inject Sync Now action on ProxmoxStorage detail pages."""

    models = ["netbox_proxbox.proxmoxstorage"]

    def buttons(self) -> str:
        """Handle buttons."""
        obj = self.context["object"]
        if not isinstance(obj, ProxmoxStorage):
            return ""
        user = self.context["request"].user
        if not user.has_perm(permission_enqueue_proxbox_sync()):
            return ""
        return self.render(
            "netbox_proxbox/inc/storage_sync_now_button.html",
            {
                "storage": obj,
                "action_url": f"{obj.get_absolute_url()}proxbox-sync-now/",
            },
        )


class VMBackupTemplateExtension(PluginTemplateExtension):
    """Inject Sync Now action on VMBackup detail pages."""

    models = ["netbox_proxbox.vmbackup"]

    def buttons(self) -> str:
        """Handle buttons."""
        obj = self.context["object"]
        if not isinstance(obj, VMBackup):
            return ""
        user = self.context["request"].user
        if not user.has_perm(permission_enqueue_proxbox_sync()):
            return ""
        return self.render(
            "netbox_proxbox/inc/vm_backup_sync_now_button.html",
            {
                "backup": obj,
                "action_url": f"{obj.get_absolute_url()}proxbox-sync-now/",
            },
        )


class VMSnapshotTemplateExtension(PluginTemplateExtension):
    """Inject Sync Now action on VMSnapshot detail pages."""

    models = ["netbox_proxbox.vmsnapshot"]

    def buttons(self) -> str:
        """Handle buttons."""
        obj = self.context["object"]
        if not isinstance(obj, VMSnapshot):
            return ""
        user = self.context["request"].user
        if not user.has_perm(permission_enqueue_proxbox_sync()):
            return ""
        return self.render(
            "netbox_proxbox/inc/vm_snapshot_sync_now_button.html",
            {
                "snapshot": obj,
                "action_url": f"{obj.get_absolute_url()}proxbox-sync-now/",
            },
        )


class VMTaskHistoryTemplateExtension(PluginTemplateExtension):
    """Inject Sync Now action on VMTaskHistory detail pages."""

    models = ["netbox_proxbox.vmtaskhistory"]

    def buttons(self) -> str:
        """Handle buttons."""
        obj = self.context["object"]
        if not isinstance(obj, VMTaskHistory):
            return ""
        user = self.context["request"].user
        if not user.has_perm(permission_enqueue_proxbox_sync()):
            return ""
        return self.render(
            "netbox_proxbox/inc/task_history_sync_now_button.html",
            {
                "task_history": obj,
                "action_url": f"{obj.get_absolute_url()}proxbox-sync-now/",
            },
        )


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
