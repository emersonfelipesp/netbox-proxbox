from proxbox_api.routes.netbox.generic import NetboxBase

class Site(NetboxBase):
    default_name = "Proxbox Basic Site"
    default_slug = "proxbox-basic-site"
    default_description = "Proxbox Basic Site (used to identify the items the plugin created)"
    
    app = "dcim"
    endpoint = "sites"
    object_name = "Site"
    
    async def get_base_dict(self):
        return {
            "name": self.default_name,
            "slug": self.default_slug,
            "description": self.default_description,
        }