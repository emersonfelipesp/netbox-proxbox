# Netbox plugin related import
from netbox.plugins import PluginConfig

class ProxboxConfig(PluginConfig):
    name = "netbox_proxbox"
    verbose_name = "Proxbox"
    description = "Integrates Proxmox and Netbox"
    version = "0.0.5"
    author = "Emerson Felipe (@emersonfelipesp)"
    author_email = "emerson.felipe@nmultifibra.com.br"
    base_url = "proxbox"
    required_settings = []
    default_settings = {
        'proxmox': [
            {
                'domain': 'proxbox.example.com',    # May also be IP address
                'http_port': 8006,
                'user': 'root@pam',
                'password': 'Strong@P4ssword',
                'token': {
                    'name': 'proxbox',
                    'value': 'PASTE_YOUR_TOKEN_HERE'
                },
                'ssl': False
            }
        ],
        'netbox': {
            'domain': 'netbox.example.com',     # May also be IP address
            'http_port': 80,
            'token': 'PASTE_YOUR_TOKEN_HERE',
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
