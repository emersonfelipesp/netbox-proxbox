"""NetBox plugin template hooks (see PluginConfig template_extensions)."""

from __future__ import annotations

from core.choices import JobStatusChoices
from core.models import Job
from netbox.plugins import PluginTemplateExtension

from netbox_proxbox.jobs import is_proxbox_sync_job
from netbox_proxbox.views.proxbox_access import permission_add_sync_process

__all__ = ("ProxboxJobTemplateExtension", "template_extensions")


class ProxboxJobTemplateExtension(PluginTemplateExtension):
    """Inject a Run now control on core Job detail for Proxbox Sync jobs."""

    models = ["core.job"]

    def buttons(self):
        obj = self.context["object"]
        if not isinstance(obj, Job) or not is_proxbox_sync_job(obj):
            return ""
        if obj.status in (
            JobStatusChoices.STATUS_PENDING,
            JobStatusChoices.STATUS_RUNNING,
        ):
            return ""
        user = self.context["request"].user
        if not user.has_perm(permission_add_sync_process()):
            return ""
        return self.render(
            "netbox_proxbox/inc/job_run_now_button.html",
            {"job": obj},
        )


template_extensions = [ProxboxJobTemplateExtension]
