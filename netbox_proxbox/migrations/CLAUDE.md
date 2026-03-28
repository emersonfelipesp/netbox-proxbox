# `netbox_proxbox.migrations`

This directory contains Django schema migrations for the plugin models.

## Contents

- Early migrations create the endpoint and sync-process models.
- Later migrations add `VMBackup`, adjust endpoint identity constraints, and add NetBox v2 token support fields.
- The migration chain reflects the current shape of `ProxmoxEndpoint`, `NetBoxEndpoint`, `FastAPIEndpoint`, `SyncProcess`, and `VMBackup`.

## Dependencies

- Inbound: Django migration runner uses these files during install and upgrade.
- Outbound: each migration depends on the historical state of `netbox_proxbox.models` and relevant NetBox app migrations.

## Notes

- Review this directory before changing model fields or uniqueness rules.
- `0010_netboxendpoint_token_v2_support.py` is the migration that documents the shift from only NetBox v1 token support to explicit v1/v2 fields.

## Links

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
