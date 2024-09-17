from netbox_proxbox.backend.routes.netbox.generic import NetboxBase
from .cluster import Cluster

class VirtualMachine(NetboxBase):
    # Default Cluster Type Params
    default_name: str = "Proxbox Basic Virtual Machine"
    default_slug: str = "proxbox-basic-virtual-machine"
    default_description: str = "Proxmox Virtual Machine (this is a fallback VM when syncing from Proxmox)"
    
    app: str = "virtualization"
    endpoint: str = "virtual_machines"
    object_name: str = "Virtual Machine"
    

    async def get_base_dict(self):
        cluster = await Cluster(nb = self.nb).get()
        return {
            "name": self.default_name,
            "slug": self.default_slug,
            "description": self.default_description,
            "status": "active",
            "cluster": cluster.id
        }