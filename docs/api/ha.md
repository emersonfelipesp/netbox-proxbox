# Cluster HA API

The plugin exposes a thin REST shim that proxies Proxmox cluster High-Availability data from the paired `proxbox-api` backend (≥ `0.0.12`). Both endpoints are **read-only**, fetched live on every request, and return the upstream JSON shape unchanged.

```
GET /api/plugins/proxbox/ha/summary/
GET /api/plugins/proxbox/ha/vm/{vmid}/
```

For common API conventions (authentication, pagination), see [API Overview](index.md). For UI-side behavior (HA tab and HA Status page) see [HA Status feature](../features/ha.md).

---

## Backend pairing

| Plugin path | Proxied to | Required `proxbox-api` |
|---|---|---|
| `GET /api/plugins/proxbox/ha/summary/` | `GET /proxmox/cluster/ha/summary` | ≥ `0.0.12` |
| `GET /api/plugins/proxbox/ha/vm/{vmid}/` | `GET /proxmox/cluster/ha/resources/by-vm/{vmid}` | ≥ `0.0.12` |

If the backend is older, both endpoints return **HTTP 503** with a body that explicitly tells the operator to upgrade `proxbox-api`. This mirrors the inline banner the UI surfaces in the same scenario.

---

## Permissions

Both endpoints reuse `_ProxboxDashboardPermission` — the same rule that gates the HTML HA pages (`/plugins/proxbox/ha/` and the per-VM HA tab). Anonymous access is honored only when `LOGIN_REQUIRED=False`; authenticated users need view rights on at least one of `ProxmoxEndpoint`, `NetBoxEndpoint`, or `FastAPIEndpoint` to access the dashboard surface.

The shim does **not** perform a NetBox `VirtualMachine` lookup for the per-VM endpoint — it forwards `{vmid}` straight to `proxbox-api`. The standard `virtualization.view_virtualmachine` permission still applies on the UI side because the HA tab itself is registered through NetBox's `register_model_view`.

---

## `GET /api/plugins/proxbox/ha/summary/`

**Example:**

```bash
curl -H "Authorization: Token <token>" \
     http://netbox.example.com/api/plugins/proxbox/ha/summary/
```

**Sample response (truncated):**

```json
{
  "nodes": [
    {"node": "pve-01", "online": true, "ha_state": "active", "quorum": 1}
  ],
  "groups": [
    {"group": "ha-default", "nodes": "pve-01,pve-02", "restricted": 0, "nofailback": 0}
  ],
  "resources": [
    {
      "sid": "vm:101",
      "type": "vm",
      "node": "pve-01",
      "group": "ha-default",
      "state": "started",
      "request_state": "started",
      "crm_state": "started",
      "max_relocate": 1,
      "max_restart": 1
    }
  ],
  "status": [
    {"id": "node:pve-01", "type": "node", "node": "pve-01", "status": "online", "quorate": 1}
  ]
}
```

The four arrays are filled by a single `asyncio.gather` fan-out on the backend, so the plugin issues **exactly one** HTTP request per render.

When the cluster has no HA configured, every array is empty (HTTP 200) — not 404.

---

## `GET /api/plugins/proxbox/ha/vm/{vmid}/`

**Example:**

```bash
curl -H "Authorization: Token <token>" \
     http://netbox.example.com/api/plugins/proxbox/ha/vm/101/
```

**Sample response (HA-managed VM):**

```json
{
  "sid": "vm:101",
  "type": "vm",
  "node": "pve-01",
  "group": "ha-default",
  "state": "started",
  "request_state": "started",
  "crm_state": "started",
  "max_relocate": 1,
  "max_restart": 1
}
```

**Sample response (unmanaged VM):**

```json
{}
```

The backend returns `null` for VMs that are not HA-managed; the shim normalizes `null` to an empty object so HTTP clients can rely on a JSON object response. The backend tries SID `vm:{vmid}` first and falls back to `ct:{vmid}`, so containers resolve through the same path.

---

## Per-VM tab gating

The corresponding **HA tab** on the `VirtualMachine` detail page only registers when the VM has a resolvable `proxmox_vm_id` custom field. If the field is absent or null, the tab is hidden — the REST endpoint still works, but there is no UI affordance until the VM has been synced through Proxbox at least once.

---

## Error responses

| Status | When |
|---|---|
| `200` | Normal upstream response (JSON forwarded unchanged). The per-VM endpoint also returns `200` with `{}` when the VM is not HA-managed. |
| `502` | Backend connection failure, non-OK upstream status (other than 404), non-JSON body, or any `requests.RequestException` (timeout, SSL error, DNS failure). Detail is built from `services._endpoint_errors.translate_request_exception`. |
| `503` | `FastAPIEndpoint` singleton is missing **or** the backend returned `404` on the HA path. The 404 case is treated as "backend too old" and the body carries the literal hint `Backend does not support HA endpoints — upgrade proxbox-api to v0.0.12 or later.` |

Per-call hard timeouts: `15s` on `/summary/` and `10s` on `/vm/{vmid}/`. Both elapse to `502` through `translate_request_exception`.

Each error response includes a `detail` string suitable for surfacing in the UI without further parsing.
