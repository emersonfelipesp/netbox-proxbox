# `netbox_proxbox.views`

This directory implements the plugin's NetBox UI behavior.

## Files And Ownership

- [`__init__.py`](./__init__.py): top-level page views and re-exports for endpoint views, sync helpers, status checks, and backup views. Re-exports `sync_devices_stream`, `sync_virtual_machines_stream`, and `sync_full_update_stream`.
- [`sync.py`](./sync.py): HTTP endpoints that trigger backend sync operations over the FastAPI service. Provides two modes:
  - **POST polling**: `_request_backend_resource()` sends a POST to the FastAPI backend, waits for completion, and returns a single JSON `JsonResponse`.
  - **GET SSE streaming**: `_sync_stream_response()` creates a Django `StreamingHttpResponse` that proxies the backend's `text/event-stream` back to the browser in real time. Helper functions:
    - `_sse_error_frames(message)`: emits standardized `event: error` + `event: complete` SSE frames.
    - `_iter_backend_sse_lines(context, path)`: performs a streaming `requests.get(..., stream=True)` to the FastAPI backend and yields raw SSE lines. Includes fallback URL support and comprehensive error handling to avoid uncaught Django 500s.
    - `_sync_stream_response(request, path)`: builds the `StreamingHttpResponse` with `Cache-Control: no-cache` and `X-Accel-Buffering: no`. Note: `Connection: keep-alive` must not be set in Django/WSGI responses.
  - View functions: `sync_devices`, `sync_virtual_machines`, `sync_full_update`, `sync_vm_backups` (POST); `sync_devices_stream`, `sync_virtual_machines_stream`, `sync_full_update_stream` (GET SSE).
- [`keepalive_status.py`](./keepalive_status.py): health and reachability checks for FastAPI, remote NetBox, and Proxmox services.
- [`cards.py`](./cards.py): dashboard card hydration for Proxmox cluster/version data.
- [`vm_backup.py`](./vm_backup.py): CRUD list/detail/delete views and the VirtualMachine tab for `VMBackup`.
- [`sync_process.py`](./sync_process.py): CRUD list/detail/delete views for `SyncProcess`.
- [`external_pages.py`](./external_pages.py): redirect or informational external community pages.
- [`endpoints/`](./endpoints/): model views for the three endpoint models.

## Dependencies

- Inbound: `urls.py` routes here for all plugin UI behavior.
- Outbound: plugin models, forms, tables, filtersets, templates, `requests`, the external ProxBox FastAPI service, and `websocket_client.py`.

## Notes

- `sync.py`, `keepalive_status.py`, `cards.py`, and `websocket_client.py` together define the plugin's integration boundary with the external backend.
- `HomeView` is the main dashboard entrypoint and assembles endpoint lists plus derived backend URLs for the templates.
- Most changes to user-visible behavior land here first, then cascade into templates and JS.
- When adding or changing SSE stream endpoints, also update `urls.py`, `templates/netbox_proxbox/home.html` (button `data-sync-stream-url` attributes), `static/netbox_proxbox/js/home.js` (SSE parsing), and `tests/test_frontend_contracts.py`.

## Links

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
- Child: [`endpoints/CLAUDE.md`](./endpoints/CLAUDE.md)
