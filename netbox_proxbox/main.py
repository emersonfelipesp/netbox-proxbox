from typing import Annotated

from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware

from netbox_proxbox.backend.exception import ProxboxException

# Netbox Routes
from .backend.routes.netbox import router as netbox_router
from .backend.routes.netbox.dcim import router as nb_dcim_router
from .backend.routes.netbox.virtualization import router as nb_virtualization_router

# Proxbox Routes
from .backend.routes.proxbox import router as proxbox_router
from .backend.routes.proxbox.clusters import router as pb_cluster_router

# Proxmox Routes
from .backend.routes.proxmox import router as proxmox_router
from .backend.routes.proxmox.cluster import router as px_cluster_router
from .backend.routes.proxmox.nodes import router as px_nodes_router


from .backend.schemas import *

from netbox import configuration

"""
CORS ORIGINS
"""

plugin_configuration = configuration.PLUGINS_CONFIG

uvicorn_host = plugin_configuration["netbox_proxbox"]["fastapi"]["uvicorn_host"]
uvicorn_port = plugin_configuration["netbox_proxbox"]["fastapi"]["uvicorn_port"]
        
fastapi_endpoint = f"http://{uvicorn_host}:{uvicorn_port}"
https_fastapi_endpoint = f"https://{uvicorn_host}:{uvicorn_port}"
fastapi_endpoint_port8000 = f"http://{uvicorn_host}:8000"
fastapi_endpoint_port80 = f"http://{uvicorn_host}:80"

netbox_host = plugin_configuration["netbox_proxbox"]["netbox"]["domain"]
netbox_port = plugin_configuration["netbox_proxbox"]["netbox"]["http_port"]

netbox_endpoint_port80 = f"http://{netbox_host}:80"
netbox_endpoint_port8000 = f"http://{netbox_host}:8000"

netbox_endpoint = f"http://{netbox_host}:{netbox_port}"
https_netbox_endpoint = f"https://{netbox_host}:{netbox_port}"

PROXBOX_PLUGIN_NAME = "netbox_proxbox"

# Init FastAPI
app = FastAPI(
    title="Proxbox Backend",
    description="## Proxbox Backend made in FastAPI framework",
    version="0.0.1"
)

"""
CORS Middleware
"""

origins = [
    fastapi_endpoint,
    https_fastapi_endpoint,
    netbox_endpoint,
    https_netbox_endpoint,
    netbox_endpoint_port80,
    netbox_endpoint_port8000,
    fastapi_endpoint_port8000,
    fastapi_endpoint_port80,
    "http://localhost",
    
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"]
)

@app.exception_handler(ProxboxException)
async def proxmoxer_exception_handler(request: Request, exc: ProxboxException):
    return JSONResponse(
        status_code=400,
        content={
            "message": exc.message,
            "detail": exc.detail,
            "python_exception": exc.python_exception,
        }
    )

from netbox_proxbox.backend.session.proxmox import ProxmoxSessionsDep
from netbox_proxbox.backend.session.netbox import NetboxSessionDep

@app.websocket("/ws")
async def websocket_endpoint(
    nb: NetboxSessionDep,
    pxs: ProxmoxSessionsDep,
    websocket: WebSocket
):
    await websocket.accept()
    
    from netbox_proxbox.backend.routes.proxbox.clusters import get_nodes, get_virtual_machines
    
    await get_nodes(nb=nb, pxs=pxs, websocket=websocket)
    await get_virtual_machines(nb=nb, pxs=pxs, websocket=websocket)
    
    while True:
        data = await websocket.receive_text()
        await websocket.send_text(f"Message text was: {data}")
        
        

#
# Routes (Endpoints)
#

# Netbox Routes
app.include_router(netbox_router, prefix="/netbox", tags=["netbox"])
app.include_router(nb_dcim_router, prefix="/netbox/dcim", tags=["netbox / dcim"])
app.include_router(nb_virtualization_router, prefix="/netbox/virtualization", tags=["netbox / virtualization"])

# Proxmox Routes
app.include_router(px_nodes_router, prefix="/proxmox/nodes", tags=["proxmox / nodes"])
app.include_router(px_cluster_router, prefix="/proxmox/cluster", tags=["proxmox / cluster"])
app.include_router(proxmox_router, prefix="/proxmox", tags=["proxmox"])

# Proxbox Routes
app.include_router(proxbox_router, prefix="/proxbox", tags=["proxbox"])
app.include_router(pb_cluster_router, prefix="/proxbox/clusters", tags=["proxbox / clusters"])






@app.get("/")
async def standalone_info():
    return {
        "message": "Proxbox Backend made in FastAPI framework",
        "proxbox": {
            "github": "https://github.com/netdevopsbr/netbox-proxbox",
            "docs": "https://docs.netbox.dev.br",
        },
        "fastapi": {
            "github": "https://github.com/tiangolo/fastapi",
            "website": "https://fastapi.tiangolo.com/",
            "reason": "FastAPI was chosen because of performance and reliabilty."
        }
    }

