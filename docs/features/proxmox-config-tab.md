# Proxmox Config Tab

The **Proxmox Config** tab is a live read-only view of a virtual machine's current Proxmox configuration, embedded as a tab on each NetBox `VirtualMachine` detail page.

## What It Shows

The tab fetches the latest config payload directly from the proxbox-api backend via the configured `FastAPIEndpoint` and renders the parsed `ProxmoxVMConfig` schema for the VM. Both **QEMU** and **LXC** guests are supported.

Typical contents:

- VM name, VM ID, node, type (`qemu` or `lxc`)
- CPU and memory configuration
- Disks (with storage and size)
- Network interfaces (with VLAN/bridge mapping)
- Boot order and any guest-agent settings
- Any other key/value pairs returned by the Proxmox API

The data is **fetched live** from Proxmox on every page load — no NetBox-side caching is involved. Use the regular sync actions to persist any of these values into NetBox models.

## How It Resolves The VM

The tab determines which Proxmox VM to query using the following lookup order:

1. **`proxmox_vm_id` custom field** on the NetBox `VirtualMachine` (preferred).
2. Legacy `cf_proxmox_vm_id` custom field, if present.
3. `proxmox_node` / `node` custom field, falling back to a regex match against the VM `description` (`Synced from Proxmox node <name>`).
4. `virtual_machine_type` slug to pick `qemu` vs `lxc`; falls back to `proxmox_vm_type` custom field, defaulting to `qemu`.

If the VM ID cannot be resolved, the tab renders an explanatory message instead of attempting a backend call.

## Backend Path

When all values resolve, the tab issues a GET against the proxbox-api endpoint that proxies to:

```
GET /nodes/{node}/{qemu|lxc}/{vmid}/config?source=database
```

The plugin sends the configured backend authentication header (see [Authentication](../developer/authentication.md)) and validates the response payload against the `ProxmoxVMConfig` Pydantic schema before rendering. Validation errors are surfaced in the tab body so operators can see when Proxmox returned something unexpected.

## Permissions

The tab uses NetBox's standard `virtualization.view_virtualmachine` permission. The `get_queryset` method calls `VirtualMachine.objects.restrict(request.user, "view")` so users only see configs for VMs they are allowed to view.

## Related Pages

- [Virtual Machine](./virtual-machine.md) — sync actions that write Proxmox-derived values back into NetBox.
- [Synchronized Data](./synchronized-data.md) — what fields the regular sync stages persist.
- [Backend Logs](./backend-logs.md) — for diagnosing backend errors that show up in the tab body.
