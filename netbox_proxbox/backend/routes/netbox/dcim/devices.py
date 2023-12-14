from netbox_proxbox.backend.routes.netbox.generic import NetboxBase
from typing import Any

from .sites import Site
from .device_types import DeviceType
from .device_roles import DeviceRole

class Device(NetboxBase):
    
    async def extra_fields(self):
        site = await Site(nb = self.nb).get()
        role = await DeviceRole(nb = self.nb).get()
        device_type = await DeviceType(nb = self.nb).get()
        
        self.default_dict.update(
            {
                "status": "active",
                "site": site.id,
                "role": role.id,
                "device_type": device_type.id,
            }
        )
        
    async def get(self):
        if self.default:
            await self.extra_fields()
                    
        return await super().get()
    
    async def post(self, data: Any = None):
        if self.default:
            await self.extra_fields()
        
        return await super().post(data = data)
    
    default_name = "Proxbox Basic Device"
    default_slug = "proxbox-basic-device"
    default_description = "Proxbox Basic Device"
    
    app = "dcim"
    endpoint = "devices"
    object_name = "Device"