# Version 0.0.23

netbox-proxbox `0.0.23` pairs with a `proxbox-api`
guest-VM-interface writer build / next release (the `guest_os_model` VM
interface sync strategy),
alongside `proxmox-sdk 0.0.12` and `netbox-sdk 0.0.10`. NetBox compatibility is
unchanged: `4.5.8` through `4.6.99` (validated against `4.5.8`, `4.5.9`, and
`4.6.0` through `4.6.4`).

Current pairing: netbox-proxbox 0.0.23 <-> proxbox-api (guest-VM-interface writer build / next release) <-> proxmox-sdk 0.0.12 <-> netbox-sdk 0.0.10.

## Highlights

- **Dual VM interface sync (new standard).** Proxmox reports NICs as `net0`,
  `net1`; the QEMU guest agent reports OS names such as `ens18`, `eth0`.
  Previously the guest-agent name *renamed* the single core `VMInterface`, which
  was lossy and broke IP-to-interface matching for VMs whose OS names differ
  from the Proxmox config names. The new default keeps the Proxmox NIC as a
  core `virtualization.VMInterface` with its canonical name (`net0`) **and**
  records each guest-OS interface as a new `GuestVMInterface` plugin object,
  mapped **one-to-one** to the core interface by MAC address. Both point at the
  **same** `ipam.IPAddress` object through `GuestVMInterfaceAddress` — the IP is
  never duplicated.
- **New setting `vm_interface_sync_strategy`.** `guest_os_model` (the new
  default) enables the behavior above. `legacy_rename` reproduces the previous
  single-interface rename behavior and is retained for backward compatibility
  but **deprecated**; the `use_guest_agent_interface_name` toggle now applies
  only under `legacy_rename`.
- **New REST endpoints.** `/api/plugins/proxbox/guest-vm-interfaces/` and
  `/api/plugins/proxbox/guest-vm-interface-addresses/`, with list views,
  filters, and navigation under Virtualization.
- **Data-integrity guards.** `GuestVMInterface.vm_interface` is a one-to-one
  link with `SET_NULL` (guest inventory survives core-interface churn).
  `GuestVMInterfaceAddress` validation guarantees the linked IP is the same
  object assigned to the mapped core interface (or, for agent-only interfaces,
  on the same virtual machine), preventing cross-VM or foreign-object IP links.

## Compatibility and upgrade notes

| NetBox  | netbox-proxbox | proxbox-api | netbox-sdk | proxmox-sdk |
|---------|----------------|-------------|------------|-------------|
| >=4.5.8 | v0.0.23 | guest-VM-interface writer build / next release | v0.0.10 | v0.0.12 |
| >=4.5.8 | v0.0.22 | v0.0.19.post5 | v0.0.10 | v0.0.12 |

- **Backend requirement.** The `guest_os_model` behavior is populated by
  `proxbox-api` with the matching guest-VM-interface writer. Against an older
  backend, the core `VMInterface`/IP sync is unchanged and the guest objects are
  simply not written.
- **Upgrade behavior.** Migration `0059` is additive. **Existing installs**
  (detected by the presence of a configured Proxmox endpoint) are backfilled to
  `legacy_rename` so an upgrade never silently changes interface naming;
  operators opt into `guest_os_model` explicitly. **Fresh installs** default to
  `guest_os_model`. This compatibility backfill is superseded by
  `0.0.23.post1`, whose migration `0060` switches existing `legacy_rename`
  settings to `guest_os_model` by default while leaving `legacy_rename`
  selectable as an opt-out.
- Addresses the long-standing "IP addresses not syncing / `net0` vs `ens18`"
  reports.
