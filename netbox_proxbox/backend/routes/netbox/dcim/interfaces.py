from netbox_proxbox.backend.routes.netbox.generic import NetboxBase
from typing import Any

from .sites import Site
from .device_types import DeviceType
from .device_roles import DeviceRole

from netbox_proxbox.backend.routes.netbox.dcim.devices import Device

class Interface(NetboxBase):
    
    default_name = "Proxbox Basic interface"
    #default_slug = "proxbox-basic-interface"
    default_description = "Proxbox Basic Interface"
    type = "other"
    
    app = "dcim"
    endpoint = "interfaces"
    object_name = "Interface"
    
    async def get_base_dict(self):
        device = await Device(nb = self.nb).get()
        
        return {
            "device": device.id,
            "name": self.default_name,
            "type": "other",
            "description": self.default_description,
            "enabled": True,
        }
