<p align="center">
  <img width="532" src="https://github.com/N-Multifibra/proxbox/blob/main/etc/img/proxbox-full-logo.png" alt="Material Bread logo">
</p>


# proxbox
Netbox plugin which integrates Proxmox and Netbox using proxmoxer and pynetbox.

It is currently able to get the following information from Proxmox:

- Cluster name
- VM/CTs:
  - Status (online / offline)
  - Name
  - ID
  - CPU
  - Disk
  - Memory
  - Node (Server)

## Installation

The plugin is available as a Python package in pypi and can be installed with pip

```
pip install netbox-proxbox
```
Enable the plugin in /opt/netbox/netbox/netbox/configuration.py:
```
PLUGINS = ['netbox-proxbox']
```
Restart NetBox and add `netbox-proxbox` to your local_requirements.txt

## Configuration

The following options are available:

* `proxmox`: (Dict) Proxmox related configuration to use proxmoxer.
* `proxmox.domain`: (String) Domain or IP address of Proxmox.
* `proxmox.http_port`: (Integer) Proxmox HTTP port (default: 8006).
* `proxmox.user`: (String) Proxmox Username.
* `proxmox.password`: (String) Proxmox Password.
* `proxmox.token`: (Dict) Contains Proxmox TokenID (name) and Token Value (value).
* `proxmox.token.name`: (String) Proxmox TokenID.
* `proxmox.token.value`: (String) Proxmox Token Value.
* `proxmox.ssl`: (Bool) Defines the use of SSL (default: False).

* `netbox`: (Dict) Netbox related configuration to use pynetbox.
* `netbox.domain`: (String) Domain or IP address of Netbox.
* `netbox.http_port`: (Integer) Netbox HTTP PORT (default: 80).
* `netbox.token`: (String) Netbox Token Value.
* `netbox.ssl`: (Bool) Defines the use of SSL (default: False). - Proxbox doesn't support SSL on Netbox yet.

### Configuration Example

```
# /opt/netbox/netbox/netbox/configuration.py

# Enable installed plugins. Add the name of each plugin to the list.
PLUGINS = ['netbox_proxbox']

# Plugins configuration settings. These settings are used by various plugins that the user may have installed.
# Each key in the dictionary is the name of an installed plugin and its value is a dictionary of settings.
PLUGINS_CONFIG = {
    'netbox_proxbox': {
        'proxmox': {
            'domain': 'proxbox.example.com',
            'http_port': 8006,
            'user': 'root@pam',
            'password': 'Strong@P4ssword',
            'token': {
                'name': 'tokenIDchosen',
                'value': '039az154-23b2-4be0-8d20-b66abc8c4686'
            },
            'ssl': False
        },
        'netbox': {
            'domain': 'netbox.example.com',
            'http_port': 80,
            'token': '0dd7cddfaee3b38bbffbd2937d44c4a03f9c9d38',
            'ssl': False
        }
    }
}
```

### Custom Fields

To get Proxmox ID, Node and Type information, is necessary to configure Custom Fields.
Below the parameters needed to make it work:

**Proxmox ID**

Required values (must be equal)
- [Custom Field] Type: Integer
- [Custom Field] Name: proxmox_id
- [Assignment] Content-type: Virtualization > virtual machine
- [Validation Rules] Minimum value: 0

Optional values (may be different)
- [Custom Field] Label: [Proxmox] ID
- [Custom Field] Description: Proxmox VM/CT ID
- 
**Proxmox Node**

Required values (must be equal)
- [Custom Field] Type: Text
- [Custom Field] Name: proxmox_node
- [Assignment] Content-type: Virtualization > virtual machine

Optional values (may be different)
- [Custom Field] Label: [Proxmox] Node
- [Custom Field] Description: Proxmox Node (Server)

**Proxmox Type (qemu or lxc)**

Required values (must be equal)
- [Custom Field] Type: Selection
- [Custom Field] Name: proxmox_type
- [Assignment] Content-type: Virtualization > virtual machine

Optional values (may be different)
- [Custom Field] Label: [Proxmox] Type
- [Custom Field] Description: Proxmox type (VM or CT)

**Custom Field example**
![custom field image](etc/img/custom_field_example.png?raw=true "preview")
## Contributing
Developing tools for this project based on [ntc-netbox-plugin-onboarding](https://github.com/networktocode/ntc-netbox-plugin-onboarding) repo.

Issues and pull requests are welcomed.

## Screenshots

