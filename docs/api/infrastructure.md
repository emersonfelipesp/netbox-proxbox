# Infrastructure API

These three models represent the Proxmox infrastructure topology synced into NetBox: cluster metadata, hypervisor nodes, and storage backends.

For common API conventions (authentication, pagination, nested serializers), see [API Overview](index.md).

For the operational guide — how to trigger cluster/node syncs, link to NetBox objects, and troubleshoot — see [Cluster and Node Tracking](../user-guide/cluster-nodes.md).

---

## Proxmox Cluster

A Proxmox VE cluster record, optionally linked to a NetBox `virtualization.Cluster`.

```
GET    /api/plugins/proxbox/clusters/
GET    /api/plugins/proxbox/clusters/{id}/
POST   /api/plugins/proxbox/clusters/
PUT    /api/plugins/proxbox/clusters/{id}/
PATCH  /api/plugins/proxbox/clusters/{id}/
DELETE /api/plugins/proxbox/clusters/{id}/
```

**Example — list all clusters:**

```bash
curl -H "Authorization: Token <token>" \
     http://netbox.example.com/api/plugins/proxbox/clusters/
```

**Example — filter for cluster-mode only:**

```bash
curl -H "Authorization: Token <token>" \
     "http://netbox.example.com/api/plugins/proxbox/clusters/?mode=cluster"
```

**Example — link a cluster to a NetBox Cluster object:**

```bash
curl -X PATCH \
     -H "Authorization: Token <token>" \
     -H "Content-Type: application/json" \
     -d '{"netbox_cluster": 5}' \
     http://netbox.example.com/api/plugins/proxbox/clusters/1/
```

**Filterable fields:** `id`, `endpoint`, `netbox_cluster`, `name`, `mode`, `quorate`

**Searchable fields (`?q=`):** `name`, `cluster_id`

**Sample response:**

```json
{
  "id": 1,
  "url": "/api/plugins/proxbox/clusters/1/",
  "display": "pve-cluster",
  "endpoint": {
    "id": 1,
    "url": "/api/plugins/proxbox/endpoints/proxmox/1/",
    "display": "prod-proxmox (proxmox.example.com)",
    "name": "prod-proxmox"
  },
  "netbox_cluster": {
    "id": 5,
    "url": "/api/virtualization/clusters/5/",
    "display": "prod-cluster",
    "name": "prod-cluster"
  },
  "name": "pve-cluster",
  "cluster_id": "abc123",
  "mode": {"value": "cluster", "label": "Cluster"},
  "nodes_count": 3,
  "node_count": 3,
  "quorate": true,
  "version": 7,
  "tags": [],
  "custom_fields": {},
  "created": "2026-01-01T00:00:00Z",
  "last_updated": "2026-04-01T00:00:00Z"
}
```

### Data Model

| Field | Type | Description |
|---|---|---|
| `endpoint` | nested ProxmoxEndpoint | Parent Proxmox endpoint |
| `netbox_cluster` | nested Cluster (nullable) | Linked NetBox `virtualization.Cluster` — set `null` on delete |
| `name` | string | Cluster name from Proxmox |
| `cluster_id` | string | Proxmox internal cluster identifier |
| `mode` | choice | Deployment mode. Choices: `undefined`, `standalone`, `cluster` |
| `nodes_count` | integer | Number of member nodes reported by Proxmox |
| `node_count` | integer (read-only) | Alias for `nodes_count` |
| `quorate` | boolean | Corosync quorum status |
| `version` | integer (nullable) | Corosync configuration version |

---

## Proxmox Node

A Proxmox VE hypervisor node, optionally linked to a NetBox `dcim.Device`.

```
GET    /api/plugins/proxbox/nodes/
GET    /api/plugins/proxbox/nodes/{id}/
POST   /api/plugins/proxbox/nodes/
PUT    /api/plugins/proxbox/nodes/{id}/
PATCH  /api/plugins/proxbox/nodes/{id}/
DELETE /api/plugins/proxbox/nodes/{id}/
```

**Example — list all nodes for a specific endpoint:**

```bash
curl -H "Authorization: Token <token>" \
     "http://netbox.example.com/api/plugins/proxbox/nodes/?endpoint_id=1"
```

**Example — filter for online nodes only:**

```bash
curl -H "Authorization: Token <token>" \
     "http://netbox.example.com/api/plugins/proxbox/nodes/?online=true"
```

**Example — link a node to a NetBox Device:**

```bash
curl -X PATCH \
     -H "Authorization: Token <token>" \
     -H "Content-Type: application/json" \
     -d '{"netbox_device": 42}' \
     http://netbox.example.com/api/plugins/proxbox/nodes/1/
```

**Filterable fields:** `id`, `endpoint`, `proxmox_cluster`, `netbox_device`, `name`, `ip_address`, `online`, `local`

**Searchable fields (`?q=`):** `name`, `ip_address`, `ssl_fingerprint`

**Sample response:**

```json
{
  "id": 1,
  "url": "/api/plugins/proxbox/nodes/1/",
  "display": "pve-node-01",
  "endpoint": {
    "id": 1,
    "url": "/api/plugins/proxbox/endpoints/proxmox/1/",
    "display": "prod-proxmox (proxmox.example.com)",
    "name": "prod-proxmox"
  },
  "proxmox_cluster": {
    "id": 1,
    "url": "/api/plugins/proxbox/clusters/1/",
    "display": "pve-cluster",
    "name": "pve-cluster"
  },
  "netbox_device": {
    "id": 42,
    "url": "/api/dcim/devices/42/",
    "display": "pve-node-01",
    "name": "pve-node-01"
  },
  "name": "pve-node-01",
  "node_id": 1,
  "ip_address": "10.0.0.10",
  "online": true,
  "local": false,
  "cpu_usage": 12.5,
  "cpu_usage_percent": 12.5,
  "max_cpu": 32,
  "memory_usage": 17179869184,
  "memory_usage_percent": 25.0,
  "max_memory": 68719476736,
  "ssl_fingerprint": "AB:CD:EF:...",
  "support_level": "",
  "tags": [],
  "custom_fields": {},
  "created": "2026-01-01T00:00:00Z",
  "last_updated": "2026-04-01T00:00:00Z"
}
```

### Data Model

| Field | Type | Description |
|---|---|---|
| `endpoint` | nested ProxmoxEndpoint | Parent Proxmox endpoint |
| `proxmox_cluster` | nested ProxmoxCluster (nullable) | Owning cluster; `null` for standalone nodes |
| `netbox_device` | nested Device (nullable) | Linked NetBox `dcim.Device` — set `null` on delete |
| `name` | string | Node name in Proxmox |
| `node_id` | integer | Proxmox-assigned numeric node ID |
| `ip_address` | string | Node management IP address |
| `online` | boolean | Whether the node is currently online |
| `local` | boolean | Whether this is the local node on the endpoint |
| `cpu_usage` | float | Raw CPU usage value from Proxmox |
| `cpu_usage_percent` | float (read-only) | CPU usage as a percentage (0–100) |
| `max_cpu` | integer | Total CPU thread count |
| `memory_usage` | integer | Used memory in bytes |
| `memory_usage_percent` | float (read-only) | Memory usage as a percentage (0–100) |
| `max_memory` | integer | Total memory in bytes |
| `ssl_fingerprint` | string | TLS certificate fingerprint |
| `support_level` | string | Proxmox support subscription level |

---

## Proxmox Storage

A Proxmox storage backend synced from a cluster, covering all storage types supported by Proxmox (local directories, NFS, CIFS, Ceph/RBD, PBS, ZFS, and more).

```
GET    /api/plugins/proxbox/storage/
GET    /api/plugins/proxbox/storage/{id}/
POST   /api/plugins/proxbox/storage/
PUT    /api/plugins/proxbox/storage/{id}/
PATCH  /api/plugins/proxbox/storage/{id}/
DELETE /api/plugins/proxbox/storage/{id}/
```

!!! note "Upsert on POST"
    POST requests are idempotent by `(cluster, name)`. If a storage record with the same cluster and name already exists, the POST updates it instead of returning a conflict error.

**Example — list all storage backends for a cluster:**

```bash
curl -H "Authorization: Token <token>" \
     "http://netbox.example.com/api/plugins/proxbox/storage/?cluster__name=prod-cluster"
```

**Example — filter for enabled shared storage:**

```bash
curl -H "Authorization: Token <token>" \
     "http://netbox.example.com/api/plugins/proxbox/storage/?enabled=true&shared=true"
```

**Filterable fields:** `id`, `cluster`, `cluster__name`, `name`, `storage_type`, `content`, `path`, `nodes`, `shared`, `enabled`, `server`, `port`, `format`, `datastore`, `pool`

**Searchable fields (`?q=`):** `name`, cluster name, `path`

**Sample response:**

```json
{
  "id": 1,
  "url": "/api/plugins/proxbox/storage/1/",
  "display": "local-lvm",
  "cluster": {
    "id": 5,
    "url": "/api/virtualization/clusters/5/",
    "display": "prod-cluster",
    "name": "prod-cluster"
  },
  "name": "local-lvm",
  "storage_type": "lvmthin",
  "content": "images,rootdir",
  "path": "",
  "nodes": "",
  "shared": false,
  "enabled": true,
  "server": "",
  "port": null,
  "username": "",
  "export": "",
  "share": "",
  "pool": "data",
  "monhost": "",
  "namespace": "",
  "datastore": "",
  "subdir": "",
  "mountpoint": "",
  "is_mountpoint": false,
  "preallocation": "",
  "format": "",
  "prune_backups": "",
  "max_protected_backups": null,
  "raw_config": {"thinpool": "data", "vgname": "pve"},
  "tags": [],
  "custom_fields": {},
  "created": "2026-01-01T00:00:00Z",
  "last_updated": "2026-04-01T00:00:00Z"
}
```

### Data Model

| Field | Type | Description |
|---|---|---|
| `cluster` | nested Cluster | NetBox `virtualization.Cluster` this storage belongs to |
| `name` | string | Storage ID in Proxmox |
| `storage_type` | string | Proxmox storage plugin type (e.g. `dir`, `lvmthin`, `nfs`, `cephfs`, `pbs`) |
| `content` | string | Comma-separated content types this storage holds (e.g. `images,iso,backup`) |
| `path` | string | Filesystem path (for `dir` type) |
| `nodes` | string | Comma-separated node names that can use this storage (empty = all nodes) |
| `shared` | boolean | Whether the storage is accessible from all nodes simultaneously |
| `enabled` | boolean | Whether the storage is currently enabled |
| `server` | string | Remote server hostname (NFS/CIFS/PBS/Ceph) |
| `port` | integer (nullable) | Remote server port |
| `username` | string | Remote auth username |
| `export` | string | NFS server export path |
| `share` | string | CIFS share name |
| `pool` | string | Ceph/RBD pool name |
| `monhost` | string | Ceph monitor host(s) |
| `namespace` | string | Ceph namespace |
| `datastore` | string | PBS datastore name |
| `subdir` | string | Subdirectory within the storage |
| `mountpoint` | string | Filesystem mount point |
| `is_mountpoint` | string (nullable) | Mountpoint flag string from Proxmox config |
| `preallocation` | string | Disk image preallocation mode |
| `format` | string | Default image format |
| `prune_backups` | string | Backup pruning policy string |
| `max_protected_backups` | integer (nullable) | Maximum number of protected backups |
| `raw_config` | object | Full raw storage configuration as returned by Proxmox |
