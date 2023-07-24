# Python Framework
from fastapi import FastAPI

# NP import to use 'copy' array method
import numpy as np

# Proxmoxer lib (https://proxmoxer.github.io/)
from proxmoxer import ProxmoxAPI, ResourceException

# HTTP SSL handling
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

TOPLEVEL_ENDPOINTS = ["access", "cluster", "nodes", "pools", "storage", "version"]

'''
HOST = "X.X.X.X"
PORT = "<PORT>"
USER = "<USER>@pam"
TOKEN_NAME = "<STRING>"
TOKEN_VALUE = "XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX"
VERIFY_SSL = "<BOOLEAN>"
'''

# Example of variables formmating/type
HOST = "10.0.30.9"
PORT = 8006
USER = "root@pam"
TOKEN_NAME = "root"
TOKEN_VALUE = "039ad154-23c2-4be0-8d20-b65bbb8c4686"
VERIFY_SSL = False

try:
    # Start PROXMOX session using TOKEN
    px = ProxmoxAPI(
        HOST,
        port=PORT,
        user=USER,
        token_name=TOKEN_NAME,
        token_value=TOKEN_VALUE,
        verify_ssl=VERIFY_SSL
    )
except Exception as error:
    raise RuntimeError(f'Error trying to initialize Proxmox Session using TOKEN (token_name: {TOKEN_NAME} and token_value: {TOKEN_VALUE} provided\n   > {error}')

# Init FastAPI
app = FastAPI()

@app.get("/")
async def root():
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

@app.get("/proxmox")
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
            "netbox-proxbox": "https://github.com/netdevopsbr/netbox-proxbox"
        },
        "base_endpoints": api_hierarchy
    }

@app.get("/proxmox/{top_level}")
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


@app.get("/proxmox/{top_level}/{second_level}")
async def second_level_endpoint(
    top_level: str | None = None,
    second_level: str | None = None,
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
        result = px(path).get()
        
        # Feed JSON result
        json_obj[top_level][second_level] = result
        
    except ResourceException as error:
        print(f"Path {path} does not exist.\n   > {error}")
        
    return json_obj