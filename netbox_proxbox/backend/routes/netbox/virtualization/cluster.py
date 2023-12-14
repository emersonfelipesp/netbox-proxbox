from netbox_proxbox.backend.routes.netbox.generic import NetboxBase
from .cluster_type import ClusterType

from typing import Any

class Cluster(NetboxBase):
 
    async def extra_fields(self):
        type = await ClusterType(nb = self.nb).get()
            
        self.default_dict.update(
            {
                "status": "active",
                "type": type.id
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
            
    # Default Cluster Type Params
    default_name = "Proxbox Basic Cluster"
    default_slug = "proxbox-basic-cluster-type"
    default_description = "Proxbox Basic Cluster (used to identify the items the plugin created)"
    
    app = "virtualization"
    endpoint = "clusters"
    object_name = "Cluster"
    

    