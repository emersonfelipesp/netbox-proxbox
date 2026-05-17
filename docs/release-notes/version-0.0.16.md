# Version 0.0.16

## Summary

Version `0.0.16` fixes the operational cluster dashboard panel so it reports
the correct node totals when Proxmox cluster members exceed what the live
`/proxmox/cluster/status` payload returns and when sibling `ProxmoxNode`
rows are only discoverable by cluster name. It pairs with backend
`proxbox-api 0.0.12` — the entire fix lives in the plugin's
dashboard data layer; no migration, no model change, no new persisted state.

It fixes one issue:

- [Issue #455](https://github.com/emersonfelipesp/netbox-proxbox/issues/455):
  the **Cluster Dashboard panel** on the Proxmox-endpoint detail page showed
  incorrect online / offline / total node counts. Two cooperating bugs were
  responsible:
  1. `cluster_summary_from_node_rows` unconditionally overrode the
     API-reported `nodes_total` / `nodes_online` with the count of locally
     rendered rows, so any time the live node row list was a strict subset of
     the cluster's real membership the total collapsed to whatever was
     rendered.
  2. `build_local_node_rows` only consulted sibling `ProxmoxNode` records
     when both the cluster name and the scoped sibling-cluster-names set were
     populated. Endpoints whose siblings could only be matched by name (the
     common case for freshly imported clusters that have not yet linked to a
     NetBox `Cluster` object) silently dropped every sibling row.
  3. There was no signal in the rendered node list for cluster members that
     existed in the cluster status payload but had not been synced yet — they
     simply vanished from the panel.

## #455 — Cluster dashboard panel reports correct node totals

The fix is split across three small dashboard helpers in
`netbox_proxbox/views/dashboard_data.py` plus one wiring change in
`netbox_proxbox/views/dashboard.py`:

- **`cluster_summary_from_node_rows` preserves API totals (B1).** When the
  API-reported `nodes_total` is greater than the count of live node rows we
  rendered, the helper now keeps the larger API total and the API's
  `nodes_online` count instead of silently overriding both. The override path
  remains in place only when the live rows are richer than the API summary
  (e.g. the API is incomplete), so existing behavior on healthy clusters is
  unchanged.
- **`build_local_node_rows` broadens sibling lookup by cluster name (B2).**
  The DB sibling query now fires whenever `cluster_name` is set; the
  `scoped_cluster_names` filter is applied only when present. Freshly
  imported clusters that have not yet linked to a NetBox `Cluster` object
  surface every sibling row instead of going blank.
- **`append_unsynced_node_placeholders` renders pending members (B3).** A new
  helper appends `{"name": <member>, "status": "unknown"}` placeholder rows
  for every cluster member named in the API status payload that did not
  match a synced `ProxmoxNode`. The dashboard panel now visibly distinguishes
  "synced and offline" from "not yet discovered".
- **Dashboard view wires the placeholders (B3 cont.).** `dashboard.py` calls
  `append_unsynced_node_placeholders` between `merge_node_rows` and
  `cluster_summary_from_node_rows` so the summary recount sees the full
  membership.

### Regression tests

Three new tests in `tests/test_dashboard.py` pin the fix:

1. API-reported totals survive when the live node rows are a strict subset.
2. Sibling rows are returned when only the cluster name is set
   (no `scoped_cluster_names`, no endpoint linkage).
3. Placeholder rows are appended for members named by the API that have no
   matching local `ProxmoxNode`.

## Compatibility

| NetBox | netbox-proxbox | proxbox-api | netbox-sdk | proxmox-sdk |
|--------|----------------|-------------|------------|-------------|
| >=4.5.8 | v0.0.16 | v0.0.12 | v0.0.8.post1 | v0.0.3.post1 |
| >=4.5.8 | v0.0.15 | v0.0.11 | v0.0.8.post1 | v0.0.3.post1 |

NetBox compatibility range: `4.5.8` – `4.6.99` (unchanged). Certified
simultaneously against NetBox `v4.5.8`, `v4.5.9`, and official `v4.6.0`.

## Upgrade Notes

- No database migration. No model change. No `OVERWRITE_FIELDS` change.
- Restart the NetBox WSGI process so the patched dashboard module is loaded.
- The plugin pairs with `proxbox-api 0.0.12`; the dashboard panel fix does
  not depend on backend changes.
