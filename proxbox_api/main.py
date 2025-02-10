import traceback

from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

# pynetbox AsPI Imports
from pynetbox_api.dcim import (
    Device,
    DeviceRole,
    DeviceType,
    Manufacturer,
    Site,
)
from pynetbox_api.extras import Tags
from pynetbox_api.exceptions import FastAPIException

# Proxbox API Imports
from proxbox_api.exception import ProxboxException

# Netbox Routes
from proxbox_api.routes.netbox import router as netbox_router
from proxbox_api.routes.netbox.dcim import router as nb_dcim_router
from proxbox_api.routes.netbox.virtualization import router as nb_virtualization_router

# Proxbox Routes
from proxbox_api.routes.proxbox import router as proxbox_router
from proxbox_api.routes.proxbox.clusters import router as pb_cluster_router

# Proxmox Routes
from proxbox_api.routes.proxmox import router as proxmox_router
from proxbox_api.routes.proxmox.cluster import router as px_cluster_router
from proxbox_api.routes.proxmox.nodes import router as px_nodes_router

from proxbox_api.schemas import *

# Sessions
from proxbox_api.session.proxmox import ProxmoxSessionsDep
from proxbox_api.session.netbox import NetboxSessionDep

"""
CORS ORIGINS
"""

cfg_not_found_msg = "Netbox configuration not found. Using default configuration."

plugin_configuration: dict = {}

uvicorn_host: str = "localhost"
uvicorn_port: int = 8800

netbox_host: str = "localhost"
netbox_port: int = 80


configuration = None
default_config: dict = {}
plugin_configuration: dict = {}
proxbox_cfg: dict = {}  


fastapi_endpoint = f"http://{uvicorn_host}:{uvicorn_port}"
https_fastapi_endpoint = f"https://{uvicorn_host}:{uvicorn_port}"
fastapi_endpoint_port8000 = f"http://{uvicorn_host}:8000"
fastapi_endpoint_port80 = f"http://{uvicorn_host}:80"

netbox_endpoint_port80 = f"http://{netbox_host}:80"
netbox_endpoint_port8000 = f"http://{netbox_host}:8000"
netbox_endpoint = f"http://{netbox_host}:{netbox_port}"
https_netbox_endpoint = f"https://{netbox_host}"
https_netbox_endpoint443 = f"https://{netbox_host}:443"
https_netbox_endpoint_port = f"https://{netbox_host}:{netbox_port}"


PROXBOX_PLUGIN_NAME: str = "netbox_proxbox"


# Init FastAPI
app = FastAPI(
    title="Proxbox Backend",
    description="## Proxbox Backend made in FastAPI framework",
    version="0.0.1"
)

@app.on_event('startup')
def on_startup():
    from proxbox_api.database import create_db_and_tables
    create_db_and_tables()

"""
CORS Middleware
"""

origins = [
    fastapi_endpoint,
    fastapi_endpoint_port8000,
    fastapi_endpoint_port80,
    https_fastapi_endpoint,
    netbox_endpoint,
    netbox_endpoint_port80,
    netbox_endpoint_port8000,
    https_netbox_endpoint,
    https_netbox_endpoint443,
    https_netbox_endpoint_port,
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

from proxbox_api.routes.proxbox.clusters import get_nodes, get_virtual_machines

@app.websocket("/ws")
async def websocket_endpoint(
    nb: NetboxSessionDep,
    pxs: ProxmoxSessionsDep,
    websocket: WebSocket
):
    try:
        await websocket.accept()
    except Exception as error:
        print(f"Error while accepting WebSocket connection: {error}")
        await websocket.close()
    
    data = None

    while True:
        try:
            data = await websocket.receive_text()
        except Exception as error:
            print(f"Error while receiving data from WebSocket: {error}")
            await websocket.close()
            break
        
        if data == "Start":
            await get_nodes(nb=nb, pxs=pxs, websocket=websocket)
            await get_virtual_machines(nb=nb, pxs=pxs, websocket=websocket)
            await websocket.close()
            
        if data == "Sync Nodes":
            await get_nodes(nb=nb, pxs=pxs, websocket=websocket)
            await websocket.close()

        if data == "Sync Virtual Machines":
            await get_virtual_machines(nb=nb, pxs=pxs, websocket=websocket)
            await websocket.close()
            
        else:
            print("Invalid command.")
            await websocket.send_text("Invalid command.")
            await websocket.close()

        await websocket.close()
    
    

@app.websocket("/ws/virtual-machine")
async def websocket_vm_endpoint(
    nb: NetboxSessionDep,
    pxs: ProxmoxSessionsDep,
    websocket: WebSocket
):
    try:
        await websocket.accept()
    except Exception as error:
        print(f"Error while accepting WebSocket connection: {error}")
        await websocket.close()

    data = None

    while True:
        try:
            data = await websocket.receive_text()
        except Exception as error:
            print(f"Error while receiving data from WebSocket: {error}")
            await websocket.close()
            break

        if data == "Sync Virtual Machines":
            await get_virtual_machines(nb=nb, pxs=pxs, websocket=websocket)
            await websocket.close()

        else:
            print("Invalid command.")
            await websocket.send_text("Invalid command.")
            await websocket.close()

         
@app.get('/dcim/devices')
async def create_devices():
    return {
        "message": "Devices created"
    }

@app.get('/dcim/devices/create')
async def get_netbox_version(
    proxmox_sessions: ProxmoxSessionsDep,
    nb: NetboxSessionDep
):
    device_list: list = []
    for px in proxmox_sessions:
        result = px.session.nodes.get()
        for node in result:
            name = node.get('node', 'Undefined Node')
            
            try:
                Device(
                    nb=nb.session,
                    name=name,
                )
            except FastAPIException as error:
                traceback.print_exc()
                raise ProxboxException(
                    message="Unknown Error creating device in Netbox",
                    detail=f"Error: {str(error)}"
                )
            
            except Exception as error:
                traceback.print_exc()
                raise ProxboxException(
                    message="Unknown Error creating device in Netbox",
                    detail=f"Error: {str(error)}"
                )


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

