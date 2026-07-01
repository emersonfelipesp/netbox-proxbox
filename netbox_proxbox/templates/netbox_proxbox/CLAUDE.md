# `templates/netbox_proxbox`

This is the main Django template namespace for the plugin.

## Main Templates

- Dashboard and informational pages: `home.html`, `dashboard.html`, `community.html`, `contributing.html`, `devices.html`, `interfaces.html`, `ip_addresses.html`, `lxc_containers.html`, `virtual_machines.html`, `logs.html`, `settings.html`, `status_badge.html`, `proxbox-backend-status.html`, and `websocket_page.html`.
- Endpoint pages: `proxmoxendpoint.html`, `proxmoxendpoint_list.html`, `proxmoxendpoint_edit.html`, `proxmoxendpoint_cluster_nodes.html`, `proxmox_endpoint.html`, `proxmox-endpoints.html`, `netboxendpoint.html`, `netboxendpoint_list.html`, `netboxendpoint_edit.html`, `fastapiendpoint.html`, `fastapiendpoint_list.html`, `fastapiendpoint_edit.html`, and `fastapiendpoint_openapi.html`.
- Sync and action pages: `schedule_sync.html`, `sync_devices.html`, `sync_virtual_machines.html`, `sync_vm_backups.html`, and `sync_full_update.html`.
- Inventory detail/list pages: `storage_list.html`, `vmbackup.html`, `vmbackup_list.html`, `vmbackup_bulk_delete.html`, `vmsnapshot.html`, `vmsnapshot_list.html`, `vmtaskhistory.html`, `proxmoxstorage.html`, `backup_routine.html`, `backup_routine_list.html`, `replication.html`, `replication_list.html`, and `vm_proxmox_config.html` (live Proxmox config tab).
- Shared fragments and includes: `footer.html`, the `inc/` snippets for job buttons, runtime panels, live poll alerts, schedule form fields, and VM sync actions, plus `widgets/` helpers for custom checkbox controls.
- Child subdirectories: `base`, `cluster`, `fastapi`, `home`, `inc`, `partials`, `proxmox`, `table`, `test`, and `widgets`.

## Dependencies

- Inbound: views throughout `views/` render these templates.
- Outbound: static assets, NetBox base templates, and the JSON/HTML response contracts used by the views.

## Export and Import Templates

All three endpoint list templates (`proxmoxendpoint_list.html`, `netboxendpoint_list.html`, `fastapiendpoint_list.html`) include:

- An **Import** button linking to the model's `bulk_import` URL.
- An **Export** dropdown with CSV / JSON / YAML links to the model's `export` URL.
- An **Export with secrets** button that opens a Bootstrap modal for authenticated sensitive export.

The modal contains the full token-version UI (v1 dropdown or manual entry, v2 key+secret), a **Quick add token** button that calls the model's `quick_add_token` endpoint, copy-to-clipboard for the new token's plaintext, and client-side form validation. All of this JS is **inlined as an IIFE** directly in `{% block javascript %}` — not loaded from a separate `.js` file — so it works without running `collectstatic`.

`singleton_import_confirm.html` is rendered when a `NetBoxEndpoint` or `FastAPIEndpoint` import is attempted while a record already exists. It shows the existing record's key fields and a re-submit form that adds `confirm_override=true`, plus a Cancel link back to the list. See [`views/endpoints/CLAUDE.md`](../../views/endpoints/CLAUDE.md) for the full singleton import flow.

## ProxmoxEndpoint Settings page (`proxmoxendpoint_settings.html`)

`proxmoxendpoint_settings.html` (rendered by `ProxmoxEndpointSettingsView`, the endpoint's **Settings** tab) presents the per-endpoint overrides as a **Bootstrap nav-tabs** layout instead of a vertical stack of cards, so operators select a section rather than scrolling. Four tab panes:

1. **Connection** — `timeout`, `max_retries`, `retry_backoff`.
2. **Sync Modes** — the `sync_mode_field_groups` context list.
3. **Sync Overwrite** — intro text + the dynamic `overwrite_field_groups` as `h6` subsections in the one pane.
4. **Tenant Assignment** — the four tenant override fields.

Contract: every tab pane stays in the DOM (Bootstrap only toggles `display`), so all fields still submit on save regardless of the active tab; the hidden fields and `changelog_message` block sit **outside** the tab strip so they always submit. The `{% block javascript %}` (calls `{{ block.super }}`) holds an inline IIFE that, on `DOMContentLoaded`, activates the first tab pane containing a `.has-errors` element (NetBox's `render_field` marker for an errored field) so a validation error on an inactive tab is not invisible; it switches by clicking the nav button — the buttons keep `type="button"` so a programmatic click never resubmits — because NetBox's bundle registers Bootstrap's tab data-api but does not expose `window.Tab`. Guarded by `tests/test_frontend_contracts.py::test_proxmox_endpoint_settings_template_uses_tabs_not_stacked_cards` and `...::test_proxmox_endpoint_settings_focuses_first_tab_with_validation_error`.

## Notes

- There is some historical naming overlap in endpoint templates; keep the Python view/template binding in mind before removing or renaming files.
- Inline sync actions such as network interfaces and IP addresses are rendered inside their page templates, not as standalone `sync_*.html` files.
- Any template with dynamic status cards or sync output is likely coupled to the JS files under `static/netbox_proxbox/js/`.
- Sync buttons in `home.html` carry `data-sync-url` for job-enqueue POST actions; job progress and log details are shown on NetBox Job pages through the Proxbox template extension fragments.

## Links

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
- Children:
  - [`base/CLAUDE.md`](./base/CLAUDE.md)
  - [`fastapi/CLAUDE.md`](./fastapi/CLAUDE.md)
  - [`home/CLAUDE.md`](./home/CLAUDE.md)
  - [`partials/CLAUDE.md`](./partials/CLAUDE.md)
  - [`proxmox/CLAUDE.md`](./proxmox/CLAUDE.md)
  - [`table/CLAUDE.md`](./table/CLAUDE.md)
  - [`test/CLAUDE.md`](./test/CLAUDE.md)
