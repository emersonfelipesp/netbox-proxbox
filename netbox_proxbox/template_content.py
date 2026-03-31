"""NetBox plugin template hooks (see PluginConfig template_extensions)."""

from __future__ import annotations

from core.choices import JobStatusChoices
from core.models import Job
from django.utils.safestring import mark_safe
from netbox.plugins import PluginTemplateExtension
from utilities.permissions import get_permission_for_model
from virtualization.models import VirtualMachine

from netbox_proxbox.jobs import is_proxbox_sync_job
from netbox_proxbox.views.proxbox_access import permission_enqueue_proxbox_sync

__all__ = (
    "ProxboxJobTemplateExtension",
    "ProxboxVirtualMachineTemplateExtension",
    "template_extensions",
)


class ProxboxJobTemplateExtension(PluginTemplateExtension):
    """Inject Run now / Cancel controls on core Job detail for Proxbox Sync jobs."""

    models = ["core.job"]

    def alerts(self):
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

    def buttons(self):
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

    def left_page(self):
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

    def buttons(self):
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


template_extensions = [
    ProxboxJobTemplateExtension,
    ProxboxVirtualMachineTemplateExtension,
]
