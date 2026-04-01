# Storage

Proxbox synchronizes Proxmox storage definitions into the `ProxmoxStorage` model.

## Current Scope

- Storage rows are linked to NetBox clusters.
- Storage can be related to NetBox virtual disks through an explicit through table.
- Backup and snapshot records can point back to the originating Proxmox storage row.

## UI Coverage

The current plugin exposes storage list and detail pages, and storage sync can run on its own or as part of **Full Update**.
