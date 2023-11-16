from fastapi import APIRouter, Depends

from .sites import Sites

# FastAPI Router
router = APIRouter()

@router.get("/sites")
async def get_sites( site: Sites = Depends() ): return await site.get()
    

@router.post("/sites")
async def create_sites( site: Sites = Depends() ): return await site.post()
