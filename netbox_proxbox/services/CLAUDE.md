# `netbox_proxbox.services`

This directory contains service-layer modules for backend HTTP proxy, keepalive checks, schema caching, and sync coordination.

## Files And Ownership

- [`__init__.py`](./__init__.py): re-exports key service functions (`get_fastapi_request_context`, `iter_backend_sse_lines`, `run_sync_stream`, `sse_error_frames`, `sync_full_update_resource`, `sync_resource`, `ServiceStatus`).
- [`backend_auth.py`](./backend_auth.py): token registration and bootstrap-status checks against the proxbox-api `/auth/` endpoints.
- [`backend_context.py`](./backend_context.py): defines `get_fastapi_request_context()` — resolves the active FastAPIEndpoint and builds the URL/header context used by all backend HTTP helpers.
- [`backend_proxy.py`](./backend_proxy.py): HTTP client helpers for proxbox-api, including SSE streaming (`run_sync_stream`, `iter_backend_sse_lines`), JSON requests (`sync_full_update_resource`, `sync_resource`). Imports and re-exports `get_fastapi_request_context` from `backend_context.py`.
- [`backend_version.py`](./backend_version.py): parses proxbox-api versions and emits operator-facing advisories for known backend release windows, including VM IP sync fixes.
- [`http_client.py`](./http_client.py): low-level HTTP client abstraction (session management, retries, timeout helpers) used by other service modules.
- [`individual_sync.py`](./individual_sync.py): per-object sync handlers called from `views/sync_now/` for cluster, node, storage, and VM objects.
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
- `sync_cluster.py` and `sync_vm_template.py` resolve the backend id first, then
  send `?proxmox_endpoint_ids=<backend_id>` to `/proxmox/cluster/status`,
  `/proxmox/nodes/`, `/proxmox/cluster/resources`, and `/proxmox/.../config`.
  Unresolved endpoints **fail loud** (result error) rather than syncing every
  endpoint's records into one.
- The SSE full-update path (`../sync_stages.py`) keeps plugin pks for plugin-side
  overwrite/sync-mode resolution but translates them to backend ids for the wire
  `proxmox_endpoint_ids` param via `_resolve_wire_endpoint_ids()`; an endpoint
  that does not resolve is skipped with a fail-loud `endpoint-scope` error stage.
- Dashboards already scope live reads by `domain`/`ip_address` (endpoint-unique),
  so they need no pk translation; `views/dashboard_data.py::build_local_node_rows`
  bounds its name fallback to `proxmox_cluster__endpoint=<this endpoint>`.

`schemas/proxmox_node.py::ProxmoxClusterStatusResponse` flattens the backend's
nested `node_list` (one cluster object per session) into top-level node records,
so `node_records` is populated for the real wire shape, not only flat payloads.

## Notes

- `get_fastapi_request_context()` is defined in `backend_context.py` and re-exported by `backend_proxy.py`; import from either, but modify only `backend_context.py`.
- `backend_proxy.py` is the primary integration point for SSE streaming and JSON sync requests to proxbox-api.
- SSE streaming uses `requests.iter_lines()` with chunk delimiters and long read timeouts to handle long sync jobs.
- `ServiceStatus` aggregates endpoint health checks into a unified status for dashboard cards.

## Links

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
