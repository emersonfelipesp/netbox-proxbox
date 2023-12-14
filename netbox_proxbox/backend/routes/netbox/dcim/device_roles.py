from netbox_proxbox.backend.routes.netbox.generic import NetboxBase
from typing import Any

class DeviceRole(NetboxBase):
    
    async def extra_fields(self):
            
        self.default_dict = {
                "name": self.default_name,
                "slug": self.default_slug,
                "color": "ff5722",
                "vm_role": False,
                "description": self.default_description,
                "tags": [self.nb.tag.id]
        }
        
    async def get(self):
        if self.default:
            await self.extra_fields()
                    
        return await super().get()
    
    async def post(self, data: Any = None):
        if self.default:
            await self.extra_fields()
        
        return await super().post(data = data)
    
    default_name = "Proxmox Node (Server)"
    default_slug = "proxbox-node"
    default_description = "Proxbox Basic Manufacturer"
    
    app = "dcim"
    endpoint = "device_roles"
    object_name = "Device Types"