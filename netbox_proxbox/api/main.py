from fastapi import FastAPI

'''
from plugins_config import (
    NETBOX,
    NETBOX_TOKEN,
    PROXMOX_SESSIONS as proxmox_sessions,
    NETBOX_SESSION as nb,
)
'''

from proxmoxer import ProxmoxAPI


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

'''
api_hierarchy = {
    "toplevel": ["access", "cluster", "nodes", "pools", "storage", "version"],
    "secondlevel": { 
        "access": ["domains", "groups", "openid", "roles", "tfa", "users", "acl", "password", "permissions", "ticket"],
        "cluster": ["acme", "backup", "backup-info", "ceph", "config", "firewall", "ha", "jobs", "mapping", "metrics",
                    "replication", "sdn", "log", "options", "resources", "status", "tasks"],
        "nodes": "node_id",
        "pools": "pool_id",
        "storage": "storage_id",
    },
    "thirdlevel": {
        "node": ["apt", "capabilities", "ceph", "certificates", "disks", "firewall", "lxc", "network", "qemu", "replication", "scan", "sdn", "services",
                 "storage", "tasks", "vzdump", "aplinfo", "config", "dns", "execute", "hosts", "journal", "migrateall", "query-url-metadata", "report",
                 "rrd", "rrddata", "spiceshell", "startall", "stopall", "subscription", "syslog", "subscription", "syslog", "termproxy",
                "time", "version", "vncshell", "vncwebsocket", "wakeonlan"]
    }
}
'''
     
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
async def root(
    top_level: str | None = None,
):
    match top_level:
        case "access": return px.access.get()
        case "cluster": return px.cluster.get()
        case "nodes": return px.nodes.get()
        case "pools": return px.pools.get()
        case "storage": return px.storage.get()
        case "version": return px.version.get()

@app.get("/proxmox/{top_level}/{second_level}/{third_level}")
async def root(
    top_level: str | None = None,
    second_level: str | None = None,
    third_level: str | None = None,
):
    return px.cluster.resources.get()

