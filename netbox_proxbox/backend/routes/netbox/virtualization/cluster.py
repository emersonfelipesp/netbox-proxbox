from netbox_proxbox.backend.routes.netbox.generic import NetboxBase
from .cluster_type import ClusterType

from typing import Any

class Cluster(NetboxBase):
    # Default Cluster Type Params
    default_name: str = "Proxbox Basic Cluster"
    default_slug: str = "proxbox-basic-cluster-type"
    default_description: str = "Proxbox Basic Cluster (used to identify the items the plugin created)"
    
    app: str = "virtualization"
    endpoint: str = "clusters"
    object_name: str = "Cluster"


    async def get_base_dict(self):
        type = await ClusterType(nb = self.nb).get()
        
        return {
            "name": self.default_name,
            "slug": self.default_slug,
            "description": self.default_description,
            "status": "active",
            "type": type.id
        }