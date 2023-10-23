# Python Framework
"""

from typing import Callable


from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.routing import APIRoute

# NP import to use 'copy' array method
import numpy as np

import json
import time
"""

# Proxmoxer lib (https://proxmoxer.github.io/)
# from proxmoxer import ProxmoxAPI, ResourceException


# HTTP SSL handling
# import requests
# import urllib3
# urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# TOPLEVEL_ENDPOINTS = ["access", "cluster", "nodes", "pools", "storage", "version"]

"""
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
"""

from typing import Annotated

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from netbox_proxbox.backend.exception import ProxboxException

from .backend.routes.netbox import (
    router as netbox_router
)
from .backend.routes.proxbox import (
    router as proxbox_router
)
from .backend.routes.proxmox import (
    router as proxmox_router
)

from .backend.schemas import *

PROXBOX_PLUGIN_NAME = "netbox_proxbox"

# Init FastAPI
app = FastAPI()

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
    
# Routes (Endpoints)
app.include_router(netbox_router, prefix="/netbox", tags=["netbox"])
app.include_router(proxbox_router, prefix="/proxbox", tags=["proxbox"])
app.include_router(proxmox_router, prefix="/proxmox", tags=["proxmox"])

# app.mount("/static", StaticFiles(directory="/opt/netbox/netbox/netbox-proxbox/netbox_proxbox/static"), name="static")

# templates = Jinja2Templates(directory="/opt/netbox/netbox/netbox-proxbox/netbox_proxbox/templates/netbox_proxbox")


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

