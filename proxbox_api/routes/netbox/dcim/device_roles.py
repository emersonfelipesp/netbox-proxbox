from netbox_proxbox.backend.routes.netbox.generic import NetboxBase

class DeviceRole(NetboxBase):
    """
    DeviceRole class represents a device role in Netbox for Proxmox nodes.
    Attributes:
        default_name (str): The default name for the device role.
        default_slug (str): The default slug for the device role.
        default_description (str): The default description for the device role.
        app (str): The application name associated with the device role.
        endpoint (str): The API endpoint for the device role.
        object_name (str): The name of the object type.
    Methods:
        get_base_dict():
            Asynchronously returns a dictionary with the base attributes for the device role.
    """
    
    default_name: str = "Proxmox Node (Server)"
    default_slug: str = "proxbox-node"
    default_description: str = "Proxbox Basic Device Role"
    
    app: str = "dcim"
    endpoint: str = "device_roles"
    object_name: str = "Device Types"
    
    async def get_base_dict(self):
        return {
            "name": self.default_name,
            "slug": self.default_slug,
            "color": "ff5722",
            "vm_role": False,
            "description": self.default_description,
        }