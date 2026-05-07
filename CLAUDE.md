# netbox-proxbox Codebase Guide

## Pre-commit Checklist

**Before committing ANY change:**

1. Run syntax check: `python -m compileall netbox_proxbox tests`
2. Run linter: `rtk ruff check .`
3. Run tests: `rtk pytest tests/`
4. Run type checker: `rtk ty check proxbox_cli`

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
- **Operational endpoints** (sync actions, schedule job, WebSocket bridge): `ContentTypePermissionRequiredMixin` with permissions defined in [`netbox_proxbox/views/proxbox_access.py`](./netbox_proxbox/views/proxbox_access.py) — typically `add` on core `Job` for queueing sync work, `delete` on core `Job` for cancel actions, and `view` on `FastAPIEndpoint` for read-only WebSocket test UI.
- **Dashboard and JSON helpers**: plugin home requires at least one of `view` on `ProxmoxEndpoint` / `NetBoxEndpoint` / `FastAPIEndpoint` when the user is authenticated; endpoint lists use `.restrict(request.user, "view")`. Proxmox card and keepalive JSON resolve objects through restricted querysets (`get_object_or_404(...restrict(...))`). Tagged devices and VMs use `Device.objects.restrict` / `VirtualMachine.objects.restrict` before listing.
- **Plugin REST API** remains on `NetBoxModelViewSet` with standard NetBox/DRF permission classes.

---

This repository packages the `netbox_proxbox` NetBox plugin. The plugin adds endpoint inventory for Proxmox, NetBox, and the companion ProxBox FastAPI backend; UI pages for sync operations, cluster summaries, status checks, and job actions; REST API endpoints for the core plugin models; and a small amount of browser-side JavaScript and styling for the plugin pages.

## Installation documentation truths

- The plugin supports both traditional host/venv NetBox deployments and Docker-based NetBox deployments (for example `netbox-community/netbox-docker`).
- Docker-based plugin installation docs are maintained at [`docs/installation/3-installing-plugin-docker.md`](./docs/installation/3-installing-plugin-docker.md), including `plugin_requirements.txt` and `configuration/plugins.py` usage.
- Backend Docker examples map host `8800` to container `8000` (`-p 8800:8000`) because the published `proxbox-api` image serves through nginx on container port `8000`.

The current plugin config lives in [`netbox_proxbox/__init__.py`](./netbox_proxbox/__init__.py). It declares plugin version `0.0.15` and NetBox compatibility `4.5.8` through `4.6.99` (certified simultaneously against `4.5.8`, `4.5.9`, and official `4.6.0`). The `0.0.15` release is certified with the separate `proxbox-api` backend release `0.0.11` (paired with the prior `0.0.14` / backend `0.0.10.post2`). `proxbox-api` is not a Python dependency of this plugin; the services communicate over HTTP.

## Architecture Summary

- `ProxmoxEndpoint`, `NetBoxEndpoint`, `FastAPIEndpoint`, `ProxmoxCluster`, `ProxmoxNode`, `ProxmoxStorage`, `BackupRoutine`, `Replication`, `VMBackup`, `VMSnapshot`, `VMTaskHistory`, and `ProxboxPluginSettings` are the plugin's main persisted models.
- **`NetBoxEndpoint` and `FastAPIEndpoint` are singletons** — the backend proxy and dashboard always use the first row of each, so only one should exist. Their bulk-import views enforce this by prompting for confirmation before replacing an existing record.
- NetBox UI routes live in [`netbox_proxbox/urls.py`](./netbox_proxbox/urls.py) and are implemented primarily in `netbox_proxbox/views/`.
- The plugin also exposes a NetBox plugin API under `netbox_proxbox/api/`, using serializers, filtersets, and standard `NetBoxModelViewSet` classes.
- Sync actions enqueue NetBox background jobs (`ProxboxSyncJob`) on NetBox's default RQ queue and call the external ProxBox FastAPI SSE endpoints to record progress/result on the Job row.
- The dashboard and Job detail pages are extended by template extensions so Proxbox jobs get run-now/cancel controls and live stream/log helpers.
- Browser updates can flow over SSE streams or the existing WebSocket channel.
- Templates and static assets are conventional Django plugin assets under `netbox_proxbox/templates/` and `netbox_proxbox/static/`.
- All three endpoint types support **CSV/JSON/YAML export** (safe and sensitive modes) and **bulk import** with IP auto-creation and id-stripping. See [`netbox_proxbox/views/endpoints/CLAUDE.md`](./netbox_proxbox/views/endpoints/CLAUDE.md).

## Backend integration notes

- **Single FastAPI row:** HTTP and WebSocket helpers such as `get_fastapi_request_context()` in [`netbox_proxbox/services/backend_proxy.py`](./netbox_proxbox/services/backend_proxy.py), `websocket_client`, and several dashboard views resolve the backend via `FastAPIEndpoint.objects.first()` (or the first row from a restricted queryset). If multiple FastAPI endpoints exist, whichever row sorts first is used; plan automation and operator docs accordingly.
- **Background Proxbox sync jobs (RQ):** `ProxboxSyncJob` enqueues on NetBox’s **`default`** RQ queue (`RQ_QUEUE_DEFAULT`) so a stock **`manage.py rqworker`** (no queue arguments) picks them up. NetBox’s default worker only listens to **`high`**, **`default`**, and **`low`**; the extra django-rq queue **`netbox_proxbox.sync`** is legacy only. Older Job rows may still show **`netbox_proxbox.sync`** in **Queue**; cancel/RQ lookup uses the stored name. Jobs call proxbox-api **SSE** via [`run_sync_stream`](./netbox_proxbox/services/backend_proxy.py) until a terminal `complete` event.
- **RQ timeout vs HTTP stream:** NetBox’s default **`RQ_DEFAULT_TIMEOUT`** (often **300s** via `configuration.py`) applies to RQ jobs unless overridden. Long syncs were previously killed by RQ while `requests` was still reading the SSE body. The plugin sets a default **`job_timeout`** of **`PROXBOX_SYNC_JOB_TIMEOUT`** (7200s) in [`ProxboxSyncJob.enqueue`](./netbox_proxbox/jobs.py); pass a larger `job_timeout=` to `enqueue()` if needed. That is separate from the HTTP **between-chunk read** timeout (3600s) inside [`run_sync_stream`](./netbox_proxbox/services/backend_proxy.py).
- **When a job looks “stuck”:** **pending** usually means **no RQ worker** is running (or it does not listen to **`default`**). **running** for a long time usually means proxbox-api is still syncing or the stream is slow/buffered; **errored** with **`JobTimeoutException`** means RQ’s wall-clock limit was hit—increase `job_timeout` or `PROXBOX_SYNC_JOB_TIMEOUT`. Inspect the job **log** and **error** fields before changing code.
- **Cancel on Job detail:** For Proxbox Sync rows in **pending**, **scheduled**, or **running** state, the plugin adds **Cancel job** (POST to `proxbox-cancel`). It requires **delete** permission on the core **Job** model, cancels or stops the linked RQ job when possible, then marks the NetBox job **failed** with a “Cancelled by user.” message. Stopping a **running** job is best-effort (RQ stop + long HTTP reads may not abort instantly).
- **Run now on Job detail:** Shown only when the job is in a **terminal** state (**completed**, **errored**, or **failed**), including after **Cancel** (failed). It is **not** shown for **pending**, **scheduled**, or **running**—use **Cancel** first if a queued run should be abandoned, then **Run now** on the finished row to queue a new sync with the same parameters.
- **Full update (UI vs jobs):** The plugin home may still use non-streaming helpers such as [`sync_full_update_resource`](./netbox_proxbox/services/backend_proxy.py) for JSON/redirect flows. Scheduled or immediate **Proxbox Sync** jobs use **`full-update/stream`** on proxbox-api and execute the full stage chain in one stream: devices, storage, virtual machines, virtual disks, backups, snapshots, network interfaces, IP addresses, VM interfaces, backup routines, and replications.

## Plugin settings and configuration

**Configuration policy — prefer DB-backed plugin settings.**
When adding a new runtime tunable that proxbox-api or this plugin needs to read,
default to making it a [`ProxboxPluginSettings`](./netbox_proxbox/models/plugin_settings.py)
field (NetBox-UI-editable, persisted in the NetBox database). On the proxbox-api side
it is read via `proxbox_api.runtime_settings.get_int / get_float / get_bool / get_str`,
which resolves **env var (override) → `ProxboxPluginSettings` → built-in default**
with a 5-minute settings cache.

Only fall back to a pure `.env` variable on the backend when the value is needed
**before** the NetBox connection exists or is **operator-only infrastructure** that
has no business in the UI: `PROXBOX_BIND_HOST`, `PROXBOX_RATE_LIMIT`,
`PROXBOX_ENCRYPTION_KEY` / `PROXBOX_ENCRYPTION_KEY_FILE`, `PROXBOX_STRICT_STARTUP`,
`PROXBOX_SKIP_NETBOX_BOOTSTRAP`, `PROXBOX_GENERATED_DIR`,
`PROXBOX_CORS_EXTRA_ORIGINS`. Anything that controls sync behavior, batching,
concurrency, caching, or feature toggles belongs in `ProxboxPluginSettings`.

Do **not** invent shadow config layers (parallel JSON/YAML files, ad-hoc dotenv
sections, module-level constants meant as overrides) to dodge the migration cost.
A new field touches all five wiring points — model, migration, form, serializer, and
template — and the existing fields plus migration
[`0037_pluginsettings_runtime_tunables.py`](./netbox_proxbox/migrations/0037_pluginsettings_runtime_tunables.py)
show the pattern (`SeparateDatabaseAndState` + `IF NOT EXISTS` for production-safe
additive schema changes).

## CI/CD Workflows

### E2E Docker workflow (`e2e-docker.yml`)

Accepts four main inputs:

| Input | Values | Default | Effect |
|-------|--------|---------|--------|
| `install_source` | `local`, `pypi`, `testpypi`, `container`, `both` | `both` | How netbox-proxbox is installed inside the NetBox container |
| `dependency_mode` | `dev`, `published`, `testpypi-package`, `pypi-package` | `dev` | How the separate proxbox-api container is built or installed |
| `proxbox_api_version` | version string | `PROXBOX_API_RELEASE_VERSION` fallback | Exact proxbox-api version for package-index E2E modes |
| `netbox_image` | full image ref | NetBox matrix | NetBox image override for focused runs |

**`dependency_mode: dev`** — clones `emersonfelipesp/proxbox-api` at HEAD and builds the `raw` Docker target locally. Use this for pre-publish E2E to verify against the latest source.

**`dependency_mode: published`** — pulls `emersonfelipesp/proxbox-api:<PROXBOX_API_RELEASE_VERSION>` from Docker Hub. Use this for post-publish E2E to verify the released image works end-to-end.

**`dependency_mode: testpypi-package`** — builds a temporary proxbox-api container by installing `proxbox-api==<proxbox_api_version>` from TestPyPI.

**`dependency_mode: pypi-package`** — builds a temporary proxbox-api container by installing `proxbox-api==<proxbox_api_version>` from PyPI.

### Release pipeline (`publish-testpypi.yml`)

```
prepare-release
├── TestPyPI lane
│   ├── publish-testpypi
│   ├── validate-testpypi
│   └── e2e-docker-testpypi (install_source=testpypi, dependency_mode=testpypi-package)
└── PyPI lane
    ├── validate-pypi-candidate
    ├── e2e-docker-pypi-candidate (install_source=local, dependency_mode=pypi-package)
    ├── publish-pypi
    ├── validate-pypi
    └── e2e-docker-pypi (install_source=pypi, dependency_mode=pypi-package)
```

Normal and `.postN` tag pushes publish to TestPyPI. `rcN` tag pushes, GitHub releases, and manual dispatch with `publish_target=pypi` publish to PyPI.

TestPyPI validation installs both `netbox-proxbox` and the configured `proxbox-api` from TestPyPI. PyPI candidate/final validation uses PyPI `proxbox-api` for backend package-index E2E.

Package uploads intentionally do not use `twine --skip-existing`; if a version is consumed by TestPyPI/PyPI and validation later fails, fix forward with the next `.postN` or `rcN`.

For public docs, keep [`docs/developer/ci-e2e-workflows.md`](./docs/developer/ci-e2e-workflows.md) and [`docs/developer/release-publishing.md`](./docs/developer/release-publishing.md) aligned with this section.

---

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
- [`netbox_proxbox/management/CLAUDE.md`](./netbox_proxbox/management/CLAUDE.md)
- [`netbox_proxbox/management/commands/CLAUDE.md`](./netbox_proxbox/management/commands/CLAUDE.md)
- [`netbox_proxbox/migrations/CLAUDE.md`](./netbox_proxbox/migrations/CLAUDE.md)
- [`netbox_proxbox/models/CLAUDE.md`](./netbox_proxbox/models/CLAUDE.md)
- [`netbox_proxbox/schemas/CLAUDE.md`](./netbox_proxbox/schemas/CLAUDE.md)
- [`netbox_proxbox/services/CLAUDE.md`](./netbox_proxbox/services/CLAUDE.md)
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
- [`netbox_proxbox/templatetags/CLAUDE.md`](./netbox_proxbox/templatetags/CLAUDE.md)
- [`netbox_proxbox/views/CLAUDE.md`](./netbox_proxbox/views/CLAUDE.md)
- [`netbox_proxbox/views/endpoints/CLAUDE.md`](./netbox_proxbox/views/endpoints/CLAUDE.md)
- [`netbox_proxbox/views/sync_now/CLAUDE.md`](./netbox_proxbox/views/sync_now/CLAUDE.md)
- [`proxbox_cli/CLAUDE.md`](./proxbox_cli/CLAUDE.md)
- [`tests/CLAUDE.md`](./tests/CLAUDE.md)
