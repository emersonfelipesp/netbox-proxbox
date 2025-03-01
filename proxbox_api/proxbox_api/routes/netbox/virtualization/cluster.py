from proxbox_api.logger import log
from proxbox_api.routes.netbox.generic import NetboxBase
from .cluster_type import ClusterType

class Cluster(NetboxBase):
    # Default Cluster Type Params
    default_name: str = "Proxbox Basic Cluster"
    default_slug: str = "proxbox-basic-cluster-type"
    default_description: str = "Proxbox Basic Cluster (used to identify the items the plugin created)"
    
    app: str = "virtualization"
    endpoint: str = "clusters"
    object_name: str = "Cluster"


    async def get_base_dict(self):
        type = None
        
        try:
            type = await ClusterType(nb = self.nb, websocket = self.websocket).get()
        except Exception as error:
            await log(self.websocket, f"Failed to fetch cluster type for cluster: {self.default_name}.\nPython Error: {error}")
        
        if type is not None:
            return {
                "name": self.default_name,
                "slug": self.default_slug,
                "description": self.default_description,
                "status": "active",
                "type": getattr(type, 'id', 0)
            }
        else:
            await log(self.websocket, f"Failed to fetch cluster type for cluster: {self.default_name}. As it is a required field, the cluster will not be created.")