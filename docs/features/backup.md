# Backups & Proxmox Backup Server

Proxbox synchronizes Proxmox VM backup metadata into the plugin's `VMBackup` model.

## Current Scope

- Backup records are linked to NetBox virtual machines.
- Backup rows can also point back to synchronized `ProxmoxStorage` records.
- Backup sync can run on its own or as part of **Full Update**.

## Operational Notes

- The plugin imports backup inventory and metadata only. It does not trigger restore operations from NetBox.
- For recurring backup inventory refresh, use [Scheduled Sync](./scheduled-sync.md).
