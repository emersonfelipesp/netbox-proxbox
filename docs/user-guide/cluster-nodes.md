# Cluster and Node Tracking

Proxbox tracks Proxmox cluster and node information, linking them to NetBox's native `virtualization.Cluster` and `dcim.Device` objects for full infrastructure visibility.

## Overview

When a Proxmox environment runs in cluster mode, multiple hypervisor nodes form a single logical unit managed by Corosync/Proxmox VE cluster services. Proxbox reflects this topology inside NetBox by:

- Creating a `ProxmoxCluster` record that mirrors the Proxmox cluster and optionally links to a NetBox `virtualization.Cluster`.
- Creating a `ProxmoxNode` record per hypervisor node, each optionally linked to a NetBox `dcim.Device`.
- Updating the `ProxmoxEndpoint.mode` field to `cluster` or `standalone` automatically after each sync.

## Features

| Feature | Description |
|---|---|
| Cluster discovery | Detects cluster name, quorum status, and node count from Proxmox |
| Node monitoring | Tracks online/offline state, CPU usage, memory (used/total), and uptime per node |
| NetBox Cluster link | Optional FK to `virtualization.Cluster` for unified cluster inventory |
| NetBox Device link | Optional FK to `dcim.Device` for unified device/server inventory |
| Mode auto-detection | Sets `standalone` or `cluster` on the endpoint during sync |
| REST API | Full CRUD and filtering for clusters and nodes via the plugin API |

## Viewing Cluster and Node Data

Navigate to the endpoint detail page:

**Plugins → ProxBox → Endpoints → Proxmox → _[Endpoint name]_ → Cluster & Nodes tab**

The tab shows:

1. **Cluster summary card** — name, mode badge, quorum badge, version, and total node count.
2. **Node table** — one row per node with columns for status, IP address, CPU %, memory (used GB / total GB), and uptime.

### Mode Badges

The `Mode` field on the endpoint detail page uses colour-coded badges:

| Badge | Meaning |
|---|---|
| Green — Cluster | Multi-node Proxmox cluster |
| Blue — Standalone | Single-node installation |
| Gray — Undefined | Sync has not run yet |

## Syncing Cluster Data

### Programmatic Sync

Call `sync_cluster_and_nodes()` from anywhere in the NetBox Django environment:

```python
from netbox_proxbox.services.sync_cluster import sync_cluster_and_nodes

result = sync_cluster_and_nodes(endpoint_id=1)
# result = {
#   "mode": "cluster",
#   "clusters": {"created": 1, "updated": 0},
#   "nodes":    {"created": 3, "updated": 0, "deleted": 0},
# }
print(result)
```

The function:

1. Calls `proxbox-api /proxmox/cluster/status` to get cluster and node topology.
2. Calls `proxbox-api /proxmox/nodes/` to get per-node resource metrics.
3. Creates or updates `ProxmoxCluster` and `ProxmoxNode` records in a single DB transaction.
4. Deletes `ProxmoxNode` rows that no longer exist in Proxmox.
5. Sets `ProxmoxEndpoint.mode` to `cluster` or `standalone`.

### Automatic Sync

The cluster sync is designed to be called inside the existing Proxbox background sync job. Add a call to `sync_cluster_and_nodes()` at the end of your custom sync flow, or wait for it to be wired into the `full-update` job in a future release.

## REST API

All cluster and node objects are accessible through the plugin REST API.

### Cluster Endpoints

```
GET  /api/plugins/proxbox/clusters/
GET  /api/plugins/proxbox/clusters/{id}/
POST /api/plugins/proxbox/clusters/
PUT  /api/plugins/proxbox/clusters/{id}/
PATCH /api/plugins/proxbox/clusters/{id}/
DELETE /api/plugins/proxbox/clusters/{id}/
```

**Example — list clusters:**

```bash
curl -H "Authorization: Token <token>" \
     http://netbox.example.com/api/plugins/proxbox/clusters/
```

**Filterable fields:** `endpoint_id`, `name`, `mode`, `quorate`

**Searchable fields:** `name`, `version`

### Node Endpoints

```
GET  /api/plugins/proxbox/nodes/
GET  /api/plugins/proxbox/nodes/{id}/
POST /api/plugins/proxbox/nodes/
PUT  /api/plugins/proxbox/nodes/{id}/
PATCH /api/plugins/proxbox/nodes/{id}/
DELETE /api/plugins/proxbox/nodes/{id}/
```

**Example — list online nodes for a specific endpoint:**

```bash
curl -H "Authorization: Token <token>" \
     "http://netbox.example.com/api/plugins/proxbox/nodes/?endpoint_id=1&online=true"
```

**Filterable fields:** `endpoint_id`, `proxmox_cluster_id`, `name`, `online`, `ip_address`

**Searchable fields:** `name`, `ip_address`

### Sample Cluster Response

```json
{
  "id": 1,
  "url": "/api/plugins/proxbox/clusters/1/",
  "endpoint": {"id": 1, "name": "prod-proxmox"},
  "netbox_cluster": {"id": 5, "name": "prod-cluster"},
  "name": "pve-cluster",
  "mode": "cluster",
  "quorate": true,
  "nodes_count": 3,
  "version": "7.4-3",
  "created": "2026-04-01T00:00:00Z",
  "last_updated": "2026-04-01T00:00:00Z"
}
```

### Sample Node Response

```json
{
  "id": 1,
  "url": "/api/plugins/proxbox/nodes/1/",
  "endpoint": {"id": 1, "name": "prod-proxmox"},
  "proxmox_cluster": {"id": 1, "name": "pve-cluster"},
  "netbox_device": {"id": 42, "name": "pve-node-01"},
  "name": "pve-node-01",
  "ip_address": "10.0.0.10",
  "online": true,
  "cpu_usage": 12.5,
  "memory_used": 17179869184,
  "memory_total": 68719476736,
  "uptime": 1209600,
  "level": "",
  "local_id": 1,
  "created": "2026-04-01T00:00:00Z",
  "last_updated": "2026-04-01T00:00:00Z"
}
```

## Linking to NetBox Objects

### Link ProxmoxCluster to a NetBox Cluster

After creating both objects, assign the FK through the API or in Python:

```python
from netbox_proxbox.models import ProxmoxCluster
from virtualization.models import Cluster

proxmox_cluster = ProxmoxCluster.objects.get(name="pve-cluster")
netbox_cluster  = Cluster.objects.get(name="prod-cluster")

proxmox_cluster.netbox_cluster = netbox_cluster
proxmox_cluster.save()
```

Or via REST PATCH:

```bash
curl -X PATCH \
     -H "Authorization: Token <token>" \
     -H "Content-Type: application/json" \
     -d '{"netbox_cluster": 5}' \
     http://netbox.example.com/api/plugins/proxbox/clusters/1/
```

### Link ProxmoxNode to a NetBox Device

```python
from netbox_proxbox.models import ProxmoxNode
from dcim.models import Device

proxmox_node  = ProxmoxNode.objects.get(name="pve-node-01")
netbox_device = Device.objects.get(name="pve-node-01")

proxmox_node.netbox_device = netbox_device
proxmox_node.save()
```

Both FKs are nullable (`SET_NULL` on delete). Deleting a NetBox Cluster or Device clears the pointer on the Proxbox object without deleting the Proxbox record.

## Data Model

### ProxmoxCluster

| Field | Type | Description |
|---|---|---|
| `endpoint` | FK → ProxmoxEndpoint | Parent Proxmox endpoint |
| `netbox_cluster` | FK → virtualization.Cluster (nullable) | Linked NetBox cluster |
| `name` | CharField | Cluster name from Proxmox |
| `mode` | CharField | `cluster` or `standalone` |
| `quorate` | BooleanField | Corosync quorum status |
| `nodes_count` | IntegerField | Number of member nodes |
| `version` | CharField | Proxmox VE version string |

### ProxmoxNode

| Field | Type | Description |
|---|---|---|
| `endpoint` | FK → ProxmoxEndpoint | Parent Proxmox endpoint |
| `proxmox_cluster` | FK → ProxmoxCluster (nullable) | Owning cluster (null for standalone) |
| `netbox_device` | FK → dcim.Device (nullable) | Linked NetBox device |
| `name` | CharField | Node name |
| `ip_address` | CharField | Management IP address |
| `online` | BooleanField | Whether node is online |
| `cpu_usage` | FloatField | CPU usage percentage (0–100) |
| `memory_used` | BigIntegerField | Used memory in bytes |
| `memory_total` | BigIntegerField | Total memory in bytes |
| `uptime` | BigIntegerField | Uptime in seconds |
| `level` | CharField | Node level (empty for normal nodes) |
| `local_id` | IntegerField | Proxmox-assigned node ID |

## Troubleshooting

**Mode shows "Undefined"**
: The endpoint sync has not run yet. Call `sync_cluster_and_nodes(endpoint_id=<id>)` or trigger a Proxbox sync job.

**"Cluster & Nodes" tab is empty**
: Verify that `proxbox-api` is reachable from NetBox and that endpoint credentials are correct. Check the proxbox-api logs for errors on `/proxmox/cluster/status`.

**Nodes not updating after a topology change**
: Stale nodes are deleted automatically during sync. If they persist, check that `proxbox-api` is returning the updated node list for that endpoint.

**Node table shows 0 % CPU or 0 GB memory**
: The `/proxmox/nodes/` endpoint may have returned missing metric fields. This is non-fatal; values default to zero and will update on the next successful sync.
