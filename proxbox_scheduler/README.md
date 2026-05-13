# proxbox-scheduler

Standalone container that triggers periodic [Proxbox](https://github.com/emersonfelipesp/netbox-proxbox)
syncs on a configurable cadence. Tracks [netbox-proxbox#372](https://github.com/emersonfelipesp/netbox-proxbox/issues/372).

This container owns **no NetBox model, no plugin config, and no shared
state** — all configuration is environment variables. It is the recommended
path when:

- the NetBox container is managed by a tenant who cannot host extra cron
  units (managed-NetBox, Kubernetes), or
- you need `cron=<expression>` semantics that NetBox's built-in
  ``Job.interval`` (minutes-only, ≥1 minute floor) does not support, or
- you need `continuous` zero-gap reconciliation, which NetBox's
  ``JobRunner.handle()`` cannot produce.

For the common case of "run a full sync every N minutes" on a NetBox
container you control, prefer the NetBox-side **Schedule Sync** form
(``netbox_proxbox.forms.ScheduleSyncForm``) — it is already shipped, is
persisted in NetBox, and is observable under **Background Jobs**.

## Modes

| `PROXBOX_MODE`            | Behaviour                                                                                                          |
| ------------------------- | ------------------------------------------------------------------------------------------------------------------ |
| `off`                     | scheduler disabled (no-op exit; container exits 0)                                                                 |
| `interval=<seconds>`      | trigger every `<seconds>` seconds, measured from the *start* of each trigger; sub-minute is supported              |
| `continuous`              | trigger again immediately after the previous trigger returns; applies a configurable backoff on failure            |
| `cron=<5-field cron>`     | trigger at each cron fire time, evaluated in `PROXBOX_SCHEDULER_TZ`                                                |

## Invocation strategies

Set `PROXBOX_SCHEDULER_INVOKE=http` (default) or `exec`.

### `http`

Calls `GET /full-update/stream` on `PROXBOX_API_URL` with the
`X-Proxbox-API-Key` header, blocking on the SSE stream until a terminal
event (`complete` / `done` / `error` / …). Works for managed-NetBox /
Kubernetes deployments where the scheduler cannot share runtime with
NetBox.

### `exec`

Runs a subprocess (defaults to `python manage.py proxbox_sync --wait
--enqueue-once`). Requires the scheduler to share the NetBox runtime
(e.g. an extended NetBox image or a `docker exec` wrapper). The
`--enqueue-once` flag uses ``JobRunner.enqueue_once()`` advisory-lock
dedup, so the scheduler coexists with any pending NetBox-side recurring
schedule without double-runs.

Override the command with `PROXBOX_SCHEDULER_EXEC_CMD` (shell-tokenized).

## Environment reference

| Variable                                    | Default                                              | Notes                                                                                          |
| ------------------------------------------- | ---------------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| `PROXBOX_MODE`                              | `off`                                                | see table above                                                                                |
| `PROXBOX_SCHEDULER_INVOKE`                  | `http`                                               | `http` or `exec`                                                                               |
| `PROXBOX_SCHEDULER_TZ`                      | `UTC`                                                | IANA timezone for cron evaluation                                                              |
| `PROXBOX_SCHEDULER_BACKOFF_ON_ERROR_SECONDS`| `30`                                                 | extra delay after any failed trigger; applies to every mode                                    |
| `PROXBOX_SCHEDULER_LOG_LEVEL`               | `INFO`                                               | passed to `logging.setLevel`                                                                   |
| `PROXBOX_SCHEDULER_LOG_JSON`                | `true`                                               | set to `false` for human-readable logs                                                         |
| `PROXBOX_API_URL`                           | _(required for `http` invoke when mode ≠ off)_       | base URL of the proxbox-api service                                                            |
| `PROXBOX_API_KEY`                           | _(empty)_                                            | `X-Proxbox-API-Key` header value                                                               |
| `PROXBOX_API_TIMEOUT`                       | `7200`                                               | seconds; applies to both `http` SSE read and `exec` subprocess wait                            |
| `PROXBOX_API_VERIFY_SSL`                    | `true`                                               | disable for self-signed certs in dev                                                           |
| `PROXBOX_SCHEDULER_EXEC_CMD`                | `python manage.py proxbox_sync --wait --enqueue-once`| shell-tokenized; only consulted when `PROXBOX_SCHEDULER_INVOKE=exec`                           |

## Quick start

```bash
docker build -t proxbox-scheduler:0.0.15 proxbox_scheduler/

docker run --rm \
  -e PROXBOX_MODE='cron=0 */4 * * *' \
  -e PROXBOX_SCHEDULER_TZ=America/Sao_Paulo \
  -e PROXBOX_API_URL=http://proxbox-api:8000 \
  -e PROXBOX_API_KEY=changeme \
  proxbox-scheduler:0.0.15
```

A complete compose snippet lives in [`docker-compose.example.yml`](./docker-compose.example.yml).

## Coordination with NetBox-side scheduling

If you already use the **Schedule Sync** form to enqueue a recurring
NetBox `Job.interval`, you can still safely run this scheduler in `exec`
mode: the default command passes `--enqueue-once`, which short-circuits
on the advisory lock keyed by `(ProxboxSyncJob, instance=None)`. The
result is that a pre-existing pending recurring schedule is reused
rather than duplicated.

`http` invocation cannot dedup against NetBox-side schedules; if you
choose `http`, make `PROXBOX_MODE` and the NetBox-side schedule
non-overlapping (e.g. NetBox-side off when the container is active).

## Testing

```bash
cd proxbox_scheduler/
pip install -e ".[test]"
pytest
```

Unit tests cover env parsing, cron evaluation, both invokers (mocked
``requests.Session`` and ``subprocess.run``), and every mode of the
runner loop with a controllable sleeper / clock.
