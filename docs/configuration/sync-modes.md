# Sync Mode Controls

Proxbox lets you decide **how** each Proxmox resource type is reflected into
NetBox by assigning one of three **sync modes** to it. Sync modes can be set
globally (via the plugin Settings page) or overridden per ProxmoxEndpoint —
the endpoint-level value always wins.

---

## The Three Modes

| Mode | Constant | Behaviour |
|------|----------|-----------|
| **Always** | `always` | Sync on every run. Objects are created, updated, and deleted as Proxmox changes. This is the default. |
| **Bootstrap only** | `bootstrap_only` | Sync the object **once** (on first discovery). After creation the object is tagged `bootstrap-only` in NetBox and subsequent sync runs leave it completely untouched — no patches, no deletes. |
| **Disabled** | `disabled` | Skip this resource type entirely. Already-synced objects are left as-is; no new objects are created and no existing objects are modified or removed. |

### Bootstrap-only tag

When a resource is first created under the `bootstrap_only` mode, Proxbox
automatically attaches the `bootstrap-only` tag (slug: `bootstrap-only`) to the
NetBox object. This tag is the sole signal that tells future sync runs to leave
the object alone.

- The tag is created automatically in NetBox during plugin bootstrap.
- You can manually **remove** the tag to allow Proxbox to resume normal syncing
  for that specific object.
- Never add this tag manually to objects you want to protect from sync — use a
  proper `disabled` or `bootstrap_only` endpoint/global setting instead.

---

## Resource Types

Nine resource types can be controlled:

| Setting field | Resource |
|---------------|----------|
| `sync_mode_vm` | Proxmox QEMU/LXC virtual machines (non-template) |
| `sync_mode_vm_template` | Proxmox VM templates (stored in `ProxmoxVMTemplate`, not `VirtualMachine`) |
| `sync_mode_vm_interface` | Interfaces discovered on Proxmox VMs |
| `sync_mode_mac` | MAC address reconciliation for VM interfaces |
| `sync_mode_cluster` | Proxmox cluster tracking rows |
| `sync_mode_node` | Proxmox node rows (DCIM devices) |
| `sync_mode_storage` | Proxmox storage pools |
| `sync_mode_ip_address` | IP addresses discovered from VM interfaces |
| `sync_mode_sdn` | Read-only Proxmox SDN inventory and EVPN/VXLAN NetBox mapping |

`sync_mode_sdn` is the exception to the normal default: it defaults to
`disabled`. Choosing **All** still includes the SDN stage in the dependency
order, but the stage is skipped until the effective SDN mode is `always` or
`bootstrap_only`.

---

## VM Templates

Proxmox templates (`template=True`) are a special case. They are **not** stored
as NetBox `virtualization.VirtualMachine` objects. Instead, Proxbox creates
dedicated `ProxmoxVMTemplate` records, which carry the full Proxmox configuration
snapshot plus optional relationships back to NetBox VMs:

- `source_vm` — the NetBox VM from which this template was originally created
  (optional FK, `SET_NULL`)
- `cloned_vms` — NetBox VMs that were cloned from this template
  (optional M2M)
- `cluster` — the Proxmox cluster the template lives in (optional FK)
- `node` — the Proxmox node hosting the template (optional FK)

The `sync_mode_vm_template` setting controls whether templates are synced at
all, while `sync_mode_vm` independently controls regular (non-template) VMs.
Setting `sync_mode_vm` to `disabled` does not disable template sync.

---

## Parent-to-child cascade

Sync modes are resolved to an **effective** mode before Proxbox decides which
stage to run or which backend query flags to forward. A resource becomes
effectively `disabled` when its own mode is `disabled` or any ancestor is
effectively `disabled`. Child resources never disable their parents.

```
cluster
└── node

vm + vm_template (both disabled only)
└── vm_interface
    ├── ip_address
    └── mac

sdn
```

The VM parent is a special case for network descendants: `vm_interface`,
`ip_address`, and `mac` inherit disabled only when both `sync_mode_vm` and
`sync_mode_vm_template` are `disabled`. Disabling only IP sync still allows VM
interfaces and MAC reconciliation to run; disabling only MAC sync still allows
interfaces and IP assignment to run.

---

## Priority: Endpoint vs Global

Settings resolve in this order:

```
ProxmoxEndpoint.sync_mode_<type>   ← takes priority (if set / not null)
        ↓ fallback
ProxboxPluginSettings.sync_mode_<type>   ← global default
```

When an endpoint-level field is left **blank** (null), the global setting
determines the effective mode. This lets you apply a global default while
selectively overriding individual endpoints.

---

## Configuration

### Global settings

Navigate to **Proxbox → Settings** and look for the **Sync Modes** section.
Each resource type has a dropdown with the three modes. Global defaults apply
to every endpoint that does not override the setting.

### Per-endpoint settings

Navigate to an existing **ProxmoxEndpoint** and open its **Settings** tab.
The same nine sync-mode dropdowns appear, but these fields are optional. Leave
them blank to inherit the global setting; choose a value to override it.

---

## Example configuration table

| Resource | Global | Endpoint A | Endpoint B | Effective for A | Effective for B |
|----------|--------|------------|------------|-----------------|-----------------|
| VM | `always` | _(blank)_ | `disabled` | `always` | `disabled` |
| VM template | `bootstrap_only` | `always` | _(blank)_ | `always` | `bootstrap_only` |
| VM interface | `always` | _(blank)_ | _(blank)_ | `always` | `always` |
| MAC | `always` | _(blank)_ | `disabled` | `always` | `disabled` |
| Cluster | `always` | _(blank)_ | _(blank)_ | `always` | `always` |
| Node | `disabled` | `always` | _(blank)_ | `always` | `disabled` |
| Storage | `always` | _(blank)_ | _(blank)_ | `always` | `always` |
| IP address | `always` | _(blank)_ | `disabled` | `always` | `disabled` |
| SDN | `disabled` | `always` | _(blank)_ | `always` | `disabled` |

---

## Checking the effective mode

The `ProxmoxEndpoint.effective_sync_mode(resource_type)` method resolves the
priority chain at runtime. You can call it from the NetBox shell:

```python
from netbox_proxbox.models import ProxmoxEndpoint
ep = ProxmoxEndpoint.objects.get(name="my-cluster")
ep.effective_sync_mode("vm")          # → "always"
ep.effective_sync_mode("vm_template") # → "bootstrap_only"
ep.effective_sync_mode("cluster")     # → "disabled"
```

Valid `resource_type` values: `vm`, `vm_template`, `vm_interface`, `mac`,
`cluster`, `node`, `storage`, `ip_address`, `sdn`.

---

## SDN behavior

SDN sync is read-only against Proxmox. When enabled, Proxbox calls the backend
`GET /proxmox/sdn/create/stream` stage after VM interfaces and VM IP addresses.
The stage collects controllers, zones, VNets, VNet subnets, fabrics, route
maps, prefix lists, node zone content, bridges, MAC-VRF, and IP-VRF rows.
Older Proxmox clusters that do not expose the SDN API are reported as skipped
warnings rather than failed jobs.

EVPN and VXLAN VNets are mapped to NetBox `vpn.L2VPN` records. EVPN
`rt-import` values create/update `ipam.RouteTarget` records and are assigned as
L2VPN import targets. Valid Proxmox subnet CIDRs create/update NetBox
`ipam.Prefix` records. When runtime rows expose an explicit NetBox target or
an unambiguous VLAN id, Proxbox creates `vpn.L2VPNTermination` records. If that
target already belongs to a different L2VPN, Proxbox records the conflict in an
SDN binding row and does not overwrite the manual assignment.

Proxmox-specific metadata, raw payloads, and bindings are stored in plugin SDN
inventory tables so operators can inspect unsupported or ambiguous rows without
Proxmox writes.

---

## FAQ

**Q: I set `sync_mode_vm_template` to `disabled` but templates still appear.**

A: If templates already existed in NetBox from a previous sync run, `disabled`
mode does not remove them — it only stops new syncs. Use NetBox bulk-delete to
clean up existing template records if needed.

**Q: Can I mix modes across endpoints?**

A: Yes. Each endpoint can independently set any combination of sync modes,
overriding the global defaults for that endpoint only.

**Q: What happens if I remove the `bootstrap-only` tag from an object?**

A: The object will be treated as a normal `always`-mode object on the next sync:
Proxbox will patch it to match the current Proxmox state.

**Q: Does `disabled` mode delete existing NetBox objects?**

A: No. `disabled` means "do nothing" — no creates, no updates, no deletes.
Existing objects remain in their current state.
