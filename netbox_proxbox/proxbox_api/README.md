<p align="center">
  <img width="532" src="https://github.com/N-Multifibra/proxbox/blob/main/etc/img/proxbox-full-logo.png" alt="Material Bread logo">
</p>


## Usage

Compare Netbox and Proxmox information and update VM on Netbox, if any difference found using the **Netbox VM ID**

```python
>>> from netbox_proxbox import proxbox_api

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
>>> from netbox_proxbox import proxbox_api

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
>>> from netbox_proxbox import proxbox_api

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
>>> from netbox_proxbox import proxbox_api

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
