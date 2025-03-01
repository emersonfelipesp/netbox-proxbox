from proxbox_api.routes.netbox.generic import NetboxBase

class IPAddress(NetboxBase):
    # Default IP Address Params
    default_description: str = "Proxbox Basic IP Address"
    
    app: str = "ipam"
    endpoint: str = "ip_addresses"
    object_name: str = "IP Address"
    
    primary_field: str = "address"
    
    async def get_base_dict(self):
        return {
            "description": self.default_description,
            "status": "active"
        }