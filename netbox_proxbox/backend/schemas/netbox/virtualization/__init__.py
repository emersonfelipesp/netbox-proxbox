from pydantic import BaseModel

from netbox_proxbox.backend.schemas.netbox.extras import TagSchema
from netbox_proxbox.backend.enum.netbox.dcim import StatusOptions

class ClusterTypeSchema(BaseModel):
    name: str
    slug: str
    description: str | None = None
    tags: list[TagSchema] | None = None
    custom_fields: dict | None = None
    