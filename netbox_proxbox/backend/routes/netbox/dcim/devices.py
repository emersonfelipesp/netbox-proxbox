from netbox_proxbox.backend.routes.netbox.generic import NetboxBase
from typing import Any

from .sites import Site
from .device_types import DeviceType
from .device_roles import DeviceRole

from netbox_proxbox.backend.routes.netbox.virtualization.cluster import Cluster

class Device(NetboxBase):
    
    default_name = "Proxbox Basic Device"
    default_slug = "proxbox-basic-device"
    default_description = "Proxbox Basic Device"
    
    app = "dcim"
    endpoint = "devices"
    object_name = "Device"
    
    async def get_base_dict(self):
        site = await Site(nb = self.nb).get()
        role = await DeviceRole(nb = self.nb).get()
        device_type = await DeviceType(nb = self.nb).get()
        cluster = await Cluster(nb = self.nb).get()
        
        return {
            "name": self.default_name,
            "slug": self.default_slug,
            "description": self.default_description,
            "site": site.id,
            "role": role.id,
            "device_type": device_type.id,
            "status": "active",
            "cluster": cluster.id
        }