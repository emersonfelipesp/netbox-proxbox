# Netbox plugin related import
from extras.plugins import PluginConfig

class ProxboxConfig(PluginConfig):
    name = "netbox_proxbox"
    verbose_name = "Proxbox"
    description = "Integrates Proxmox and Netbox"
    version = "0.1"
    author = "Emerson Felipe (@emersonfelipesp)"
    author_email = "emerson.felipe@nmultifibra.com.br"
    #base_url = "proxbox"
    required_settings = []
    default_settings = {}


config = ProxboxConfig
