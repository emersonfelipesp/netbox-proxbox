# Deploy FastAPI

Using **[uvicorn](https://www.uvicorn.org/)** to deploy Proxbox backend using **[FastAPI](https://fastapi.tiangolo.com/)** on port **9000** using development mode with --reload.

### It's not ready for PRODUCTION!

FastAPI was chosen to replace the current Django Backend, but it's not fully implemented and tested.

```
cd /opt/netbox/netbox
uvicorn netbox-proxbox.netbox_proxbox.api.main:app --reload --port 9000
```

## Testing FastAPI

Access the following URL **http://HOST:PORT/proxmox/cluster/resources** to view all VMs/Nodes/Storages of your environment.
Docs: **http://HOST:PORT/docs** or **http://HOST:PORT/redoc**

## Security

The password is not securely stored yet, but I will fix it.
About the integration, we only use **GET HTTP methods** and we do not modify anything of your environment using **POST / PUT** methods, even though the token allows it or not.