"""Register the netbox-pbs NetBox plugin and declare its compatibility metadata.

This plugin adds read-only inventory for Proxmox Backup Server (PBS):
datastores, backup groups, snapshots, and job status. The integration
is `netbox-branching`-aware from day one and hard-depends on
``netbox_proxbox`` for shared utilities (NetBoxEndpoint, FastAPIEndpoint,
branch lifecycle helpers, HTTP client patterns).

A presentation-only cross-link panel is rendered on both the ``VMBackup``
detail page and the ``PBSSnapshot`` detail page. The two sides are
matched by natural key (``vmid`` + ``creation_time``) — no foreign key,
no schema change. See ``template_content.py``.
"""

from netbox.plugins import PluginConfig


class PBSConfig(PluginConfig):
    """Django app config for the netbox-pbs NetBox plugin."""

    name = "netbox_pbs"
    verbose_name = "Proxmox Backup Server"
    description = (
        "Read-only Proxmox Backup Server (PBS) inventory: datastores, "
        "backup groups, snapshots, and job status."
    )
    version = "0.0.1"
    author = "Emerson Felipe (@emersonfelipesp)"
    author_email = "emersonfelipe.2003@gmail.com"
    min_version = "4.5.8"
    max_version = "4.6.99"
    base_url = "pbs"
    required_settings = []
    required_plugins = ["netbox_proxbox"]
    queues = []


config = PBSConfig
