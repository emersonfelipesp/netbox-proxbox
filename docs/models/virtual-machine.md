# Virtual Machine Data Model

Proxbox stores synchronized compute inventory in NetBox's built-in `virtualization.VirtualMachine` model rather than a plugin-specific VM table.

## Current Behavior

- Proxmox QEMU guests and LXC containers are both represented as NetBox virtual machines.
- The plugin separates them in the UI by filtering on Proxbox-managed metadata such as guest type.
- Related plugin-side records include `VMBackup`, `VMSnapshot`, `VMTaskHistory`, and storage links through `ProxmoxStorage`.
- VM networking uses a dual model when `vm_interface_sync_strategy=guest_os_model`:
  Proxmox config NICs remain core `virtualization.VMInterface` rows with their
  canonical names (`net0`, `net1`), while QEMU guest-agent OS interfaces are
  stored as plugin `GuestVMInterface` rows (`ens18`, `eth0`). A
  `GuestVMInterface` links back to the core VM interface when the MAC address
  matches; it may also stand alone for agent-only interfaces such as bridges.
- `GuestVMInterfaceAddress` links a guest OS interface to an existing core
  `ipam.IPAddress`. It does not create duplicate IP rows; the IP object remains
  the same NetBox IP used by the core VM interface assignment.
- VMs that carry a resolvable `proxmox_vm_id` (custom field set during sync) gain a read-only **HA** tab on the detail page, sibling to **Proxmox Config**. The tab queries the paired `proxbox-api` and is hidden when the VM has not been synced through Proxbox. See [High Availability (HA)](../features/ha.md).

See [Virtual Machine](../features/virtual-machine.md) for the user-facing view split between VMs and containers.
