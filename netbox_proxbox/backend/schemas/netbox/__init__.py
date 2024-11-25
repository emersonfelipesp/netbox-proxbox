from pydantic import BaseModel, RootModel

class NetboxSessionSettingsSchema(BaseModel):
    virtualmachine_role_id: int
    node_role_id: int
    site_id: int
    
class NetboxSessionSchema(BaseModel):
    domain: str
    http_port: int
    token: str
    settings: NetboxSessionSettingsSchema | None = None
    
CreateDefaultBool = RootModel[ bool | None ]