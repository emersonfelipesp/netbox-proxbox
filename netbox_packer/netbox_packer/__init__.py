"""NetBox Packer plugin built on top of netbox-proxbox."""

from __future__ import annotations

from netbox.plugins import PluginConfig


class PackerConfig(PluginConfig):
    """Plugin metadata for Proxmox image builds backed by Packer."""

    name = "netbox_packer"
    verbose_name = "NetBox Packer"
    description = "Proxmox VM image baking via HashiCorp Packer and proxbox-api"
    version = "0.0.1"
    author = "N-MultiCloud"
    base_url = "packer"
    min_version = "4.5.8"
    max_version = "4.6.99"
    required_plugins = ["netbox_proxbox"]
    queues: list[str] = []


config = PackerConfig
