# `netbox_proxbox.services`

This directory contains service-layer modules for backend HTTP proxy, keepalive checks, schema caching, and sync coordination.

## Files And Ownership

- [`__init__.py`](./__init__.py): re-exports key service functions (`get_fastapi_request_context`, `iter_backend_sse_lines`, `run_sync_stream`, `sse_error_frames`, `sync_full_update_resource`, `sync_resource`, `ServiceStatus`).
- [`backend_proxy.py`](./backend_proxy.py): HTTP client helpers for proxbox-api, including SSE streaming (`run_sync_stream`, `iter_backend_sse_lines`), JSON requests (`sync_full_update_resource`, `sync_resource`), and URL context resolution (`get_fastapi_request_context`).
- [`individual_sync.py`](./individual_sync.py): per-object sync handlers called from `views/sync_now/` for cluster, node, storage, and VM objects.
- [`openapi_schema.py`](./openapi_schema.py): OpenAPI schema caching and retrieval from the backend.
- [`service_status.py`](./service_status.py): `ServiceStatus` class and helpers for keepalive/health checks against FastAPI, NetBox, and Proxmox endpoints.
- [`sync_backup_routines.py`](./sync_backup_routines.py): sync coordination for backup routine inventory between NetBox and proxbox-api.
- [`sync_cluster.py`](./sync_cluster.py): sync coordination for cluster and node inventory.

## Dependencies

- Inbound: views, jobs, and API handlers call these service functions to interact with the backend.
- Outbound: `requests`, `netbox_proxbox.models`, `netbox_proxbox.schemas`, and the external proxbox-api FastAPI service.

## Notes

- `backend_proxy.py` is the primary integration point for all HTTP communication with proxbox-api.
- SSE streaming uses `requests.iter_lines()` with chunk delimiters and long read timeouts to handle long sync jobs.
- `ServiceStatus` aggregates endpoint health checks into a unified status for dashboard cards.

## Links

- Parent: [`../CLAUDE.md`](../CLAUDE.md)