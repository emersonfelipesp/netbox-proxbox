# Data Protection Calendar

Proxbox provides server-rendered month and ISO-week calendars for backup,
snapshot, replication, and backup-routine inventory. Open **Proxbox > Data
Protection > Data Protection** to view all four sources together, or use the
calendar above the table on any individual Data Protection list page.

## Calendar navigation

The default view is a Monday-first month grid. Use **Month** or **Week** to
change the period, and use **Previous**, **Today**, and **Next** to navigate.
Calendar navigation preserves the current filters, ordering, and page-size
selection. Calendar state uses the `cal_view` and `cal_date` query parameters,
which are separate from the list filter fields.

Events in the displayed calendar window are loaded independently of the
paginated object table. To keep rendering work bounded, each source loads at
most 1,000 rows per request and scheduled sources stop projecting once 1,000
events exist, because a month grid can span 42 days. Active, enabled schedules
are projected before stale or disabled ones, so old jobs cannot crowd current
protection out of the budget. When a limit is reached, a notice states exactly
what was left out in its own units — projected occurrences not shown, scheduled
objects not projected, and whether further rows exist beyond the first 1,000
loaded — and recommends narrower filters or the week view. The plugin never
runs a full count over a large source just to size that notice.

A day displays four event badges initially. Its **+N more** expander renders at
most 40 additional badges and reports any further hidden events. The **Today**
marker follows NetBox's configured `TIME_ZONE`, not the host clock.

## Event sources

- VM backups use `VMBackup.creation_time` and VM snapshots use
  `VMSnapshot.snaptime`. Their timestamps are converted to NetBox's active time
  zone before choosing the calendar day. Records without a timestamp remain in
  the list and are reported by the calendar's undated-record notice.
- Replications and backup routines are projected across the visible dates from
  their Proxmox calendar-event schedule. Weekday lists and ranges, date
  selectors, supported time expressions, and standard aliases are recognized.
  A schedule that consists only of a weekday or date selector (for example
  `sat,sun` or `*-*-01`) is treated as running at `00:00`, matching Proxmox.
- An unknown schedule is deliberately fail-open. It appears on every visible
  day with its original text and an **unparsed schedule** marker, so malformed
  or newly introduced Proxmox syntax is visible instead of disappearing.
- Disabled backup routines, disabled replications, and stale scheduled records
  are shown with muted styling.

Schedule times are displayed as the Proxmox node's local wall-clock time. The
plugin does not currently persist or resolve a time zone for each endpoint, so
it cannot convert those times to NetBox's configured time zone. Per-endpoint
time-zone resolution is deferred to a follow-up change.

## Combined filters and permissions

The combined page can filter by Proxmox cluster, Proxmox node, NetBox virtual
machine, date range, and event kind. Cluster and node filters use the plugin's
typed links to NetBox clusters and devices. Snapshot node names and replication
target names are also considered when a Proxmox node is selected. A backup
routine without a direct VM relationship is excluded when a virtual-machine
filter is active, avoiding an unverified association based only on a numeric
VMID.

Applying the filter form omits `cal_date`, so the calendar re-anchors to **Date
from** while retaining the selected month or week view. A valid explicit
`cal_date` from navigation wins when its visible window intersects the selected
range. If it is stale and does not intersect a complete valid **Date from** and
**Date to** range, the calendar re-anchors to **Date from** instead of showing an
empty grid.

Node-name fallback matching is endpoint-qualified. Snapshot names also require
the selected node's linked NetBox cluster, replication target names also require
the selected node's endpoint, and standalone nodes do not widen snapshot
matching across clusters. A routine scoped to all nodes is included when its
endpoint contains a selected node.

The unified table below the calendar lists at most 500 materialized events for
the visible range and says so when it truncates. The source-limit notice covers
events excluded before that table cap; the week view or narrower filters reduce
both forms of truncation.

Each source queryset is restricted with NetBox object permissions before any
calendar event is built. A user sees only event kinds and objects for which
they have view access. The calendar does not bypass the permissions or filters
of an individual list page.

The calendar is informational. It does not start backups, snapshots,
replications, or routines, and it does not change synchronization behavior.
