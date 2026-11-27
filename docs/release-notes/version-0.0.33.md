# Version 0.0.33

Version `0.0.33rc1` establishes stable Proxmox VE 9.3 guest UID identity and
pairs netbox-proxbox with proxbox-api `0.0.33`. Deploy and qualify proxbox-api
`0.0.33` before installing this plugin candidate. The paired backend pins
proxmox-sdk `0.0.16.post1`; netbox-sdk remains `0.0.13`.
The certified NetBox range remains `4.5.8` through `4.7.99`, including GA
`4.7.0`.

## Stable guest and cluster identity

Migration `0109_guest_uid_identity` adds `proxmox_vm_uid` and
`proxmox_cluster_uid` to VM sync state and adds `proxmox_cluster_uid` to the
Proxmox cluster model. Guest UIDs are 20-character lowercase base32 identifiers
matching `[a-z2-7]`. The new columns use empty-string database defaults, so
older application code remains safe during rollback.

A partial unique constraint protects each non-empty
`(proxmox_cluster_uid, proxmox_vm_uid)` pair. Filtersets, serializers, tables,
and templates expose the new identity. Serializer writes return HTTP 409 for a
conflicting UID pair instead of silently selecting the wrong guest. Cluster
synchronization records Proxmox VE's `cluster-id` when the server supplies it.

The duplicate-resolution chain now treats the UID pair as primary identity.
When either UID is unavailable, synchronization retains the legacy endpoint,
VMID, and guest-type chain. The name-collision and `duplicate_name_resolved`
contract is unchanged.

## Storage download host allowlist

`ProxboxPluginSettings.storage_download_allowed_hosts` adds an exact hostname
allowlist that backend consumers use for Proxmox ISO URL downloads. Downloads
use HTTPS port 443 only, and an empty list denies every download. Configure
only trusted vendor hosts that do not provide open redirects. The setting is
exposed in the plugin settings form, page, and REST serializer, which
normalizes and validates each hostname.

## Upgrade contract

This candidate adds exactly one migration: `0109_guest_uid_identity`. It
contains the guest and cluster UID fields and the storage download allowlist
field; the development-only `0110_storage_download_allowed_hosts` migration was
consolidated into it before publication. Every field operation is idempotent.
A development database that already applied both former migrations keeps a
consistent schema; its orphan `0110` recorder row is ignored. Deploy
proxbox-api `0.0.33` first, then install netbox-proxbox `0.0.33rc1`, run the
normal NetBox migration and static-asset steps, and restart all application and
worker processes.

The audited backend contract contains all 313 proxbox-api `0.0.33` HTTP
operations. Every literal plugin and CLI backend route resolves. Every query
parameter sent by proxbox-api to the audited plugin REST filtersets exists,
including `proxmox_vm_uid` and `proxmox_cluster_uid` on the VM sync-state
endpoint.
