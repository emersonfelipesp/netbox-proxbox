# VM Cloud-Init Data Model

`ProxmoxVMCloudInit` mirrors the Proxmox cloud-init configuration of each synced QEMU virtual machine onto NetBox. The row is **read-only on the NetBox side** — Proxmox stays the source of truth. proxbox-api populates and refreshes it from `qm config <vmid>` on every sync that touches the VM.

## Shape

| Field | Type | Notes |
|---|---|---|
| `virtual_machine` | One-to-one → `virtualization.VirtualMachine` | Cascade-deletes with the VM. Reverse accessor is `vm.proxmox_cloudinit`. |
| `ciuser` | CharField (≤64) | Proxmox cloud-init user (`ciuser`). |
| `sshkeys` | TextField | Decoded SSH-key bundle (one key per line). Proxmox stores this URL-encoded; proxbox-api runs `urllib.parse.unquote` before writing. |
| `ipconfig0` | CharField (≤255) | First-NIC IP configuration string from Proxmox, e.g. `ip=dhcp` or `ip=10.0.0.5/24,gw=10.0.0.1`. |
| `sshkeys_truncated` | BooleanField | `True` when proxbox-api truncated the `sshkeys` payload because the decoded blob exceeded **10 KB**. |
| `last_synced` | DateTimeField | `auto_now` timestamp updated on every reconciliation pass. |

The one-to-one constraint means at most one cloud-init row exists per VM. Deleting the VM removes the cloud-init row via `CASCADE`.

## UI Surface

- A dedicated **Cloud-Init** tab is rendered on the VM detail page **only when the row exists**. VMs with no Proxmox cloud-init record render an explicit empty-state message ("No Proxmox cloud-init record") so the tab does not falsely advertise data.
- The plugin home does **not** list cloud-init rows; they are accessed through the parent VM.

## REST API

The serializer is exposed at `plugins-api:netbox_proxbox-api:proxmoxvmcloudinit-list`:

- `GET /api/plugins/proxbox/vm-cloudinit/` — list rows; supports `?brief=1` to return only `id`, `url`, `display`, `virtual_machine`, `ciuser`.
- `POST /api/plugins/proxbox/vm-cloudinit/` — proxbox-api creates one row per QEMU VM during cloud-init reflection.
- `PATCH /api/plugins/proxbox/vm-cloudinit/<id>/` — proxbox-api refreshes individual fields on subsequent syncs.

The endpoint is the only sanctioned write path. NetBox operators should treat the rows as read-only and use Proxmox to edit cloud-init.

## Operator Visibility

Truncation is surfaced through `sshkeys_truncated`. When that flag is true, the UI banner indicates that the key bundle was clipped — operators should consult Proxmox for the authoritative payload rather than relying on the NetBox-side mirror.

## See Also

- [Virtual Machine](./virtual-machine.md) — parent VM model overview.
- [Sync Overwrite Flags](../configuration/sync-overwrite-flags.md) — `overwrite_vm_cloudinit` controls whether cloud-init reflection runs at all.
- Source: [`netbox_proxbox/models/vm_cloudinit.py`](https://github.com/netdevopsbr/netbox-proxbox/blob/main/netbox_proxbox/models/vm_cloudinit.py).
