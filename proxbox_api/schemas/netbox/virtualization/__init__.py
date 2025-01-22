from pydantic import BaseModel

from proxbox_api.schemas.netbox.extras import TagSchema
from proxbox_api.enum.netbox.virtualization import ClusterStatusOptions


class ClusterTypeSchema(BaseModel):
    name: str
    slug: str | None = None
    description: str | None = None
    tags: list[TagSchema] | None = None
    custom_fields: dict | None = None

class ClusterSchema(BaseModel):
    name: str
    type: int
    group: int | None = None
    site: int | None = None
    status: ClusterStatusOptions
    tenant: int | None = None
    description: str | None = None
    comments: str | None = None
    tags: list[int] | None = None
    custom_fields: dict | None = None
    