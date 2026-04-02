# Virtual Machine Data Model

Proxbox stores synchronized compute inventory in NetBox's built-in `virtualization.VirtualMachine` model rather than a plugin-specific VM table.

## Current Behavior

- Proxmox QEMU guests and LXC containers are both represented as NetBox virtual machines.
- The plugin separates them in the UI by filtering on Proxbox-managed metadata such as guest type.
- Related plugin-side records include `VMBackup`, `VMSnapshot`, `VMTaskHistory`, and storage links through `ProxmoxStorage`.

See [Virtual Machine](../features/virtual-machine.md) for the user-facing view split between VMs and containers.
