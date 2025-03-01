from proxbox_api.routes.netbox.generic import NetboxBase
from .cluster import Cluster
from proxbox_api.logger import log

class VirtualMachine(NetboxBase):
    # Default Cluster Type Params
    default_name: str = "Proxbox Basic Virtual Machine"
    default_slug: str = "proxbox-basic-virtual-machine"
    default_description: str = "Proxmox Virtual Machine (this is a fallback VM when syncing from Proxmox)"
    
    app: str = "virtualization"
    endpoint: str = "virtual_machines"
    object_name: str = "Virtual Machine"

    async def get_base_dict(self):
        cluster = None
        
        try:
            cluster = await Cluster(nb = self.nb, websocket = self.websocket).get()
        except Exception as error:
            await log(self.websocket, f"Failed to fetch cluster for virtual machine: {self.default_name}.\nPython Error: {error}")

        if cluster is not None:     
            return {
                "name": self.default_name,
                "slug": self.default_slug,
                "description": self.default_description,
                "status": "active",
                "cluster": getattr(cluster, 'id', 0)
            }
        else:
            await log(self.websocket, f"Failed to fetch cluster for virtual machine: {self.default_name}. As it is a required field, the virtual machine will not be created.")