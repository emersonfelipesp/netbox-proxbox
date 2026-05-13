# Version 0.0.15

## Summary

Version `0.0.15` fixes five issues and adds three new features in pair with backend `proxbox-api 0.0.11`:

- [Issue #352](https://github.com/emersonfelipesp/netbox-proxbox/issues/352): the `FastAPIEndpoint` model could not express the combination "use HTTPS but skip certificate verification", which is the default state of the proxbox-api `*-nginx` image (TLS-only with a self-signed mkcert certificate).
- [Issue #354](https://github.com/emersonfelipesp/netbox-proxbox/issues/354): IPAM `IPAddress` records created during virtualization sync had an empty `dns_name`, even though Proxmox knew the guest hostname. The plugin now exposes a new `overwrite_ip_address_dns_name` setting (global + per-endpoint) so operators can opt out of `dns_name` writes; the actual hostname resolution and write live in `proxbox-api 0.0.11`.
- [Issue #391](https://github.com/emersonfelipesp/netbox-proxbox/issues/391): the Virtual Machines and LXC Containers plugin pages now auto-detect whether the installed NetBox has the 4.6 `VirtualMachineType` relation. NetBox 4.5.x stays on the legacy `proxmox_vm_type` custom-field path, while NetBox 4.6.x keeps native type support.
- [Issue #243](https://github.com/emersonfelipesp/netbox-proxbox/issues/243): Proxmox cluster High-Availability state was not surfaced anywhere in NetBox. The plugin now ships a per-VM **HA tab** and a cluster-wide **HA Status** page, both backed by new read-only HA endpoints in `proxbox-api 0.0.11`.
- [Issue #360](https://github.com/emersonfelipesp/netbox-proxbox/issues/360): operators had no headless way to trigger a full Proxmox→NetBox sync — every run required a human clicking **Full Update** in the plugin UI, which blocked cron, systemd timers, Kubernetes CronJobs, and CI smoke checks. The plugin now ships a `python manage.py proxbox_sync` Django management command that enqueues the same `ProxboxSyncJob` as the UI button.
- [Issue #359](https://github.com/emersonfelipesp/netbox-proxbox/issues/359): VM-interface MACs synced through the plugin never appeared in NetBox. The legacy inline `mac_address` field on `VMInterface` is `read_only=True` at NetBox 4.5/4.6 (computed from `primary_mac_address`), so every MAC `proxbox-api` posted was silently dropped. The plugin itself ships no code change; the fix lives in `proxbox-api 0.0.11`, which now writes MACs via `dcim.MACAddress` and links them through `VMInterface.primary_mac_address`. Existing v0.0.15 installs pick the fix up by upgrading the backend.
- [Issue #367](https://github.com/emersonfelipesp/netbox-proxbox/issues/367): operators need a safe way to remove VMs that were previously discovered by Proxbox but no longer appear in the current Proxmox inventory. The plugin now exposes a default-off **Delete orphan VMs** setting that proxbox-api reads before running its orphan sweep.

## #352 — `Use HTTPS` toggle decoupled from `Verify SSL`

Until this release, the `Verify SSL` flag on the FastAPI endpoint was overloaded — it controlled both the URL scheme (`http` vs `https`) and the underlying `requests` `verify=` argument. With the bundled mkcert cert, `Verify SSL=True` failed on cert validation; `Verify SSL=False` downgraded the URL to plain HTTP, which the nginx image rejects with `400 Bad Request: The plain HTTP request was sent to HTTPS port`.

A new `Use HTTPS` field decouples scheme selection from certificate verification:

| Use HTTPS | Verify SSL | Resulting connection |
|---|---|---|
| ✗ | — | `http://` (cert verification flag is unused) |
| ✓ | ✓ | `https://` with strict cert verification |
| ✓ | ✗ | `https://` with cert verification skipped — required for the `*-nginx` image with the bundled mkcert cert |

A migration backfills `use_https = verify_ssl` for existing rows so installs that were already on a working HTTPS-with-verified-cert setup keep working without operator intervention.

The plugin also returns a clearer error when it detects nginx's `plain HTTP request was sent to HTTPS port` body, prompting the operator to enable `Use HTTPS`.

## #243 — HA tab and cluster-wide HA Status page

Proxmox cluster High-Availability state was previously invisible inside NetBox. Operators had to open the Proxmox web UI just to answer "is this VM HA-managed and what's its current CRM state?". This release adds two read-only views — both fetched live from `proxbox-api 0.0.11` on every page render, no caching, no NetBox-side persistence, no migration.

- **VM HA tab.** A new tab on every `virtualization.VirtualMachine` detail page, sibling to **Proxmox Config** (slot weight `1400`). It calls `GET /proxmox/cluster/ha/resources/by-vm/{vmid}` and renders HA managed yes/no, group, current state / CRM state / request state, node, and the restart/relocate/failback counters. VMs that are not HA-managed get a friendly empty state with a link to the cluster page.
- **HA Status page.** A new top-level Proxbox menu entry (`/plugins/proxbox/ha/`) that calls `GET /proxmox/cluster/ha/summary` once and renders three sections: Cluster Status (per-node CRM state and quorum), HA Groups (name / nodes / restricted / nofailback), and HA Resources (every HA-managed VM/CT, sid linked to its NetBox `VirtualMachine` when one exists with the matching `proxmox_vm_id`).
- **Backend version awareness.** When the FastAPI backend is older than `0.0.11` and returns `404` on the new HA routes, both views render an inline "Backend does not support HA endpoints — upgrade proxbox-api to v0.0.11 or later." banner instead of a 500.

### Changes

- **`netbox_proxbox/views/vm_ha.py` (new).** `ProxmoxVMHATabView` registered via `register_model_view(VirtualMachine, "proxmox_ha", path="proxmox-ha")` with `ViewTab(label="HA", permission="virtualization.view_virtualmachine", weight=1400)`. Reuses `services.backend_context.get_fastapi_request_context` and `services._endpoint_errors.translate_request_exception` exactly like `ProxmoxVMConfigTabView`.
- **`netbox_proxbox/views/ha.py` (new).** `HAClusterView` extending `ConditionalLoginRequiredMixin` + `RequireProxboxDashboardAccessMixin`, fetching `/proxmox/cluster/ha/summary` with a 15s timeout and rendering `netbox_proxbox/ha.html`.
- **Templates.** `templates/netbox_proxbox/vm_proxmox_ha.html` (extends `generic/object.html`) and `templates/netbox_proxbox/ha.html` (extends `base/layout.html`), both using NetBox's standard card / table / badge styling.
- **`urls.py`.** New route `path("ha/", views.HAClusterView.as_view(), name="ha")`.
- **`navigation.py`.** New `ha_item = PluginMenuItem(link="plugins:netbox_proxbox:ha", link_text="HA Status")` slotted between Replications and Task History under the "Proxmox Plugin" group.
- **Tests.** `tests/test_views_vm_ha.py` and `tests/test_views_ha.py` are AST-based source-contract tests — same pattern as `test_views_vm_config.py` — pinning the `register_model_view` arguments, `ViewTab` kwargs, template names, backend URLs (`/proxmox/cluster/ha/resources/by-vm/` and `/proxmox/cluster/ha/summary`), the `_extract_vmid` helper, and the navigation/URL wiring.
- **No DB migration. No new persisted model. No `OVERWRITE_FIELDS` change.** HA state is read-only.

## Compatibility

| NetBox | netbox-proxbox | proxbox-api | netbox-sdk | proxmox-sdk |
|--------|----------------|-------------|------------|-------------|
| >=4.5.8 | v0.0.15 | v0.0.11 | v0.0.8.post1 | v0.0.3.post1 |
| >=4.5.8 | v0.0.14 | v0.0.10.post2 | v0.0.8.post1 | v0.0.3.post1 |

NetBox compatibility range: `4.5.8` – `4.6.99` (unchanged).

## Changes

- **`FastAPIEndpoint.use_https` (new field).** Controls the URL scheme. Default `False` for new rows; existing rows are backfilled to `verify_ssl`'s current value (preserving the effective scheme). Help text guides operators to enable it for the proxbox-api `*-nginx` image.
- **`FastAPIEndpoint.verify_ssl` (semantics change).** Now controls only TLS certificate verification — never the URL scheme. The default remains `True`.
- **Migration `0038_fastapiendpoint_use_https`.** Adds the column with `IF NOT EXISTS` for production-safe additive deployment, plus a `RunPython` step that copies `verify_ssl` into `use_https` so existing rows do not regress.
- **Form, table, serializer, detail page.** All surface the new field; the table includes it as a default column next to `Verify SSL`.
- **`services/_endpoint_errors.py` (new).** Translates the two known misconfiguration errors into operator-actionable messages:
  - `400` body containing `plain HTTP request was sent to HTTPS port` → "Enable 'Use HTTPS' on the FastAPI endpoint."
  - `SSLError` (e.g. self-signed cert) → "Uncheck 'Verify SSL' on the FastAPI endpoint."
- **`services/openapi_schema.py`.** Wires the translator into the `/openapi.json` and `/version` fetch path the FastAPI endpoint detail page uses, so the misconfigured-image error is shown inline instead of the raw `requests` exception.
- **`utils.get_fastapi_url` and `signals._get_backend_url`.** Updated to derive the scheme from `use_https` only, while still propagating `verify_ssl` separately so the requests layer can decide cert strictness.
- **`FastAPIEndpoint.url` and `FastAPIEndpoint.websocket_url`.** Use `use_https` for `http`/`https` and `ws`/`wss` selection, overriding the inherited `CommonProperties.url`.
- **Docs.** [`docs/installation/backend-setup.md`](../installation/backend-setup.md) now spells out the `Use HTTPS` + `Verify SSL` combination required for the `*-nginx` image.

## #354 — IPAM `dns_name` populated from Proxmox guest hostnames

The plugin already renders `IPAddress.dns_name` in the IP-addresses table; the gap was on the write side. With `proxbox-api 0.0.11`, the backend now resolves the guest hostname (LXC: `VMConfig.hostname`; QEMU: `agent/get-host-name`, with a fallback through the network-interfaces payload) and writes it to `IPAddress.dns_name` on every IP create / reconcile path. This release wires the corresponding overwrite toggle through the plugin so operators can disable the write without touching the backend.

### Changes

- **`ProxboxPluginSettings.overwrite_ip_address_dns_name` (new field, default `True`).** When disabled, sync never changes `dns_name` on existing IP addresses; `dns_name` is still populated when an IP is created.
- **`ProxmoxEndpoint.overwrite_ip_address_dns_name` (new tri-state field).** Per-endpoint override; leave blank to inherit the global setting.
- **Migration `0039_pluginsettings_overwrite_ip_address_dns_name`.** Adds the column to both `ProxboxPluginSettings` (`NOT NULL DEFAULT TRUE`) and `ProxmoxEndpoint` (nullable) using `SeparateDatabaseAndState` + `ALTER TABLE … IF NOT EXISTS`.
- **`OVERWRITE_FIELDS` / `OVERWRITE_FIELD_GROUPS`.** The new flag is part of the canonical 23-flag set and lives in the IP Address group on the Settings tab.
- **`contracts/overwrite_flags.json`.** Updated mirror manifest (paired with the matching update in `proxbox-api/contracts/overwrite_flags.json`); the cross-repo drift detector test (`tests/test_overwrite_flags_contract.py`) covers it.
- **Settings + endpoint forms, serializers, tables.** Surface the new flag wherever the sibling `overwrite_*` flags appear, so it can be toggled from the UI and exported in CSV/JSON/YAML.
- **`sync_params._build_base_query_params`.** Forwards the resolved `overwrite_ip_address_dns_name` value to proxbox-api as a flat query-string key (the same shape every other overwrite flag uses).

## #367 — Optional orphan VM cleanup toggle

The backend now stamps every reconciled VM with a shared run UUID and can sweep
Proxbox-discovered VMs whose stamp is stale or missing. This plugin release adds
the operator-facing gate for that destructive behavior.

### Changes

- **`ProxboxPluginSettings.delete_orphans` (new field, default `False`).** When enabled, proxbox-api full-update runs may delete Proxbox-discovered QEMU/LXC VMs that were not touched by the current sync run.
- **Migration `0046_pluginsettings_delete_orphans`.** Adds the default-off column using the established `SeparateDatabaseAndState` + `ALTER TABLE ... IF NOT EXISTS` pattern.
- **Settings form, template, and API serializer.** Surface the flag in the Plugin Settings page and `/api/plugins/proxbox/settings/` so proxbox-api can read it through the existing runtime settings client.
- **Docs.** The Plugin Settings guide documents the `PROXBOX_DELETE_ORPHANS` backend env override and recommends reviewing the full-update dry-run stream before enabling deletion.

## #360 — Headless `proxbox_sync` Django management command

Operators previously had no programmatic way to trigger a full Proxmox→NetBox sync — every run required a logged-in user clicking **Full Update** in the plugin UI. This blocked the entire operational-verbs roadmap (#14, #15, #16) for cron, systemd timers, Kubernetes CronJobs, and CI smoke checks.

This release adds a `proxbox_sync` Django management command that is the exact headless equivalent of clicking **Full Update**: it enqueues the same `ProxboxSyncJob` (queue `default`, `sync_types=[SyncTypeChoices.ALL]`, all configured `ProxmoxEndpoint` rows) and writes a styled success / failure line.

```bash
# Fire-and-forget — enqueue and return immediately
python manage.py proxbox_sync

# Block until the job reaches a terminal state and mirror its exit code
python manage.py proxbox_sync --wait --timeout 7200

# Attribute the job to a specific user instead of the oldest active superuser
python manage.py proxbox_sync --user backupbot --wait
```

### Changes

- **`netbox_proxbox/management/commands/proxbox_sync.py` (new).** Thin wrapper around `ProxboxSyncJob.enqueue(...)` with five flags — `--user`, `--wait`, `--timeout`, `--poll-interval`, `--worker-grace` — and `CommandError`-driven non-zero exits for cron/systemd-friendly failure semantics.
- **Pre-flight reachability.** Reuses `services.backend_auth.wait_for_backend_ready` (5-retry snappy CLI mode) and `services.backend_context.get_fastapi_request_context` so the command surfaces the same backend-unreachable / no-FastAPIEndpoint errors the UI does.
- **`--wait` no-worker fast-fail.** If `--wait` is set and the job stays `pending` for more than `--worker-grace` seconds with zero RQ workers on the `default` queue, the command exits non-zero with an actionable "no RQ worker is consuming the `default` queue" message instead of hanging.
- **User attribution.** Defaults to the oldest active superuser; `--user USERNAME` overrides. Missing user is a `CommandError`.
- **Tests.** `tests/management/test_proxbox_sync.py` (10 scenarios) plus `tests/management/conftest.py` install lightweight `django.core.management.base` / `django.contrib.auth` stubs so the command can be exercised without bootstrapping NetBox.
- **Docs.** New [`docs/operations/headless-sync.md`](../operations/headless-sync.md) page covering flag reference, exit codes, the RQ-worker requirement, a 3-line cron example, and a 6-line systemd-timer example.

No DB migration. No model change. No new persisted state.

## Upgrade Notes

- Run `python manage.py migrate netbox_proxbox` after upgrading; the migrations are additive and include a one-time data backfill (issue #352), a single new column on `ProxboxPluginSettings` and `ProxmoxEndpoint` (issue #354), and the default-off `delete_orphans` flag (issue #367).
- If you operate the proxbox-api `*-nginx` image and previously could not connect, edit the FastAPI endpoint after upgrade and tick **Use HTTPS** (and untick **Verify SSL** if you use the bundled mkcert cert).
- For the `dns_name` fix, pair with `proxbox-api ≥ 0.0.11`. `proxbox-api 0.0.10.post2` is still wire-compatible for the `Use HTTPS` fix but does not populate `dns_name`. With an older backend, the new toggle has no effect because the backend never writes `dns_name`.
- The `dns_name` default is "always overwrite" to match every other overwrite flag. If you have hand-edited `dns_name` on synced IPs, untick **Overwrite IP address DNS name** before the next sync (globally, or per Proxmox endpoint).
