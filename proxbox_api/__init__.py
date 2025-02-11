from proxbox_api.routes.netbox.virtualization.cluster_type import ClusterType
from proxbox_api.routes.netbox.virtualization.cluster import Cluster
from proxbox_api.routes.netbox.virtualization.virtual_machines import VirtualMachine

from proxbox_api.routes.netbox.virtualization.interfaces import VMInterface

from proxbox_api.routes.netbox.dcim.sites import Site
from proxbox_api.routes.netbox.dcim.device_roles import DeviceRole
from proxbox_api.routes.netbox.dcim.device_types import DeviceType
from proxbox_api.routes.netbox.dcim.devices import Device
from proxbox_api.routes.netbox.dcim.interfaces import Interface
from proxbox_api.routes.netbox.ipam.ip_addresses import IPAddress


from pydantic import BaseModel
from pynetbox_api.extras import Tags, TagsSchemaIn

class ProxboxTagSchemaIn(TagsSchemaIn):
    name: str = 'Proxbox'
    slug: str = 'proxbox'
    color: str = 'ff5722'
    description: str = 'Proxbox Identifier (used to identify the items the plugin created)'

class ProxboxTag(Tags):
    schema_in = ProxboxTagSchemaIn