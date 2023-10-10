from pydantic import BaseModel
from .netbox import *
from .proxmox import *

class PluginConfig(BaseModel):
    proxmox: list[ProxmoxSession]
    netbox: NetboxSession