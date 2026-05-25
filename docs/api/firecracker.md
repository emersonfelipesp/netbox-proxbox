# Firecracker API

Firecracker inventory is exposed under the NetBox plugin API so NMS Cloud can discover available runtime capacity and show provisioned micro-VMs beside existing QEMU and LXC instances.

For common authentication, pagination, and nested serializer behavior, see [API Overview](index.md).

## Inventory Endpoints

All paths are relative to `/api/plugins/proxbox/`.

| Resource | Path | Purpose |
|---|---|---|
| Host pools | `firecracker-host-pools/` | Tenant-visible pools that group Firecracker host-agent VMs |
| Hosts | `firecracker-hosts/` | Host-agent VM records with agent URL, capacity, status, and KVM/network capability fields |
| Image templates | `firecracker-image-templates/` | Kernel/rootfs image bundles available to Cloud users |
| Micro-VMs | `firecracker-microvms/` | Provisioned Firecracker instances tracked in NetBox |
| Cloud resource list | `resources/firecracker-microvms/` | NMS-compatible list shape used by `/cloud/instances` |

The CRUD viewsets support the normal NetBox REST verbs:

```text
GET    /api/plugins/proxbox/firecracker-host-pools/
GET    /api/plugins/proxbox/firecracker-host-pools/{id}/
POST   /api/plugins/proxbox/firecracker-host-pools/
PUT    /api/plugins/proxbox/firecracker-host-pools/{id}/
PATCH  /api/plugins/proxbox/firecracker-host-pools/{id}/
DELETE /api/plugins/proxbox/firecracker-host-pools/{id}/
```

Use the same verb pattern for `firecracker-hosts`, `firecracker-image-templates`, and `firecracker-microvms`.

## Cloud List Shape

`GET /api/plugins/proxbox/resources/firecracker-microvms/` returns micro-VMs in the shape consumed by `nms-backend`:

```json
{
  "count": 1,
  "results": [
    {
      "id": 42,
      "instance_ref": "firecracker:42",
      "kind": "firecracker",
      "name": "tenant-api-01",
      "status": {"value": "running", "label": "Running"},
      "host_pool": {"id": 3, "display": "edge-firecracker"},
      "image": {"id": 7, "display": "Alpine 3.20"},
      "vcpus": 1,
      "memory_mib": 512,
      "disk_mib": 1024,
      "guest_ip": "10.10.0.21"
    }
  ]
}
```

`kind` is always `firecracker`. `instance_ref` is the stable Cloud identifier and uses the `firecracker:<netbox-id>` format so it cannot collide with numeric NetBox `VirtualMachine` IDs.

## Provisioning Boundary

This plugin stores and exposes inventory. The actual micro-VM boot sequence is handled by `proxbox-api` through `/cloud/firecracker/provision` or `/cloud/firecracker/provision/stream`, which calls the selected host-agent.
