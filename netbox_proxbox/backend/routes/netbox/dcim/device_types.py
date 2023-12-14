from netbox_proxbox.backend.routes.netbox.generic import NetboxBase
from .manufacturers import Manufacturer

from typing import Any

class DeviceType(NetboxBase):
    async def extra_fields(self):
        manufacturer = await Manufacturer(nb = self.nb).get()
        
        
        # Replaces the default_dict variable
        self.default_dict = {
                "model": "Proxbox Basic Device Type",
                "slug": self.default_slug,
                "manufacturer": manufacturer.id,
                "description": self.default_description,
                "u_height": 1,
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
    
    # Default Device Type Params
    default_name = "Proxbox Basic Device Type"
    default_slug = "proxbox-basic-device-type"
    default_description = "Proxbox Basic Device Type"
    
    app = "dcim"
    endpoint = "device_types"
    object_name = "Device Types"