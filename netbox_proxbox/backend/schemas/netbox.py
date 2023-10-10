from pydantic import BaseModel

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