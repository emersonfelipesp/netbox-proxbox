
from fastapi import APIRouter, Depends



#from netbox_proxbox.backend.schemas import PluginConfig
#from netbox_proxbox.backend.schemas.netbox import *

router = APIRouter()

@router.get("/")
async def proxmox():
    
    def minimize_result(endpoint_name):
        endpoint_list = []
        result = px(endpoint_name).get()
        
        match endpoint_name:
            case "access":
                for obj in result:
                    endpoint_list.append(obj.get("subdir"))
            
            case "cluster":
                for obj in result:
                    endpoint_list.append(obj.get("name"))
                
        return endpoint_list
    
    api_hierarchy = {
        "access": minimize_result("access"),
        "cluster": minimize_result("cluster"),
        "nodes": px.nodes.get(),
        "pools": px.pools.get(),
        "storage": px.storage.get(),
        "version": px.version.get(),
    }

    return {
        "message": "Proxmox API",
        "proxmox_api_viewer": "https://pve.proxmox.com/pve-docs/api-viewer/",
        "github": {
            "netbox": "https://github.com/netbox-community/netbox",
            "pynetbox": "https://github.com/netbox-community/pynetbox",
            "proxmoxer": "https://github.com/proxmoxer/proxmoxer",
            "proxbox": "https://github.com/netdevopsbr/netbox-proxbox"
        },
        "base_endpoints": api_hierarchy
    }

"""
# Import Proxmox Session Config
from .proxbox import app_settings

@router.get("/session")
async def proxmox_session(
    app: str = "proxmox",
    PROXMOX_CONFIG =  Depends(app_settings),
):
    print(app)
    # Import lib to run Proxmox communication
    from proxmoxer import ProxmoxAPI

    return PROXMOX_CONFIG
"""

"""
@router.get("/{top_level}")
async def top_level_endpoint(
    top_level: str | None = None,
):
    if top_level not in TOPLEVEL_ENDPOINTS:
        return {
            "message": f"'{top_level}' is not a valid endpoint/path name.",
            "valid_names": TOPLEVEL_ENDPOINTS,
        }
    
    current_index = TOPLEVEL_ENDPOINTS.index(top_level)
    other_endpoints = TOPLEVEL_ENDPOINTS.copy()
    other_endpoints.pop(current_index)
    
    return {
        f"{top_level}": px(top_level).get(),
        "other_endpoints": other_endpoints,
    }


@router.get("/{top_level}/{second_level}")
async def second_level_endpoint(
    top_level: str | None = None,
    second_level: str | None = None,
    type: str | None = None,
    id: str | None = None,
):
    if top_level not in TOPLEVEL_ENDPOINTS:
        return {
            "message": f"'{top_level}' is not a valid endpoint/path name.",
            "valid_names": TOPLEVEL_ENDPOINTS,
        }

    json_obj = {f"{top_level}": {}}
    
    try:
        path = f"{top_level}/{second_level}"
        
        # HTTP request through proxmoxer lib
        if path == "cluster/resources" and type != None:
            result = px(path).get(type = type)
        else:
            result = px(path).get()
        
        # Feed JSON result
        json_obj[top_level][second_level] = result
        
    except ResourceException as error:
        return {
            "message": f"Path {path} does not exist.",
            "error": error
        }
        
    return json_obj
"""

"""
@app.get("/netbox", response_class=HTMLResponse)
async def netbox(
    request: Request,
    proxmox: Annotated[dict, Depends(root)]
):
    return templates.TemplateResponse("fastapi/home.html", {
            "request": request,
            "json_content": proxmox
        }
    )
"""


"""
@app.get("/", response_class=HTMLResponse)
async def root(
    request: Request,
    json_content: Annotated[dict, Depends(standalone_info)],
    proxmox_output: Annotated[dict, Depends(proxmox)]
):
    return templates.TemplateResponse("fastapi/home.html", {
            "request": request,
            "json_content": json_content,
            "proxmox": proxmox_output,
            "proxmox_str": json.dumps(proxmox_output, indent=4),
        }
    )
"""