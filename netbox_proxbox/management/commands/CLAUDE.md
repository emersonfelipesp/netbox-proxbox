# `netbox_proxbox.management.commands`

This directory contains Django management commands for the ProxBox plugin.

## Files And Ownership

- [`__init__.py`](./__init__.py): package marker.
- [`proxbox_fix_tokens.py`](./proxbox_fix_tokens.py): management command to check and fix FastAPIEndpoint tokens. Lists all endpoints and their token status; with `--fix`, attempts to register unregistered tokens with the proxbox-api backend.
- [`proxbox_sync.py`](./proxbox_sync.py): management command that enqueues a full Proxmox→NetBox `ProxboxSyncJob` from the shell — the headless equivalent of clicking **Full Update** in the plugin UI. Supports `--user`, `--wait`, `--timeout`, `--poll-interval`, and `--worker-grace`. See [`docs/operations/headless-sync.md`](../../../docs/operations/headless-sync.md).

## Dependencies

- Inbound: Django's `manage.py` CLI imports these commands when `netbox_proxbox` is installed.
- Outbound: `netbox_proxbox.models` (`FastAPIEndpoint`, `ProxmoxEndpoint`), `netbox_proxbox.jobs.ProxboxSyncJob`, `netbox_proxbox.services.backend_auth.wait_for_backend_ready`, `netbox_proxbox.services.backend_context.get_fastapi_request_context`, `netbox_proxbox.signals._get_backend_url`, `netbox_proxbox.signals._register_token_with_backend`.

## Usage

```bash
# Check token status for all FastAPIEndpoint objects
python manage.py proxbox_fix_tokens

# Check and attempt to register unregistered tokens
python manage.py proxbox_fix_tokens --fix

# Enqueue a full Proxmox→NetBox sync (cron / systemd / CI entry point)
python manage.py proxbox_sync

# Same, but block until the job finishes and mirror its exit code
python manage.py proxbox_sync --wait --timeout 7200
```

## Notes

- `proxbox_fix_tokens --fix` is best-effort; failures are logged but do not raise.
- `proxbox_sync` raises `CommandError` (exit non-zero) when `proxbox-api` is unreachable, no `FastAPIEndpoint` is configured, no usable user is found, or — with `--wait` — the job ends in a non-success terminal state. The job appears under **Background Jobs** identical to a UI-triggered sync.

## Links

- Parent: [`../CLAUDE.md`](../CLAUDE.md)