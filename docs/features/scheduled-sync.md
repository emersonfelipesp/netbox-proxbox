# Scheduled Sync

Proxbox supports scheduled and recurring sync operations using NetBox's built-in background job system. You can configure a sync to run once at a specific time or repeat on an interval (e.g. daily at 02:00).

## Prerequisites

Scheduled sync requires a running **NetBox RQ worker**. Proxbox sync jobs use NetBox’s **`default`** queue, so the stock worker command (no queue arguments) is enough. Without any worker, jobs stay **`pending`** or **`scheduled`**.

Start the worker alongside your other NetBox services:

```bash
cd /opt/netbox/netbox
source /opt/netbox/venv/bin/activate
python3 manage.py rqworker
```

!!! tip
    This is the same worker NetBox uses for other background tasks (`high`, `default`, `low`). Older deployments may still have systemd units that only listen on `netbox_proxbox.sync`; those jobs will not run until you use a worker that includes **`default`** (or re-queue jobs after upgrading the plugin).

### systemd Unit

Use your existing NetBox RQ worker unit if one is already enabled (`netbox-rq` or similar). If you maintain a custom unit, ensure **`ExecStart`** runs `manage.py rqworker` with no queue list **or** explicitly includes **`default`**. Example:

```ini
[Unit]
Description=NetBox RQ Worker
After=redis.service netbox.service
Requires=redis.service

[Service]
Type=simple
User=netbox
Group=netbox
WorkingDirectory=/opt/netbox/netbox
ExecStart=/opt/netbox/venv/bin/python3 manage.py rqworker
Restart=on-failure
RestartSec=30

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now netbox-rq
```

## Scheduling a Sync

1. In NetBox, navigate to **Proxbox > Schedule Sync**.
2. Choose one or more **Sync types** (checkboxes):
    - **All** — full update in one backend stream (devices, storage, VMs, disks, backups, snapshots). Do not combine with other types.
    - **Devices** — sync Proxmox nodes as NetBox devices.
    - **Storage** — sync Proxmox storage records.
    - **Virtual Machines** — sync Proxmox VMs as NetBox virtual machines.
    - **VM Disks** — sync VM virtual disks (run after VMs exist in NetBox).
    - **VM Backups** — sync all VM backup records.
    - **VM Snapshots** — sync all VM snapshot records.
    - **Backup Routines** — sync Proxmox vzdump backup schedules.
    - **Replications** — sync Proxmox storage replication jobs.

    When you pick several types (not **All**), the job runs them **in order**: devices → storage → virtual machines → VM disks → VM backups → VM snapshots, skipping any type you did not select.
3. Optionally set a **Schedule at** time. Leave blank to run immediately.
4. Optionally set a **Recurs every** interval in minutes. Common values:
    - `1` — every minute
    - `60` — every hour
    - `1440` — every day (daily)
    - `10080` — every week (weekly)
5. Click **Schedule**.

After scheduling, you are redirected to the NetBox job list where you can track the job's status.

### Examples

| Goal | Schedule at | Interval |
|------|------------|----------|
| Run immediately, once | *(blank)* | *(blank)* |
| Run once at 2026-04-01 02:00 | `2026-04-01 02:00` | *(blank)* |
| Run every day starting now | *(blank)* | `1440` |
| Run every day starting at 02:00 | `2026-04-01 02:00` | `1440` |
| Run every hour starting at next hour | `2026-04-01 13:00` | `60` |

## Viewing Job Status and Logs

All scheduled sync jobs appear in the standard NetBox job list:

- **Proxbox > Sync Jobs** (shortcut in the plugin menu)
- **Operations > Background Jobs** (NetBox's built-in page)

Each job record shows:

| Field | Description |
|-------|-------------|
| **Status** | `scheduled`, `pending`, `running`, `completed`, `errored`, or `failed` |
| **Scheduled** | When the job is/was scheduled to run |
| **Started / Completed** | Execution timestamps |
| **Interval** | Recurrence interval in minutes (blank for one-time jobs) |
| **Data** | JSON from the ProxBox backend: single payload for **All**, or a `stages` list when multiple types ran |
| **Error** | Error message if the job failed |

### Structured Logs

Click on a job and open the **Log** tab to see structured log entries recorded during execution. These include:

- `INFO: Starting Proxbox sync stages: ...` — when the job begins (listed stages)
- `INFO: Sync completed successfully (HTTP 202)` — on success
- `ERROR: Sync failed (HTTP <status>): <detail>` — on failure, with the backend error message

### When a Sync Fails

Read the **first** preflight lines of the log before the stage error. Every run
begins by pushing your NetBox and Proxmox endpoint records into proxbox-api,
and a problem there usually surfaces later as a confusing error about whatever
the backend happened to try first.

| Log line | What it means | What to do |
|---|---|---|
| `Proxbox preflight failed: no usable proxbox-api backend is configured in NetBox (...)` — job stops immediately, before any stage | NetBox has no enabled FastAPI endpoint, or the selected one has no URL. Every sync stage runs through that backend, so none of them can run. | Add or enable a FastAPI endpoint under **Proxbox > Endpoints > FastAPI**, then re-run the sync. When the job was scheduled against a specific backend the message names it as `selected endpoint id <n>` — check that that row still exists and is enabled. |
| `Proxbox preflight failed: proxbox-api holds no NetBox endpoint and this run could not push one (...)` — job stops immediately, before any stage | proxbox-api has no NetBox credentials, so it cannot write anything. Typical on a fresh install where the backend was unreachable when the endpoint was saved, or where NetBox itself has no enabled `NetBoxEndpoint` row to push. | The message names the backend URL it tried. Confirm proxbox-api is running and reachable there, check the FastAPI endpoint token in **Proxbox > Endpoints**, confirm an enabled NetBox endpoint exists, then re-run the sync. |
| `Proxbox preflight failed: this NetBox has no enabled NetBox endpoint, so proxbox-api is not authorized to write to it` — job stops immediately, before any stage | Every `NetBoxEndpoint` row here is disabled or missing. This is a **hard stop, not a warning**, and the backend's stored rows are deliberately not consulted — proxbox-api may still hold credentials from before the row was disabled, and honouring them would keep writing with exactly the authorization you revoked. | Enable (or create) the NetBox endpoint under **Proxbox > Endpoints**, then re-run the sync. If you disabled it on purpose, the run stopping is the intended behaviour. |
| `Skipping SSE sync entirely: no enabled Proxmox endpoint exists in NetBox ...` or `... every Proxmox endpoint selected for this run is disabled or no longer exists` — job fails without running a stage | There was nothing in scope to sync. Running **without** an endpoint filter is not a fallback: proxbox-api would read an empty scope as "sync every endpoint you still hold", including ones disabled here. | Enable at least one Proxmox endpoint under **Proxbox > Endpoints**, or re-scope the schedule to endpoints that still exist. |
| `Selected-object sync did not run: no enabled Proxmox endpoint exists in NetBox ...` / `... every Proxmox endpoint selected for this run is disabled or no longer exists` / `... none of the enabled Proxmox endpoints is registered with this ProxBox backend under a matching connection target` — a **sync selected objects** run stops before contacting proxbox-api | Same rule as the row above, applied to the selected-object path. It reaches proxbox-api through a different route, but that route resolves its Proxmox sessions through the *same* dependency — so an unscoped request is the **widest** one the backend accepts, not a narrower one. Nothing is sent. | Enable at least one Proxmox endpoint under **Proxbox > Endpoints**. If the endpoints are enabled but unregistered, fix the endpoint push first (the rows below cover the failed-push and retargeted-host cases), then retry the selection. |
| `Selected-object sync is scoped to <n> fewer Proxmox endpoint(s) than are enabled; unresolved endpoint id(s): ...` — warning, run continues | Some enabled endpoints resolved to a backend id and some did not. The run proceeds on the ones that did, because a narrowed scope is still far safer than an unscoped one. Objects belonging to a skipped endpoint are refused by name (next row) rather than asked of the remaining endpoints. | Not fatal. If one of your selected objects then fails, this line names the endpoints that were left out; fix their push (see the retargeted-host row) and retry. |
| `The Proxmox endpoint this object belongs to (id <n>) is not in this run's endpoint scope, so it was not synced.` — that **one selected object** fails, the rest of the batch runs | Its endpoint was skipped (the row above), and the object was not re-asked of the remaining endpoints on purpose. A selected-object request names only a cluster, a node and a VMID, and those are unique **per endpoint**, not across your estate — so if another Proxmox installation happens to have a `cluster01/pve1/100` too, it would answer, and *its* data would be written into this NetBox row with no error anywhere. | Fix the skipped endpoint's push (see the retargeted-host row below), then re-select that object. Objects on the endpoints that did resolve are unaffected and have already synced. |
| `This object's Proxmox cluster is claimed by more than one Proxmox endpoint (ids <a>, <b>) ...` — that **one selected object** fails, the rest of the batch runs | Two enabled Proxmox endpoints have each reflected a `ProxmoxCluster` for this object's cluster, so which estate the object actually lives on cannot be determined. That is not a missing-data problem — it is *proof* the duplicated-name situation described in the row above exists in your estate right now. Asking both claimants would write whichever answered first; picking one would be a guess. | The message names every claiming endpoint id. Open **Proxbox > Clusters**, find the duplicate reflected cluster (usually left over from an endpoint that was re-pointed at a different Proxmox installation), delete the stale one, then re-select the object. |
| `Batch sync failed for <n> selected <type> object(s) — failed object(s): <id> (<status>: <error>); ...; and <k> more` — the **whole job** fails | At least one object in a *selected-object* run did not sync. Every object in that run was named by you, so there is no "partial success" reading of it: the job fails rather than finishing green with the errors buried in the job data. The per-object statuses and errors are still saved on the failed row, and when branching is enabled the branch is **not** merged, so a partial result is never promoted into main. | The message lists up to ten failed objects with their status and error and summarises the rest — fix those (the two rows above cover the two per-object refusals), then re-select. Objects that did sync are already written and do not need re-selecting. |
| `Proxbox preflight failed: this run could not push its NetBox endpoint (...), and the NetBox endpoint record proxbox-api holds was written with different credentials than this NetBox endpoint now carries` — job stops immediately, before any stage | The stored row *is* yours and reports the right host, port, TLS setting and token version — but its API token was rotated in place since the last successful push, so proxbox-api would keep writing with the credential you just revoked. The backend never returns the token itself, so this is detected against a fingerprint recorded locally by the last successful push. The same message appears when no push has **ever** succeeded (nothing to compare against, which is treated as "changed" on purpose). | Get the push to succeed and the run clears permanently: confirm proxbox-api is reachable at the URL named in the message and that the FastAPI endpoint token in NetBox matches the one it expects, then re-run. After upgrading into this check, the very first sync may hit this row once — that is expected, and one successful push resolves it. |
| `Proxbox preflight failed: this run could not push its NetBox endpoint (...), and the <n> NetBox endpoint record(s) proxbox-api already holds do not point at this NetBox` — job stops immediately, before any stage | The push failed and the backend *does* hold NetBox credentials — but for a different instance. proxbox-api's NetBox endpoint is a single slot that every push overwrites, so a stored row can easily belong to a previous deployment or to another NetBox sharing this backend. Continuing would sync this estate's Proxmox inventory **into their NetBox**. | Fix the push first: confirm proxbox-api is reachable at the URL named in the message, and that the stored row resolves to the same address proxbox-api would dial for this instance — that is `domain` if this NetBox endpoint sets one and `ip_address` only when it does not, plus the same `port`. A stored row on the right address under a *different* name is a different service, and a row that reports no port at all is not something this backend produced. If two NetBox instances genuinely share one proxbox-api, give each its own backend. The same message also appears when the stored row *is* yours but its `verify_ssl` or token version no longer matches what this NetBox declares — you changed the TLS setting or rotated the token scheme, and the push that would have told proxbox-api about it failed, so continuing would have it write under the setting you replaced. Re-run once the push succeeds. |
| `Proxbox preflight failed: this run could not push its NetBox endpoint (...), and could not read back which NetBox endpoint proxbox-api holds either (...)` — job stops immediately, before any stage | Both directions failed, so there is no evidence at all that the backend's credentials belong to this NetBox — only that it may hold somebody's. "Unknown" is not treated as "ours" here, because this branch is only reachable *after* a failed push. | Almost always the backend is down or unreachable rather than misconfigured. Check that proxbox-api is running at the URL named in the message and that the FastAPI endpoint token in NetBox matches the one it expects, then re-run. |
| `Stage '<name>' likely failed because of an earlier problem. Preflight reported: ...` | The stage error is a **symptom**. The preflight hit a non-fatal problem — an unreachable backend, a failed key registration, or a failed Proxmox endpoint push — and it is named in the `Preflight reported:` list. | Fix the preflight problem named in the hint, not the stage the error mentions. |
| `Preflight: the <N>s endpoint-push budget was exhausted; skipped pushing <n> Proxmox endpoint(s) ...` | The preflight spent its whole push budget on the earlier endpoints — usually a slow or half-responsive backend — and stopped pushing so the stages still get to run. The skipped endpoints appear in **Endpoint runtime** as `warning` phases reading `Skipped: the preflight endpoint-push budget of <N>s was exhausted`. | Not fatal: the backend may already hold those rows. If the run then fails on those endpoints, fix the backend's responsiveness first — the log line names exactly which endpoints were never pushed. |
| `<n> Proxmox endpoint(s) were skipped and did not sync — endpoint <id>: ...` or `No sync stage ran: every selected Proxmox endpoint was skipped — ...` — job fails at the end | An endpoint in the run's scope never resolved to a backend id, so no stage ever ran for it. The run used to finish green while silently syncing nothing for that endpoint. | The message names each endpoint and its error. Usually the endpoint was never pushed to proxbox-api — re-check the preflight lines above it for a failed or budget-skipped push, or for the retargeted-endpoint case in the next row. The **Endpoint runtime** breakdown is saved before the failure, so it stays readable on the failed row. |
| `Skipping Proxmox endpoint <id>: ... the backend's stored copy points at <host:port> instead of <host:port>` | You changed this endpoint's domain, IP address, or port in NetBox, and the push that would have told proxbox-api about it failed. The backend still holds the **previous** host under this endpoint's name, so syncing through it would reflect the *old* Proxmox host's VMs, nodes, and storage into NetBox under the renamed endpoint. The endpoint is refused instead, and the message names both hosts. | Get the endpoint push to succeed, then re-run: confirm proxbox-api is reachable, and that the endpoint's `domain` (or its `ip_address` when no domain is set) plus `port` are what you intend. The same check protects the endpoint's **Templates** tab and the **Create new instance** wizard, so both will report the mismatch rather than list or provision onto the wrong host. |
| `Preflight: ...` warnings, then the sync completes | The backend already held a usable record, so the failed push did not matter. | No action needed, though the backend's stored configuration may be stale. |

!!! tip "A backend that is still starting up"
    proxbox-api spends its first few seconds opening its database and resolving
    the NetBox API schema. The preflight waits for it and allows generous
    per-call timeouts, so a slow start is not itself a failure. If preflight
    calls time out repeatedly, the backend is genuinely unreachable — check the
    URL, TLS settings, and firewall rules between NetBox and proxbox-api rather
    than raising timeouts.

## How Recurring Jobs Work

When a job has an `interval` set, NetBox's job system automatically re-schedules the next execution after each run:

1. The job runs at the scheduled time.
2. After completion (success or failure), a new job is enqueued with `scheduled = previous_scheduled + interval`.
3. The minimum re-schedule time is 1 minute in the future.

This means a daily sync at 02:00 will run at 02:00 every day, regardless of how long each execution takes.

!!! note
    Recurring jobs continue to re-schedule even after failures. Check the job list periodically to ensure your syncs are completing successfully.

## Cancelling a Scheduled Job

To stop a recurring sync or cancel a pending one-time job:

1. Go to **Operations > Background Jobs**.
2. Find the job with status `scheduled`.
3. Delete it.

Deleting a scheduled recurring job stops the recurrence chain. No further jobs will be scheduled.

## Architecture

The scheduled sync feature uses NetBox's built-in infrastructure:

- **RQ (Redis Queue)** for job queuing and scheduling
- **`core.models.Job`** for job state, logs, and metadata
- **`JobRunner`** for execution lifecycle and automatic re-scheduling

The plugin registers a `ProxboxSyncJob` runner that calls the same backend HTTP endpoints used by manual sync buttons. The ProxBox FastAPI backend is unaware of scheduling — it receives the same sync requests whether triggered manually or by a background job.

```
User schedules sync
        |
        v
  ScheduleSyncView
        |
        v
  ProxboxSyncJob.enqueue()
        |
        v
  RQ Worker picks up job
        |
        v
  ProxboxSyncJob.run()
        |
        v
  sync_resource() / sync_full_update_resource()
        |
        v
  HTTP GET to proxbox-api backend
        |
        v
  Backend syncs Proxmox -> NetBox
        |
        v
  Job marked completed (or errored)
        |
        v
  If interval set: new job scheduled at scheduled + interval
```
