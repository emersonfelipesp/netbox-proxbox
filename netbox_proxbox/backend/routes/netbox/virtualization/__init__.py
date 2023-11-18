from fastapi import APIRouter, Depends

from .cluster_type import ClusterType
from .cluster import Cluster

from netbox_proxbox.backend.schemas.netbox import CreateDefaultBool
from netbox_proxbox.backend.schemas.netbox.virtualization import ClusterTypeSchema, ClusterSchema

from netbox_proxbox.backend.session.netbox import NetboxSessionDep

router = APIRouter()

@router.get("/cluster-types")
async def get_cluster_types( cluster_type: ClusterType = Depends() ):
    return await cluster_type.get()

@router.post("/cluster-types")
async def create_cluster_types(
    cluster_type: ClusterType = Depends(),
    default: CreateDefaultBool = False,
    data: ClusterTypeSchema = None
):
    """
    **default:** Boolean to define if Proxbox should create a default Cluster Type if there's no Cluster Type registered on Netbox.\n
    **data:** JSON to create the Cluster Type on Netbox. You can create any Cluster Type you want, like a proxy to Netbox API.
    """
    return await cluster_type.post(default, data)


Depends
@router.get("/clusters")
async def get_clusters(
    nb: NetboxSessionDep,
    cluster: Cluster = Depends(),
):
    # Instantiate ClusterType class to get Cluster Type ID
    cluster_type_obj = ClusterType(nb=nb)
    type = await cluster_type_obj.get()
    
    default_extra_fields = {
        "status": "active",
        "type": type.id
    }
    
    return await cluster.get(default_extra_fields)


@router.post("/clusters")
async def create_cluster(
    nb: NetboxSessionDep,
    cluster: Cluster = Depends(),
    default: CreateDefaultBool = False,
    data: ClusterSchema = None,
):
    """
    **default:** Boolean to define if Proxbox should create a default Cluster Type if there's no Cluster Type registered on Netbox.\n
    **data:** JSON to create the Cluster Type on Netbox. You can create any Cluster Type you want, like a proxy to Netbox API.
    """
    # Instantiate ClusterType class to get Cluster Type ID
    cluster_type_obj = ClusterType(nb=nb)
    type = await cluster_type_obj.get()
    
    if default:
        default_extra_fields = {
            "status": "active",
            "type": type.id
        }
        
        return await cluster.post(default, default_extra_fields)
    
    if data:
        print(data)
        return await cluster.post(data = data)