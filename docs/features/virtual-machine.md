# Virtual Machine

The Proxbox plugin now separates Proxmox compute inventory into two dedicated views:

- **Virtual Machines**: renders only QEMU entries
- **LXC Containers**: renders only container entries

Both pages are sourced from NetBox `VirtualMachine` objects tagged by Proxbox.
They filter on `ProxboxVirtualMachineSyncState.proxmox_vm_type` (`qemu` or
`lxc`) and retain the native NetBox `virtual_machine_type` branch where that
field is available.

## Deleting several VMs from a cluster

On a NetBox cluster's **Virtual Machines** tab, select the VM rows and use
**Delete Selected** in the selected-row toolbar. Proxbox repairs the NetBox
4.5–4.7 child-view action declaration so this button targets NetBox's core
`VirtualMachine` bulk-delete endpoint. The normal delete permission,
confirmation page, changelog snapshots, transaction, and protected-object
checks still apply.

Do not use the cluster page's top-level **Delete** action to remove selected
VMs. That action deletes the cluster itself. Because
`VirtualMachine.cluster` is protected, NetBox correctly refuses the cluster
deletion and lists its VMs as dependent objects. This does not indicate that
the selected VMs cannot be deleted.

This operation deletes NetBox inventory records only. It does not delete the
corresponding QEMU or LXC workloads from Proxmox.

## Why the split exists

Proxmox reports QEMU and LXC resources under the same cluster resource inventory, but operationally they differ in runtime behavior and lifecycle. The split in the plugin mirrors that distinction while preserving one canonical VM model in NetBox.
