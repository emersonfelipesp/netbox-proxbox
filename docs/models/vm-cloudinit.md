# VM Cloud-Init Data Model

`ProxmoxVMCloudInit` combines two related records for a QEMU virtual machine:
the latest cloud-init values reflected from Proxmox and the create-time intent
accepted by the NetBox API. Proxmox remains authoritative for reflected values;
intent and credential metadata are not overwritten by reflection syncs.

## Shape

| Field | Type | Notes |
|---|---|---|
| `virtual_machine` | One-to-one → `virtualization.VirtualMachine` | Parent VM. The reverse accessor is `vm.proxmox_cloudinit`. |
| `ciuser` | CharField (≤64) | Reflected Proxmox cloud-init user. |
| `sshkeys` | TextField | Reflected, decoded public SSH-key bundle. |
| `ipconfig0` | CharField (≤255) | Reflected first-NIC configuration, such as `ip=dhcp`. |
| `sshkeys_truncated` | BooleanField | Indicates that the reflected public-key bundle exceeded 10 KB and was clipped. |
| `is_intent` | BooleanField | Distinguishes create-time intent from a reflection-only row. |
| `hostname`, `search_domain`, `dns_servers` | CharField | Create-time guest naming and DNS intent. |
| `bridge`, `vlan_tag`, `gateway`, `ip_cidr` | Mixed | Create-time primary-NIC intent. |
| `ssh_pwauth` | Nullable BooleanField | Create-time password-login choice and OpenBao primary-selection input. |
| `enable_agent` | Nullable BooleanField | Create-time QEMU guest-agent choice. |
| `credential_reference_id` | Nullable PositiveIntegerField | Opaque external reference used only in explicit legacy storage mode. |
| `openbao_password_credential_uuid` | Nullable UUIDField | Internal durable reference to the OpenBao password credential; not directly writable through REST. |
| `openbao_keypair_credential_uuid` | Nullable UUIDField | Internal durable reference to the OpenBao SSH-keypair credential; not directly writable through REST. |
| `sshkeys_enc` | TextField | Locally encrypted create-time public-key bundle written through `sshkeys_intent`; never returned in cleartext. |
| `last_synced` | DateTimeField | Timestamp updated on reconciliation. |

The one-to-one constraint allows at most one row per VM. The public `sshkeys`
field is decoded after Proxmox reflection; `sshkeys_intent` is the separate
write-only create-time public-key input. Neither `sshkeys` nor `sshkeys_enc` is
password/private-key material, and neither is ever sent to the credential
provider.

## Login Credentials

When the selected credential backend is OpenBao, REST clients submit login
material only through the write-only `password` and `private_key` fields. The
response never returns those fields or either internal OpenBao UUID. The plugin
creates credentials of type `password` and `ssh-keypair`, respectively, and
assigns them to the parent NetBox VM with purpose `login`.

Primary selection follows the cloud-init policy:

- `ssh_pwauth=true` selects the password when one is configured.
- Otherwise, a configured SSH keypair is primary.
- A password remains primary when it is the only configured credential.

The owner row, parent VM, `ssh_pwauth`, both UUID references, assignments,
credentials, and policy are locked as one mutation graph. Stale owner state
fails closed before a provider write, and provider failures roll back database
changes. Direct UUID rebinding, unguarded bulk mutation, unsafe cascade, and a
storage downgrade while OpenBao ownership remains are rejected.

Clearing a write-only material field removes that row's UUID reference and its
owned VM assignment. Deleting the cloud-init row also removes only its owned
assignments. Credential records, provider material, foreign assignments, and
assignments on other VMs are retained so cleanup is safe for shared data.

## Storage Modes

OpenBao mode and legacy mode are intentionally disjoint:

- In OpenBao mode, `password` and `private_key` are accepted, while writes to
  `credential_reference_id` are rejected. Reads resolve only the selected
  OpenBao credential and never fall back to the opaque legacy reference.
  Missing credentials, provider absence, denied access, incompatible types,
  incomplete assignments, and unavailable material all fail closed.
- In explicit legacy mode, `credential_reference_id` is preserved unchanged as
  an opaque external identifier. Password and private-key input is rejected,
  and OpenBao UUIDs or owned assignments must be cleaned through the supported
  OpenBao path before downgrade.

Cross-store material migration is a separate feature owned through the
canonical Gitea workflow; changing the backend does not silently copy secrets.

## Secret-Free API Metadata

Responses expose only configuration and assignment state:

| Field | Meaning |
|---|---|
| `password_configured` | A password write is pending or a password reference is configured. |
| `private_key_configured` | A private-key write is pending or a keypair reference is configured. |
| `credential_assignment_ready` | The selected UUIDs have the complete expected enabled login-assignment and primary shape. |
| `credential_assignment_detail` | Secret-free readiness or failure explanation. |
| `credential_assignment_lookup` | Ansible-compatible selector containing `assigned_object_type=virtualization.virtualmachine`, the VM ID, and `purpose=login`. |
| `has_sshkeys` | A locally encrypted public-key intent bundle exists. |

These fields never resolve or serialize password/private-key material.

## UI Surface

- A dedicated **Cloud-Init** tab is rendered on the VM detail page only when
  the row exists. A missing row produces an explicit empty state.
- The plugin home does not list cloud-init rows; they are reached through the
  parent VM.
- `sshkeys_truncated=true` displays a warning that Proxmox remains the
  authoritative source for the clipped public-key bundle.

## REST API

The serializer is exposed at
`plugins-api:netbox_proxbox-api:proxmoxvmcloudinit-list`:

- `GET /api/plugins/proxbox/vm-cloudinit/` lists rows; `?brief=1` returns only
  `id`, `url`, `display`, `virtual_machine`, and `ciuser`.
- `POST /api/plugins/proxbox/vm-cloudinit/` creates reflection or intent rows.
  Authenticated credential writes require the corresponding object and
  netbox-openbao permissions.
- `PATCH /api/plugins/proxbox/vm-cloudinit/<id>/` updates supported reflection,
  intent, or write-only credential inputs through the outer provider boundary.
- `DELETE` and supported bulk deletion use the same outer boundary and
  assignment cleanup contract.

Proxbox-api remains the sanctioned producer for reflected fields. Clients that
create VM intent may use the documented intent and write-only fields; they must
not write internal UUID references directly.

## See Also

- [Virtual Machine](./virtual-machine.md) — parent VM model overview.
- [Sync Overwrite Flags](../configuration/sync-overwrite-flags.md) —
  `overwrite_vm_cloudinit` controls whether reflection runs.
- [OpenBao Companion](../companion-plugins/netbox-openbao.md) — credential
  backend and assignment operations.
- Source: [`netbox_proxbox/models/vm_cloudinit.py`](https://github.com/emersonfelipesp/netbox-proxbox/blob/develop/netbox_proxbox/models/vm_cloudinit.py).
