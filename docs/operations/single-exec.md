# Scheduled sync — one-shot `docker compose` pattern

This page documents `docs/installation/docker-compose-single-exec.yml`, a
single-container Docker Compose file that runs one full Proxmox→NetBox sync
and exits. It is the lightest of the three supported scheduled-sync
topologies — the others being the long-lived plugin worker (UI-triggered
syncs) and the standalone [`proxbox-scheduler`](../scheduler/README.md)
container (interval/cron/continuous loop).

The compose file is a thin wrapper around the [`proxbox_sync`
management command][headless-sync]. For the command's full flag reference,
exit codes, and RQ-worker requirements, read that page first.

[headless-sync]: ./headless-sync.md

## When to use it

- You already run NetBox via [`netbox-docker`][netbox-docker] and you want
  scheduled syncs without standing up a second long-lived plugin process.
- You drive the schedule from a host crontab, a systemd timer, a
  Kubernetes `CronJob`, or any other one-shot launcher.
- You want each invocation to leave **no residue** — `--rm` deletes the
  container as soon as the sync finishes.

[netbox-docker]: https://github.com/netbox-community/netbox-docker

## How it works

Each invocation:

1. Spins up a single short-lived container from the same NetBox image
   used by your long-lived stack.
2. Installs `netbox-proxbox` into the container (or upgrades it if a newer
   wheel is available).
3. Joins your existing netbox-docker network so it can reach the same
   PostgreSQL, Redis, and RQ workers.
4. Runs `python manage.py proxbox_sync --wait --timeout 7200`.
5. Exits with the job's terminal status — `0` on success, non-zero on
   `proxbox-api` unreachable, errored job, missing endpoint
   configuration, missing user, or no RQ worker on the `default` queue.
6. The `--rm` flag on `docker compose run` deletes the container.

The container does **not** run an RQ worker — it relies on the worker
already running in your long-lived stack to actually execute the enqueued
job. Without a healthy worker on the `default` queue, the command
fast-fails after the `--worker-grace` window (default 30s — see the
[`proxbox_sync` flag reference][headless-sync]).

## Configuration

The container reads all NetBox-side config (`SECRET_KEY`, `ALLOWED_HOSTS`,
`DB_*`, `REDIS_*`, `REDIS_TASK_*`, ...) from the env file you point it at.
The default path is `./env/netbox.env`, which matches the bundled file in
the upstream `netbox-docker` compose project. Tune the wrapper itself via
the small set of variables below — everything else lives in the env file.

| Variable | Default | Purpose |
|---|---|---|
| `NETBOX_IMAGE` | `netboxcommunity/netbox:v4.6.5` | Image tag to run. Use the **same tag** as your long-lived stack so the migrations and schema match. |
| `NETBOX_ENV_FILE` | `./env/netbox.env` | env file consumed by the container. Set to a non-existent path (or `/dev/null`) to disable env_file loading entirely and pass everything via `-e` on the command line. |
| `NETBOX_NETWORK` | `netbox-docker_default` | External Docker network that already hosts your NetBox, PostgreSQL, and Redis. Matches netbox-docker's compose-generated network name. |
| `NETBOX_PROXBOX_PIP_SPEC` | `netbox-proxbox` | PEP 508 spec passed to `uv pip install`. Pin a version (e.g. `netbox-proxbox==0.0.15`) to make scheduled runs reproducible. |
| `PROXBOX_SYNC_TIMEOUT` | `7200` | Forwarded to `--timeout`. Matches `PROXBOX_SYNC_JOB_TIMEOUT`. |
| `PROXBOX_SYNC_USER` | _(unset)_ | Forwarded to `--user`. Defaults to the oldest active superuser. |

## Crontab example

Run a full sync every six hours and append output to a log file:

```cron
0 */6 * * * cd /opt/netbox-docker && docker compose -f /opt/netbox-proxbox/docs/installation/docker-compose-single-exec.yml run --rm netbox >> /var/log/proxbox-sync.log 2>&1
```

Notes:

- `cd /opt/netbox-docker` puts the compose project in the directory whose
  `env/netbox.env` is the operative one. Adjust to wherever your
  long-lived stack lives.
- The redirect to a log file is mandatory in practice — `--rm` deletes the
  container so its stdout disappears with it. The crontab line is the
  only place this output is captured.

## systemd timer example

`/etc/systemd/system/proxbox-sync.service`:

```ini
[Unit]
Description=ProxBox full sync (single-exec compose)
After=docker.service netbox-docker.service
Requires=docker.service

[Service]
Type=oneshot
WorkingDirectory=/opt/netbox-docker
Environment=NETBOX_PROXBOX_PIP_SPEC=netbox-proxbox==0.0.15
ExecStart=/usr/bin/docker compose -f /opt/netbox-proxbox/docs/installation/docker-compose-single-exec.yml run --rm netbox
StandardOutput=append:/var/log/proxbox-sync.log
StandardError=append:/var/log/proxbox-sync.log
```

`/etc/systemd/system/proxbox-sync.timer`:

```ini
[Unit]
Description=Run proxbox-sync every 6 hours

[Timer]
OnCalendar=0/6:00
Persistent=true
RandomizedDelaySec=10m

[Install]
WantedBy=timers.target
```

Enable:

```bash
systemctl daemon-reload
systemctl enable --now proxbox-sync.timer
```

## Concurrent invocations — read this

Two `docker compose run` invocations launched simultaneously will both
enqueue full syncs. The plugin does **not** currently coalesce concurrent
sync jobs, and `proxbox-api` runs them in parallel with no shared lock.

**Pick a schedule interval safely greater than your typical sync
duration.** A six-hour interval is a sensible starting point for most
deployments; a one-hour interval is reasonable only if you have measured
your full sync running in well under an hour. Do **not** invoke the
single-exec compose from two crontabs / timers / runbooks at once.

A real `/sync/active` endpoint and a join-or-fast-fail mode for
`proxbox_sync` are tracked separately; until those land, this is a
documentation-level constraint.

## Smoke test

CI exercises this compose file as part of
[`.github/workflows/e2e-docker.yml`][e2e]: after the e2e stack is healthy
and the plugin endpoints are configured, the workflow runs
`docker compose -f docs/installation/docker-compose-single-exec.yml run --rm netbox`
attached to the e2e network and asserts exit code `0`.

[e2e]: https://github.com/emersonfelipesp/netbox-proxbox/blob/develop/.github/workflows/e2e-docker.yml

## Related

- [`proxbox_sync` flag and exit-code reference](./headless-sync.md)
- [Installing the plugin in a Docker NetBox deployment](../installation/3-installing-plugin-docker.md)
- [`netbox_proxbox/jobs.py`](https://github.com/emersonfelipesp/netbox-proxbox/blob/develop/netbox_proxbox/jobs.py) for the RQ job model
