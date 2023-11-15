from pydantic import BaseModel
from .netbox import NetboxSessionSchema
from .proxmox import ProxmoxSessionSchema

class PluginConfig(BaseModel):
    proxmox: list[ProxmoxSessionSchema]
    netbox: NetboxSessionSchema