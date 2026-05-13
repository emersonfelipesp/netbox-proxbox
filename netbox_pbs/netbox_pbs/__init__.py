"""Register the netbox-pbs NetBox plugin and declare its compatibility metadata.

This plugin adds read-only inventory for Proxmox Backup Server (PBS):
datastores, backup groups, snapshots, and job status. The integration
is `netbox-branching`-aware from day one (the branch lifecycle helpers
mirror those used by ``netbox_proxbox``).

This file ships in PR C1 as scaffold only — domain models, sync jobs,
and the optional cross-link to ``netbox_proxbox.VMBackup`` land in
subsequent sub-PRs of issue #325.
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
    version = "0.0.15"
    author = "Emerson Felipe (@emersonfelipesp)"
    author_email = "emersonfelipe.2003@gmail.com"
    min_version = "4.5.8"
    max_version = "4.6.99"
    base_url = "pbs"
    required_settings = []
    queues = []


config = PBSConfig
