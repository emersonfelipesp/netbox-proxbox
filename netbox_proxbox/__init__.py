"""Register the ProxBox NetBox plugin and declare its compatibility metadata."""

# Netbox plugin related import
from netbox.plugins import PluginConfig


class ProxboxConfig(PluginConfig):
    """Django app config for the Proxbox NetBox plugin (URLs, queues, job registration)."""

    name = "netbox_proxbox"
    verbose_name = "Proxbox"
    description = "Integrates Proxmox and Netbox"
    version = "0.0.8"
    author = "Emerson Felipe (@emersonfelipesp)"
    author_email = "emersonfelipe.2003@gmail.com"
    min_version = "4.5.0"
    max_version = "4.5.99"
    base_url = "proxbox"
    required_settings = []
    queues = ["sync"]

    def ready(self):
        """Register models, then import job modules so runners and core Job views hook in."""
        super().ready()
        from . import jobs  # noqa: F401 — registers ProxboxSyncJob with the NetBox job system
        from .views import job_run  # noqa: F401 — core Job detail: proxbox-run + template button


config = ProxboxConfig

# from . import proxbox_api
