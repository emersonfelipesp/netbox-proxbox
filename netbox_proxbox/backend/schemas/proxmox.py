from pydantic import BaseModel

class ProxmoxTokenSchema(BaseModel):
    name: str
    value: str
    
class ProxmoxSessionSchema(BaseModel):
    domain: str
    http_port: int
    user: str
    password: str
    token: ProxmoxTokenSchema
    ssl: bool
    
    """
    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    'domain': 'proxbox2.example.com',
                    'http_port': 8006,
                    'user': 'root@pam',
                    'password': 'Strong@P4ssword',
                    'token': {
                        'name': 'tokenID',
                        'value': '039az154-23b2-4be0-8d20-b66abc8c4686'
                    },
                    'ssl': False
                }
            ]
        }
    }
    """