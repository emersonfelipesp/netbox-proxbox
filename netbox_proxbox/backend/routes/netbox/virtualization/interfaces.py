from netbox_proxbox.backend.routes.netbox.generic import NetboxBase

from netbox_proxbox.backend.routes.netbox.virtualization import VirtualMachine

class VMInterface(NetboxBase):
    
    default_name = "Proxbox Virtual Machine Basic Interface"
    default_description = "Proxbox Virtual Machine Basic Interface Description"
    
    app = "virtualization"
    endpoint = "interfaces"
    object_name = "Virtual Machine Interface"
    
    primary_field: str =  "virtual_machine"
    
    async def get_base_dict(self):
        
        virtual_machine = await VirtualMachine(nb = self.nb, websocket = self.websocket).get()
        
        return {
            "virtual_machine": virtual_machine.id,
            "name": self.default_name,
            "description": self.default_description,
            "enabled": True
        }