from netbox_proxbox.backend.routes.netbox.generic import NetboxBase
from typing import Any

class DeviceRole(NetboxBase):
    
    default_name = "Proxmox Node (Server)"
    default_slug = "proxbox-node"
    default_description = "Proxbox Basic Manufacturer"
    
    app = "dcim"
    endpoint = "device_roles"
    object_name = "Device Types"
    
    async def get_base_dict(self):
        return {
            "name": self.default_name,
            "slug": self.default_slug,
            "color": "ff5722",
            "vm_role": False,
            "description": self.default_description,
        }