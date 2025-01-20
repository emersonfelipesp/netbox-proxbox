from proxbox_api.routes.netbox.generic import NetboxBase

class ClusterType(NetboxBase):
    
    app = "virtualization"
    endpoint = "cluster_types"
    object_name = "Cluster Type"
    
    # Default Cluster Type Params
    default_name = "Proxbox Basic Cluster Type"
    default_slug = "proxbox-basic-cluster-type"
    default_description = "Proxbox Basic Cluster Type (used to identify the items the plugin created)"
    
    async def get_base_dict(self) -> dict:
        return {
            "name": self.default_name,
            "slug": self.default_slug,
            "description": self.default_description,
        }