# Virtual Machine

The Proxbox plugin now separates Proxmox compute inventory into two dedicated views:

- **Virtual Machines**: renders only QEMU entries
- **LXC Containers**: renders only container entries

Both pages are sourced from NetBox `VirtualMachine` objects tagged by Proxbox and filtered by the custom field `proxmox_vm_type` (`qemu` or `lxc`).

## Why the split exists

Proxmox reports QEMU and LXC resources under the same cluster resource inventory, but operationally they differ in runtime behavior and lifecycle. The split in the plugin mirrors that distinction while preserving one canonical VM model in NetBox.