# Netbox plugin related import
from extras.plugins import PluginConfig

class ProxboxConfig(PluginConfig):
    name = "netbox_proxbox"
    verbose_name = "Proxbox"
    description = "Integrates Proxmox and Netbox"
    version = "0.0.5-beta1"
    author = "Emerson Felipe (@emersonfelipesp)"
    author_email = "emerson.felipe@nmultifibra.com.br"
    base_url = "proxbox"
    required_settings = []
    default_settings = {
        'proxmox': {
            'domain': 'proxbox.example.com',    # May also be IP address
            'http_port': 8006,
            'user': 'root@pam',
            'password': 'Strong@P4ssword',
            'token': {
                'name': 'tokenID',
                'value': '039az154-23b2-4be0-8d20-b66abc8c4686'
            },
            'ssl': False
        },
        'netbox': {
            'domain': 'netbox.example.com',     # May also be IP address
            'http_port': 80,
            'token': '0dd7cddfaee3b38bbffbd2937d44c4a03f9c9d38',
            'ssl': False,
            'settings': {
                'virtualmachine_role_id' : 0,
                'node_role_id' : 0,
                'site_id': 0
            }
        }
    }

config = ProxboxConfig

from . import proxbox_api