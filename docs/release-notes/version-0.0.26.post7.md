# Version 0.0.26.post7

## Canonical import path for VM list filter helpers

Export `get_proxbox_tagged_virtual_machines_queryset` and
`apply_virtual_machine_list_filters` from `netbox_proxbox.utils` (the package
`__init__`) so production imports resolve through the canonical package. The
unreachable peer `netbox_proxbox/utils.py` module was later removed to prevent
the package and module from claiming the same import name.

## Production deploy compatibility for VM list filters

Restores migration `0083_openbao_credential_storage.py` to the byte-identical
history already installed in production so package-first deploys pass the
migration-preservation gate. The OpenBao default change remains in migration
`0094_automatic_credential_storage_default`.

## Proxbox virtual machines list search and filtering

Current backend-runtime pairing: netbox-proxbox 0.0.26.post7 <-> proxbox-api 0.0.22 <-> proxmox-sdk 0.0.13 <-> netbox-sdk 0.0.13. This netbox-sdk version is proxbox-api's REST dependency only and does not provide the semantic MCP bridge.

This maintenance release ships NetBox-native search and filtering on the Proxbox virtual machines list. The page reuses `VirtualMachineFilterSet`, exposes the standard Results and Filters tabs, and keeps sync actions and pagination. The list and API views share the same proxbox-tagged queryset helper so filter behavior stays aligned.

No compatibility floor or ceiling changes in this release. NetBox `4.5.8` through official `4.7.0` GA remains supported.

| NetBox | netbox-proxbox | proxbox-api | netbox-sdk | proxmox-sdk |
|---|---|---|---|---|
| 4.5.8-4.7.0 GA | v0.0.26.post7 | v0.0.22 | v0.0.13 | v0.0.13 |
