<p align="center">
  <img width="532" src="https://github.com/N-Multifibra/proxbox/blob/main/etc/img/proxbox-full-logo.png" alt="Material Bread logo">
</p>


# proxbox
Netbox plugin which integrates Proxmox and Netbox using proxmoxer and pynetbox.


## Installation

Use the package manager [pip](https://pip.pypa.io/en/stable/) to install **proxbox**.

1. Install informing GitHub self credentials (user and password)

```bash
pip3 install git+https://github.com/N-Multifibra/proxbox.git

```
2. Install using @emerpereira token (meant to be used on scripts)

```bash
pip3 install git+https://16d91b5fb6890672dd24254622330029fcc08ad4@github.com/N-Multifibra/proxbox.git
```

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
    "status": false,
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
    "resources": false
  },
  "result": true
},
{
  "name": "ZABBIX",
  "changes": {
    "status": false,
    "custom_fiedls": false,
    "local_context": false,
    "resources": false
  },
  "result": true
}
```

---

[Workflow do ProxBox](https://whimsical.com/proxbox-integracao-netbox-e-proxmox-XtrSijkFx2ZUKmkcAZqoUx)
