# `pxb sync run`

`pxb sync run` is the operator-friendly trigger for a full Proxmox→NetBox sync.
It wraps the [`proxbox_sync` Django management command](../operations/headless-sync.md)
as a subprocess, auto-locates NetBox's `manage.py` and the venv interpreter
that should run it, and forwards stdout, stderr, and the exit code back to
the terminal.

This is the same primitive as the plugin UI's **Full Update** button, the
`netbox-rq`-scheduled job, and the bare `python manage.py proxbox_sync`
invocation — just with a single, predictable CLI surface that does not require
knowing where NetBox lives on disk.

## When to use which trigger

| Trigger | Best for |
|---|---|
| Plugin UI → **Full Update** | Interactive operator runs from the browser. |
| `python manage.py proxbox_sync` | Cron jobs and systemd timers that already know the NetBox path. |
| `pxb sync run` | Operators on the shell who want one command regardless of host layout. |

## Examples

### Enqueue and exit

```bash
pxb sync run
```

Resolves `manage.py`, enqueues a `ProxboxSyncJob` on the default RQ queue,
prints `Enqueued ProxboxSyncJob (pk=N)`, and exits 0. The RQ worker picks
the job up; check its progress in the NetBox UI under **Background Tasks**.

### Wait for completion with live progress

```bash
pxb sync run --wait --timeout 600
```

Blocks until the job reaches a terminal state. The management command's
poll loop writes a progress line every `--poll-interval` seconds (default
2.0s); the CLI relays each line as it arrives, with `completed` in green
and `errored` / `failed` in red. Exit code mirrors the job:
`0` for `completed`, non-zero for `errored` / `failed` / timeout.

`--worker-grace` (default 30s) fast-fails when the job stays pending and
no RQ worker is consuming the default queue.

### Machine-readable output

```bash
pxb sync run --json | jq '.job_pk'
```

Emits a single JSON document at exit. `--json` captures the merged
stdout/stderr stream as a single `output` field rather than streaming it,
which is the right shape for log aggregators and CI step parsers.

Schema:

```json
{
  "exit_code": 0,
  "success": true,
  "job_pk": 42,
  "manage_py": "/opt/netbox/manage.py",
  "command": ["/opt/netbox/venv/bin/python", "-u", "/opt/netbox/manage.py", "proxbox_sync", "--poll-interval", "2.0", "--worker-grace", "30.0"],
  "output": "Enqueued ProxboxSyncJob (pk=42) on queue 'default' for 1 Proxmox endpoint(s), attributed to user 'admin'.\n"
}
```

`job_pk` is `null` when the management command exits before enqueuing
(for example when no `ProxmoxEndpoint` records are configured).

## `manage.py` resolution

The CLI checks each source in order and uses the first match:

1. `--netbox-path FILE_OR_DIR` (explicit override).
2. Walk up from the current working directory, looking at each ancestor's
   `manage.py`. The match must look like a NetBox install — its sibling
   `netbox/settings.py` contains `from netbox.plugins`, or
   `netbox/configuration_example.py` exists. Non-NetBox matches are skipped
   so the walk continues past unrelated Django projects.
3. `$NETBOX_PATH` environment variable — accepts either a file path or a
   directory containing `manage.py`.
4. `/opt/netbox/manage.py` (the canonical install path used by
   [`docs/operations/headless-sync.md`](../operations/headless-sync.md)).
5. `netbox_manage_py` from `~/.config/proxbox-cli/config.json`.

If every source is exhausted, `pxb sync run` exits non-zero with:

```text
Error: could not find manage.py — set $NETBOX_PATH or run from inside the project tree
```

## Interpreter resolution

The locate helper resolves `manage.py` first (so symlinks like `/opt/netbox`
point at the real install dir), then prefers
`<resolved_parent>/venv/bin/python` when it exists, and falls back to
`Path(sys.executable)`. This matters because `sys.executable` is the *CLI's*
interpreter (often a pipx-managed venv) — NetBox has its own venv with the
plugin installed, and the management command must run inside that one.

## Flags

| Flag | Default | Effect |
|---|---|---|
| `--wait` | off | Block until the job is in a terminal state. |
| `--timeout SECONDS` | `PROXBOX_SYNC_JOB_TIMEOUT` (7200) | Max wait when `--wait` is set. |
| `--poll-interval SECONDS` | `2.0` | Seconds between status polls. |
| `--worker-grace SECONDS` | `30.0` | Fast-fail when no worker takes the job. |
| `--user USERNAME` | oldest active superuser | Owner attribution for the enqueued job. |
| `--json` | off | Emit JSON at exit instead of streaming. |
| `--netbox-path PATH` | — | Override the `manage.py` resolution chain. |

## See also

- [`docs/operations/headless-sync.md`](../operations/headless-sync.md) — the
  management command this wraps, plus cron/systemd guidance.
