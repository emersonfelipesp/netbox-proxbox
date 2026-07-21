# `netbox_proxbox` Package

This package contains the NetBox plugin itself. It defines the plugin config, URL registration, navigation, models, forms, tables, API layer, background jobs, sync helpers, dashboard views, template hooks, and bundled static assets.

## Files And Ownership

- [`__init__.py`](./__init__.py): plugin registration via `PluginConfig`, plugin metadata, and supported NetBox version range.
- [`urls.py`](./urls.py): plugin URL map for UI pages, model views, sync routes, keepalive checks, card hydration, and the WebSocket test endpoint.
- [`navigation.py`](./navigation.py): NetBox plugin menu groups and buttons.
- [`choices.py`](./choices.py): `ChoiceSet` definitions for endpoint modes, sync types/statuses, token versions, and VM backup metadata.
- [`fields.py`](./fields.py): custom model/form field helpers used by the endpoint models.
- [`filtersets.py`](./filtersets.py): NetBox filtersets backing list views and API query filtering.
- [`jobs.py`](./jobs.py): `ProxboxSyncJob` background job class, enqueue helpers, and concurrent-run ownership guards.

> **Job log messages must be pre-formatted.** NetBox persists job log entries via
> `core.dataclasses.JobLogEntry.from_logrecord`, which stores `record.msg` — the
> **raw** format string. Python only merges `record.args` inside
> `record.getMessage()`, which NetBox never calls. So
> `job.logger.info("... %s", value)` writes a literal `%s` to the job log and
> drops the value; users reporting sync problems pasted logs full of
> `Preflight: API key verified — %s` and `Running SSE sync for Proxmox endpoint
> %s (backend id %s)`, which made those reports much harder to diagnose. Always
> use an f-string for `job.logger` / `self.logger` calls. Module-level
> `logger.info("%s", x)` is unaffected and stays fine. Guarded by
> `tests/test_job_log_formatting.py`, which scans every plugin module.
- [`sync_types.py`](./sync_types.py): regex-based targeted VM job name parsing and sync-type expansion helpers used by `jobs.py`.

> **Targeted per-VM runs are scoped, not estate-wide.** When `netbox_vm_ids` is
> non-empty (the per-VM "Sync now" button), `ProxboxSyncJob.run()` sets
> `targeted_vm_run` and **skips** the datacenter-wide preflight passes —
> firewall sync, datacenter CPU-model sync, and VM template inventory. Those
> three take no scoping argument (firewall/datacenter take none at all; templates
> loop every endpoint) and are irrelevant to reconciling one VM, yet they
> dominated the wall-clock of a targeted run. Each skip is logged so it is
> visible, and a full/scheduled sync still runs all of them. Cluster/node sync
> stays, but is scoped: `views/vm_sync_now.py::_endpoint_ids_for_vm()` resolves
> the VM's own endpoint through `ProxmoxCluster.netbox_cluster` and passes only
> that id, falling back to all enabled endpoints when the VM has no reflected
> Proxmox cluster yet. Guarded by `tests/test_targeted_sync_scope.py` and
> `tests/test_vm_sync_now_view.py`.
- [`sync_params.py`](./sync_params.py): normalises and serialises sync parameters passed into `ProxboxSyncJob.enqueue`.
- [`sync_stages.py`](./sync_stages.py): runs a single named sync stage against the backend SSE stream.
- [`sync_ownership.py`](./sync_ownership.py): helpers that claim and release RQ job ownership to prevent concurrent duplicate runs.
- [`schedule_hints.py`](./schedule_hints.py): quick-schedule heuristics and UI defaults for the home dashboard.
- [`github.py`](./github.py): fetches markdown content from GitHub for the contributing page.
- [`template_content.py`](./template_content.py): plugin template extensions for Job and VirtualMachine buttons/panels. `ProxboxJobTemplateExtension.buttons()` also renders a **Bug report** button on core Job detail pages for Proxbox sync jobs that ended in an error/unknown state (see `bug_report.py`).
- [`bug_report.py`](./bug_report.py): pure, read-only helper that assembles the failed-job **Bug report** modal context — plugin/NetBox versions, job metadata, formatted `log_entries`, a copy-to-clipboard `report_text`, and a prefilled netbox-proxbox GitHub *new issue* URL. Gated by `is_reportable_status(status)` (errored/failed or any unknown status).
- [`type_defs.py`](./type_defs.py): shared type aliases and lightweight protocol helpers used across the package.
- [`utils.py`](./utils.py): URL and host helpers, especially for the FastAPI backend and mkcert-aware local TLS handling.
- [`websocket_client.py`](./websocket_client.py): long-lived WebSocket client, message queue, and HTTP view used to stream backend messages into NetBox pages.
- [`signals.py`](./signals.py): Django signal handlers for automatic token generation and backend registration when enabled FastAPIEndpoint objects are created or updated.
- [`schemas/`](./schemas): Pydantic models and formatters for backend payloads, normalized sync context, and OpenAPI helpers.
- [`services/`](./services): backend proxy, schema caching, service status, and sync coordination helpers.
- [`management/`](./management): Django management commands package.
- [`templatetags/`](./templatetags): custom template tags for ProxBox templates.
- [`models/`](./models): persisted plugin models for Proxmox, remote NetBox, FastAPI, clusters, nodes, storage, backups, snapshots, task history, backup routines, replications, and settings.
- [`forms/`](./forms): create/edit, filter, and scheduling forms for plugin models and sync actions.
- [`tables/`](./tables): list-view table classes for endpoint, storage, backup, snapshot, replication, and cluster views.
- [`views/`](./views): dashboard pages, endpoint CRUD, sync actions, job helpers, status checks, and targeted sync buttons.
- [`api/`](./api): NetBox plugin API viewsets, serializers, filters, and URL wiring.
- [`migrations/`](./migrations): Django schema history for the plugin models.
- [`templates/`](./templates): bundled Django templates for plugin pages and template fragments.
- [`static/`](./static): bundled images, JS, CSS, SCSS, and generated theme assets.

## Data Flow

- Endpoint objects are created in NetBox through forms and model views.
- List and detail pages are rendered by classes in `views/` using tables, filtersets, and templates.
- Sync routes call the external ProxBox FastAPI backend using the configured `FastAPIEndpoint`. Two sync transport modes are available:
  - POST polling (traditional): the plugin waits for completion and returns a single JSON response.
  - GET SSE streaming: the plugin proxies `text/event-stream` from the FastAPI backend to the browser via `StreamingHttpResponse`. The browser JS parses SSE frames and renders granular per-object progress in real time.
- The API layer exposes the same main models through NetBox plugin API endpoints.
- Browser-side pages use templates plus JS from `static/netbox_proxbox/js/` for dashboard hydration, keepalive polling, SSE streaming, log rendering, and WebSocket updates.
- Operator recovery for missing Proxbox bootstrap/custom-field setup is exposed
  through `views/sync_state_repair.py` and the shared
  `partials/bootstrap_status_card.html`. The card appears on Home and Settings,
  loads proxbox-api `GET /extras/bootstrap-status` on demand through the
  session-gated `sync-state/bootstrap-status/` JSON endpoint for users with
  `view_fastapiendpoint`, and posts to `sync-state/repair/` for users with
  `core.add_job`. Both backend calls resolve the FastAPI endpoint through a
  request-user-restricted queryset before passing the endpoint ID to the backend
  proxy. The POST path calls
  `POST /extras/custom-fields/reconcile` through `services/backend_proxy.py`
  before queuing a normal full `ProxboxSyncJob`; it must remain a UI/session
  action with flash-message error handling, not a new sync transport.

## Import / Export

All three endpoint types support CSV, JSON, and YAML export via dedicated `ExportView` classes in `views/endpoints/`. Export comes in two modes:

- **Safe export** (no credentials): available to any user with `view` permission.
- **Sensitive export** (includes credentials): requires the user to supply a valid NetBox API token (v1 or v2) via the export-secrets modal. The token is validated server-side before the download is served.

Import uses NetBox's `BulkImportView`. All import forms auto-create missing `IPAddress` objects via `get_or_create` so data can move between NetBox instances without manual IPAM pre-population. Exported `id` columns are stripped before processing to prevent PK collisions.

**NetBoxEndpoint and FastAPIEndpoint are singleton-shaped.** If a record already exists when a bulk import is submitted, the import view intercepts the request and renders a confirmation page (`singleton_import_confirm.html`) before deleting the existing record and creating the replacement. Operational helpers use the first enabled FastAPI endpoint; disabled endpoints are inventory-only and must not trigger backend registration or HTTP probes. ProxmoxEndpoint allows multiple rows and has no singleton constraint.

For detailed implementation notes see [`views/endpoints/CLAUDE.md`](./views/endpoints/CLAUDE.md) and [`forms/CLAUDE.md`](./forms/CLAUDE.md).

## Dependencies

- Inbound: NetBox plugin loader imports `config`, NetBox route registration imports `urls.py`, and the menu system imports `navigation.py`.
- Outbound: Django/NetBox APIs, `requests`, `websockets`, the external ProxBox FastAPI service, GitHub raw content for the contributing page, and standard NetBox core models like `users.Token`, `ipam.IPAddress`, `virtualization.VirtualMachine`, and `virtualization.Cluster`.

## Optional netbox-rpc companion card (home dashboard)

The home dashboard renders an optional **netbox-rpc** companion card when that
plugin is installed. `integrations/rpc.py::rpc_dashboard_context()` is a soft,
best-effort helper (never imports `netbox_rpc` at module load; `try/except
ImportError`; never issues a network call) that returns
`{"rpc_integration": {installed, enabled, backend_name, backend_url, home_url,
settings_supported}}` — or `{}` when netbox-rpc is absent, so the card is simply
omitted. It reads `netbox_rpc.RpcPluginSettings.get_solo()` for the opt-in
`enabled` flag and configured backend when present, and degrades cleanly against
an older netbox-rpc that predates that model. `views/home_context.py`
(`_build_rpc_integration_context`) wires it into `build_home_dashboard_context`,
and `templates/netbox_proxbox/home.html` renders the card (config state +
"Configure & opt in" link to `/plugins/rpc/`). Live backend reachability is left
to the netbox-rpc landing page's own *Test connection* action, so the Proxbox
dashboard render stays fast. Guarded by `tests/test_rpc_integration.py`.

## Per-endpoint netbox-rpc enablement (optional companion)

`ProxmoxEndpoint.rpc_enabled` is a **tri-state** (`BooleanField(null=True)`)
per-endpoint override for netbox-rpc operations against that endpoint, mirroring
the `overwrite_*` pattern. `ProxmoxEndpoint.effective_rpc_enabled()` resolves it:
netbox-rpc installation is a precondition for all paths; after the
**function-local, guarded** `try/except ImportError` import succeeds, the
per-endpoint value wins when set (`is not None`, so an explicit `False` is
respected); otherwise it **inherits the global** netbox-rpc opt-in flag
(`netbox_rpc.RpcPluginSettings.enabled`). This is the allowed **optional**
proxbox→rpc integration; the model never imports netbox-rpc at load time and
**must never depend on the NMS stack**.

The field is editable on the endpoint **Settings tab** (new **RPC** pane,
`NullBooleanSelect`, `RPC_FIELD_GROUPS` in `constants.py`) and exposed over REST
(`ProxmoxEndpointSerializer.rpc_enabled` writable + read-only
`effective_rpc_enabled` `SerializerMethodField`) so external callers can read the
resolved value. Added by migration `0059_proxmoxendpoint_rpc_enabled`
(`add_field_idempotent`). Contract-tested in `tests/test_rpc_endpoint_override.py`
and `tests/test_frontend_contracts.py` (5-pane Settings tab).

**Non-enforcing here:** resolution + UI only. The fail-closed *gate* (block RPC
against a disabled endpoint) lives in the layer allowed to read the endpoint —
netbox-proxbox for RPC it initiates, and the NMS layer (nms-backend) for
dispatch — and ships separately once operators have enabled RPC.

## Configuration

`ProxboxPluginSettings` (see [`models/plugin_settings.py`](./models/plugin_settings.py))
is the singleton that holds runtime tunables for both this plugin and the companion
`proxbox-api` backend. **New runtime tunables belong here, not in proxbox-api's
`.env`** — the backend reads them through `proxbox_api.runtime_settings.get_*` which
resolves env > plugin settings > default with a 5-minute cache. See
[top-level `CLAUDE.md` → Plugin settings and configuration](../CLAUDE.md) for the full
policy and the short list of `.env`-only operator infrastructure variables.

Tenant assignment for Proxmox-synced NetBox `VirtualMachine` rows is plugin-side
post-sync behavior. Regex assignment is controlled by
`enable_tenant_name_regex` plus `tenant_name_regex_rules`; tag assignment is
controlled by `enable_tenant_tag_assignment`. The tag resolver requires both a
`cloud-customer` marker tag and exactly one `tenant-<slug>` tag, never overwrites
an existing VM tenant, and auto-creates missing `Tenant` rows under the
`cloud-customers` `TenantGroup`. Cluster inheritance is controlled by
`enable_tenant_from_cluster`; when enabled it runs after regex and tag assignment
and fills an empty VM tenant from `vm.cluster.tenant`, so explicit name/tag rules
win and existing VM tenants are never overwritten. Per-`ProxmoxEndpoint`
overrides inherit from the global plugin settings when left null.

Cloud-customer network discovery is also settings-backed. The plugin stores the
operator-designated IPAM Prefix ID, bridge, VLAN tag, gateway, and lock flag on
`ProxboxPluginSettings`; proxbox-api and nms-backend must resolve those fields
instead of hardcoding estate network values. Populate them with the idempotent
`python manage.py ensure_cloud_customer_network --prefix ... --vlan ... --gateway ... [--enable-lock]`
command.

## Installation Docs

- Docker-based NetBox installation guidance is documented at [`../docs/installation/3-installing-plugin-docker.md`](../docs/installation/3-installing-plugin-docker.md).
- Traditional host/venv installation remains documented in [`../docs/installation/2-installing-plugin-git.md`](../docs/installation/2-installing-plugin-git.md).

## Child Docs

- [`../CLAUDE.md`](../CLAUDE.md)
- [`api/CLAUDE.md`](./api/CLAUDE.md)
- [`forms/CLAUDE.md`](./forms/CLAUDE.md)
- [`management/CLAUDE.md`](./management/CLAUDE.md)
- [`management/commands/CLAUDE.md`](./management/commands/CLAUDE.md)
- [`migrations/CLAUDE.md`](./migrations/CLAUDE.md)
- [`models/CLAUDE.md`](./models/CLAUDE.md)
- [`schemas/CLAUDE.md`](./schemas/CLAUDE.md)
- [`services/CLAUDE.md`](./services/CLAUDE.md)
- [`static/CLAUDE.md`](./static/CLAUDE.md)
- [`tables/CLAUDE.md`](./tables/CLAUDE.md)
- [`templates/CLAUDE.md`](./templates/CLAUDE.md)
- [`templatetags/CLAUDE.md`](./templatetags/CLAUDE.md)
- [`views/CLAUDE.md`](./views/CLAUDE.md)
