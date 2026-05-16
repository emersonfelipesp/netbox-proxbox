"""NetBox Ceph plugin built on top of netbox-proxbox."""

from __future__ import annotations

from netbox.plugins import PluginConfig


class CephConfig(PluginConfig):
    """Plugin metadata for the read-only Ceph inventory package."""

    name = "netbox_ceph"
    verbose_name = "NetBox Ceph"
    description = "Read-only Ceph inventory via netbox-proxbox and proxbox-api"
    version = "0.0.1"
    author = "N-MultiCloud"
    base_url = "ceph"
    min_version = "4.5.8"
    max_version = "4.6.99"
    required_plugins = ["netbox_proxbox"]
    queues: list[str] = []


config = CephConfig
