from netbox_proxbox.backend.routes.netbox.generic import NetboxBase

class Manufacturer(NetboxBase):
    default_name = "Proxbox Basic Manufacturer"
    default_slug = "proxbox-basic-manufacturer"
    default_description = "Proxbox Basic Manufacturer"
    
    app = "dcim"
    endpoint = "manufacturers"
    object_name = "Manufacturer"