# Proxbox Scheduler Container

Issue: [#372](https://github.com/emersonfelipesp/netbox-proxbox/issues/372)
Version: ships in `netbox-proxbox 0.0.15`

A standalone container that fires periodic Proxbox sync triggers without
asking the operator to install a cron unit on the NetBox host. Code and
build artefacts live in [`proxbox_scheduler/`](../../proxbox_scheduler/).

This page is the operator-facing summary. For the full
environment-variable reference and developer notes, see
[`proxbox_scheduler/README.md`](../../proxbox_scheduler/README.md).

## When to use it

| Situation                                                                                | Use the scheduler? |
| ---------------------------------------------------------------------------------------- | ------------------ |
| On-prem NetBox you control, want a recurring sync every N minutes                        | **No** — use the NetBox-side **Schedule Sync** form (it's already shipped) |
| Need `cron=<expression>` semantics (e.g. `0 */4 * * *`)                                  | **Yes**            |
| Need `continuous` zero-gap reconciliation (NetBox enforces a 1-minute floor on intervals)| **Yes**            |
| Managed-NetBox tenant who cannot ship a cron unit inside the NetBox container            | **Yes**            |
| Want sub-minute interval triggers                                                        | **Yes**            |

## How it relates to NetBox-side scheduling

NetBox's [`JobRunner.handle()`](https://github.com/netbox-community/netbox/blob/main/netbox/netbox/jobs.py)
already auto-reschedules periodic jobs in its `finally` block, with a hard
floor of `now + 1 minute`:

```python
if job.interval:
    new_scheduled_time = max(
        (job.scheduled or job.started) + timedelta(minutes=job.interval),
        timezone.now() + timedelta(minutes=1),
    )
    cls.enqueue(..., schedule_at=new_scheduled_time, interval=job.interval, ...)
```

That covers the **`interval` ≥ 60s** case, which is what
`ScheduleSyncForm` (and the **Schedule Sync** quick action on the
plugin home dashboard) configures. The scheduler container ships only to
cover the genuinely new capabilities: cron expressions, zero-gap
continuous loops, and the managed-NetBox deployment shape.

## Coexistence: `--enqueue-once`

When the scheduler invokes the management command (`exec` invocation,
default), it passes `--enqueue-once`. This routes through
`ProxboxSyncJob.enqueue_once()` (inherited from NetBox's `JobRunner`),
which is keyed on the advisory lock `('job-schedules', class, instance)`
and:

- reuses an existing pending recurring schedule if one exists, or
- creates a fresh one otherwise.

The practical effect: if an operator also configures the NetBox-side
**Schedule Sync** form, the scheduler container's invocation no-ops on
top of that pending schedule rather than enqueuing a duplicate run.

`http` invocation cannot use this dedup. If you choose `http`, ensure
NetBox-side scheduling and the container do not overlap.

## Modes at a glance

```
PROXBOX_MODE=off                       # disabled
PROXBOX_MODE=interval=30               # fire every 30 seconds
PROXBOX_MODE=continuous                # back-to-back, no gap (with error backoff)
PROXBOX_MODE='cron=0 */4 * * *'        # every 4 hours on the hour
```

Set `PROXBOX_SCHEDULER_TZ=America/Sao_Paulo` (or any IANA zone) to fix
the cron evaluation timezone.

## Running it

The minimal Compose snippet lives at
[`proxbox_scheduler/docker-compose.example.yml`](../../proxbox_scheduler/docker-compose.example.yml).
Copy it into your stack and edit the env vars to match your environment.

```bash
docker build -t proxbox-scheduler:0.0.15 proxbox_scheduler/
docker run --rm \
  -e PROXBOX_MODE='cron=0 */4 * * *' \
  -e PROXBOX_SCHEDULER_TZ=America/Sao_Paulo \
  -e PROXBOX_API_URL=http://proxbox-api:8000 \
  -e PROXBOX_API_KEY=changeme \
  proxbox-scheduler:0.0.15
```

## Acceptance-criteria checklist

These items are covered by the test suite in
[`proxbox_scheduler/tests/`](../../proxbox_scheduler/tests/) and by
`tests/management/test_proxbox_sync.py`:

- [x] `off`, `interval`, `continuous`, and `cron` modes all parse from env
- [x] `cron` honours `PROXBOX_SCHEDULER_TZ`
- [x] HTTP invocation reads SSE until terminal event, fails closed on connection error
- [x] Exec invocation maps non-zero exit codes to `InvokeResult.failed`
- [x] Error backoff is applied after any failed trigger (every mode)
- [x] `proxbox_sync --enqueue-once` routes through `JobRunner.enqueue_once()` so the scheduler coexists with NetBox-side recurring schedules without double-runs
