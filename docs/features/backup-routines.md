# Backup Routines

Proxbox synchronizes Proxmox vzdump backup schedules (backup routines) into the plugin's `BackupRoutine` model. This feature enables tracking of scheduled backup jobs including their retention policies, scheduling, and advanced options.

## Overview

Backup routines represent Proxmox's scheduled backup jobs (vzdump). When enabled, Proxbox discovers these from the Proxmox API and stores them in NetBox for visibility and documentation purposes.

## Key Features

- **Schedule Tracking**: View backup schedules in systemd calendar format (e.g., 'daily 04:00')
- **Retention Policies**: Track how many backups to retain (last, daily, weekly, monthly, yearly)
- **Status Monitoring**: Active routines appear normally; routines that no longer exist in Proxmox are marked as "stale"
- **Node/Storage Links**: Associate backup routines with specific nodes and target storage
- **Advanced Options**: Bandwidth limits, zstd compression threads, fleecing options

## Sync Operations

Backup routines can be synced as part of a full update or individually:

1. **Full Update**: Includes backup routines in the comprehensive sync along with devices, storage, VMs, etc.
2. **Scheduled Sync**: Select "Backup Routines" as a standalone sync type for periodic refresh
3. **Individual Sync**: Sync backup routines from a specific Proxmox endpoint

See [Scheduled Sync](./scheduled-sync.md) for details on configuring recurring sync jobs.

## UI Pages

- **Backup Routines List**: Navigate to **Proxbox > Backup Routines** to view all synced routines
- **Backup Routine Detail**: Click on a routine to view its full configuration including retention settings
- **Sync Now Button**: Trigger an immediate sync of backup routines from the endpoint detail page

## API Endpoints

Backup routines are exposed through the plugin REST API:

- `/api/plugins/proxbox/backup-routines/` — List and manage backup routines
- Supports standard NetBox filtering, search, ordering, and pagination

## Model Fields

| Field | Description |
|-------|-------------|
| `endpoint` | ProxmoxEndpoint this backup routine was discovered from |
| `job_id` | Unique Proxmox job identifier (e.g., 'local:123') |
| `enabled` | Whether this backup job is currently enabled |
| `schedule` | Systemd calendar format schedule string |
| `next_run` | Computed next scheduled run time |
| `node` | Node to run backup on (null = all nodes) |
| `storage` | Target storage for backup files |
| `selection` | List of VMID values selected for this backup job |
| `status` | Active or stale (stale routines no longer exist in Proxmox) |

### Retention Fields

| Field | Description |
|-------|-------------|
| `keep_last` | Number of last backups to retain |
| `keep_daily` | Number of daily backups to retain |
| `keep_weekly` | Number of weekly backups to retain |
| `keep_monthly` | Number of monthly backups to retain |
| `keep_yearly` | Number of yearly backups to retain |
| `keep_all` | Retain all backups regardless of other retention settings |

### Advanced Fields

| Field | Description |
|-------|-------------|
| `bwlimit` | I/O bandwidth limit in KiB/s (0 = unlimited) |
| `zstd` | Number of zstd compression threads (0 = auto) |
| `io_workers` | Number of IO workers for parallel processing |
| `fleecing` | Options for backup fleecing (VM only) |
| `fleecing_storage` | Storage to use for fleecing operations |
| `repeat_missed` | Run job if missed while scheduler was not running |
| `pbs_change_detection_mode` | PBS mode for detecting file changes |
| `raw_config` | Full raw configuration from Proxmox API |

## Operational Notes

- Backup routine sync requires a configured ProxmoxEndpoint
- The plugin imports backup routine metadata only. It does not trigger or manage backup execution.
- For recurring backup routine refresh, use [Scheduled Sync](./scheduled-sync.md)
- Routines marked as "stale" indicate the backup job no longer exists in Proxmox