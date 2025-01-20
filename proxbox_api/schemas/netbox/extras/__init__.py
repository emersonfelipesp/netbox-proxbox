from pydantic import BaseModel

class TagSchema(BaseModel):
    name: str
    slug: str
    color: str
    description: str | None = None
    object_types: list[str] | None = None
    
    
    