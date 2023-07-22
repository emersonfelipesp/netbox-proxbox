from fastapi import FastAPI

from netbox_proxbox.plugins_config import (
    NETBOX,
    NETBOX_TOKEN,
    PROXMOX_SESSIONS as proxmox_sessions,
    NETBOX_SESSION as nb,
)

app = FastAPI()


@app.get("/")
async def root():
    return {"message": "Proxbox Backend"}
