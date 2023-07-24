from fastapi import FastAPI

from proxmoxer import ProxmoxAPI, ResourceException

import endpoint

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

'''
HOST = "X.X.X.X"
PORT = "<PORT>"
USER = "<USER>@pam"
TOKEN_NAME = "<STRING>"
TOKEN_VALUE = "XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX"
VERIFY_SSL = "<BOOLEAN>"
'''

TOPLEVEL_ENDPOINTS = ["access", "cluster", "nodes", "pools", "storage", "version"]

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
    api_hierarchy = {
        "access" : px.access.get(),
        "cluster": px.cluster.get(),
        "nodes": px.nodes.get(),
        "pools": px.pools.get(),
        "storage": px.storage.get(),
        "version": px.version.get(),
    }

    return {
        "message": "Proxmox API",
        "api_viewer": "https://pve.proxmox.com/pve-docs/api-viewer/",
        "github": {
            "netbox": "https://github.com/netbox-community/netbox",
            "pynetbox": "https://github.com/netbox-community/pynetbox",
            "proxmoxer": "https://github.com/proxmoxer/proxmoxer",
            "netbox-proxbox": "https://github.com/netdevopsbr/netbox-proxbox"
        },
        "api_base_results": api_hierarchy
    }
    return 

@app.get("/proxmox/{top_level}")
async def top_level_endpoint(
    top_level: str | None = None,
):
    if top_level not in TOPLEVEL_ENDPOINTS:
        return {
            "message": f"'{top_level}' is not a valid endpoint/path name.",
            "valid_names": TOPLEVEL_ENDPOINTS,
        }
    
    import numpy as np
    
    current_index = TOPLEVEL_ENDPOINTS.index(top_level)
    other_endpoints = TOPLEVEL_ENDPOINTS.copy()
    other_endpoints.pop(current_index)
    
    return {
        f"{top_level}": px(top_level).get(),
        "other_endpoints": other_endpoints,
    }
    
    '''
    match top_level:
        case "access": 
            json_obj = {"access": {}}
            second_level = endpoint.access(px.access.get())
            print(second_level)
            for endpoint_name in second_level:
                try:
                    path = f"{top_level}/{endpoint_name}"
                    result = px(path).get()
                    
                    json_obj["access"][endpoint_name] = result
                except ResourceException as error:
                    print(f"Path {path} does not exist.\n   > {error}")
                
            return json_obj
    '''





@app.get("/proxmox/{top_level}/{second_level}")
async def second_level_endpoint(
    top_level: str | None = None,
    second_level: str | None = None,
):
    match top_level:
        case "access": return px.access.get()
        case "cluster": return px.cluster.get()
        case "nodes": return px.nodes.get()
        case "pools": return px.pools.get()
        case "storage": return px.storage.get()
        case "version": return {f"{top_level}": px.version.get(), "secondlevel": second_level}