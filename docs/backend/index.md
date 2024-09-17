## How it works

The backend made using the FastAPI framework connects with both Netbox and Proxmox (it can be many different clusters) and exposes the API REST routes that will be consumed by the Netbox Plugin (the Frontend) that is simply a Django App attached to the Netbox Django Project.

### Proxbox Architecture

![Proxbox Architecure Image](./proxbox-architecture.png)
