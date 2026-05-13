# netbox-pbs

NetBox plugin that adds first-class read-only inventory for Proxmox Backup
Server (PBS): datastores, backup groups, snapshots, and job status.

This package is shipped from the same repository as `netbox-proxbox` but is
installed as a separate wheel (`netbox-pbs`). When both plugins are installed
the `netbox-proxbox` `VMBackup` model gains an optional cross-link to a PBS
snapshot; when only `netbox-pbs` is installed the plugin runs standalone.

## Status

Scaffold (PR C1 of issue
[emersonfelipesp/netbox-proxbox#325](https://github.com/emersonfelipesp/netbox-proxbox/issues/325)).
Domain models, sync jobs, and the optional `netbox-branching` integration land
in subsequent sub-PRs.

## Compatibility

- NetBox: 4.5.8 — 4.6.99
- Backend: `proxbox-api >= 0.0.11`
