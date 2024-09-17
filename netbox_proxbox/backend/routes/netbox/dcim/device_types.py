from netbox_proxbox.backend.routes.netbox.generic import NetboxBase
from .manufacturers import Manufacturer

from typing import Any

class DeviceType(NetboxBase):
        
    # Default Device Type Params
    default_name = "Proxbox Basic Device Type"
    default_slug = "proxbox-basic-device-type"
    default_description = "Proxbox Basic Device Type"
    
    app = "dcim"
    endpoint = "device_types"
    object_name = "Device Types"
    
    async def get_base_dict(self):
        manufacturer = await Manufacturer(nb = self.nb).get()
        
        return {
            "model": self.default_name,
            "slug": self.default_slug,
            "manufacturer": manufacturer.id,
            "description": self.default_description,
            "u_height": 1,
        }