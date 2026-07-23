# `templates/netbox_proxbox`

This is the main Django template namespace for the plugin.

## Main Templates

- Dashboard and informational pages: `home.html`, `dashboard.html`, `community.html`, `contributing.html`, `devices.html`, `interfaces.html`, `ip_addresses.html`, `lxc_containers.html`, `virtual_machines.html`, `logs.html`, `settings.html`, `status_badge.html`, `proxbox-backend-status.html`, and `websocket_page.html`.
- Endpoint pages: `proxmoxendpoint.html`, `proxmoxendpoint_list.html`, `proxmoxendpoint_edit.html`, `proxmoxendpoint_cluster_nodes.html`, `proxmox_endpoint.html`, `proxmox-endpoints.html`, `netboxendpoint.html`, `netboxendpoint_list.html`, `netboxendpoint_edit.html`, `fastapiendpoint.html`, `fastapiendpoint_list.html`, `fastapiendpoint_edit.html`, and `fastapiendpoint_openapi.html`.
- Sync and action pages: `schedule_sync.html`, `sync_devices.html`, `sync_virtual_machines.html`, `sync_vm_backups.html`, and `sync_full_update.html`.
- Inventory detail/list pages: `storage_list.html`, `vmbackup.html`, `vmbackup_list.html`, `vmbackup_bulk_delete.html`, `vmsnapshot.html`, `vmsnapshot_list.html`, `vmtaskhistory.html`, `proxmoxstorage.html`, `backup_routine.html`, `backup_routine_list.html`, `replication.html`, `replication_list.html`, and `vm_proxmox_config.html` (live Proxmox config tab).
- Shared fragments and includes: `footer.html`, the `inc/` snippets for job buttons, runtime panels, live poll alerts, schedule form fields, and VM sync actions, plus `widgets/` helpers for custom checkbox controls.
- Operator bootstrap/status fragment:
  `partials/bootstrap_status_card.html` is included by `home.html` and
  `settings.html`. It displays the escaped proxbox-api
  `/extras/bootstrap-status` payload and the permission-aware
  **Repair / Rebuild Proxbox sync-state** POST form. **The card only surfaces
  when it is useful (issue #255).** For a user who can view status it renders
  hidden (`d-none`); its inline JS auto-checks `bootstrap-status` on load (only
  when `data-can-view="true"`) and calls `revealCard()` only for a genuine
  backend-reported problem — `needsAttention(data)` is `ok === false` with
  `Number(http_status) === 200` — and never auto-hides a revealed card within a
  page view. **A repair-only user** (can `core.add_job` but not view status) gets
  the card rendered server-visible instead, so they keep the repair affordance
  with no payload exposed; the `{% if bootstrap_status.can_view or not
  can_repair_sync_state %} d-none{% endif %}` guard encodes this. Its JS is inline
  (Bootstrap's `d-none` toggle only) and must not use `innerHTML`.
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
2. **Sync Modes** — the `sync_mode_field_groups` context list plus the
   `netbox_bgp_status` alert for optional SDN BGP projection availability.
3. **Sync Overwrite** — intro text + the dynamic `overwrite_field_groups` as `h6` subsections in the one pane.
4. **Tenant Assignment** — the four tenant override fields.

Contract: every tab pane stays in the DOM (Bootstrap only toggles `display`), so all fields still submit on save regardless of the active tab; the hidden fields and `changelog_message` block sit **outside** the tab strip so they always submit. The `{% block javascript %}` (calls `{{ block.super }}`) holds an inline IIFE that, on `DOMContentLoaded`, activates the first tab pane containing a `.has-errors` element (NetBox's `render_field` marker for an errored field) so a validation error on an inactive tab is not invisible; it switches by clicking the nav button — the buttons keep `type="button"` so a programmatic click never resubmits — because NetBox's bundle registers Bootstrap's tab data-api but does not expose `window.Tab`. Guarded by `tests/test_frontend_contracts.py::test_proxmox_endpoint_settings_template_uses_tabs_not_stacked_cards` and `...::test_proxmox_endpoint_settings_focuses_first_tab_with_validation_error`.

**Shared object header on edit sub-pages.** `proxmoxendpoint_settings.html` and `proxmoxendpoint_ssh_settings.html` are NetBox `ObjectEditView`s, so `generic/object_edit.html` would render the minimal edit header (title `Editing …`, a lone **Edit** tab, no timestamps/actions), which looks different from the detail-style tabs. Both templates keep `object_edit.html` as parent (so the edit **form** and its submit path are untouched) but override the header blocks to reproduce `generic/object.html`'s header verbatim, so switching between any of the object's tabs keeps identical chrome:

- `{% block page-header %}` — breadcrumb (`action_url object 'list'`) + object identifier + `{{ block.super }}`.
- `{% block title %}{{ object }}{% endblock %}` — the object name (not "Settings for …").
- `{% block subtitle %}` — created/updated timestamps.
- `{% block controls %}` — `plugin_buttons` + Bookmark/Subscribe + `action_buttons actions object` (Clone/Edit/Delete) + `custom_links`.
- `{% block tabs %}` — the full object tab strip: primary detail tab (`object.get_absolute_url`) + `{% model_view_tabs object %}` (navigable `<a href>` per `ViewTab`: Settings / SSH / Terminal / Sync Jobs / Templates …).

This needs `{% load buttons custom_links helpers perms plugins tabs %}` and two context vars `ObjectEditView` does not inject: `tab` (highlights the current tab; primary tab gated on `{% if not tab %}`) and `actions` (for the Clone/Edit/Delete buttons). Both `ProxmoxEndpointSettingsView` and `ProxmoxEndpointSSHSettingsView` therefore mix `ActionsMixin` (`actions = (CloneObject, EditObject, DeleteObject)`) and return `{"tab": self.tab, "actions": self.get_permitted_actions(...)}` from `get_extra_context`. `EditObject`/`DeleteObject`/`CloneObject.render()` only need `perms`/`request` from context (both present), so this is render-safe. The edit form still renders because `object_edit.html`'s content pane is hardcoded `tab-pane show active`. Guarded by `tests/test_frontend_contracts.py::{test_proxmox_endpoint_edit_subpages_keep_object_tab_strip, test_proxmox_endpoint_edit_subpages_render_shared_object_header}` and `tests/test_proxmox_endpoint_settings_view.py::{test_*_mixes_actions_mixin, test_*_exposes_actions_for_header_buttons, test_*_exposes_tab_for_active_highlight}`.

## ProxmoxEndpoint Overwrite Behavior tab (`proxmoxendpoint_overwrite_behavior.html`)

`proxmoxendpoint_overwrite_behavior.html` (rendered by `ProxmoxEndpointOverwriteBehaviorView`, an `ObjectView` at path `overwrite-behavior`, tab **Overwrite Behavior**, weight 905) is the read-only view of the resolved sync-overwrite behavior that used to be the **Sync Overwrite Behavior** card on the endpoint detail page. It extends `generic/object.html` (so it reuses the shared object header + tab strip) and its `{% block content %}` splits the `overwrite_*` flags into **Bootstrap nav-tabs sub-tabs by category** — Device / Virtual Machine / Cluster / Node Interface / Storage / VM Interface / IP Address — matching `OVERWRITE_FIELD_GROUPS` and the Settings edit tab's grouping. Each sub-tab pane is an `attr-table` of that group's fields with the effective value (`Yes`/`No`) + origin badge (`override` when set on the endpoint, else `global`). The context var `overwrite_row_groups` = `[(group_label, [{field, label, value, is_override}, …]), …]` is built by `_build_overwrite_row_groups()` in `views/endpoints/proxmox.py` from `instance.effective_overwrites()`. The old flat `overwrite_rows` card was removed from `proxmoxendpoint.html`. Guarded by `tests/test_overwrite_behavior_view.py`. The card header carries a change-permission-gated **Edit** button (`{% action_url object 'settings' %}#proxbox-settings-overwrite`) that deep-links to the Settings page's **Sync Overwrite** sub-tab; the Settings template's inline tab script activates the pane targeted by `location.hash` (after the validation-error focus) so the link lands on the right sub-tab.

## ProxmoxEndpoint Sync Jobs tab (`proxmoxendpoint_sync_jobs.html`)

`proxmoxendpoint_sync_jobs.html` (rendered by `ProxmoxEndpointSyncJobsTabView`, path `sync-jobs`, weight 875) lists this endpoint's Proxbox sync jobs **and** hosts a **Create Sync Job** modal for scheduling an immediate or recurring routine scoped to the viewed endpoint. The card header carries a `perms.core.add_job`-gated **Create Sync Job** button (disabled with a tooltip when `object.enabled` is false, mirroring the detail page's Sync Now). The Bootstrap modal (`#proxbox-create-sync-job-modal`) posts back to the tab's own URL (`plugins:netbox_proxbox:proxmoxendpoint_sync_jobs`), which the `ObjectView` handles via a `post()` method. It renders a **subset** of `ScheduleSyncForm` — `job_name`, `sync_types` (Bootstrap checkboxes), `schedule_at` (DateTimePicker), `interval_value`, `interval_unit` — and deliberately **omits the `proxmox_endpoints`/`netbox_endpoints` pickers** (the target endpoint is fixed to the current one and shown as a read-only "Target endpoint" note; the server hard-scopes to it regardless of POST body). On a validation error the view re-renders this template with `show_create_modal=True`, and the `{% block javascript %}` auto-opens the modal (`bootstrap.Modal.getOrCreateInstance(...).show()`) so field errors are visible. All JS is inline (no `collectstatic` dependency). Scheduling rides `core.Job` + `ProxboxSyncJob` + django_rq — **no NMS dependency**. Guarded by `tests/test_sync_jobs_create_contracts.py` (template/AST) and `tests/test_endpoint_sync_job_create.py` (handler behavior).

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
