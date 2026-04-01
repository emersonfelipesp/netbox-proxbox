"""Register the ProxBox NetBox plugin and declare its compatibility metadata."""

# Netbox plugin related import
from netbox.plugins import PluginConfig


class ProxboxConfig(PluginConfig):
    """Django app config for the Proxbox NetBox plugin (URLs, queues, job registration).

    Proxbox sync work is enqueued as core NetBox Jobs (see ``jobs.ProxboxSyncJob``) on
    ``netbox.constants.RQ_QUEUE_DEFAULT`` (``jobs.PROXBOX_SYNC_QUEUE_NAME``), so the stock
    ``manage.py rqworker`` without extra queue flags picks them up. We intentionally do not
    register a dedicated plugin RQ queue here (``queues`` empty); legacy jobs may still show
    ``queue_name`` ``netbox_proxbox.sync`` from older releases.
    """

    name = "netbox_proxbox"
    verbose_name = "Proxbox"
    description = "Integrates Proxmox and Netbox"
    version = "0.0.10"
    author = "Emerson Felipe (@emersonfelipesp)"
    author_email = "emersonfelipe.2003@gmail.com"
    min_version = "4.5.0"
    max_version = "4.5.99"
    base_url = "proxbox"
    required_settings = []
    queues = []

    def ready(self):
        """Register models, then import job modules so runners and core Job views hook in."""
        super().ready()
        from . import jobs  # noqa: F401 — registers ProxboxSyncJob with the NetBox job system
        from .views import job_cancel, job_run  # noqa: F401 — core Job: proxbox-run / proxbox-cancel


config = ProxboxConfig

# from . import proxbox_api
