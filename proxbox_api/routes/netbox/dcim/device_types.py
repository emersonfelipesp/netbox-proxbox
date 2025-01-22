from proxbox_api.routes.netbox.generic import NetboxBase
from proxbox_api.logging import log
from .manufacturers import Manufacturer

class DeviceType(NetboxBase):
        
    # Default Device Type Params
    default_name = "Proxbox Basic Device Type"
    default_slug = "proxbox-basic-device-type"
    default_description = "Proxbox Basic Device Type"
    
    app = "dcim"
    endpoint = "device_types"
    object_name = "Device Types"
    
    async def get_base_dict(self):
        manufacturer = await Manufacturer(nb = self.nb, websocket = self.websocket).get()
        
        if manufacturer is None:
            await log(self.websocket, f"Failed to fetch manufacturer for device type: {self.default_name}")
            
        return {
            "model": self.default_name,
            "slug": self.default_slug,
            "manufacturer": getattr(manufacturer, "id", None),
            "description": self.default_description,
            "u_height": 1,
        }