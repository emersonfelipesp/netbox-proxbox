# Replications

Proxbox synchronizes Proxmox storage replication job metadata into the plugin's `Replication` model. This feature enables tracking of VM replication jobs between Proxmox nodes.

## Overview

Replications represent Proxmox's storage replication jobs that replicate VM data between nodes. Proxbox discovers these from the Proxmox API and links them to their corresponding NetBox VirtualMachine records.

## Key Features

- **VM Association**: Each replication is linked to a NetBox VirtualMachine
- **Node Targeting**: Track which Proxmox node is the replication target
- **Schedule Tracking**: View replication schedules in systemd calendar format
- **Rate Limiting**: Configure and view replication rate limits in MB/s
- **Disable Control**: Flag to disable a replication entry without deleting it

## Sync Operations

Replications can be synced as part of a full update or individually:

1. **Full Update**: Includes replications in the comprehensive sync along with devices, storage, VMs, etc.
2. **Scheduled Sync**: Select "Replications" as a standalone sync type for periodic refresh
3. **Individual Sync**: Sync replications from a specific Proxmox endpoint

See [Scheduled Sync](./scheduled-sync.md) for details on configuring recurring sync jobs.

## UI Pages

- **Replications List**: Navigate to **Proxbox > Replications** to view all synced replications
- **Replication Detail**: Click on a replication to view its full configuration
- **VM Tab**: Replications also appear on the VirtualMachine detail page under the "Proxbox" tab
- **Sync Now Button**: Trigger an immediate sync of replications from the endpoint detail page

## API Endpoints

Replications are exposed through the plugin REST API:

- `/api/plugins/proxbox/replications/` — List and manage replication records
- Supports standard NetBox filtering, search, ordering, and pagination

## Model Fields

| Field | Description |
|-------|-------------|
| `virtual_machine` | Link to the NetBox VirtualMachine |
| `proxmox_node` | Target Proxmox node for replication |
| `replication_id` | Unique job ID: '<GUEST>-<JOBNUM>' (e.g., '100-1') |
| `guest` | Guest ID (VM ID) |
| `target` | Target node for replication |
| `job_type` | Replication type (currently only "local") |
| `schedule` | Replication schedule in systemd calendar format |
| `rate` | Rate limit in MB/s |
| `disable` | Flag to disable the replication entry |
| `comment` | Description of the replication job |
| `jobnum` | Unique sequential ID assigned to each job |
| `remove_job` | Mark replication job for removal ("local" or "full") |
| `source` | Source node (for internal use) |

## Operational Notes

- Replication sync requires a configured ProxmoxEndpoint
- The plugin imports replication metadata only. It does not trigger or manage replication execution.
- For recurring replication refresh, use [Scheduled Sync](./scheduled-sync.md)
- The replication ID combines the guest ID and job number for unique identification
- Replications are automatically linked to their corresponding NetBox VirtualMachine records