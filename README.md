<p align="center">
  <img width="532" src="https://github.com/N-Multifibra/proxbox/blob/main/etc/img/proxbox-full-logo.png" alt="Proxbox logo">
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

### Versions
The following table shows the Netbox and Proxmox versions compatible (tested) with Proxbox plugin.

| netbox version        | proxmox version          | proxbox version
| ------------- |-------------|-------------|
| = 2.10.9 | >= v6.2.0 | v0.0.2

## Installation

The instructions below detail the process for installing and enabling Proxbox plugin.
The plugin is available as a Python package in pypi and can be installed with pip.

### Install Package

Enter Netbox's virtual environment.
```
source /opt/netbox/venv/bin/activate
```

Install the plugin package.
```
(venv) $ pip install netbox-proxbox
```

### Enable the Plugin

Enable the plugin in **/opt/netbox/netbox/netbox/configuration.py**:
```python
PLUGINS = ['netbox_proxbox']
```

### Configure Plugin

The plugin's configuration is also located in **/opt/netbox/netbox/netbox/configuration.py**:

Replace the values with your own following the [Configuration Parameters](#configuration-parameters) section.

```python
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

### Run Database Migrations

```
(venv) $ cd /opt/netbox/netbox/
(venv) $ python3 manage.py migrate
```

### Restart WSGI Service

Restart the WSGI service to load the new plugin:
```
# sudo systemctl restart netbox
```

---

### Configuration Parameters

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

---

### Custom Fields

To get Proxmox ID, Node and Type information, is necessary to configure Custom Fields.
Below the parameters needed to make it work:

---

**1. Proxmox ID**

Required values (must be equal)
- [Custom Field] **Type:** Integer
- [Custom Field] **Name:** proxmox_id
- [Assignment] **Content-type:** Virtualization > virtual machine
- [Validation Rules] **Minimum value:** 0

Optional values (may be different)
- [Custom Field] **Label:** [Proxmox] ID
- [Custom Field] **Description:** Proxmox VM/CT ID

---

**2. Proxmox Node**

Required values (must be equal)
- [Custom Field] **Type:** Text
- [Custom Field] **Name:** proxmox_node
- [Assignment] **Content-type:** Virtualization > virtual machine

Optional values (may be different)
- [Custom Field] **Label:** [Proxmox] Node
- [Custom Field] **Description:** Proxmox Node (Server)

---

**3. Proxmox Type (qemu or lxc)**

Required values (must be equal)
- [Custom Field] **Type:** Selection
- [Custom Field] **Name:** proxmox_type
- [Assignment] **Content-type:** Virtualization > virtual machine
- [Choices] **Choices:** qemu,lxc

Optional values (may be different)
- [Custom Field] **Label:** [Proxmox] Type
- [Custom Field] **Description:** Proxmox type (VM or CT)

---

### Custom Field Example

![custom field image](etc/img/custom_field_example.png?raw=true "preview")

---

### Usage

If everything is working correctly, you should see in Netbox's navigation the **Proxmox VM/CT** button in **Plugins** dropdown list.

On **Proxmox VM/CT** page, click button ![full update button](etc/img/proxbox_full_update_button.png?raw=true "preview")

It will redirect you to a new page and you just have to wait until the plugin runs through all Proxmox Cluster and create the VMs and CTs in Netbox.

**OBS:** Due the time it takes to full update the information, your web brouse might show a timeout page (like HTTP Code 504) even though it actually worked.

---

## Contributing
Developing tools for this project based on [ntc-netbox-plugin-onboarding](https://github.com/networktocode/ntc-netbox-plugin-onboarding) repo.

Issues and pull requests are welcomed.
