from proxbox_api.routes.netbox.generic import NetboxBase
from proxbox_api.routes.netbox.dcim.devices import Device

class Interface(NetboxBase):
    
    default_name: str = "Proxbox Basic interface"
    default_description: str = "Proxbox Basic Interface"
    type: str = "other"
    
    app: str = "dcim"
    endpoint: str = "interfaces"
    object_name: str = "Interface"
    
    async def get_base_dict(self):
        device = await Device(nb = self.nb, websocket = self.websocket).get()
        
        return {
            "device": device.id,
            "name": self.default_name,
            "type": "other",
            "description": self.default_description,
            "enabled": True,
        }
