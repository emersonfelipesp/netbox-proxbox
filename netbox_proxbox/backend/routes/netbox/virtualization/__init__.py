from fastapi import APIRouter, Depends, Body, Query
from typing import Annotated

from .cluster_type import ClusterType
from .cluster import Cluster

from netbox_proxbox.backend.schemas.netbox import CreateDefaultBool
from netbox_proxbox.backend.schemas.netbox.virtualization import ClusterTypeSchema, ClusterSchema

from netbox_proxbox.backend.session.netbox import NetboxSessionDep

router = APIRouter()

@router.get("/cluster-types")
async def get_cluster_types( all = None, cluster_type: ClusterType = Depends() ):
    print(f"1 - all: {all}")
    
    return await cluster_type.get()

@router.post("/cluster-types")
async def create_cluster_types(
    cluster_type: ClusterType = Depends(),
    # default: Annotated[
    #     bool, 
    #     Body(
    #         title="Create default object.",
    #         description="Create a default object if there's no object registered on Netbox."
    #     )
    # ] = False,
    data: Annotated[
        ClusterTypeSchema,
        Body(
            title="Netbox Cluster Type",
            description="JSON to create the Cluster Type on Netbox. You can create any Cluster Type you want, like a proxy to Netbox API."
        )
    ] = None
):
    """
    **default:** Boolean to define if Proxbox should create a default Cluster Type if there's no Cluster Type registered on Netbox.\n
    **data:** JSON to create the Cluster Type on Netbox. You can create any Cluster Type you want, like a proxy to Netbox API.
    """
    return await cluster_type.post(data)


@router.get("/clusters")
async def get_clusters(
    cluster: Cluster = Depends(),
):
    return await cluster.get()


@router.post("/clusters")
async def create_cluster(
    cluster: Cluster = Depends(),
    # default: Annotated[
    #     bool, 
    #     Body(
    #         title="Create default object.",
    #         description="Create a default object if there's no object registered on Netbox."
    #     ),
    # ] = False,
    data: dict = None,
):
    print(data, type(data))
    """
    **default:** Boolean to define if Proxbox should create a default Cluster Type if there's no Cluster Type registered on Netbox.\n
    **data:** JSON to create the Cluster Type on Netbox. You can create any Cluster Type you want, like a proxy to Netbox API.
    """

    # if default:
    #     return await cluster.post()

    # if data:
    #     print(f"create_cluster: {data}")
    #     return await cluster.post(data = data)
    return await cluster.post(data)
    