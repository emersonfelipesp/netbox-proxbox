from netbox_proxbox.backend.routes.netbox.generic import NetboxBase

class Device(NetboxBase):
    default_name = "Proxbox Basic Device"
    default_slug = "proxbox-basic-device"
    default_description = "Proxbox Basic Device"
    
    app = "dcim"
    endpoint = "devices"
    object_name = "Device"