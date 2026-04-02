# Containers

LXC guests are synchronized into NetBox and shown through a dedicated **LXC Containers** page in the plugin UI.

## Current Behavior

- Containers share the same underlying NetBox `VirtualMachine` model as QEMU guests.
- The plugin distinguishes them using synchronized Proxmox guest-type metadata.
- Container inventory is included in VM-oriented sync flows and in **Full Update**.
