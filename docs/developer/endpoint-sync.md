# Endpoint Data Exchange

This page explains how the `netbox-proxbox` plugin automatically keeps its endpoint configuration
in sync with the `proxbox-api` backend — covering the problem, the three delivery mechanisms,
the complete data flow, and the security model.

---

## The Problem

The plugin and the backend are two **separate processes with separate databases**:

| System | Database | Endpoint Model |
|---|---|---|
| `netbox-proxbox` (Django plugin) | NetBox PostgreSQL | `NetBoxEndpoint`, `ProxmoxEndpoint`, `FastAPIEndpoint` (ORM models) |
| `proxbox-api` (FastAPI backend) | Local SQLite (`database.db`) | `NetBoxEndpoint`, `ProxmoxEndpoint` (SQLModel tables) |

When an operator registers a `NetBoxEndpoint` in the plugin's UI, that record lives only in
PostgreSQL. The backend needs its own copy in SQLite to open a NetBox API session — without it,
every SSE sync stage fails immediately:

```
ProxboxException: No NetBox endpoint found
detail: Please add a NetBox endpoint in the database
```

The same gap exists for `ProxmoxEndpoint`: the backend needs Proxmox credentials in its own
SQLite table before it can open a Proxmox session for sync stages.

---

## System Overview

```mermaid
flowchart TB
    subgraph Plugin["netbox-proxbox (Django / PostgreSQL)"]
        NB_EP["NetBoxEndpoint\n(ORM model)"]
        PX_EP["ProxmoxEndpoint\n(ORM model)"]
        FA_EP["FastAPIEndpoint\n(ORM model)"]
    end

    subgraph Backend["proxbox-api (FastAPI / SQLite)"]
        BE_NB["netboxendpoint table\n(SQLite)"]
        BE_PX["proxmoxendpoint table\n(SQLite)"]
        BE_KEY["apikey table\n(bcrypt hash)"]
    end

    subgraph SyncJob["ProxboxSyncJob (RQ worker)"]
        Preflight["_ensure_backend_endpoints()\npreflight push"]
        Stages["SSE sync stages\n(12 stages)"]
    end

    NB_EP -- "post_save signal\nsync_netbox_endpoint_to_backend()" --> BE_NB
    PX_EP -- "post_save signal\nsync_proxmox_endpoint_to_backend()" --> BE_PX
    FA_EP -- "post_save signal\nPOST /auth/register-key" --> BE_KEY

    Preflight -- "PUT/POST /netbox/endpoint" --> BE_NB
    Preflight -- "PUT/POST /proxmox/endpoints" --> BE_PX

    BE_NB --> Stages
    BE_PX --> Stages
    BE_KEY -. "X-Proxbox-API-Key\nvalidation" .-> Stages
```

---

## Delivery Mechanism 1 — `post_save` Signals

All three `post_save` signals fire whenever an operator saves an endpoint record through
the plugin's UI or REST API. Each signal is **best-effort**: it logs on failure but never
raises an exception, so a transient backend outage does not break the Django request.

### `FastAPIEndpoint` → API key registration

**File:** `netbox_proxbox/signals.py` — `ensure_fastapi_endpoint_token`

```mermaid
sequenceDiagram
    autonumber
    actor Op as Operator
    participant NB as NetBox UI
    participant Sig as Django Signal
    participant FA as FastAPIEndpoint (PostgreSQL)
    participant API as proxbox-api

    Op->>NB: Save FastAPIEndpoint
    NB->>FA: ORM save()
    FA-->>Sig: post_save fired
    Sig->>FA: Generate 48-byte token if missing
    Sig->>API: GET /auth/bootstrap-status
    API-->>Sig: { "needs_bootstrap": true }
    Sig->>API: POST /auth/register-key { "api_key": token }
    API-->>Sig: 201 Created
    Note over Sig,API: Token stored as bcrypt hash in apikey table
```

The auto-generated token is stored on `FastAPIEndpoint.token` in PostgreSQL and used as the
`X-Proxbox-API-Key` header on every subsequent backend request. If the backend already has a
key (`needs_bootstrap: false`), the registration step is skipped.

---

### `NetBoxEndpoint` → backend SQLite sync

**File:** `netbox_proxbox/signals.py` — `sync_netbox_endpoint_to_backend`  
**Shared function:** `netbox_proxbox/views/backend_sync.py` — `sync_netbox_endpoint_to_backend()`

```mermaid
sequenceDiagram
    autonumber
    actor Op as Operator
    participant NB as NetBox UI
    participant Sig as Django Signal
    participant NB_EP as NetBoxEndpoint (PostgreSQL)
    participant API as proxbox-api

    Op->>NB: Save NetBoxEndpoint
    NB->>NB_EP: ORM save()
    NB_EP-->>Sig: post_save fired
    Sig->>Sig: Resolve FastAPIEndpoint (singleton)
    Sig->>Sig: Build base_url + X-Proxbox-API-Key header
    Sig->>API: GET /netbox/endpoint
    API-->>Sig: [] (empty) or [{ id: 1, ... }]

    alt No existing entry
        Sig->>API: POST /netbox/endpoint { name, ip, port, token, ... }
        API-->>Sig: 201 Created
    else Entry exists (singleton PUT)
        Sig->>API: PUT /netbox/endpoint/1 { name, ip, port, token, ... }
        API-->>Sig: 200 OK
    end
    Note over API: Token encrypted at rest with Fernet (AES-128-CBC)
```

The payload contains the IP address, port, SSL flag, token version, and credential material.
On the backend, tokens are encrypted with Fernet before storage — see
[Security Model](#security-model) below.

---

### `ProxmoxEndpoint` → backend SQLite sync

**File:** `netbox_proxbox/signals.py` — `ensure_proxmox_endpoint_has_fastapi_token`  
**Shared function:** `netbox_proxbox/views/backend_sync.py` — `sync_proxmox_endpoint_to_backend()`

```mermaid
sequenceDiagram
    autonumber
    actor Op as Operator
    participant NB as NetBox UI
    participant Sig as Django Signal
    participant PX_EP as ProxmoxEndpoint (PostgreSQL)
    participant API as proxbox-api

    Op->>NB: Save ProxmoxEndpoint
    NB->>PX_EP: ORM save()
    PX_EP-->>Sig: post_save fired
    Sig->>Sig: Resolve FastAPIEndpoint (singleton)
    Sig->>Sig: Ensure FastAPIEndpoint has a token
    Sig->>API: POST /auth/register-key (if needed)

    Sig->>Sig: Build base_url + auth headers
    Sig->>API: GET /proxmox/endpoints
    API-->>Sig: list of existing entries

    alt No entry with matching name
        Sig->>API: POST /proxmox/endpoints { name, ip, port, credentials }
        API-->>Sig: 201 Created
    else Matching entry found
        Sig->>API: PUT /proxmox/endpoints/{id} { name, ip, port, credentials }
        API-->>Sig: 200 OK
    end
    Note over API: Password/token encrypted at rest with Fernet
```

The endpoint name uses the stable format `"{name} (nb:{pk})"` so that the same Proxmox cluster
registered under different NetBox PKs is treated as a distinct backend entry.

---

## Delivery Mechanism 2 — Sync Job Preflight

`post_save` signals are best-effort: if the backend was offline when an endpoint was first
saved, the push is silently lost. The **preflight step** in `ProxboxSyncJob.run()` closes
this gap by pushing all endpoint data immediately before any SSE stage starts — regardless
of whether the signals previously succeeded.

**File:** `netbox_proxbox/jobs.py` — `_ensure_backend_endpoints()`

```mermaid
flowchart TD
    A["ProxboxSyncJob.run() called"] --> B["_ensure_backend_endpoints()"]

    B --> C["get_fastapi_request_context()\n→ resolve backend URL + auth headers"]
    C --> D{Context found?}
    D -- No --> E["Log warning\n'No FastAPIEndpoint configured'"]
    E --> Z["Proceed with sync\n(best-effort — endpoint\nmight already exist)"]

    D -- Yes --> F["For each NetBoxEndpoint:\nsync_netbox_endpoint_to_backend()"]
    F --> G["For each ProxmoxEndpoint:\nsync_proxmox_endpoint_to_backend()\n(filtered by proxmox_endpoint_ids if scoped)"]
    G --> Z

    Z --> H["sync_cluster_and_nodes()\n(cluster/node sync — direct REST)"]
    H --> I["SSE stage loop\n(devices → ... → backup-routines)"]

    style E fill:#e65100,color:#fff
    style Z fill:#1565c0,color:#fff
    style I fill:#2e7d32,color:#fff
```

!!! note "Best-effort, never blocking"
    If `_ensure_backend_endpoints()` cannot reach the backend (network error, wrong URL), it
    logs a warning and returns without raising. The sync continues — a subsequent stage will
    fail with its own error if the endpoint is truly missing, giving the operator a clear
    log message.

### Full Sync Job Sequence

```mermaid
sequenceDiagram
    autonumber
    participant Op as Operator
    participant NB as NetBox UI / RQ
    participant Job as ProxboxSyncJob (RQ worker)
    participant API as proxbox-api

    Op->>NB: Trigger sync (UI button or schedule)
    NB->>Job: ProxboxSyncJob.enqueue(sync_types=["all"], proxmox_endpoint_ids=[1,2])
    Job->>Job: _claim_rq_sync_ownership() — prevent concurrent runs

    Note over Job,API: Preflight push (new)
    Job->>API: GET /netbox/endpoint
    API-->>Job: [] or [existing]
    Job->>API: POST/PUT /netbox/endpoint (NetBoxEndpoint data)
    Job->>API: GET /proxmox/endpoints
    API-->>Job: existing list
    Job->>API: POST/PUT /proxmox/endpoints/... (for each ProxmoxEndpoint)

    Note over Job,API: Cluster/node sync (direct REST)
    loop for each Proxmox endpoint
        Job->>API: GET /proxmox/cluster/status
        API-->>Job: cluster data
        Job->>API: GET /proxmox/nodes/
        API-->>Job: node list
        Job->>Job: Write ProxmoxCluster + ProxmoxNode to NetBox ORM
    end

    Note over Job,API: SSE stage pipeline
    loop for each stage in [devices, storage, vms, ...]
        Job->>API: GET /{stage}/stream (SSE)
        API-->>Job: event: step (progress)
        API-->>Job: event: complete ok=true
        Job->>Job: Write progress to NetBox Job log
    end

    Job->>NB: Job status = completed
```

---

## Delivery Mechanism 3 — Dashboard View Push

The existing `sync_proxmox_endpoint_to_backend()` call from dashboard card views acts as a
third, opportunistic push — whenever an operator opens the Proxbox dashboard, the currently
selected Proxmox endpoint is pushed to the backend. This was the only push mechanism before
the preflight and `post_save` signal were added.

It remains in place as a zero-cost "refresh on view" that keeps credentials current even
when the operator edits a Proxmox endpoint and then immediately opens the dashboard without
triggering a full sync.

---

## Shared Push Functions

Both signals and the preflight delegate to two shared functions in
`netbox_proxbox/views/backend_sync.py`:

```python title="netbox_proxbox/views/backend_sync.py"
def sync_netbox_endpoint_to_backend(
    endpoint: NetBoxEndpoint,
    *,
    base_url: str,
    auth_headers: dict[str, str] | None = None,
    backend_verify_ssl: bool = True,
    timeout: int = 10,
) -> tuple[bool, str | None, int | None]:
    """GET /netbox/endpoint, then PUT (update) or POST (create). Returns (ok, error, http_status)."""

def sync_proxmox_endpoint_to_backend(
    endpoint: ProxmoxEndpoint,
    *,
    base_url: str,
    auth_headers: dict[str, str] | None = None,
    backend_verify_ssl: bool = True,
    timeout: int = 15,
) -> tuple[bool, str | None, int | None]:
    """GET /proxmox/endpoints, then PUT (update) or POST (create). Returns (ok, error, http_status)."""
```

Both functions follow the same pattern:

```mermaid
flowchart LR
    A["Call push function"] --> B["GET list endpoint\n(check existing)"]
    B --> C{Entry exists?}
    C -- No --> D["POST /endpoint\n(create)"]
    C -- Yes --> E["PUT /endpoint/{id}\n(update)"]
    D --> F["Return (True, None, None)"]
    E --> F
    B -- "error" --> G["Return (False, error_msg, http_status)"]
    D -- "error" --> G
    E -- "error" --> G
```

---

## Bootstrap Sequence (First-Time Setup)

When both systems start fresh (empty databases), the recommended setup order is:

```mermaid
sequenceDiagram
    autonumber
    actor Op as Operator
    participant NB as NetBox Plugin UI
    participant NBPG as NetBox PostgreSQL
    participant API as proxbox-api SQLite

    Note over Op,API: Step 1 — FastAPIEndpoint (connection to backend)
    Op->>NB: Create FastAPIEndpoint (IP/port of proxbox-api)
    NB->>NBPG: Save FastAPIEndpoint
    NBPG-->>NB: post_save signal
    NB->>API: POST /auth/register-key { api_key: <48-byte token> }
    API-->>NB: 201 — key stored as bcrypt hash

    Note over Op,API: Step 2 — NetBoxEndpoint (NetBox credentials for backend)
    Op->>NB: Create NetBoxEndpoint (this NetBox URL + token)
    NB->>NBPG: Save NetBoxEndpoint
    NBPG-->>NB: post_save signal
    NB->>API: POST /netbox/endpoint { ip, port, token }
    API-->>NB: 201 — token encrypted + stored in SQLite

    Note over Op,API: Step 3 — ProxmoxEndpoint (Proxmox VE credentials)
    Op->>NB: Create ProxmoxEndpoint (Proxmox IP + credentials)
    NB->>NBPG: Save ProxmoxEndpoint
    NBPG-->>NB: post_save signal (extended)
    NB->>API: POST /proxmox/endpoints { ip, port, username, password }
    API-->>NB: 201 — credentials encrypted + stored in SQLite

    Note over Op,API: Step 4 — Trigger sync
    Op->>NB: Click "Run Sync Now"
    NB->>API: Preflight: verify/update all endpoints
    NB->>API: GET /dcim/devices/create/stream (SSE)
    API-->>NB: event: complete ok=true
```

!!! tip "Order matters"
    Create the `FastAPIEndpoint` **first** so that the `post_save` signals for
    `NetBoxEndpoint` and `ProxmoxEndpoint` have an active backend connection to push to.
    If you create endpoints in a different order, the preflight at sync time will still
    push everything correctly — but you will see warnings in the NetBox log for the missed
    signal pushes.

---

## HTTP Status Code Propagation

Before this implementation, `run_sync_stream()` always returned HTTP `503` when a stage failed,
even when the backend returned `400` (missing endpoint). This caused unnecessary retries — the
plugin retries on `>= 500` only.

Now `_try_sync_stream_url()` returns the actual backend status code as a fourth tuple element,
and `run_sync_stream()` propagates it:

```python title="netbox_proxbox/services/backend_proxy.py (simplified)"
# Before: always fell through to 503
return { "detail": last_detail }, 503

# After: propagates actual backend status
return { "detail": last_detail }, last_http_status or 503
```

| Backend response | Old plugin status | New plugin status | Retry triggered? |
|---|---|---|---|
| `400` missing endpoint | `503` | `400` | Yes (wrong) → **No (correct)** |
| `401` invalid API key | `503` | `401` → auto-retry with new key | Handled separately |
| `502` bad gateway | `503` | `502` | Yes (unchanged) |
| `503` backend overloaded | `503` | `503` | Yes (unchanged) |

---

## Security Model

### Authentication between plugin and backend

All plugin → backend requests include:

```
X-Proxbox-API-Key: <48-byte URL-safe random token>
```

The token is auto-generated on `FastAPIEndpoint.save()` (via `secrets.token_urlsafe(48)`)
and registered with the backend as a **bcrypt hash** stored in the `apikey` SQLite table.
The plaintext token is never stored on the backend.

The backend's `APIKeyAuthMiddleware` validates the header on every non-exempt request.
Brute-force attempts are blocked by the `AuthLockout` table (5 attempts per IP in 300 s).

### Credential encryption on the backend

NetBox and Proxmox credentials stored in the backend's SQLite are encrypted at rest using
**Fernet (AES-128-CBC + HMAC-SHA256)** via the `cryptography` library:

```mermaid
flowchart LR
    A["Plugin: token = 'abc123'"] -->|"POST /netbox/endpoint"| B["Backend receives plaintext"]
    B --> C["set_encrypted_token(token)\n→ Fernet.encrypt()"]
    C --> D["Store as 'enc:...' in SQLite"]
    D -->|"Session open"| E["get_decrypted_token()\n→ Fernet.decrypt()"]
    E --> F["netbox-sdk session"]
```

The encryption key is resolved using the following priority chain:

1. **`PROXBOX_ENCRYPTION_KEY` environment variable** — set on the proxbox-api host (highest priority).
2. **`ProxboxPluginSettings.encryption_key`** — fetched from the NetBox plugin API via `settings_client.get_settings()` and configurable on the plugin settings page under **Encryption**.
3. **None** — credentials stored in plaintext; a `CRITICAL` warning is logged.

The raw key (from either source) is hashed with SHA-256 to derive exactly 32 bytes,
then base64url-encoded to form a valid Fernet key. If neither source is set, credentials
are stored in plaintext with a dev-mode warning logged.

### Token version support

`NetBoxEndpoint` supports both NetBox token formats:

| Version | Field | Backend payload |
|---|---|---|
| `v1` | `token.key` (FK to `users.Token`) | `token_version: "v1"`, `token: "<key>"` |
| `v2` | `token_key` + `token_secret` fields | `token_version: "v2"`, `token: "<secret>"`, `token_key: "<key>"` |

---

## Code Reference

| File | Role |
|---|---|
| `netbox_proxbox/signals.py` | `post_save` handlers for all three endpoint types |
| `netbox_proxbox/views/backend_sync.py` | Shared `sync_netbox_endpoint_to_backend()` and `sync_proxmox_endpoint_to_backend()` |
| `netbox_proxbox/jobs.py` | `_ensure_backend_endpoints()` preflight; `ProxboxSyncJob.run()` |
| `netbox_proxbox/services/backend_proxy.py` | `run_sync_stream()`, `_try_sync_stream_url()` (HTTP status propagation) |
| `netbox_proxbox/services/backend_context.py` | `get_fastapi_request_context()` — URL + auth header resolution |
| `proxbox_api/routes/netbox/__init__.py` | `POST/PUT /netbox/endpoint` (backend CRUD) |
| `proxbox_api/routes/proxmox/__init__.py` | `POST/PUT /proxmox/endpoints` (backend CRUD) |
| `proxbox_api/session/netbox.py` | `get_netbox_session()` — reads SQLite, raises on empty |
| `proxbox_api/database.py` | `NetBoxEndpoint`, `ProxmoxEndpoint` SQLModel tables |
| `proxbox_api/credentials.py` | Fernet encryption helpers |
| `proxbox_api/routes/auth.py` | `/auth/register-key`, `/auth/bootstrap-status` |
