# netbox-pbs

Standalone NetBox plugin for Proxmox Backup Server inventory reflected through
the `proxbox-api` `/pbs/*` endpoints.

The plugin can reuse `netbox-proxbox` FastAPI endpoint resolution when that
plugin is installed. Without `netbox-proxbox`, configure the fallback
`proxbox_api_url` and optional `proxbox_api_key` in PBS plugin settings.

## Included Models

- PBS servers
- PBS datastores
- PBS snapshots
- PBS jobs
- PBS plugin settings

## Sync Job

`PBSSyncJob` calls proxbox-api sync resources:

- `full`
- `datastores`
- `snapshots`
- `jobs`
- `node`

When NetBox branching support is available through `netbox-proxbox`, PBS sync
jobs can create a branch, run the backend sync against that branch schema, and
merge it back according to the plugin settings conflict policy.
