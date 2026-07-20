# Other Data Models

The plugin's main plugin-specific models are:

- `ProxmoxEndpoint`: Proxmox cluster or node credentials and connectivity settings (with per-endpoint sync overwrite flags and a Settings tab)
- `NetBoxEndpoint`: target NetBox API endpoint and token configuration (singleton)
- `FastAPIEndpoint`: `proxbox-api` backend connectivity settings (singleton). Since v0.0.15 the model exposes `use_https` (URL scheme) and `verify_ssl` (certificate verification) as **independent** boolean flags — `use_https=true, verify_ssl=false` is the supported combination for the `*-nginx` image with a self-signed mkcert certificate. See [Backend Setup](../installation/backend-setup.md) for the full combination table and migration `0038_fastapiendpoint_use_https.py` for the upgrade-path backfill.
- `ProxmoxCluster`: synchronized cluster metadata linked to NetBox `Cluster`
- `ProxmoxNode`: synchronized hypervisor node metadata linked to NetBox `Device`
- `ProxmoxMetricsInfluxDB`: InfluxDB metrics endpoint metadata for a Proxmox cluster, with token fields stored as `nms-secret:<uuid>` references instead of plaintext
- `ProxmoxStorage`: synchronized storage rows linked to NetBox clusters and virtual disks
- `VMBackup`: backup metadata for synchronized virtual machines
- `VMSnapshot`: snapshot metadata for synchronized virtual machines
- `VMTaskHistory`: archived Proxmox task history linked to virtual machines
- `BackupRoutine`: Proxmox vzdump backup schedule metadata with retention policies and scheduling
- `Replication`: Proxmox storage replication job metadata for virtual machines
- `ProxboxPluginSettings`: singleton-style plugin behavior toggles

These models are exposed through the plugin UI and plugin REST API using standard NetBox model views and viewsets.

## BackupRoutine Model

The `BackupRoutine` model tracks Proxmox vzdump backup schedules synchronized from Proxmox endpoints. Key fields include:

- **endpoint**: Link to the ProxmoxEndpoint this backup routine was discovered from
- **job_id**: Unique Proxmox job identifier (e.g., 'local:123')
- **enabled**: Whether this backup job is currently enabled
- **schedule**: Systemd calendar format schedule string (e.g., 'daily 04:00')
- **next_run**: Computed next scheduled run time
- **node**: Node to run backup on (null = all nodes)
- **storage**: Target storage for backup files
- **selection**: List of VMID values selected for this backup job
- **status**: Active or stale (stale routines no longer exist in Proxmox)

### Retention Fields

- `keep_last`: Number of last backups to retain
- `keep_daily`: Number of daily backups to retain
- `keep_weekly`: Number of weekly backups to retain
- `keep_monthly`: Number of monthly backups to retain
- `keep_yearly`: Number of yearly backups to retain
- `keep_all`: Retain all backups regardless of other retention settings

### Advanced Fields

- `bwlimit`: I/O bandwidth limit in KiB/s (0 = unlimited)
- `zstd`: Number of zstd compression threads (0 = auto)
- `io_workers`: Number of IO workers for parallel processing
- `fleecing`: Options for backup fleecing (VM only)
- `fleecing_storage`: Storage to use for fleecing operations
- `repeat_missed`: Run the job as soon as possible if missed while scheduler was not running
- `pbs_change_detection_mode`: PBS mode used to detect file changes for container backups
- `raw_config`: Full raw configuration from Proxmox API for reference

## Replication Model

The `Replication` model stores Proxmox storage replication metadata attached to NetBox VirtualMachines. Key fields include:

- **virtual_machine**: Link to the NetBox VirtualMachine
- **proxmox_node**: Target Proxmox node for replication
- **guest**: Guest ID (VM ID)
- **target**: Target node for replication
- **job_type**: Replication type (currently only "local")
- **schedule**: Replication schedule in systemd calendar format
- **rate**: Rate limit in MB/s
- **disable**: Flag to disable the replication entry
- **replication_id**: Unique replication job ID composed of guest ID and job number ('<GUEST>-<JOBNUM>')
