from proxbox_api.logger import log
from proxbox_api.routes.netbox.generic import NetboxBase
from proxbox_api.routes.netbox.virtualization import VirtualMachine

class VMInterface(NetboxBase):
    
    default_name = "Proxbox Virtual Machine Basic Interface"
    default_description = "Proxbox Virtual Machine Basic Interface Description"
    
    app = "virtualization"
    endpoint = "interfaces"
    object_name = "Virtual Machine Interface"
    
    primary_field: str = "virtual_machine"
    
    async def get_base_dict(self):
        virtual_machine = None
        
        try:
            virtual_machine = await VirtualMachine(nb = self.nb, websocket = self.websocket).get()
        except Exception as error:
            await log(self.websocket, f"Failed to fetch virtual machine for interface: {self.default_name}.\nPython Error: {error}")
        
        if virtual_machine is not None:
            return {
                "virtual_machine": getattr(virtual_machine, "id", 0),
                "name": self.default_name,
                "description": self.default_description,
                "enabled": True
            }
        else:
            await log(self.websocket, f"Failed to fetch virtual machine for interface: {self.default_name}. As it is a required field, the interface will not be created.")