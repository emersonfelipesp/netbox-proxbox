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

## Contributing
Developing tools for this project based on [ntc-netbox-plugin-onboarding](https://github.com/networktocode/ntc-netbox-plugin-onboarding) repo.

Issues and pull requests are welcomed.

## Screenshots




## Usage

Compare Netbox and Proxmox information and update VM on Netbox, if any difference found using the **Netbox VM ID**

```python
>>> import proxbox

>>> json_result = proxbox.update.virtual_machine(id = 1)
>>> print(json_result)
{
  "name": "Netbox",
  "changes": {
    "status": false,
    "custom_fiedls": false,
    "local_context": false,
    "resources": false
  },
  "result": true
}
```
Compare Netbox and Proxmox information and update VM on Netbox, if any difference found using the **Proxmox VM ID**

```python
>>> import proxbox

>>> json_result = proxbox.update.virtual_machine(proxmox_id = 414)
>>> print(json_result)
{
  "name": "Netbox",
  "changes": {
    "status": false,
    "custom_fiedls": false,
    "local_context": false,
    "resources": false
  },
  "result": true
}
```

Compare Netbox and Proxmox information and update VM on Netbox, if any difference found using the **VM Name**

```python
>>> import proxbox

>>> json_result = proxbox.update.virtual_machine(name = 'Netbox')
>>> print(json_result)
{
  "name": "Netbox",
  "changes": {
    "status": true,
    "custom_fiedls": false,
    "local_context": false,
    "resources": false
  },
  "result": true
}
```

Updates all VM's at once on Netbox with the information gotten from Proxmox

```python
>>> import proxbox

>>> json_result = proxbox.update.all()
>>> print(json_result)
{
  "name": "Netbox",
  "changes": {
    "status": false,
    "custom_fiedls": false,
    "local_context": false,
    "resources": false
  },
  "result": true
},
{
  "name": "GRAYLOG",
  "changes": {
    "status": false,
    "custom_fiedls": false,
    "local_context": false,
    "resources": true
  },
  "result": true
},
{
  "name": "ZABBIX",
  "changes": {
    "status": false,
    "custom_fiedls": true,
    "local_context": true,
    "resources": false
  },
  "result": true
}
```

Compare all VM's on Netbox with Proxmox and delete VM on Netbox if it doesn't exist on Proxmox.

```python
>>> import proxbox

>>> json_result = proxbox.remove.all()
>>> print(json_result)
[
  {
    "name": "vm01",
    "result": false,
    "log": [
      "[OK] VM existe em ambos sistemas -> nfsen-debian"
    ]
  },
  {
    "name": "vm02",
    "result": false,
    "log": [
      "[OK] VM existe em ambos sistemas -> nmt-backend"
    ]
  },
  {
    "name": "vm03",
    "result": true,
    "log": [
      "[WARNING] VM existe no Netbox, mas não no Proxmox. Deletar a VM! -> teste123",
      "[OK] VM removida do Netbox com sucesso"
    ]
  }
]
```

---

[Workflow do ProxBox](https://whimsical.com/proxbox-integracao-netbox-e-proxmox-XtrSijkFx2ZUKmkcAZqoUx)
