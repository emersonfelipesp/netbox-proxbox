from netbox_proxbox.backend.routes.netbox.generic import NetboxBase

class Manufacturer(NetboxBase):

    default_name = "Proxbox Basic Manufacturer"
    default_slug = "proxbox-basic-manufacturer"
    default_description = "Proxbox Basic Manufacturer"
    
    app = "dcim"
    endpoint = "manufacturers"
    object_name = "Manufacturer"
    
    
    async def get_base_dict(self):
        return {
            "name": self.default_name,
            "slug": self.default_slug,
            "description": self.default_description,
        }