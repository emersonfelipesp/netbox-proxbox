# `netbox_proxbox.services`

This directory contains service-layer modules for backend HTTP proxy, keepalive checks, schema caching, and sync coordination.

## Files And Ownership

- [`__init__.py`](./__init__.py): lazily re-exports key service functions
  (`get_fastapi_request_context`, `iter_backend_sse_lines`, `run_sync_stream`,
  `sse_error_frames`, `sync_full_update_resource`, `sync_resource`,
  `ServiceStatus`). Keep this initializer import-light: pure URL/auth helpers
  must import `services.backend_key_adoption` without initializing Django or
  NetBox models.
- [`backend_auth.py`](./backend_auth.py): read-only stored-key verification and
  backend readiness checks against proxbox-api. The `PREFLIGHT_READY_*`
  constants provide a bounded cold-start allowance; the short `/health` probe
  is retried rather than given one long blocking timeout.
- [`backend_key_adoption.py`](./backend_key_adoption.py): fail-closed key state
  machine shared by model, form, API, signal, job, and management-command paths.
  It uses the bootstrap POST only for an explicitly retained candidate and only
  when the backend reports no keys; ordinary signal/job/status checks are
  read-only. Initialized backends must authenticate a candidate with one
  read-only `GET /auth/keys` request before encrypted persistence. All three
  adoption requests set `allow_redirects=False` so the API-key header or body
  cannot cross an origin through redirects. The service validates and
  canonicalizes the authority before the first request: URL userinfo/path/query/
  fragment syntax and malformed hosts are rejected, while IPv6 literals are
  emitted only as bracketed authorities. Its bootstrap/auth/register HTTP
  ceilings are named constants sized for a cold backend opening SQLite and
  resolving the NetBox OpenAPI schema; warm calls still return immediately.
- [`backend_context.py`](./backend_context.py): defines `get_fastapi_request_context()` — resolves the active FastAPIEndpoint and builds the URL/header context used by all backend HTTP helpers.
- [`backend_proxy.py`](./backend_proxy.py): HTTP client helpers for proxbox-api,
  including SSE streaming (`run_sync_stream`, `iter_backend_sse_lines`), JSON
  requests (`sync_full_update_resource`, `sync_resource`), and operator
  bootstrap repair helpers for `GET /extras/bootstrap-status` and
  `POST /extras/custom-fields/reconcile`. Imports and re-exports
  `get_fastapi_request_context` from `backend_context.py`. **It is also the
  redaction producer for the sync-stream error path** — see below. Every
  transport/OS exception that reaches a log, a stored `last_detail`, or an SSE
  error frame goes through either `extract_backend_error_detail()` or the
  module's `_safe_exception_text()` (class name + swept text) — never raw
  `str(exc)` and never `logger.exception`, whose traceback re-renders the raw
  message beside the redacted one. The same rule holds in `backend_auth.py`
  (the key-registration POST carries the API key in its body, so its failure
  messages are class-plus-swept before they reach job logs) and
  `views/cards.py` (logs the redacted detail, not the exception).
- [`backend_version.py`](./backend_version.py): parses proxbox-api versions and emits operator-facing advisories for known backend release windows, including VM IP sync fixes.
- [`endpoint_enabled.py`](./endpoint_enabled.py): shared `enabled=False` guard helpers for endpoint-like rows.
- [`endpoint_scope.py`](./endpoint_scope.py): shared helper that translates enabled `ProxmoxEndpoint` rows to proxbox-api backend ids and returns `source=database` query params for multi-endpoint live reads. `enabled_backend_endpoint_scope(endpoint_ids=…)` narrows the scope to specific plugin pks: `None` keeps the historic all-enabled scope, a non-empty list becomes a `pk__in` filter beside `enabled=True`, and an **empty list is "no scope", never "all"** — the backend reads a missing `proxmox_endpoint_ids` as "use every endpoint I hold", so widening an empty selection would send the widest request precisely when the caller asked for the narrowest. `sync_firewall()` and `sync_datacenter()` take the same `endpoint_ids` and forward it here, so a job launched against one endpoint no longer syncs every enabled endpoint's firewall objects and CPU models in its pre-SSE passes (`jobs.py` passes `endpoint_ids_to_sync`); stale marking in both passes runs per resolved endpoint, so a narrowed run leaves out-of-scope rows untouched. **The scope travels twice**: once to the backend as `proxmox_endpoint_ids`, and once locally as the allowed plugin-pk set (the keys of the resolved mapping) that both passes check before writing a response entry — a backend that ignores the query filter (older release, or a bug) returns every endpoint's clusters, and the by-cluster-name resolution would otherwise write rows for endpoints outside the run's selection. **A cluster name claimed by more than one endpoint is refused outright** in both passes' `_resolve_endpoint_by_cluster_name()`: cluster names are only unique *per endpoint*, so a response row naming only the cluster cannot be attributed when two endpoints both hold a `pve` — the old `.first()` guess wrote one estate's firewall/CPU data under the other, or let an out-of-scope row impersonate an in-scope endpoint through the shared name. Ambiguous never guesses (the batch path's rule), and the refusal is logged naming every claimant. Pinned by `tests/test_endpoint_scope.py`, the forwarding and out-of-scope-refusal tests in `tests/test_services_sync_firewall.py` / `tests/test_services_sync_datacenter.py` / `tests/test_datacenter_models.py`, and `test_run_scopes_firewall_and_datacenter_to_the_runs_endpoints` in `tests/test_jobs.py`.
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

## Credentialed requests never follow redirects, and a 401 retry is identity-bound

Every direct `requests.<verb>()` call in the **whole plugin** (not only this
package) sends `allow_redirects=False`; the one deliberate exception is
`github.py`, whose fetches are unauthenticated public content. This is enforced
structurally by `tests/test_outbound_redirect_policy.py`, which AST-scans every
module under `netbox_proxbox/` and fails on any call missing the literal
keyword — so a new call site written with the library default cannot silently
reopen the exfiltration class. Following a redirect would replay
`X-Proxbox-API-Key` (and, on the endpoint-push paths in
`views/backend_sync.py`, request bodies carrying the downstream NetBox and
Proxmox credentials) to whatever origin a compromised or misconfigured backend
names, including a plaintext-HTTP downgrade of the original host — a redirect
is evidence of an untrustworthy target, not a routing hint.

On top of the blanket no-follow rule, the proxy paths in this package — the
JSON helpers (`request_backend_json`, `request_backend_resource`), the
SSE/stream paths (`run_sync_stream` / `_try_sync_stream_url`,
`iter_backend_sse_lines`), and the readiness probe in `backend_auth.py` — also
treat **any 3xx as a terminal transport failure**: the response is closed
unread, the fixed detail `"ProxBox backend redirects are not permitted."` is
returned (HTTP 502 on the JSON/stream paths), and the redirect `Location` is
never dialled — not by the same candidate, and not by the IP fallback.
`RequestsHttpClient` enforces the same rule structurally via
`_checked_response()` / `HttpRedirectError`. Elsewhere a 3xx simply surfaces
through the call site's existing non-2xx error handling; with redirects
disabled the credential is never replayed either way.

The 401 auth-retry is bound to one endpoint identity end to end.
`backend_context.py::_handle_auth_registration_and_retry(context, *,
endpoint_id=None)` returns either **one complete, freshly resolved and
authenticated `BackendRequestContext`** or `None` to fail closed — never a bare
header mapping. On success the caller must **restart candidate selection from
the returned context** (fresh `http_url`, `ip_address_url`, `headers`,
`verify_ssl`), so fresh credentials can never be combined with a stale URL and a
stale key is never replayed against a rotated endpoint. The helper refuses a
caller/context endpoint-id mismatch before resolving anything, re-authenticates
the exact URL/key pair via
`backend_auth.py::authenticate_backend_request_context()`, and confirms with
`_request_context_binding()` that the endpoint's full authority tuple
(endpoint id, target fingerprint, URLs, TLS flag, headers) did not change while
the key was being checked. The retry stays bounded to one attempt per request
(`auth_register_attempted`).

Context construction is fingerprint-verified at the source:
`utils.get_fastapi_context()` recomputes the credential-free
`backend_key_target_fingerprint` — through a fresh IP FK read, before **and**
after the credential headers are built — and returns `None` on any drift or
recomputation error, so a stale `select_related` IP row cannot authenticate the
previous address or persist its fingerprint against a newly selected one. The
emitted context carries `endpoint_id` and `target_fingerprint` so downstream
retries can enforce the binding. Guarded end to end by
`tests/test_backend_proxy_credential_binding.py`.

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
- Never treat `POST /auth/register-key` HTTP 409 as key adoption. Rotation uses
  `adopt_rotated_backend_key()`, whose secret-safe failures preserve the prior
  encrypted value and whose proof binds the key to the exact URL and TLS target.
- `get_fastapi_request_context()` and stored-key verification helpers must resolve only enabled, target-adopted `FastAPIEndpoint` rows. Disabled, blank-fingerprint, and drifted-target rows are visible inventory, not usable connection targets.
- `endpoint_enabled.py::disabled_endpoint_detail()` is the shared guard for status/openapi/backend-sync code that receives endpoint-like objects (`FastAPIEndpoint`, `NetBoxEndpoint`, `PBSEndpoint`, `PDMEndpoint`, companion `PBSServer`, etc.). Call it before the first HTTP request.
- Proxmox keepalive/status code should return `status="disabled"` for disabled `ProxmoxEndpoint` rows and must not push/sync the row to proxbox-api, resolve backend ids, or issue backend Proxmox reads. The list/detail/dashboard templates should avoid calling the keepalive route at all for disabled Proxmox rows.
- `backend_proxy.py` is the primary integration point for SSE streaming and JSON sync requests to proxbox-api.
- SSE streaming uses `requests.iter_lines()` with chunk delimiters and long read timeouts to handle long sync jobs.
- `ServiceStatus` aggregates endpoint health checks into a unified status for dashboard cards.

## Links

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
