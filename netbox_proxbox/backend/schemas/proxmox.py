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