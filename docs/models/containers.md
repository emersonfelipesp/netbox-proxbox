# Containers Data Model

Proxbox does not maintain a separate Django model for containers. LXC guests are synchronized into NetBox's `virtualization.VirtualMachine` model and then presented in a dedicated container-focused UI.

## What Distinguishes Containers

- Proxmox guest type is tracked in synchronized metadata.
- The plugin filters LXC guests into the **LXC Containers** page.
- Snapshots, backups, and task history still attach to the corresponding NetBox virtual machine record.
