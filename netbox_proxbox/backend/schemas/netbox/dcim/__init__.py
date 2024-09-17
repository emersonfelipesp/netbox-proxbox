from pydantic import BaseModel

from netbox_proxbox.backend.schemas.netbox.extras import TagSchema
from netbox_proxbox.backend.enum.netbox.dcim import StatusOptions

class SitesSchema(BaseModel):
    name: str
    slug: str
    status: StatusOptions
    region: int | None = None
    group: int | None = None
    facility: str | None = None
    asns: list[int] | None = None
    time_zone: str | None = None
    description: str | None = None
    tags: list[TagSchema | int] | None = None
    custom_fields: dict | None = None
    physical_address: str | None = None
    shipping_address: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    tenant: int | None = None
    