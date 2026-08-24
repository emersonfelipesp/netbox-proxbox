# Background Jobs

Proxbox uses NetBox's built-in RQ-based background job system for asynchronous and scheduled operations.

## Scheduled Sync

The primary background job feature is scheduled recurring sync. See [Scheduled Sync](./scheduled-sync.md) for full documentation covering:

- Starting the RQ worker
- Scheduling a sync from the UI
- Viewing job status, logs, and errors
- How recurring intervals work
- Cancelling jobs

## NetBox Job Infrastructure

All Proxbox background jobs are stored in NetBox's `core.models.Job` table and are visible under **Operations > Background Jobs**. No separate job database or external service is required beyond the Redis instance already needed by NetBox.

## The Sync Jobs page

**Proxbox > Sync & Operations > Sync Jobs** opens `/plugins/proxbox/jobs/`, a
Proxbox-only view of that same job table. NetBox's own **Operations > Background
Jobs** page lists *every* job in the instance — reports, custom scripts, and any
other plugin's background work — so this page applies a Proxbox filter and shows
nothing else.

It is the core job list underneath, so the familiar filtering, sorting,
pagination, column selection, and CSV/export controls all work exactly as they
do on the NetBox page. Bulk delete is deliberately omitted: its confirmation
flow returns to the unfiltered core list. Delete a job from its detail page, or
from **Operations > Background Jobs**, when you need to.

## Reporting a failed sync

Jobs that finish in an **errored** or **failed** state — or in a status NetBox
does not recognise — carry a **Bug report** action. On the Sync Jobs list it is
a per-row button that opens the job; on the job's own page it opens a modal
containing the environment metadata, the error, and the job log, with a
copy-to-clipboard box and a link that pre-fills a new issue on
[the netbox-proxbox issue tracker](https://github.com/emersonfelipesp/netbox-proxbox/issues).

### What gets anonymized

Sync errors and logs routinely mention things that should not be posted in
public. Before anything is shown to you, the report is scrubbed: hostnames and
FQDNs, IPv4/IPv6 and MAC addresses, URLs, e-mail addresses, Proxmox realm
principals such as `root@pam`, and credential values (`PVEAPIToken`,
`Authorization`, and generic `password=` / `token=` / `secret=` pairs) are
replaced with placeholders.

Placeholders are **stable within a report**: the same host is `<host-1>`
everywhere it appears, so a maintainer can still follow which node failed which
stage without learning what it is called. The same scrubbed text is used for the
modal, the clipboard copy, and the pre-filled issue link — there is no path that
publishes the raw text.

Plugin and NetBox version numbers, timestamps, job IDs, and status values are
kept as-is; they carry nothing identifying and are what make a report
actionable.

!!! warning "Review before you submit"
    Scrubbing is best-effort. A bare, single-word Proxmox node name in a log
    message (`pve-node-01`) looks like any other identifier and may survive, and
    a host under an unusual domain suffix can be missed when it appears outside
    a URL. Read the report before posting it.
