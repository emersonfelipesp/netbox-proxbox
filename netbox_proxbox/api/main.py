# Python Framework
from typing import Annotated

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# NP import to use 'copy' array method
import numpy as np

# Proxmoxer lib (https://proxmoxer.github.io/)
from proxmoxer import ProxmoxAPI, ResourceException

# HTTP SSL handling
import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

TOPLEVEL_ENDPOINTS = ["access", "cluster", "nodes", "pools", "storage", "version"]

# Proxbox
from netbox_proxbox.proxbox_api.plugins_config import PROXMOX_SESSIONS, PROXMOX_SETTING

sessions_list = []

# Get SESSIONs from JSON
for px_node in PROXMOX_SETTING:
    domain = px_node.get("domain")
    
    px_json = PROXMOX_SESSIONS.get(domain)
    px_session = px_json.get('PROXMOX_SESSION')
    sessions_list.append(px_session)

# Single Session
px = None
try:
    px = sessions_list[0]
except Exception as error:
    print(f"Not able to establish session.\n   > {error}")

FASTAPI_HOST = "127.0.0.1"
FASTAPI_PORT = "9000"
    
# Init FastAPI
app = FastAPI()

app.mount("/static", StaticFiles(directory="/opt/netbox/netbox/netbox-proxbox/netbox_proxbox/static"), name="static")

templates = Jinja2Templates(directory="/opt/netbox/netbox/netbox-proxbox/netbox_proxbox/templates/netbox_proxbox")

import time
from typing import Callable

from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.routing import APIRoute

import json

@app.get("/standalone-info")
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
            "proxbox": "https://github.com/netdevopsbr/netbox-proxbox"
        },
        "base_endpoints": api_hierarchy
    }


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