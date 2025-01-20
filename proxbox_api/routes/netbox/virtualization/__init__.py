from fastapi import APIRouter, Depends, Body
from typing import Annotated

from .cluster_type import ClusterType
from .cluster import Cluster
from .virtual_machines import VirtualMachine

from proxbox_api.schemas.netbox.virtualization import ClusterTypeSchema

router = APIRouter()

@router.get("/cluster-types")
async def get_cluster_types( all = None, cluster_type: ClusterType = Depends() ):
    """
    ### Asynchronous function to retrieve cluster types.
    
    **Args:**
    - **all (`Optional[Any]`):** An optional parameter, default is None.
    - **cluster_type (`ClusterType`, optional):** Dependency injection of ClusterType.
    
    **Returns:**
    - `Any:` The result of the cluster_type.get() method.
    """
    
    print(f"1 - all: {all}")
    
    return await cluster_type.get()

@router.post("/cluster-types")
async def create_cluster_types(
    cluster_type: ClusterType = Depends(),
    data: Annotated[
        ClusterTypeSchema,
        Body(
            title="Netbox Cluster Type",
            description="JSON to create the Cluster Type on Netbox. You can create any Cluster Type you want, like a proxy to Netbox API."
        )
    ] = None
):
    """
    ### Asynchronously creates a new cluster type in Netbox.

    **Args:**
    - **cluster_type (`ClusterType`):** Dependency injection for the ClusterType instance.
    - **data (`Annotated[ClusterTypeSchema, Body]`):** JSON body containing the details for the new cluster type. 
    The body should have a title "Netbox Cluster Type" and a description explaining that it is used to 
    create any cluster type, such as a proxy to the Netbox API. Defaults to None.

    **Returns:**
    The result of the `cluster_type.post(data)` call, which is an awaitable object representing the creation 
    of the cluster type in Netbox.
    """

    return await cluster_type.post(data)


@router.get("/clusters")
async def get_clusters(
    cluster: Cluster = Depends(),
):
    """
    ### Asynchronously retrieves cluster information.
    
    This function depends on a `Cluster` instance and returns the result of the 
    `get` method called on that instance.
    
    **Args:**
    - **cluster (`Cluster`):** The cluster instance to retrieve information from. 
    This is injected via dependency injection.
    
    **Returns:**
    - The result of the `get` method called on the `cluster` instance.
    """
    
    return await cluster.get()


@router.post("/clusters")
async def create_cluster(
    cluster: Cluster = Depends(),
    data: dict = None,
):
    """
    ### Asynchronously creates a cluster by posting data to the specified cluster.
    
    **Args:**
    - **cluster (`Cluster`):** The cluster dependency to which the data will be posted.
    - **data (`dict`, optional):** The data to be posted to the cluster. Defaults to None.
    
    **Returns:**
    - The result of the cluster's post method.
    """

    return await cluster.post(data)
    

@router.get("/virtual-machines")
async def get_virtual_machines(
    virtual_machine: VirtualMachine = Depends(),
):
    """
    ### Asynchronous function to retrieve virtual machines.
    
    This function depends on the `VirtualMachine` dependency to be injected,
    and it calls the `get` method on the `virtual_machine` instance to fetch
    the virtual machines.
    
    **Args:**
    - **virtual_machine (`VirtualMachine`):** The virtual machine dependency.
    
    **Returns:**
    - The result of the `get` method called on the `virtual_machine` instance.
    """
    
    return await virtual_machine.get()


@router.post("/virtual-machines")
async def create_virtual_machines(
    virtual_machine: VirtualMachine = Depends(),
    data: Annotated[dict, Body()] = None
):
    """
    ### Asynchronously creates virtual machines.
    
    **Args:**
    - **virtual_machine (`VirtualMachine`):** The virtual machine dependency.
    - **data (`dict`, optional):** The data for the virtual machine creation. Defaults to None.
    
    **Returns:**
    - The result of the virtual machine creation.
    """
    
    return await virtual_machine.post(data)