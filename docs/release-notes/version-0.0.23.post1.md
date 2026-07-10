# Version 0.0.23.post1

netbox-proxbox `0.0.23.post1` pairs with a `proxbox-api`
guest-VM-interface writer build / next release, alongside
`proxmox-sdk 0.0.12` and `netbox-sdk 0.0.10`. NetBox compatibility is unchanged:
`4.5.8` through `4.6.99` (validated against `4.5.8`, `4.5.9`, and `4.6.0`
through `4.6.4`).

Current pairing: netbox-proxbox 0.0.23.post1 <-> proxbox-api (guest-VM-interface writer build / next release) <-> proxmox-sdk 0.0.12 <-> netbox-sdk 0.0.10.

## Compatibility and upgrade notes

| NetBox  | netbox-proxbox | proxbox-api | netbox-sdk | proxmox-sdk |
|---------|----------------|-------------|------------|-------------|
| >=4.5.8 | v0.0.23.post1 | guest-VM-interface writer build / next release | v0.0.10 | v0.0.12 |
| >=4.5.8 | v0.0.23 | guest-VM-interface writer build / next release | v0.0.10 | v0.0.12 |

`0.0.23.post1` makes `guest_os_model` the universal default for VM interface
sync, including existing installs. Migration `0060` supersedes the `0.0.23`
backward-compat backfill that had kept upgrades on `legacy_rename`.

This resolves the `net0`-vs-`ensX` interface-naming reports out-of-the-box on
upgrade. Proxmox `netX` interfaces stay named `netX`, and guest OS names are
stored in `GuestVMInterface` rows. `legacy_rename` remains a deprecated,
selectable opt-out in plugin settings. No other behavior change.

This is a documented, intentional behavior change on upgrade.
