# Netbox plugin related import
from netbox.plugins import PluginConfig

class ProxboxConfig(PluginConfig):
    name = "netbox_proxbox"
    verbose_name = "Proxbox"
    description = "Integrates Proxmox and Netbox"
    version = "0.0.6b2"
    author = "Emerson Felipe (@emersonfelipesp)"
    author_email = "emersonfelipe.2003@gmail.com"
    min_version = '4.2.0'
    max_version = '4.2.99'
    base_url = "proxbox"
    required_settings = []

config = ProxboxConfig

#from . import proxbox_api