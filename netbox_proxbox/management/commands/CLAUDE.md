# `netbox_proxbox.management.commands`

This directory contains Django management commands for the ProxBox plugin.

## Files And Ownership

- [`__init__.py`](./__init__.py): package marker.
- [`ensure_cloud_customer_network.py`](./ensure_cloud_customer_network.py): idempotent command that creates/reuses the NetBox IPAM Role, VLAN, Prefix, and reserved gateway IP for the cloud customer network, then writes the `ProxboxPluginSettings` prefix ID, bridge, VLAN tag, gateway, and optional lock flag. Use this instead of hardcoding estate-specific cloud network values.
- [`proxbox_fix_tokens.py`](./proxbox_fix_tokens.py): secret-safe management
  command to inspect already-adopted FastAPIEndpoint authentication without
  printing token fragments. Disabled rows and blank legacy fingerprints are
  skipped without network access in default mode. After target review, `--fix`
  records a blank legacy row's target fingerprint and performs one-time
  registration only when the backend explicitly reports that it has no keys.
  A nonblank drifted fingerprint is refused before network access and requires
  explicit key resubmission through the form/API.
- [`proxbox_sync.py`](./proxbox_sync.py): management command that enqueues a full Proxmox→NetBox `ProxboxSyncJob` from the shell — the headless equivalent of clicking **Full Update** in the plugin UI. Supports `--user`, `--wait`, `--timeout`, `--poll-interval`, and `--worker-grace`. See [`docs/operations/headless-sync.md`](../../../docs/operations/headless-sync.md).

## Dependencies

- Inbound: Django's `manage.py` CLI imports these commands when `netbox_proxbox` is installed.
- Outbound: `ipam.models` (`Role`, `VLAN`, `Prefix`, `IPAddress`), `netbox_proxbox.models` (`FastAPIEndpoint`, `ProxmoxEndpoint`, `ProxboxPluginSettings`), `netbox_proxbox.jobs.ProxboxSyncJob`, `netbox_proxbox.services.backend_auth.wait_for_backend_ready`, `netbox_proxbox.services.backend_context.get_fastapi_request_context`, and `netbox_proxbox.services.backend_key_adoption`.

## Usage

```bash
# Designate the cloud customer network and enable the settings lock
python manage.py ensure_cloud_customer_network \
  --prefix 168.0.98.0/25 \
  --vlan 2050 \
  --vlan-name cloud-vmbr1 \
  --bridge vmbr1 \
  --gateway 168.0.98.1 \
  --enable-lock

# Check already-adopted token status; blank legacy rows make no request
python manage.py proxbox_fix_tokens

# Review and explicitly adopt a blank legacy target (bootstrap only if empty)
python manage.py proxbox_fix_tokens --fix

# Enqueue a full Proxmox→NetBox sync (cron / systemd / CI entry point)
python manage.py proxbox_sync

# Same, but block until the job finishes and mirror its exit code
python manage.py proxbox_sync --wait --timeout 7200
```

## Notes

- `proxbox_fix_tokens` is read-only unless `--fix` is supplied. A blank legacy
  fingerprint is diagnostic-only and makes no network request without `--fix`.
  Its diagnostics
  expose only typed error codes; response bodies, transport exception text, and
  token previews are intentionally omitted. Disabled rows make no request even
  with `--fix`.
- `proxbox_sync` raises `CommandError` (exit non-zero) when `proxbox-api` is unreachable, no `FastAPIEndpoint` is configured, no usable user is found, or — with `--wait` — the job ends in a non-success terminal state. The job appears under **Background Jobs** identical to a UI-triggered sync.

## Links

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
