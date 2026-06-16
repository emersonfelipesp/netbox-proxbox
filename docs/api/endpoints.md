# Endpoint Configuration API

These three models define the connection targets for the systems Proxbox integrates: a Proxmox VE API server, a remote NetBox instance, and the Proxbox FastAPI backend. All three share a common base structure (name, IP address or domain, port, SSL verification) and inherit from `EndpointBase`.

For common API conventions (authentication, pagination, nested serializers), see [API Overview](index.md).

---

## Proxmox Endpoint

Stores connection credentials for a Proxmox VE API server.

```
GET    /api/plugins/proxbox/endpoints/proxmox/
GET    /api/plugins/proxbox/endpoints/proxmox/{id}/
POST   /api/plugins/proxbox/endpoints/proxmox/
PUT    /api/plugins/proxbox/endpoints/proxmox/{id}/
PATCH  /api/plugins/proxbox/endpoints/proxmox/{id}/
DELETE /api/plugins/proxbox/endpoints/proxmox/{id}/
```

**Example — list all Proxmox endpoints:**

```bash
curl -H "Authorization: Token <token>" \
     http://netbox.example.com/api/plugins/proxbox/endpoints/proxmox/
```

**Example — create a Proxmox endpoint using token auth:**

```bash
curl -X POST \
     -H "Authorization: Token <token>" \
     -H "Content-Type: application/json" \
     -d '{
       "name": "prod-proxmox",
       "domain": "proxmox.example.com",
       "port": 8006,
       "username": "root@pam",
       "token_name": "proxbox",
       "token_value": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
       "verify_ssl": false
     }' \
     http://netbox.example.com/api/plugins/proxbox/endpoints/proxmox/
```

**Example — filter by mode:**

```bash
curl -H "Authorization: Token <token>" \
     "http://netbox.example.com/api/plugins/proxbox/endpoints/proxmox/?mode=cluster"
```

**Filterable fields:** `id`, `name`, `domain`, `ip_address`, `mode`, `allowed_tenants`, `allowed_tenants_id`, `allowed_tenants__id__in`, `allowed_tenants__isnull`

**Searchable fields (`?q=`):** `name`, `domain`

**Sample response:**

```json
{
  "id": 1,
  "url": "/api/plugins/proxbox/endpoints/proxmox/1/",
  "display": "prod-proxmox (proxmox.example.com)",
  "name": "prod-proxmox",
  "ip_address": null,
  "domain": "proxmox.example.com",
  "port": 8006,
  "mode": {"value": "cluster", "label": "Cluster"},
  "version": "8.1.4",
  "repoid": "",
  "username": "root@pam",
  "token_name": "proxbox",
  "verify_ssl": false,
  "allowed_tenants": [],
  "tags": [],
  "custom_fields": {},
  "created": "2026-01-01T00:00:00Z",
  "last_updated": "2026-04-01T00:00:00Z"
}
```

!!! note "Write-only credentials"
    `password` and `token_value` are write-only. They are accepted on POST/PUT/PATCH but never returned in GET responses.

### Data Model

| Field | Type | Description |
|---|---|---|
| `name` | string | Display name for this Proxmox server |
| `ip_address` | nested IPAddress (nullable) | NetBox IPAddress object linked to this endpoint |
| `domain` | string (nullable) | FQDN, hostname, or `localhost` |
| `port` | integer | API port (default `8006`) |
| `mode` | choice | Deployment mode. Choices: `undefined`, `standalone`, `cluster` |
| `version` | string | Proxmox VE version string (set on sync) |
| `repoid` | string | Proxmox repository/release ID |
| `username` | string | Proxmox API username (default `root@pam`) |
| `password` | string (write-only) | Proxmox user password for auth |
| `token_name` | string | Proxmox API token name |
| `token_value` | string (write-only) | Proxmox API token secret |
| `verify_ssl` | boolean | Whether to verify the Proxmox TLS certificate (default `false`) |
| `allowed_tenants` | nested Tenant list | Tenant allow-list for NMS Cloud endpoint visibility. Empty means default/global visibility. |
| `allow_writes` | boolean | Gate for the operational verb routes on the paired `proxbox-api` (start/stop/snapshot/migrate). Defaults to `false`. When `false`, `proxbox-api` returns `403 {"reason": "writes_disabled_for_endpoint"}` for verb POSTs against this endpoint even with a valid API key and `X-Proxbox-Actor` header. Flip to `true` per-endpoint to opt that Proxmox cluster into write access. |

!!! warning "Validation"
    At least one of `domain` or `ip_address` must be provided. Omitting both returns a 400 error on both fields.

!!! tip "Operational verbs"
    `allow_writes` does **not** gate any of the read-side sync paths. It only controls the POST verb routes (`/proxmox/qemu/{vmid}/{start,stop,snapshot,migrate}` and the LXC equivalents) on the paired `proxbox-api`. See [Operational verbs design](../design/operational-verbs.md) and the [Endpoint Operations API](./operations.md).

### Tenant allow-list semantics

- `allowed_tenants=[]` means the endpoint remains in the default/global pool.
- Supplying one or more tenants makes the endpoint visible only to those
  tenants in tenant-scoped NMS Cloud flows.
- `PATCH {"allowed_tenants": []}` clears explicit grants and returns the
  endpoint to default/global visibility.
- When `nms-backend` resolves `X-Cloud-Tenant`, it keeps global/default
  endpoints visible only if the tenant has no explicit endpoint grants. As soon
  as one explicit match exists, the backend hides the global pool and returns
  only explicit matches.

---

## NetBox Endpoint

Stores connection details for a remote NetBox API instance that Proxbox synchronizes data into.

```
GET    /api/plugins/proxbox/endpoints/netbox/
GET    /api/plugins/proxbox/endpoints/netbox/{id}/
POST   /api/plugins/proxbox/endpoints/netbox/
PUT    /api/plugins/proxbox/endpoints/netbox/{id}/
PATCH  /api/plugins/proxbox/endpoints/netbox/{id}/
DELETE /api/plugins/proxbox/endpoints/netbox/{id}/
```

**Example — create a NetBox endpoint with v2 token:**

```bash
curl -X POST \
     -H "Authorization: Token <token>" \
     -H "Content-Type: application/json" \
     -d '{
       "name": "remote-netbox",
       "domain": "netbox.example.com",
       "port": 443,
       "verify_ssl": true,
       "token_version": "v2",
       "token_key": "my-key-id",
       "token_secret": "my-secret-value"
     }' \
     http://netbox.example.com/api/plugins/proxbox/endpoints/netbox/
```

**Example — filter by name:**

```bash
curl -H "Authorization: Token <token>" \
     "http://netbox.example.com/api/plugins/proxbox/endpoints/netbox/?name=remote-netbox"
```

**Filterable fields:** `id`, `name`, `domain`, `ip_address`

**Searchable fields (`?q=`):** `name`, `domain`

**Sample response:**

```json
{
  "id": 1,
  "url": "/api/plugins/proxbox/endpoints/netbox/1/",
  "display": "remote-netbox (netbox.example.com)",
  "name": "remote-netbox",
  "ip_address": null,
  "domain": "netbox.example.com",
  "port": 443,
  "token_version": {"value": "v2", "label": "v2 Token"},
  "token": null,
  "token_key": "my-key-id",
  "verify_ssl": true,
  "tags": [],
  "custom_fields": {},
  "created": "2026-01-01T00:00:00Z",
  "last_updated": "2026-04-01T00:00:00Z"
}
```

!!! note "Write-only credentials"
    `token_secret` is write-only and never returned in GET responses.

### Data Model

| Field | Type | Description |
|---|---|---|
| `name` | string | Display name for this remote NetBox instance |
| `ip_address` | nested IPAddress (nullable) | NetBox IPAddress object linked to this endpoint |
| `domain` | string (nullable) | FQDN, hostname, or `localhost` |
| `port` | integer | API port (default `443`) |
| `token_version` | choice | Authentication style. Choices: `v1`, `v2` |
| `token` | nested Token (nullable) | NetBox v1 Token FK — use for v1 plaintext tokens only |
| `token_key` | string | v2 token key (ID) |
| `token_secret` | string (write-only) | v2 token secret |
| `verify_ssl` | boolean | Whether to verify the remote NetBox TLS certificate (default `true`) |

!!! warning "Token version rules"
    - **v1**: Provide the `token` FK pointing to a NetBox `users.Token` with a readable plaintext value. Clear `token_key` and `token_secret`.
    - **v2**: Provide `token_key` and `token_secret` directly. Setting `token_version=v2` without both fields returns a 400 error. Do not use the `token` FK for v2 tokens — their secret is not retrievable from the DB.
    - At least one of `domain` or `ip_address` is required.

---

## FastAPI Endpoint

Stores the HTTP and WebSocket connection details for the Proxbox FastAPI backend service.

```
GET    /api/plugins/proxbox/endpoints/fastapi/
GET    /api/plugins/proxbox/endpoints/fastapi/{id}/
POST   /api/plugins/proxbox/endpoints/fastapi/
PUT    /api/plugins/proxbox/endpoints/fastapi/{id}/
PATCH  /api/plugins/proxbox/endpoints/fastapi/{id}/
DELETE /api/plugins/proxbox/endpoints/fastapi/{id}/
```

**Example — create a FastAPI endpoint:**

```bash
curl -X POST \
     -H "Authorization: Token <token>" \
     -H "Content-Type: application/json" \
     -d '{
       "name": "proxbox-backend",
       "domain": "proxbox-api.example.com",
       "port": 8800,
       "use_https": true,
       "verify_ssl": false,
       "use_websocket": true,
       "websocket_port": 8800
     }' \
     http://netbox.example.com/api/plugins/proxbox/endpoints/fastapi/
```

**Example — list all FastAPI endpoints:**

```bash
curl -H "Authorization: Token <token>" \
     http://netbox.example.com/api/plugins/proxbox/endpoints/fastapi/
```

**Filterable fields:** `id`, `name`, `domain`, `ip_address`

**Searchable fields (`?q=`):** `name`, `domain`

**Sample response:**

```json
{
  "id": 1,
  "url": "/api/plugins/proxbox/endpoints/fastapi/1/",
  "display": "proxbox-backend (proxbox-api.example.com)",
  "name": "proxbox-backend",
  "ip_address": null,
  "domain": "proxbox-api.example.com",
  "port": 8800,
  "use_https": true,
  "verify_ssl": false,
  "token": "a1b2c3d4e5f6...",
  "use_websocket": true,
  "websocket_domain": "",
  "websocket_port": 8800,
  "server_side_websocket": false,
  "tags": [],
  "custom_fields": {},
  "created": "2026-01-01T00:00:00Z",
  "last_updated": "2026-04-01T00:00:00Z"
}
```

!!! note "Auto-generated token"
    The `token` field is automatically generated via `secrets.token_urlsafe(48)` when a FastAPIEndpoint is saved without one. The token is registered with the Proxbox backend automatically. You do not need to set it manually.

### Data Model

| Field | Type | Description |
|---|---|---|
| `name` | string | Display name for this backend endpoint |
| `ip_address` | nested IPAddress (nullable) | NetBox IPAddress object linked to this endpoint |
| `domain` | string (nullable) | FQDN, hostname, or `localhost` |
| `port` | integer | HTTP API port (default `8800`) |
| `use_https` | boolean | URL scheme selector. `true` → `https://`, `false` → `http://`. Independent of `verify_ssl` since v0.0.15 (migration `0038`, [#352](https://github.com/emersonfelipesp/netbox-proxbox/issues/352)). See [Backend Setup → TLS combinations](../installation/backend-setup.md) and [v0.0.15 release notes](../release-notes/version-0.0.15.md). |
| `verify_ssl` | boolean | Whether to verify the backend TLS certificate. Only meaningful when `use_https=true`. |
| `token` | string (read-only) | Bearer token used to authenticate requests to the backend |
| `use_websocket` | boolean | Whether to use a WebSocket connection for streaming |
| `websocket_domain` | string | Override domain for WebSocket connections (defaults to `domain`) |
| `websocket_port` | integer | WebSocket port (default `8800`) |
| `server_side_websocket` | boolean | Whether the backend initiates the WebSocket connection |
