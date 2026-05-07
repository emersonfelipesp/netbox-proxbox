# High Availability (HA)

netbox-proxbox surfaces Proxmox cluster High-Availability state directly inside NetBox so operators can answer "is this VM HA-managed and what's its current state?" without leaving the inventory UI.

There are two entry points:

- A **HA tab** on every `virtualization.VirtualMachine` detail page, scoped to that VM.
- A **HA Status** page (`/plugins/proxbox/ha/`) showing cluster-wide HA state — nodes, groups, and every HA-managed resource.

Both views are **read-only** and **fetched live** from the proxbox-api backend on every request. There is no NetBox-side caching, no persisted HA model, and no migration. Stop the proxbox-api service and the pages render an inline error banner instead of a 500.

## VM HA Tab

The tab appears next to **Proxmox Config** on each `VirtualMachine` detail page (slot weight `1400`).

When the VM has a resolvable Proxmox VM ID it issues:

```
GET /proxmox/cluster/ha/resources/by-vm/{vmid}
```

The backend tries SID `vm:{vmid}` first and falls back to `ct:{vmid}`, returning `null` (not 404) when neither is HA-managed. The tab renders:

- **HA managed** yes/no, group, current state, CRM state, request state, node.
- **Counters** — max-restart, max-relocate, failback.
- **Empty state** — "This VM is not HA-managed in Proxmox." with a link to the cluster page.

If the proxbox-api backend is too old to expose the HA endpoints (i.e. `< 0.0.11`), the tab surfaces a clear "upgrade proxbox-api to v0.0.11 or later" message.

## Cluster-wide HA Status Page

The **HA Status** menu entry under Proxbox routes to `/plugins/proxbox/ha/`. The view issues a single composed call:

```
GET /proxmox/cluster/ha/summary
```

The backend `summary` endpoint fans out four parallel HA reads via `asyncio.gather` and returns one envelope, so the plugin makes exactly one HTTP request per page render.

The page renders three sections:

- **Cluster Status** — node-level CRM state and quorum, derived from rows in `/cluster/ha/status/current` where `type == "node"`.
- **HA Groups** — table of HA group definitions (name, member nodes, restricted, nofailback).
- **HA Resources** — every HA-managed VM/CT (sid, group, current state, CRM state, max-restart, max-relocate). When a NetBox `VirtualMachine` exists with the matching `proxmox_vm_id` custom field, the SID column links to it.

When the cluster has no HA configured, each section renders an empty-state row instead of a missing table.

## Backend Paths

| Plugin view | Backend endpoint | Purpose |
|---|---|---|
| VM HA tab | `GET /proxmox/cluster/ha/resources/by-vm/{vmid}` | Single resource for one VM/CT (`null` if unmanaged) |
| HA Status page | `GET /proxmox/cluster/ha/summary` | Composed `{nodes, groups, resources, status}` envelope |

The plugin's REST shim that exposes both backend calls as JSON for non-HTML consumers is documented in [Cluster HA API](../api/ha.md).

## Permissions

- The VM HA tab uses NetBox's standard `virtualization.view_virtualmachine` permission and `restrict()` so users only see HA state for VMs they may view.
- The cluster page reuses the plugin's dashboard mixin chain (`ConditionalLoginRequiredMixin` + `RequireProxboxDashboardAccessMixin`), so it follows the same access rules as the rest of the Proxbox UI.

## Related Pages

- [Proxmox Config Tab](./proxmox-config-tab.md) — sibling tab on the same VM detail page.
- [Backend Logs](./backend-logs.md) — for diagnosing backend errors that surface in the HA banners.
- [API Integration](./api-integration.md) — backend authentication header used by both views.
