"""Standalone NetBox plugin for Proxmox Backup Server inventory."""

from __future__ import annotations

from netbox.plugins import PluginConfig


class PBSConfig(PluginConfig):
    """Plugin metadata for PBS inventory reflected through proxbox-api."""

    name = "netbox_pbs"
    verbose_name = "NetBox PBS"
    description = "Proxmox Backup Server inventory via proxbox-api"
    version = "0.0.1"
    author = "N-MultiCloud"
    base_url = "pbs"
    min_version = "4.5.8"
    max_version = "4.6.99"
    queues: list[str] = []


config = PBSConfig
