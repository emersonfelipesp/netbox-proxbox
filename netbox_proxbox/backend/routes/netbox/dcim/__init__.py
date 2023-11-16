from fastapi import APIRouter

from netbox_proxbox.backend.session.netbox import NetboxSessionDep

# FastAPI Router
router = APIRouter()

@router.get("/sites")
async def get_sites(
    nb: NetboxSessionDep
):
    response = nb.dcim.sites.all()
    print(response)
    return response 

@router.post("/sites")
async def create_sites(
    nb: NetboxSessionDep
):
    response = nb.dcim.sites.create(name="Teste")
    print(response)
    return response