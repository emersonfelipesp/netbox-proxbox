# `netbox_proxbox.services`

This directory contains service-layer modules for backend HTTP proxy, keepalive checks, schema caching, and sync coordination.

## Files And Ownership

- [`__init__.py`](./__init__.py): re-exports key service functions (`get_fastapi_request_context`, `iter_backend_sse_lines`, `run_sync_stream`, `sse_error_frames`, `sync_full_update_resource`, `sync_resource`, `ServiceStatus`).
- [`backend_auth.py`](./backend_auth.py): token registration and bootstrap-status checks against the proxbox-api `/auth/` endpoints. Its HTTP budgets are **named module constants** (`BOOTSTRAP_STATUS_TIMEOUT`, `REGISTER_KEY_TIMEOUT`, `PREFLIGHT_READY_*`), not inline literals, because a cold backend spends its first seconds opening SQLite and resolving the NetBox OpenAPI schema — a 5-second budget failed at *exactly* 5.03 s while a later call to the same host answered in 3.78 s (netbox-proxbox issue #624). Timeouts are ceilings, not delays: a warm backend still answers well under a second. The `/health` probe inside `wait_for_backend_ready()` deliberately keeps its own short literal — it is a *retried* readiness poll, so a long budget there would stall the whole wait. Pinned by `tests/test_preflight_diagnosis.py`.
- [`backend_context.py`](./backend_context.py): defines `get_fastapi_request_context()` — resolves the active FastAPIEndpoint and builds the URL/header context used by all backend HTTP helpers.
- [`backend_proxy.py`](./backend_proxy.py): HTTP client helpers for proxbox-api,
  including SSE streaming (`run_sync_stream`, `iter_backend_sse_lines`), JSON
  requests (`sync_full_update_resource`, `sync_resource`), and operator
  bootstrap repair helpers for `GET /extras/bootstrap-status` and
  `POST /extras/custom-fields/reconcile`. Imports and re-exports
  `get_fastapi_request_context` from `backend_context.py`. **It is also the
  redaction producer for the sync-stream error path** — see below.
- [`backend_version.py`](./backend_version.py): parses proxbox-api versions and emits operator-facing advisories for known backend release windows, including VM IP sync fixes.
- [`endpoint_enabled.py`](./endpoint_enabled.py): shared `enabled=False` guard helpers for endpoint-like rows.
- [`endpoint_scope.py`](./endpoint_scope.py): shared helper that translates all enabled `ProxmoxEndpoint` rows to proxbox-api backend ids and returns `source=database` query params for multi-endpoint live reads.
- [`http_client.py`](./http_client.py): low-level HTTP client abstraction (session management, retries, timeout helpers) used by other service modules.
- [`individual_sync.py`](./individual_sync.py): per-object sync handlers called from `views/sync_now/` for cluster, node, storage, and VM objects. `sync_individual()` accepts an optional **`fastapi_endpoint_id`** and resolves its backend with `get_first_fastapi_context(endpoint_id=…)`, returning a 503 that names the selected id when that endpoint cannot be resolved; `sync_individual_with_dependencies()` and the internal `_sync_dependency()` forward it so every recursive dependent sync lands on the *same* proxbox-api. Pass the **id**, never a `fastapi_url` — the URL branch skips the resolved context's `verify_ssl` and would silently force TLS verification on. The selected-object batch sync path in `sync_stages.py::_run_batch_selected_sync()` pins it for exactly this reason: each per-object call resolves its own backend, so an unpinned call in a multi-backend install syncs against whichever row sorts first rather than the backend the job's preflight validated. The per-object views (`views/sync_now/`) leave it unset and keep the "first enabled backend" default.

  **`netbox_branch_schema_id` must be passed as an *argument*, not merely as a query param.** `_sync_dependency()` rebuilds each dependent call's params dict from scratch out of `_CONTEXT_KEYS`, and that tuple does **not** include `netbox_branch_schema_id` — so a schema id that travelled only inside `query_params` reaches the object itself and is then dropped for everything resolved off it. The object lands on the branch schema while its dependencies are written to **main**, which is a silent cross-schema write, not a failed one. `sync_individual_with_dependencies()` therefore takes the id explicitly and re-injects it on every recursive call, and `sync_stages.py::_run_batch_selected_sync()` sets **both** (`query_params["netbox_branch_schema_id"]` *and* the keyword) for the same reason. Pinned by `test_run_batch_selected_sync_passes_the_branch_schema_to_dependency_syncs`.

  **`proxmox_endpoint_ids` travels the same way, and dropping it is worse.** `sync_individual()` merges an optional `proxmox_endpoint_ids: str | None` into its outgoing `query_params`, and `sync_individual_with_dependencies()` / `_sync_dependency()` forward it recursively — again because `_CONTEXT_KEYS` omits it. The failure mode is not a *narrower* dependency sync, it is a **wider** one: proxbox-api resolves every `sync/individual/*` route's Proxmox sessions through `ProxmoxSessionsDep`, which reads a missing `proxmox_endpoint_ids` as "use every endpoint I hold" — including endpoints disabled in this NetBox. So a scope that reached the selected object but not its dependencies would resolve those dependencies against the *whole* backend estate. `sync_stages.py::_run_batch_selected_sync()` takes the resolved scope as keyword-only `proxmox_wire_endpoint_ids=` and sets both the query param and the argument; `jobs.py` resolves it with `sync_stages._batch_wire_endpoint_scope()` and refuses the run when nothing resolves. Pinned by `test_run_batch_selected_sync_passes_the_proxmox_scope_to_dependency_syncs`.
- [`openapi_schema.py`](./openapi_schema.py): OpenAPI schema caching and retrieval from the backend.
- [`service_status.py`](./service_status.py): `ServiceStatus` class and helpers for keepalive/health checks against FastAPI, NetBox, and Proxmox endpoints.
- [`sync_backup_routines.py`](./sync_backup_routines.py): sync coordination for backup routine inventory between NetBox and proxbox-api.
- [`sync_cluster.py`](./sync_cluster.py): sync coordination for cluster and node inventory.

## Dependencies

- Inbound: views, jobs, and API handlers call these service functions to interact with the backend.
- Outbound: `requests`, `netbox_proxbox.models`, `netbox_proxbox.schemas`, and the external proxbox-api FastAPI service.

## Multi-endpoint identity scoping (issue #563)

When more than one `ProxmoxEndpoint` exists, every backend read/sync call MUST be
scoped to a single endpoint, and the selector MUST be the endpoint's **stable
identity**, not its NetBox primary key:

- The backend (`proxbox-api`) assigns its **own** autoincrement endpoint ids and
  stores each pushed endpoint under the name produced by
  `views/backend_sync.py::proxmox_backend_name()` — `"<name> (nb:<pk>)"`, which
  embeds the NetBox pk. Plugin pk **!=** backend id in general.
- `views/backend_sync.py::resolve_backend_endpoint_id()` /
  `resolve_backend_endpoint_ids()` translate a plugin `ProxmoxEndpoint` to the
  backend database id by matching that name against `GET /proxmox/endpoints`.
  Disabled endpoints return before this backend request.
- `endpoint_scope.py::enabled_backend_endpoint_scope()` builds the common
  `source=database&proxmox_endpoint_ids=<backend ids>` scope for all enabled
  Proxmox endpoints. If no endpoints are enabled, callers should treat the
  operation as a successful no-op rather than performing an unscoped backend
  read.
- `sync_cluster.py` and `sync_vm_template.py` resolve the backend id first, then
  send `?proxmox_endpoint_ids=<backend_id>` to `/proxmox/cluster/status`,
  `/proxmox/nodes/`, `/proxmox/cluster/resources`, and `/proxmox/.../config`.
  Unresolved endpoints **fail loud** (result error) rather than syncing every
  endpoint's records into one.
- The SSE full-update path (`../sync_stages.py`) keeps plugin pks for plugin-side
  overwrite/sync-mode resolution but translates them to backend ids for the wire
  `proxmox_endpoint_ids` param via `_resolve_wire_endpoint_ids()`; an endpoint
  that does not resolve is skipped with a fail-loud `endpoint-scope` error stage.
- Dashboard card, endpoint status, and dashboard per-endpoint live reads also
  resolve the backend id via `resolve_backend_endpoint_id()` and send
  `?proxmox_endpoint_ids=<backend_id>` to proxbox-api. They do **not** fall back
  to `domain`/`ip_address` selectors, so duplicate Proxmox domains and stale
  backend endpoint rows cannot bind reads to the first matching session.
  `views/dashboard_data.py::build_local_node_rows` bounds its name fallback to
  `proxmox_cluster__endpoint=<this endpoint>`.

`schemas/proxmox_node.py::ProxmoxClusterStatusResponse` flattens the backend's
nested `node_list` (one cluster object per session) into top-level node records,
so `node_records` is populated for the real wire shape, not only flat payloads.

## Pinning the FastAPI backend: pass the id, never the URL

`sync_cluster_and_nodes()`, `sync_firewall()`, `sync_datacenter()`, and
`sync_vm_templates()` all accept `fastapi_endpoint_id: int | None = None` and
forward it as `get_fastapi_request_context(endpoint_id=fastapi_endpoint_id)`.
`ProxboxSyncJob` threads its already-selected backend pk into all four, so the
four **pre-SSE service passes** talk to the same `FastAPIEndpoint` row the
preflight validated and the SSE stages use. Without it each pass re-resolved
"first enabled row" independently, and on a host with two enabled backends a job
could preflight one and sync against another.

**Do not add a `fastapi_url` parameter instead.** Each of these functions already
has one, and it is a trap: the resolved context's `verify_ssl` is only read on
the branch where `fastapi_url` is falsy. Passing an explicit URL therefore takes
the branch that leaves `verify_ssl = True`, silently forcing certificate
verification on for operators who deliberately disabled it — a working sync
turns into an SSL error. The id parameter selects the row *through* the resolver,
so both the URL and the TLS setting come from the same place.

## Backend error text is redacted at the producer, not at each reader

Everything `run_sync_stream()` hands back on a failure ends up somewhere
long-lived and operator-readable: `sync_stages.py` json-dumps each SSE frame
into the NetBox **job log** via `on_frame`, and folds the failed payload into
the `RuntimeError` that becomes **`Job.error`**. Both are readable by anyone
with `view` on core `Job`. Meanwhile the sync **preflight** pushes the
`NetBoxEndpoint` API token and every `ProxmoxEndpoint` password/token into
proxbox-api — and a FastAPI **422** echoes the rejected request body back
verbatim in `detail[].input`. Left alone, that chain writes live credentials
into NetBox.

`backend_proxy.py` closes it at the **producer**, in two places:

- `_consume_sse_until_complete()` wraps every frame in `_redacted_mapping(data)`
  before calling `on_frame`.
- `run_sync_stream()` redacts the **whole payload mapping** whenever
  `status >= 400`, before returning. Redacting only `detail` is not enough: the
  `ok is False` branch also returns `"response": last_complete.model_dump()`,
  the raw `complete` frame including its unredacted `errors` list.

The **success** payload is deliberately left alone — it carries the sync
counters callers depend on, not error text.

Two consequences to preserve:

- **`_redacted_mapping()` must stay fail-closed.** If redaction ever returns a
  non-mapping, it wraps the *redacted* value (`{"detail": redacted}`), never the
  original. The one path that loses its shape would otherwise be the one path
  that leaks.
- **Redaction happens here, not in `sync_stages.py` / `sync_types.py`.**
  Redaction lives in `views/error_utils.py`, and importing from
  `netbox_proxbox.views.*` drags in the heavy `views/__init__.py`. Neither
  `sync_stages.py` nor `sync_types.py` imports it today, and several tests
  path-load those modules against hand-built stubs — adding that import edge
  would break the harness. `backend_proxy.py` already imports `error_utils`, so
  putting it there costs no new edge and covers every downstream reader
  (including the `str(payload)` fallbacks and `_format_stage_sync_error()`).

Redaction is key-based and shape-preserving, so the two **substring markers**
downstream code branches on both survive it: `"init_ok"`
(`sync_stages.py`, backend-not-ready detection) and `"remaining connection slots
are reserved for roles with the superuser attribute"` (`sync_types.py`,
Postgres-overload explanation). Neither is a credential assignment, and
`_SENSITIVE_ASSIGNMENT_RE` requires a `[:=]` separator. Guarded by the
redaction section of `tests/test_run_sync_stream.py`.

The one place the **raw** value is still read is the 401 auth-retry guard in
`_try_sync_stream_url()` (`"API key" in str(d)`) — control flow only; the value
is never logged.

## Notes

- `get_fastapi_request_context()` is defined in `backend_context.py` and re-exported by `backend_proxy.py`; import from either, but modify only `backend_context.py`.
- `get_fastapi_request_context()` and token-registration helpers must resolve only enabled `FastAPIEndpoint` rows. Disabled endpoint rows are visible inventory, not usable connection targets.
- `endpoint_enabled.py::disabled_endpoint_detail()` is the shared guard for status/openapi/backend-sync code that receives endpoint-like objects (`FastAPIEndpoint`, `NetBoxEndpoint`, `PBSEndpoint`, `PDMEndpoint`, companion `PBSServer`, etc.). Call it before the first HTTP request.
- Proxmox keepalive/status code should return `status="disabled"` for disabled `ProxmoxEndpoint` rows and must not push/sync the row to proxbox-api, resolve backend ids, or issue backend Proxmox reads. The list/detail/dashboard templates should avoid calling the keepalive route at all for disabled Proxmox rows.
- `backend_proxy.py` is the primary integration point for SSE streaming and JSON sync requests to proxbox-api.
- SSE streaming uses `requests.iter_lines()` with chunk delimiters and long read timeouts to handle long sync jobs.
- `ServiceStatus` aggregates endpoint health checks into a unified status for dashboard cards.

## Links

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
