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

The tab resolves identity through the plugin's canonical typed VM resolver:

1. VM ID comes from `ProxboxVirtualMachineSyncState.proxmox_vm_id`.
2. Node prefers the VM's assigned NetBox device, then the sidecar's resolved
   `ProxmoxNode`, then `proxmox_node_name`. The existing description/snapshot
   compatibility hint remains available where the live config view needs it.
3. Type prefers `ProxboxVirtualMachineSyncState.proxmox_vm_type`, then the
   native `virtual_machine_type` slug, and defaults to `qemu`.

If the sidecar VM ID cannot be resolved, the tab tells the operator to run a
sync instead of attempting a backend call.

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
