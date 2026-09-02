"""NetBox plugin template hooks (see PluginConfig template_extensions)."""

from __future__ import annotations

from urllib.parse import urlsplit

from core.choices import JobStatusChoices
from core.models import Job
from django.urls import NoReverseMatch, reverse
from django.utils.safestring import mark_safe
from netbox.plugins import PluginTemplateExtension
from utilities.permissions import get_permission_for_model
from utilities.views import get_viewname
from virtualization.models import VirtualMachine

from netbox_proxbox.bug_report import build_bug_report_context, is_reportable_status
from netbox_proxbox.jobs import is_proxbox_sync_job
from netbox_proxbox.intent.firewall_common import resolve_firewall_endpoint
from netbox_proxbox.models import (
    ProxmoxCluster,
    ProxmoxFirewallAlias,
    ProxmoxFirewallIPSet,
    ProxmoxFirewallIPSetEntry,
    ProxmoxFirewallOptions,
    ProxmoxFirewallRule,
    ProxmoxFirewallSecurityGroup,
    ProxmoxNode,
    ProxmoxStorage,
    ProxboxPluginSettings,
    VMBackup,
    VMSnapshot,
    VMTaskHistory,
)
from netbox_proxbox.views.operational import resolve_vm_endpoint_context
from netbox_proxbox.views.proxbox_access import (
    permission_enqueue_proxbox_sync,
    permission_run_proxmox_action,
)

__all__ = (
    "ProxboxJobTemplateExtension",
    "ProxboxVirtualMachineTemplateExtension",
    "ProxmoxClusterTemplateExtension",
    "ProxmoxFirewallPushTemplateExtension",
    "ProxmoxNodeTemplateExtension",
    "ProxmoxStorageTemplateExtension",
    "VMBackupTemplateExtension",
    "VMSnapshotTemplateExtension",
    "VMTaskHistoryTemplateExtension",
    "template_extensions",
)


def _sync_now_action_url(target) -> str | None:
    """Reverse the registered ``proxbox_sync_now`` action URL for *target*.

    Returns ``None`` when the action is not registered for the target's model,
    so callers can hide the button instead of rendering a POST that 404s
    (issue #294: the old approach concatenated ``get_absolute_url()`` with a
    hard-coded action suffix, silently assuming a route that
    ``register_model_view`` may never have mounted).
    """
    viewname = get_viewname(target, "proxbox_sync_now")
    try:
        return reverse(viewname, kwargs={"pk": target.pk})
    except NoReverseMatch:
        return None


def _console_base_url() -> str | None:
    """Return the configured console origin, rejecting unsafe values."""
    try:
        value = (
            str(ProxboxPluginSettings.get_solo().console_url or "").strip().rstrip("/")
        )
    except (AttributeError, RuntimeError):
        return None
    if any(character.isspace() for character in value):
        return None
    try:
        parsed = urlsplit(value)
        parsed.port
    except ValueError:
        return None
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        return None
    return value


def _synced_console_vm_type(vm: VirtualMachine) -> str | None:
    """Return a console type only for an authoritative synchronized guest record."""
    state = getattr(vm, "proxbox_sync_state", None)
    vmid = getattr(state, "proxmox_vm_id", None)
    vm_type = str(getattr(state, "proxmox_vm_type", "") or "").strip().lower()
    endpoint = getattr(state, "endpoint", None)
    if (
        not isinstance(vmid, int)
        or vmid < 1
        or endpoint is None
        or not bool(getattr(endpoint, "enabled", True))
    ):
        return None
    return vm_type if vm_type in {"qemu", "lxc"} else None


def _optional_related(obj: object, relation: str) -> object | None:
    """Return an optional reverse one-to-one relation without raising."""
    try:
        return getattr(obj, relation, None)
    except AttributeError:
        return None


def _ssh_key_count(cloud_init: object | None) -> int:
    """Count reflected cloud-init SSH keys without exposing their contents."""
    sshkeys = str(getattr(cloud_init, "sshkeys", "") or "")
    return sum(1 for line in sshkeys.splitlines() if line.strip())


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
            action_url = _sync_now_action_url(tracking)
        else:
            action_url = _sync_now_action_url(obj)
        if action_url is None:
            return ""
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
        # Joined HTML comes from this plugin's own templates rendered above.
        return mark_safe("".join(parts))  # nosec

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

        # Bug report: only for jobs that ended in an error/unknown state. The
        # modal shows data the user can already see on this page, so no extra
        # permission beyond viewing the Job is required.
        if is_reportable_status(obj.status):
            parts.append(
                self.render(
                    "netbox_proxbox/inc/bug_report_button.html",
                    build_bug_report_context(obj),
                )
            )

        # Joined HTML comes from this plugin's own templates rendered above.
        return mark_safe("".join(parts)) if parts else ""  # nosec

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

    def left_page(self) -> str:
        """Render typed Proxmox reflection data on a VM detail page."""
        obj = self.context["object"]
        if not isinstance(obj, VirtualMachine):
            return ""

        vm = (
            VirtualMachine.objects.select_related(
                "proxbox_sync_state__proxmox_node",
                "proxbox_sync_state__proxmox_cluster",
                "proxmox_cloudinit",
            )
            .filter(pk=obj.pk)
            .first()
        )
        if vm is None:
            return ""
        sync_state = _optional_related(vm, "proxbox_sync_state")
        cloud_init = _optional_related(vm, "proxmox_cloudinit")
        if sync_state is None and cloud_init is None:
            return ""

        rendered = self.render(
            "netbox_proxbox/inc/vm_proxmox_card.html",
            {
                "sync_state": sync_state,
                "cloud_init": cloud_init,
                "ssh_key_count": _ssh_key_count(cloud_init),
            },
        )
        # The rendered HTML comes from this plugin's own autoescaped template.
        return mark_safe(rendered)  # nosec

    def buttons(self) -> str:
        """Handle buttons."""
        obj = self.context["object"]
        if not isinstance(obj, VirtualMachine):
            return ""
        user = self.context["request"].user
        parts: list[str] = []
        if user.has_perm(permission_enqueue_proxbox_sync()):
            action_url = _sync_now_action_url(obj)
            if action_url is not None:
                parts.append(
                    self.render(
                        "netbox_proxbox/inc/vm_sync_now_button.html",
                        {
                            "vm": obj,
                            "action_url": action_url,
                        },
                    )
                )
        if user.has_perm(permission_run_proxmox_action()):
            resolved = resolve_vm_endpoint_context(obj)
            if resolved is not None:
                endpoint_id, _vmid, _vm_type = resolved
                from netbox_proxbox.models import ProxmoxEndpoint

                endpoint = ProxmoxEndpoint.objects.filter(pk=endpoint_id).first()
                allow_writes = bool(
                    endpoint and getattr(endpoint, "allow_writes", False)
                )
                base = obj.get_absolute_url()
                parts.append(
                    self.render(
                        "netbox_proxbox/inc/vm_operational_buttons.html",
                        {
                            "vm": obj,
                            "allow_writes": allow_writes,
                            "action_start_url": f"{base}proxbox-operational-start/",
                            "action_stop_url": f"{base}proxbox-operational-stop/",
                            "action_snapshot_url": f"{base}proxbox-operational-snapshot/",
                            "action_migrate_url": f"{base}proxbox-operational-migrate/",
                        },
                    )
                )
        # Joined HTML comes from this plugin's own templates rendered above.
        return mark_safe("".join(parts)) if parts else ""  # nosec

    def console_button(self) -> str:
        """Handle console button."""
        obj = self.context["object"]
        if not isinstance(obj, VirtualMachine):
            return ""
        user = self.context["request"].user
        if not user.has_perm(permission_enqueue_proxbox_sync()):
            return ""

        vm_type = _synced_console_vm_type(obj)
        console_base_url = _console_base_url()
        if vm_type is None or not console_base_url or not obj.pk:
            return ""
        resource = "lxc-containers" if vm_type == "lxc" else "virtual-machines"
        console_url = f"{console_base_url}/virtualization/{resource}/{obj.pk}"

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


class ProxmoxFirewallPushTemplateExtension(PluginTemplateExtension):
    """Inject a Push to Proxmox button on firewall object detail pages."""

    models = [
        "netbox_proxbox.proxmoxfirewallsecuritygroup",
        "netbox_proxbox.proxmoxfirewallrule",
        "netbox_proxbox.proxmoxfirewallipset",
        "netbox_proxbox.proxmoxfirewallipsetentry",
        "netbox_proxbox.proxmoxfirewallalias",
        "netbox_proxbox.proxmoxfirewalloptions",
    ]
    model_classes = (
        ProxmoxFirewallSecurityGroup,
        ProxmoxFirewallRule,
        ProxmoxFirewallIPSet,
        ProxmoxFirewallIPSetEntry,
        ProxmoxFirewallAlias,
        ProxmoxFirewallOptions,
    )

    def buttons(self) -> str:
        """Render Push to Proxmox for supported firewall objects."""
        obj = self.context["object"]
        if not isinstance(obj, self.model_classes):
            return ""
        user = self.context["request"].user
        if not user.has_perm(permission_run_proxmox_action()):
            return ""
        endpoint = resolve_firewall_endpoint(obj)
        allow_writes = bool(endpoint and getattr(endpoint, "allow_writes", False))
        return self.render(
            "netbox_proxbox/inc/firewall_push_button.html",
            {
                "object": obj,
                "allow_writes": allow_writes,
                "action_url": f"{obj.get_absolute_url()}push-to-proxmox/",
                "api_push_url": _firewall_api_action_url(obj, "push"),
            },
        ) + self.render("netbox_proxbox/inc/firewall_push_assets.html", {})

    def right_page(self) -> str:
        """Render a NetBox-vs-Proxmox preview panel."""
        obj = self.context["object"]
        if not isinstance(obj, self.model_classes):
            return ""
        user = self.context["request"].user
        if not user.has_perm(permission_run_proxmox_action()):
            return ""
        return self.render(
            "netbox_proxbox/inc/firewall_preview_panel.html",
            {
                "object": obj,
                "api_preview_url": _firewall_api_action_url(obj, "preview"),
            },
        )


def _firewall_api_action_url(obj: object, action: str) -> str:
    basename = obj._meta.model_name
    return reverse(
        f"plugins-api:netbox_proxbox-api:{basename}-{action}",
        kwargs={"pk": obj.pk},
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
    ProxmoxFirewallPushTemplateExtension,
]
