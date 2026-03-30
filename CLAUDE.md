# netbox-proxbox Codebase Guide

## Pre-commit Checklist

**Before committing ANY change:**

1. Run syntax check: `python -m compileall netbox_proxbox tests`
2. Run linter: `rtk ruff check .`
3. Run tests: `rtk pytest tests/`

---

## Framework stack preference

Follow the same dependency order agents use (see [`AGENTS.md`](./AGENTS.md)):

1. **NetBox plugin layer** — Reuse this plugin’s established patterns and NetBox’s plugin APIs (registration, plugin paths, `NetBoxModel` / `NetBoxModelViewSet`, tables and filtersets consistent with other plugin code here).
2. **NetBox core** — Prefer `utilities.forms.fields`, `utilities.forms.widgets`, `utilities.views`, and other `utilities.*` / `netbox.*` primitives before inventing parallel implementations.
3. **Django** — Use `django.forms`, `django.http`, ORM, and related stdlib-backed APIs when NetBox does not offer a specific helper.

**Third-party packages:** Do not introduce new PyPI dependencies for capabilities NetBox or Django already cover. The project already declares `requests`, `websockets`, and optional CLI-related packages in [`pyproject.toml`](./pyproject.toml); add new deps only for integration needs that have no NetBox/Django path, not as shortcuts for UI or API patterns the core stack handles.

**Example:** NetBox may remove or rename widgets (for example legacy Select2 helpers under `utilities.forms.widgets`). Prefer current NetBox field/widget pairs such as `DynamicModelMultipleChoiceField` with API-driven multi-select rather than pulling in extra front-end or Python widget libraries. For form layout and field choices in this plugin, see [`netbox_proxbox/forms/CLAUDE.md`](./netbox_proxbox/forms/CLAUDE.md).

## Security and permissions

- **Registered CRUD** (via `register_model_view` and `netbox.views.generic`) inherits NetBox `ObjectPermissionRequiredMixin`: model permissions plus `queryset.restrict()` for object-level rules.
- **Custom views** should use `utilities.views.ConditionalLoginRequiredMixin` (respects `LOGIN_REQUIRED`) instead of Django’s unconditional `login_required`, and `TokenConditionalLoginRequiredMixin` where REST tokens should authenticate browser-style endpoints.
- **Operational endpoints** (sync, SSE streams, schedule job, WebSocket bridge): `ContentTypePermissionRequiredMixin` with permissions defined in [`netbox_proxbox/views/proxbox_access.py`](./netbox_proxbox/views/proxbox_access.py) — typically `change` on `FastAPIEndpoint` for backend sync, `add` on `SyncProcess` for queued jobs, `view` on `FastAPIEndpoint` for read-only WebSocket test UI.
- **Dashboard and JSON helpers**: plugin home requires at least one of `view` on `ProxmoxEndpoint` / `NetBoxEndpoint` / `FastAPIEndpoint` when the user is authenticated; endpoint lists use `.restrict(request.user, "view")`. Proxmox card and keepalive JSON resolve objects through restricted querysets (`get_object_or_404(...restrict(...))`). Tagged devices and VMs use `Device.objects.restrict` / `VirtualMachine.objects.restrict` before listing.
- **Plugin REST API** remains on `NetBoxModelViewSet` with standard NetBox/DRF permission classes.

---

This repository packages the `netbox_proxbox` NetBox plugin. The plugin adds endpoint inventory for Proxmox, NetBox, and the companion ProxBox FastAPI backend; UI pages for sync operations and status checks; REST API endpoints for those models; and a small amount of browser-side JavaScript and styling for the plugin pages.

The current plugin config lives in [`netbox_proxbox/__init__.py`](./netbox_proxbox/__init__.py). It declares plugin version `0.0.7` and NetBox compatibility `4.5.0` through `4.5.99`.

## Architecture Summary

- `ProxmoxEndpoint`, `NetBoxEndpoint`, `FastAPIEndpoint`, `SyncProcess`, and `VMBackup` are the plugin's main persisted models.
- NetBox UI routes live in [`netbox_proxbox/urls.py`](./netbox_proxbox/urls.py) and are implemented primarily in `netbox_proxbox/views/`.
- The plugin also exposes a NetBox plugin API under `netbox_proxbox/api/`, using serializers, filtersets, and standard `NetBoxModelViewSet` classes.
- Sync actions do not perform the sync themselves inside NetBox. They trigger work on the external ProxBox FastAPI service over HTTP. Two modes are supported:
  - **POST polling**: traditional request/response where the plugin waits for the backend to finish and returns a single JSON payload.
  - **GET SSE stream**: the plugin proxies the backend's `text/event-stream` response back to the browser as a Django `StreamingHttpResponse`. The browser parses SSE frames in real time via `EventSource`-style fetching and renders granular per-object progress. Stream endpoints are at `sync/<kind>/stream/`.
- Browser updates can flow over SSE streams or the existing WebSocket channel.
- Templates and static assets are conventional Django plugin assets under `netbox_proxbox/templates/` and `netbox_proxbox/static/`.

## Backend integration notes

- **Single FastAPI row:** HTTP and WebSocket helpers such as `get_fastapi_request_context()` in [`netbox_proxbox/services/backend_proxy.py`](./netbox_proxbox/services/backend_proxy.py), `websocket_client`, and several dashboard views resolve the backend via `FastAPIEndpoint.objects.first()` (or the first row from a restricted queryset). If multiple FastAPI endpoints exist, whichever row sorts first is used; plan automation and operator docs accordingly.
- **Background Proxbox sync jobs (RQ):** `ProxboxSyncJob` enqueues on the NetBox core Job queue **`netbox_proxbox.sync`** (plugin queue name `sync` under app `netbox_proxbox`). If jobs stay **pending**, ensure an RQ worker is running that consumes **`netbox_proxbox.sync`** (not only `high` or `default`). Jobs call proxbox-api **SSE** routes via [`run_sync_stream`](./netbox_proxbox/services/backend_proxy.py) until a terminal `complete` event (long read timeout), matching the browser stream proxy behavior.
- **RQ timeout vs HTTP stream:** NetBox’s default **`RQ_DEFAULT_TIMEOUT`** (often **300s** via `configuration.py`) applies to RQ jobs unless overridden. Long syncs were previously killed by RQ while `requests` was still reading the SSE body. The plugin sets a default **`job_timeout`** of **`PROXBOX_SYNC_JOB_TIMEOUT`** (7200s) in [`ProxboxSyncJob.enqueue`](./netbox_proxbox/jobs.py); pass a larger `job_timeout=` to `enqueue()` if needed. That is separate from the HTTP **between-chunk read** timeout (3600s) inside [`run_sync_stream`](./netbox_proxbox/services/backend_proxy.py).
- **When a job looks “stuck”:** On the core **Job** record, check **status**: **pending** means no worker is dequeuing `netbox_proxbox.sync`; **running** for a long time usually means proxbox-api is still syncing or the stream is slow/buffered; **errored** with **`JobTimeoutException`** means RQ’s wall-clock limit was hit—increase `job_timeout` or `PROXBOX_SYNC_JOB_TIMEOUT`. Inspect the job **log** and **error** fields before changing code.
- **Full update (UI vs jobs):** The plugin home may still use non-streaming helpers such as [`sync_full_update_resource`](./netbox_proxbox/services/backend_proxy.py) for JSON/redirect flows. Scheduled or immediate **Proxbox Sync** jobs use **`full-update/stream`** on proxbox-api (devices then VMs in one stream; no backups in that stream). Run a **VM backups** sync type when backups are required.

## How To Navigate

- Start with [`netbox_proxbox/CLAUDE.md`](./netbox_proxbox/CLAUDE.md) for the package-level map.
- Go to `models`, `views`, and `api` first when changing behavior.
- Use `forms`, `filtersets`, and `tables` when changing how plugin objects are edited or listed in NetBox.
- Use `templates` and `static` together when adjusting UI behavior, page structure, or browser-side interactions.
- Check `migrations` before changing any model field or constraint.
- For sync streaming changes, see `views/CLAUDE.md` (SSE proxy), `static/netbox_proxbox/js/CLAUDE.md` (browser SSE parsing), and `templates/netbox_proxbox/CLAUDE.md` (stream URL wiring).

## Index

- [`netbox_proxbox/CLAUDE.md`](./netbox_proxbox/CLAUDE.md)
- [`netbox_proxbox/api/CLAUDE.md`](./netbox_proxbox/api/CLAUDE.md)
- [`netbox_proxbox/forms/CLAUDE.md`](./netbox_proxbox/forms/CLAUDE.md)
- [`netbox_proxbox/migrations/CLAUDE.md`](./netbox_proxbox/migrations/CLAUDE.md)
- [`netbox_proxbox/models/CLAUDE.md`](./netbox_proxbox/models/CLAUDE.md)
- [`netbox_proxbox/static/CLAUDE.md`](./netbox_proxbox/static/CLAUDE.md)
- [`netbox_proxbox/static/netbox_proxbox/CLAUDE.md`](./netbox_proxbox/static/netbox_proxbox/CLAUDE.md)
- [`netbox_proxbox/static/netbox_proxbox/js/CLAUDE.md`](./netbox_proxbox/static/netbox_proxbox/js/CLAUDE.md)
- [`netbox_proxbox/static/netbox_proxbox/styles/CLAUDE.md`](./netbox_proxbox/static/netbox_proxbox/styles/CLAUDE.md)
- [`netbox_proxbox/tables/CLAUDE.md`](./netbox_proxbox/tables/CLAUDE.md)
- [`netbox_proxbox/templates/CLAUDE.md`](./netbox_proxbox/templates/CLAUDE.md)
- [`netbox_proxbox/templates/netbox_proxbox/CLAUDE.md`](./netbox_proxbox/templates/netbox_proxbox/CLAUDE.md)
- [`netbox_proxbox/templates/netbox_proxbox/base/CLAUDE.md`](./netbox_proxbox/templates/netbox_proxbox/base/CLAUDE.md)
- [`netbox_proxbox/templates/netbox_proxbox/fastapi/CLAUDE.md`](./netbox_proxbox/templates/netbox_proxbox/fastapi/CLAUDE.md)
- [`netbox_proxbox/templates/netbox_proxbox/home/CLAUDE.md`](./netbox_proxbox/templates/netbox_proxbox/home/CLAUDE.md)
- [`netbox_proxbox/templates/netbox_proxbox/partials/CLAUDE.md`](./netbox_proxbox/templates/netbox_proxbox/partials/CLAUDE.md)
- [`netbox_proxbox/templates/netbox_proxbox/proxmox/CLAUDE.md`](./netbox_proxbox/templates/netbox_proxbox/proxmox/CLAUDE.md)
- [`netbox_proxbox/templates/netbox_proxbox/table/CLAUDE.md`](./netbox_proxbox/templates/netbox_proxbox/table/CLAUDE.md)
- [`netbox_proxbox/templates/netbox_proxbox/test/CLAUDE.md`](./netbox_proxbox/templates/netbox_proxbox/test/CLAUDE.md)
- [`netbox_proxbox/views/CLAUDE.md`](./netbox_proxbox/views/CLAUDE.md)
- [`netbox_proxbox/views/endpoints/CLAUDE.md`](./netbox_proxbox/views/endpoints/CLAUDE.md)
- [`tests/CLAUDE.md`](./tests/CLAUDE.md)
