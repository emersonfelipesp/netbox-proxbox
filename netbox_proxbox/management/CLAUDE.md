# `netbox_proxbox.management`

This package contains Django management commands for the ProxBox plugin.

## Files And Ownership

- [`__init__.py`](./__init__.py): package marker.
- [`commands/`](./commands): Django management command modules.

## Dependencies

- Inbound: Django's `manage.py` CLI imports commands from this package when `netbox_proxbox` is installed.
- Outbound: `netbox_proxbox.models`, `netbox_proxbox.signals`, and Django core management utilities.

## Usage

Management commands are invoked via:

```bash
python manage.py proxbox_fix_tokens [--fix]
```

## Links

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
- Child: [`commands/CLAUDE.md`](./commands/CLAUDE.md)