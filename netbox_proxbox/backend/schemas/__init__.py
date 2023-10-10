from pydantic import BaseModel

class ProxmoxToken(BaseModel):
    name: str
    value: str
    
class ProxmoxSession(BaseModel):
    domain: str
    http_port: int
    user: str
    password: str
    token: ProxmoxToken

class NetboxSessionSettings(BaseModel):
    virtualmachine_role_id: int
    node_role_id: int
    site_id: int
    
class NetboxSession(BaseModel):
    domain: str
    http_port: int
    token: str
    ssl: bool
    settings: NetboxSessionSettings | None = None

class PluginConfig(BaseModel):
    proxmox: list[ProxmoxSession]
    netbox: NetboxSession