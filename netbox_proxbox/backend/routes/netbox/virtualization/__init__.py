from fastapi import APIRouter, Depends

from .cluster_type import ClusterType

from netbox_proxbox.backend.schemas.netbox import CreateDefaultBool
from netbox_proxbox.backend.schemas.netbox.virtualization import ClusterTypeSchema

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


from netbox_proxbox.backend.session.netbox import NetboxSessionDep
@router.get("/testing")
async def get_testing(
    nb: NetboxSessionDep,
    app: str  | None = None,
    endpoint: str | None = None,
): 
    response_list = []
    
    teste = getattr(getattr(nb.session, app), endpoint)
    for item in teste.all():
        response_list.append(item)

    return response_list