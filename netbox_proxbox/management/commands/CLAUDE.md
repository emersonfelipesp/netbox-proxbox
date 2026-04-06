# `netbox_proxbox.management.commands`

This directory contains Django management commands for the ProxBox plugin.

## Files And Ownership

- [`__init__.py`](./__init__.py): package marker.
- [`proxbox_fix_tokens.py`](./proxbox_fix_tokens.py): management command to check and fix FastAPIEndpoint tokens. Lists all endpoints and their token status; with `--fix`, attempts to register unregistered tokens with the proxbox-api backend.

## Dependencies

- Inbound: Django's `manage.py` CLI imports this command when `netbox_proxbox` is installed.
- Outbound: `netbox_proxbox.models.FastAPIEndpoint`, `netbox_proxbox.signals._get_backend_url`, `netbox_proxbox.signals._register_token_with_backend`.

## Usage

```bash
# Check token status for all FastAPIEndpoint objects
python manage.py proxbox_fix_tokens

# Check and attempt to register unregistered tokens
python manage.py proxbox_fix_tokens --fix
```

## Notes

- This command is useful when tokens need to be re-registered after backend restarts or configuration changes.
- The `--fix` flag is a best-effort operation; failures are logged but do not raise exceptions.

## Links

- Parent: [`../CLAUDE.md`](../CLAUDE.md)