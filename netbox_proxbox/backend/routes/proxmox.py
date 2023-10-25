
from fastapi import APIRouter, Depends, HTTPException, Path, Query
from fastapi.exceptions import ResponseValidationError, ValidationException

from typing import Annotated, Any

from proxmoxer.core import ResourceException

from netbox_proxbox.backend.schemas.proxmox import *
from netbox_proxbox.backend.routes.proxbox import proxmox_settings
from netbox_proxbox.backend.session.proxmox import ProxmoxSession
from netbox_proxbox.backend.exception import ProxboxException
from netbox_proxbox.backend.enum.proxmox import *

router = APIRouter()

async def proxmox_session(
    proxmox_settings: Annotated[ProxmoxSessionSchema, Depends(proxmox_settings)],
):
    proxmox_session_obj = []
    
    try:
        for cluster in proxmox_settings:
            proxmox_session_obj.append(
                await ProxmoxSession(cluster).proxmoxer()
            )
        
        return proxmox_session_obj
    except Exception as error:
        print(f"Exception error: {error}")
        raise ProxboxException(
            message = "Could not return Proxmox Sessions connections based on user-provided parameters",
            python_exception = f"{error}"
        )

# Make Session reusable
ProxmoxSessionDep = Annotated[Any, Depends(proxmox_session)]
    
@router.get("/version")
async def proxmox_version(
    px_sessions: ProxmoxSessionDep
):
    response = []
    
    print(f"{px_sessions}")
    return f"{px_sessions}"

    for px in px_sessions:
        print("PX type equal to: ", type(px))
        response.append(px.version.get())
    
    return response
    

@router.get("/")
async def proxmox(
    px_sessions: ProxmoxSessionDep
):
    return_list = []
    
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
    
    for px in px_sessions:  
        api_hierarchy = {
            "access": minimize_result("access"),
            "cluster": minimize_result("cluster"),
            "nodes": px.nodes.get(),
            "pools": px.pools.get(),
            "storage": px.storage.get(),
            "version": px.version.get(),
        }
        
        return_list.append(api_hierarchy)

    return {
        "message": "Proxmox API",
        "proxmox_api_viewer": "https://pve.proxmox.com/pve-docs/api-viewer/",
        "github": {
            "netbox": "https://github.com/netbox-community/netbox",
            "pynetbox": "https://github.com/netbox-community/pynetbox",
            "proxmoxer": "https://github.com/proxmoxer/proxmoxer",
            "proxbox": "https://github.com/netdevopsbr/netbox-proxbox"
        },
        "clusters": return_list
    }




@router.get("/{top_level}")
async def top_level_endpoint(
    px_sessions: ProxmoxSessionDep,
    top_level: ProxmoxUpperPaths,
):
    # Get only a Proxmox Cluster
    px = px_sessions[0]
    
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

async def get_cluster_name(px):
    cluster_status_list = px("cluster/status").get()
    
    for item in cluster_status_list:
        if item.get("type") == "cluster":
            return item.get("name")
    

@router.get("/cluster/resources", response_model=ClusterResourcesList)
async def cluster_resources(
    px_sessions: ProxmoxSessionDep,
    type: Annotated[
        ClusterResourcesType, 
        Query(
            title="Proxmox Resource Type",
            description="Type of Proxmox resource to return (ex. 'vm' return QEMU Virtual Machines).",
        )
    ],
    mode: Annotated[
        ProxmoxModeOptions,
        Query(
            title="Proxmox Cluster Mode",
            description="Defines if the API call will be made to a single cluster or to all clusters.",
        )
    ] = "multi"
):
    json_response = {}
    if mode == "multi":
        
        for px in px_sessions:
            
            try:
                print("Testing Resources/Cluster")
                cluster_name = await get_cluster_name(px)
                print(cluster_name)

                cluster_resources_response = px("cluster/resources").get(type = "vm")
                json_response[cluster_name] = cluster_resources_response
 
            except ResponseValidationException as error:
                raise ProxboxException(
                    message = f"Could not validate data returned by Proxmox API (path: cluster/resources)",
                    python_exception = f"{error}"
                )
                
    if mode == "single":
        raise HTTPException(
                status_code=501,
                detail="Single-cluster API call not implemented yet."
            )

    return json_response

'''
@router.get("/cluster/{cluster_paths}")
async def cluster_paths(
    px_sessions: ProxmoxSessionDep,
    cluster_paths: ProxmoxClusterPaths,
    mode: ProxmoxModeOptions = "multi",
):
    pass
'''

@router.get("/{top_level}/{second_level}")
async def second_level_endpoint(
    px_sessions: ProxmoxSessionDep,
    top_level: ProxmoxUpperPaths,
    second_level: str,
    mode: ProxmoxModeOptions = "multi",
    type: str | None = None,
):
        
        
    async def single_cluster(px):
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
            
            return json_obj
            
        except ResourceException as error:
            raise ProxboxException(
                message =  f"Path {path} does not exist.",
                python_exception = f"{error}"
            )


    async def multi_cluster(px_sessions):
        clusters_response = []
        
        for px in px_sessions:
            clusters_response.append(await single_cluster(px))
        
        return clusters_response


    if mode == "multi":
        return await multi_cluster(px_sessions) 
    
    if mode == "single":
        raise HTTPException(
                status_code=501,
                detail="Single-cluster API call not implemented yet."
            )
        
    
    return json_obj