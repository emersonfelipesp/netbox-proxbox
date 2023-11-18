from fastapi import Depends, Query
from typing import Annotated

from netbox_proxbox.backend.routes.netbox.generic import NetboxBase

class Cluster(NetboxBase):
    # Default Cluster Type Params
    default_name = "Proxbox Basic Cluster"
    default_slug = "proxbox-basic-cluster-type"
    default_description = "Proxbox Basic Cluster (used to identify the items the plugin created)"
    
    app = "virtualization"
    endpoint = "clusters"
    object_name = "Cluster"

    