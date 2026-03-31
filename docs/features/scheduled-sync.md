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
