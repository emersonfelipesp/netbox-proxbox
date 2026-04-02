# Version 0.0.10

## Summary

Version 0.0.10 adds cluster and node inventory tracking (GitHub issue #308) and fixes the Mode field showing "undefined" on Proxmox endpoint detail pages.

## New Features

### Cluster and Node Tracking

Proxbox now discovers and stores Proxmox cluster topology alongside existing VM/container sync:

- **ProxmoxCluster model** — tracks cluster name, mode, quorum status, node count, and Proxmox VE version. Optionally links to a NetBox `virtualization.Cluster` object via a nullable FK.
- **ProxmoxNode model** — tracks each hypervisor node's online status, IP address, CPU usage, memory (used/total in bytes), uptime, and Proxmox-assigned node ID. Optionally links to a NetBox `dcim.Device` via a nullable FK.
- **Cluster & Nodes tab** — new tab on the ProxmoxEndpoint detail page showing a cluster summary card and a sortable node table with resource metrics.
- **Sync service** — `netbox_proxbox.services.sync_cluster.sync_cluster_and_nodes()` fetches data from `proxbox-api` and creates/updates/deletes cluster and node records in a single atomic transaction.
- **REST API** — `/api/plugins/proxbox/clusters/` and `/api/plugins/proxbox/nodes/` with filtering, search, and pagination.

### Mode Field Fix

The `Mode` field on the ProxmoxEndpoint detail page previously always displayed "undefined". It now:

- Shows a **green "Cluster"** badge when the endpoint belongs to a multi-node cluster.
- Shows a **blue "Standalone"** badge for single-node installations.
- Shows a **gray "Undefined"** badge only before the first sync, with a hint to run sync.
- Is updated automatically whenever `sync_cluster_and_nodes()` runs.

## Database Migrations

Migration `0016_proxmox_cluster_node_models` creates the `netbox_proxbox_proxmoxcluster` and `netbox_proxbox_proxmoxnode` tables.

Run after upgrading:

```bash
python manage.py migrate netbox_proxbox
```

## API Changes

Two new viewsets are registered:

| Route | ViewSet |
|---|---|
| `/api/plugins/proxbox/clusters/` | `ProxmoxClusterViewSet` |
| `/api/plugins/proxbox/nodes/` | `ProxmoxNodeViewSet` |

Both support standard NetBox filtering, search, ordering, and pagination.

## Compatibility

No change to existing compatibility: NetBox `4.5.0` – `4.5.99`.
