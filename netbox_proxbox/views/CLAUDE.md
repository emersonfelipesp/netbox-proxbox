# `netbox_proxbox.views`

This directory implements the plugin's NetBox UI behavior, including dashboard pages, endpoint CRUD views, sync actions, job integration, and status utilities.

## Files And Ownership

- [`__init__.py`](./__init__.py): top-level page views and re-exports for endpoint views, cluster views, dashboard pages, sync enqueue actions, status checks, settings/storage views, backup/replication views, snapshot/task views, and job integration helpers.
- [`backend_sync.py`](./backend_sync.py): shared helper that ensures a Proxmox endpoint is synchronized to proxbox-api before live reads, including TLS verification and per-endpoint Proxmox request tuning fields.
- [`dashboard_data.py`](./dashboard_data.py): assembles endpoint and cluster summary data for the dashboard page context.
- [`mixins.py`](./mixins.py): shared view mixins used across multiple view modules.
- [`resource_list_views.py`](./resource_list_views.py): list views for resource objects (nodes, VMs, LXC containers, virtual disks, clusters, interfaces, IP addresses). Every list table is paginated through the module-level `paginate_object_list()` helper, which wraps NetBox's `EnhancedPaginator` + `get_paginate_count` so the pages honour `?per_page=`, the saved per-page preference, and `PAGINATE_COUNT`/`MAX_PAGE_SIZE` — the same machinery NetBox object tables use. These views must never re-introduce a fixed `[:100]` slice; raising the visible count is done by paginating, not by capping. The two aggregate pages (interfaces, IP addresses) render two tables each and paginate them independently via the `vm_page` / `node_page` query parameters, with summary counts computed from the full querysets (`.count()`) rather than the current page.
- [`schedule_helpers.py`](./schedule_helpers.py): utility functions for scheduling logic shared between scheduling views.
- [`backup_routine.py`](./backup_routine.py): list/detail/edit/delete views and VM-related tab views for `BackupRoutine`.
- [`cards.py`](./cards.py): dashboard card hydration for Proxmox cluster/version data.
- [`cluster.py`](./cluster.py): cluster storage summary tab and Proxmox cluster summary tab.
- [`cluster_nodes_tab.py`](./cluster_nodes_tab.py): cluster/node tab for Proxmox endpoint detail pages.
- [`proxmox_templates_tab.py`](./proxmox_templates_tab.py): **Templates** tab for the Proxmox endpoint detail page (`.../endpoints/proxmox/<pk>/templates/`). Fetches templates live from proxbox-api for that endpoint via `get_fastapi_request_context()` + `resolve_backend_endpoint_id()` (the established backend boundary), classifies QEMU templates into **Cloud-Init** vs **plain QEMU/KVM** (derived from `cloud_init_drives`/`cicustom`, not the unreliable `cloud_init` flag) and lists **LXC** (`vztmpl`) images. Degrades gracefully (renders a message, no 500) when no FastAPI backend is configured, the endpoint is unresolved, or a request fails. Surfaces a "Create Cloud-Init template image" action wired to the optional `netbox-packer` plugin (via `integrations/packer.py`), disabled with a tooltip when netbox-packer is not installed. Also passes the endpoint `allow_writes` state and create-instance URL to the row-action wizard.
- [`proxmox_create_instance.py`](./proxmox_create_instance.py): POST-only registered ProxmoxEndpoint action (`path="create-instance"`) for the Templates-tab wizard. Requires `core.run_proxmox_action`, validates JSON server-side, pre-checks `allow_writes`, calls proxbox-api directly for QEMU/LXC provisioning, retries QEMU VMID collisions, surfaces proxbox-api 403 reasons verbatim, and performs best-effort single-object VM sync-back.
- [`dashboard.py`](./dashboard.py): operational cluster and node summary dashboard.
- [`endpoints/`](./endpoints/): model views for the three endpoint models.
- [`error_utils.py`](./error_utils.py): helpers for rendering and normalizing user-facing error messages.
- [`external_pages.py`](./external_pages.py): redirect or informational external community pages.
- [`home_context.py`](./home_context.py): home page context assembly and quick-schedule defaults. Also exposes `latest_sync_jobs` (the newest 5 visible Proxbox sync jobs, resolved via `is_proxbox_sync_job()` over restricted `core.Job` rows) and `sync_jobs_list_url` (the core job list filtered to Proxbox jobs via `?q=Proxbox Sync`), rendered as the "Latest Sync Jobs" table + "View all sync jobs" button at the bottom of `home.html`. See also `ProxmoxEndpointSyncJobsTabView` in `endpoints/proxmox.py` for the per-endpoint job list tab.
- [`job_run.py`](./job_run.py), [`job_cancel.py`](./job_cancel.py), and [`job_stream.py`](./job_stream.py): integrate rerun/cancel actions and SSE log streaming into NetBox core Job views for Proxbox sync jobs.
- [`keepalive_status.py`](./keepalive_status.py): health and reachability checks for FastAPI, remote NetBox, and Proxmox services.
- [`logs.py`](./logs.py): backend log aggregation page and related rendering helpers.
- [`replication.py`](./replication.py): list/detail/edit/delete views and VM-related tab views for `Replication`.
- [`schedule_sync.py`](./schedule_sync.py): recurring/one-shot scheduler UI and quick-schedule flow from the home dashboard. Also exports `handle_endpoint_sync_routine_post(request, endpoint, post_data)` — the NetBox-independent core of the per-endpoint Sync Jobs tab "Create Sync Job" modal (permission gate → disabled-endpoint refusal → `ScheduleSyncForm` validation → **hard endpoint scoping** → enqueue → flash), returning an `(outcome, form)` tuple the tab view maps to a response. Kept here (not in the heavy `endpoints/proxmox.py`) so it is unit-loadable via the stubbed test harness.
- [`settings.py`](./settings.py): plugin settings page for runtime feature toggles.
- [`sync_state_repair.py`](./sync_state_repair.py): operator recovery surface
  for missing Proxbox bootstrap/custom-field setup. It builds the shared
  Home/Settings repair-card context without blocking page render, gates the
  on-demand `GET /extras/bootstrap-status` JSON endpoint with
  `view_fastapiendpoint`, and exposes the session-only `RepairSyncStateView`
  POST action requiring `core.add_job`. Bootstrap and repair backend calls use a
  request-user-restricted `FastAPIEndpoint` lookup, classify the proxy envelope
  plus inner proxbox-api body, and treat inner `ok=false` / `success=false` /
  error responses as failures. The repair action calls proxbox-api
  `POST /extras/custom-fields/reconcile` and then enqueues a normal full
  `ProxboxSyncJob`; backend and enqueue failures are flash messages.
- [`storage.py`](./storage.py): CRUD list/detail/delete views for `ProxmoxStorage`.
- [`sync.py`](./sync.py): POST endpoints that enqueue `ProxboxSyncJob` runs for devices, storage, virtual machines, virtual disks, backups, snapshots, network interfaces, IP addresses, backup routines, replications, and full update.
- [`sync_now/`](./sync_now/): targeted per-object sync handlers for cluster, node, storage, and VM actions.
- [`vm_backup.py`](./vm_backup.py): CRUD list/detail/delete views and the VirtualMachine tab for `VMBackup`.
- [`vm_config.py`](./vm_config.py): live Proxmox config tab for `VirtualMachine` records.
- [`vm_snapshot.py`](./vm_snapshot.py): CRUD list/detail/delete views and the VirtualMachine tab for `VMSnapshot`.
- [`vm_sync_now.py`](./vm_sync_now.py): targeted per-VM sync action button handler.
- [`vm_task_history.py`](./vm_task_history.py): detail and VirtualMachine tab views for `VMTaskHistory`.

## Dependencies

- Inbound: `urls.py` routes here for all plugin UI behavior.
- Outbound: plugin models, forms, tables, filtersets, templates, `requests`, the external ProxBox FastAPI service, and `websocket_client.py`.

## Notes

- `HomeView` is the main dashboard entrypoint and assembles endpoint lists plus derived backend URLs for the templates.
- Most changes to user-visible behavior land here first, then cascade into templates, static assets, and tests.
- When adding or changing sync actions, update `urls.py`, `sync.py`, scheduling forms/views, template extensions, and relevant frontend/tests that assert button routes and job flow.
- **URL namespace for tabs registered on core models.** When `register_model_view`
  attaches a tab/view to a NetBox **core** model (e.g. `virtualization.Cluster`,
  `virtualization.VirtualMachine`, `core.Job`), NetBox names that URL under the
  **core** model's namespace, not the plugin namespace — `get_viewname` only
  prepends `plugins:` for models that belong to a `PluginConfig`. So reverse
  these as `virtualization:cluster_<name>` / `virtualization:virtualmachine_<name>`
  (e.g. `virtualization:cluster_proxbox-storages` for
  `register_model_view(Cluster, "proxbox-storages", ...)`), **never**
  `plugins:netbox_proxbox:cluster_<name>`. Only the plugin's *own* models use the
  `plugins:netbox_proxbox:` namespace. Using the wrong namespace raises
  `NoReverseMatch` at template-render time and returns HTTP 500 (this caused the
  cluster summary crash). `tests/test_frontend_contracts.py` guards the cluster
  summary template against this regression.

## Links

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
- Child: [`endpoints/CLAUDE.md`](./endpoints/CLAUDE.md)
- Child: [`sync_now/CLAUDE.md`](./sync_now/CLAUDE.md)
