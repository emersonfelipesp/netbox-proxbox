from netbox_proxbox.backend.routes.netbox.generic import NetboxBase

class ClusterType(NetboxBase):
    # Default Cluster Type Params
    default_name = "Proxbox Basic Cluster Type"
    default_slug = "proxbox-basic-cluster-type"
    default_description = "Proxbox Basic Cluster Type (used to identify the items the plugin created)"
    
    app = "virtualization"
    endpoint = "cluster_types"