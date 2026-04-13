# Version 0.0.11

## Summary

Version 0.0.11 is a major feature release. It adds Backup Routines, individual per-object sync buttons, a live job panel, a Backend Logs page, non-blocking live log streaming, encryption key storage, extended storage and replication views, endpoint CSV import/export, auto-push of NetBox endpoint config to the backend, three-tier error severity in sync output, and dozens of bug fixes and stability improvements.

## Compatibility

| NetBox   | netbox-proxbox | proxbox-api | netbox-sdk     | proxmox-sdk    |
|----------|----------------|-------------|----------------|----------------|
| >=4.5.7  | v0.0.11        | v0.0.7      | v0.0.7.post4   | v0.0.2.post2   |

NetBox compatibility range: `4.5.0` – `4.5.99` (verified on `v4.5.7` with django-rq `4.0`).

---

## New Features

### Backup Routines

Proxbox now discovers and stores Proxmox `vzdump` backup schedules as **BackupRoutine** objects in NetBox. Each routine captures the job ID, enabled state, schedule (cron expression), storage target, compression mode, and retention policies (`keepLast`, `keepHourly`, `keepDaily`, `keepWeekly`, `keepMonthly`, `keepYearly`). Routines can be synced individually or as part of a Full Update. Bulk edit and bulk import are supported.

### Individual Sync Buttons on All Objects

Every NetBox plugin object (virtual machines, containers, clusters, nodes, backups, snapshots, replications, backup routines, storage) now shows a **Sync Now** button on its detail page. Clicking the button enqueues a targeted sync job for that single object without triggering a full update.

### Live Job Panel and Real-Time Polling

The sync UI now streams job progress through a live panel with stage-by-stage status, log entries, and error counts. Jobs can be followed in real time from the NetBox UI without reloading the page. The panel polls the running job and updates its state, badges, and log table automatically.

### Errors Tab in Live Job Panel

A dedicated **Errors** tab appears in the live job panel when any non-fatal error occurs during sync. Errors are classified into three severity tiers — **critical**, **error**, and **warning** — each shown with a distinct badge colour. This allows operators to review problems without the sync being interrupted.

### Backend Logs Page

A new **Backend Logs** page under Plugins → Proxbox streams log output directly from the `proxbox-api` process. Logs are retrieved non-blocking via SSE and displayed with level-based colouring. The page includes filters for log level and date range.

### Encryption Key Storage

`ProxboxPluginSettings` gains an **encryption_key** field for storing a secret used to encrypt sensitive Proxmox API tokens at rest. The field is surfaced in a new **Encryption** card on the `/proxbox/settings/` page and is excluded from non-admin API responses.

### Configurable Primary IP Preference

A new setting in `ProxboxPluginSettings` lets operators choose which IP address Proxbox assigns as the primary IP for synced virtual machines — e.g. prefer the management interface over the first discovered address.

### Auto-Push NetBox Endpoint Config to Backend

Proxbox now automatically pushes the active `NetBoxEndpoint` (URL + API token) to `proxbox-api` whenever:

- The endpoint is saved or updated in the NetBox UI.
- NetBox starts up and the plugin initialises.
- The keepalive heartbeat fires.
- A sync job is about to run.

This removes the manual step of configuring the backend separately for each deployment.

### Per-Stage Runtime Breakdown

The sync card on the Proxbox home page now shows a per-stage runtime breakdown after a sync completes, listing the wall-clock time spent in each pipeline stage (devices, VMs, storage, backups, etc.).

### Extended Storage Detail Tabs

The ProxmoxStorage detail page now has dedicated tabs for Virtual Disks, Backups, and Snapshots, replacing the previous inline cards. Extended fields — content types, shared flag, active status, disk counts — are shown in a structured layout.

### Extended Replication Fields

`Replication` objects now expose `endpoint`, `status`, and `raw_config` fields. The list view supports bulk edit and bulk import. Status choices use a centralised enum for consistency across the UI, API, and import paths.

### Snapshot Bulk Edit and Bulk Import

VM Snapshots support bulk edit and bulk import from CSV/JSON/YAML in addition to the existing list actions.

### Endpoint CSV/JSON Import and Export

All three endpoint types (`ProxmoxEndpoint`, `NetBoxEndpoint`, `FastAPIEndpoint`) support export (safe and sensitive modes) and bulk import. Import auto-creates `IPAddress` objects when an IP is provided as a plain string and strips the `id` column to prevent cross-instance conflicts. The plugin home page and endpoint list pages show an **Import from CSV** button.

### Token Export Modal Improvements

The export-secrets modal now supports v1 (raw token) and v2 (encrypted) token formats via a selector, and includes a **Quick Add** shortcut for adding new tokens without leaving the export flow.

### Task History as a Sync Stage

Task history records from `proxbox-api` are now fetched and stored as part of the full sync pipeline, giving NetBox a record of every Proxmox task that ran on each node.

### REST API for Non-Model Pages

REST API endpoints are now available for all Proxbox plugin pages that previously had no API representation, including sync trigger endpoints and settings.

### Retry on 5xx Backend Errors

Sync stages that receive a `5xx` response from `proxbox-api` are automatically retried up to two times before the stage is marked as failed.

### Run Now for Scheduled Jobs

Scheduled jobs in a terminal state (completed, errored, failed) now show a **Run now** button that immediately re-enqueues the same job parameters on the high-priority RQ queue.

---

## Bug Fixes

| Area | Fix |
|------|-----|
| Security | Fixed IDOR in sensitive endpoint export — token lookup is now scoped to the requesting user |
| WebSocket | `websocket_port` now defaults to the configured HTTP port instead of the hardcoded `8800` |
| Backend handshake | `wait_for_backend_ready` now passes on any HTTP `200` response regardless of the `init_ok` field |
| Backend handshake | Fail fast with a clear log message when `proxbox-api` bootstrap check is incomplete |
| API key push | Registers the API key with the backend before each `NetBoxEndpoint` push |
| RQ queue | `Run Now` uses the **high** priority queue so jobs are picked up immediately |
| Templates | Fixed `NoReverseMatch` — replaced removed `core:job_rerun` URL with `core:job_proxbox_run` |
| Templates | Fixed `TemplateSyntaxError` — replaced removed `hyperlinked_object` filter with `linkify` |
| Templates | Fixed `TemplateSyntaxError` on schedule page that hid recurring jobs |
| Templates | Fixed `render_table` tag missing in cluster nodes template |
| Migrations | Fixed `pstart` migration cast error on PostgreSQL |
| Migrations | Lowered `dcim` migration dependency in `0016` to support NetBox `4.5.0+` |
| Migrations | Added `state_operations` to squashed migration to remove stale `unique_together` constraint |
| Models | Fixed Proxmox API type mismatches for `encrypted` and `pstart` fields |
| API serializers | Used `WritableNestedSerializer` for nested endpoint/cluster/node fields |
| API serializers | Added `display`, `tags`, `custom_fields`, and `encryption_key` to `ProxboxPluginSettingsSerializer` |
| API serializers | Added `select_related` chains to fix N+1 queries; fixed backup routine node URL |
| API serializers | Guarded `perform_create` against bulk POST `validated_data` lists |
| API serializers | Added ordering to `ProxboxPluginSettingsViewSet` queryset |
| API serializers | Replaced `SerializerMethodField` with `NestedProxmoxNodeSerializer` for node representation |
| CSV import | Fixed id-column stripping by overriding `create_and_update_objects` |
| CSV import | Fixed circular import — lazy-imports `sync_cluster_and_nodes` inside `run()` |
| CSV import | Guarded PK lookup against non-integer `ip_address` query params |
| Export modal | Inlined export-secrets-modal JS to fix stuck token dropdown |
| Export modal | Fixed v1 manual token input and JS loading order in export-secrets modal |
| Job log view | Set orange badge for `processing` and blue for `info` states |
| Job summaries | Store compact stage summaries and verify `runtime_seconds` after DB save |
| Sync session | Used `proxmox_backend_name()` for `proxbox-api` session lookup in config tab |
| Sync params | Fixed individual sync dependency parameter names and added missing required params |
| Recurring jobs | Widened banner detection to include completed recurring jobs; pre-fill Proxmox endpoints |
| Recurring jobs | Used unrestricted query in `has_recurring_proxbox_sync_all` |
| RQ worker | Restart RQ worker in `reinstall.sh` and replace deprecated `setup.py` call |
| Reinstall | Run migrations in `reinstall.sh` to prevent missing-column HTTP 500 on fresh installs |

---

## Database Migrations

Migration `0022` is a squashed migration that consolidates the following schema changes introduced during the v0.0.11 development cycle:

- `BackupRoutine` model and table
- `Replication` extended fields (`endpoint`, `status`, `raw_config`)
- `ProxboxPluginSettings.encryption_key` field
- `VMSnapshot` and `VMBackup` bulk-operation support fields
- Removal of stale `unique_together` constraints via `state_operations`

Run migrations after upgrading:

```bash
python manage.py migrate netbox_proxbox
```

---

## API Changes

New and updated routes in `/api/plugins/proxbox/`:

| Route | Notes |
|-------|-------|
| `/backup-routines/` | Full CRUD for `BackupRoutine` objects |
| `/settings/` | Now includes `encryption_key`, `display`, `tags`, `custom_fields` |
| `/clusters/` | Now returns `NestedProxmoxNodeSerializer` for node field |
| `/nodes/` | `select_related` chains added; fixed N+1 queries |
| All list endpoints | Consistent ordering added where previously missing |
