# Headless sync — `proxbox_sync` management command

The `proxbox_sync` Django management command triggers a full Proxmox→NetBox
sync from the NetBox shell. It is the headless equivalent of clicking the
**Full Update** button on the plugin home page and is the supported entry
point for cron jobs, systemd timers, Kubernetes `CronJob`s, CI smoke tests,
and runbook automation.

## What it does

`proxbox_sync` enqueues the same `ProxboxSyncJob` that the UI's
**Full Update** button enqueues:

- Queue: NetBox's default RQ queue (`default`).
- Sync types: `[SyncTypeChoices.ALL]` — all stages.
- Endpoints: every configured `ProxmoxEndpoint`.
- Job timeout: `PROXBOX_SYNC_JOB_TIMEOUT` (7200 seconds).

The job appears under **Background Jobs** in NetBox identical to a
UI-triggered sync, so the existing job-detail page, log stream, and
**Cancel job** / **Run now** controls all work unchanged.

## Usage

```bash
python manage.py proxbox_sync
```

Common variants:

```bash
# Block until the job finishes; exit code mirrors the job's terminal status.
python manage.py proxbox_sync --wait

# Run as a specific user (overrides the default oldest active superuser).
python manage.py proxbox_sync --user automation

# Bound the wait loop (default: 7200s).
python manage.py proxbox_sync --wait --timeout 1800

# Poll less aggressively while waiting (default: 2.0s).
python manage.py proxbox_sync --wait --poll-interval 5

# Fail fast if no RQ worker is consuming the default queue (default: 30s).
python manage.py proxbox_sync --wait --worker-grace 10
```

## Flags

| Flag | Default | Purpose |
|---|---|---|
| `--user USERNAME` | oldest active superuser | Username to attribute the job to. Used for audit and job ownership. |
| `--wait` | off | Block until the job reaches a terminal state; exit code mirrors the job's status. |
| `--timeout SECONDS` | `7200` | Upper bound on the `--wait` loop. Matches `PROXBOX_SYNC_JOB_TIMEOUT`. |
| `--poll-interval SECONDS` | `2.0` | Seconds between job-status polls while `--wait` is set. |
| `--worker-grace SECONDS` | `30.0` | Maximum seconds the job may stay pending before the command checks for an active RQ worker and fast-fails if none is found. |
| `--enqueue-once` | off | Route through `JobRunner.enqueue_once()` so the command reuses an already-pending recurring schedule instead of duplicating it. Designed for the [`proxbox-scheduler`](../scheduler/README.md) container so it coexists with the NetBox-side **Schedule Sync** form. |

## Exit codes

| Exit code | Condition |
|---|---|
| `0` | Job enqueued (and, with `--wait`, finished with status `completed`). |
| non-zero | Any of: no `FastAPIEndpoint` configured · `proxbox-api` unreachable on `/health` · no usable user · `ProxboxSyncJob.enqueue` raised · with `--wait`, job ended in `errored` / `failed` or timed out / no worker available. |

All failure paths emit an actionable message to stderr via Django's
`CommandError` so cron / systemd capture useful logs.

## RQ worker requirement

`proxbox_sync` only **enqueues** the job. An RQ worker on the `default`
queue must be running for the job to actually execute. With `--wait`,
the command probes `django_rq.get_queue("default").workers` after
`--worker-grace` seconds and fails fast if no worker is consuming the
queue — useful in CI and during deployment-window automation.

Without `--wait`, the command returns the moment the job is enqueued.
A long-pending job in the **Background Jobs** UI usually means the
worker is not running.

See the
[Backend integration notes in the top-level `CLAUDE.md`](../../CLAUDE.md#backend-integration-notes)
for the full RQ queue / timeout model.

## Example: cron

Run a full sync every six hours:

```cron
0 */6 * * * cd /opt/netbox && /opt/netbox/venv/bin/python manage.py proxbox_sync --wait --timeout 7200
```

## Example: systemd timer

`/etc/systemd/system/proxbox-sync.service`:

```ini
[Unit]
Description=ProxBox full sync (headless)
After=netbox-rq.service

[Service]
Type=oneshot
WorkingDirectory=/opt/netbox
ExecStart=/opt/netbox/venv/bin/python manage.py proxbox_sync --wait --timeout 7200
```

`/etc/systemd/system/proxbox-sync.timer`:

```ini
[Unit]
Description=Run proxbox-sync every 6 hours

[Timer]
OnCalendar=0/6:00
Persistent=true

[Install]
WantedBy=timers.target
```

Enable:

```bash
systemctl daemon-reload
systemctl enable --now proxbox-sync.timer
```

## Related

- UI equivalent: **Full Update** button on the plugin home page
  (`SyncFullUpdateView` in `netbox_proxbox/views/sync.py`).
- Token-status diagnostics: `python manage.py proxbox_fix_tokens`.
- Sync internals: [`netbox_proxbox/jobs.py`](../../netbox_proxbox/jobs.py).
- Container-based scheduler with cron/continuous modes: [`docs/scheduler/README.md`](../scheduler/README.md) (issue #372).
