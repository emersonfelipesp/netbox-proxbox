# `netbox_proxbox.migrations`

This directory contains Django schema migrations for the plugin models.

## Contents

- **0001–0008:** Historical chain (VM resources → endpoints, `SyncProcess` creation in 0008, etc.).
- **0009_squashed_post_v006b2_to_v008:** Single squashed migration (replaces the former
  `0009_vmbackup` … `0015_remove_syncprocess` chain). It adds `VMBackup`, NetBox v2 token
  fields, endpoint identity constraints, optional domains, `VMSnapshot`, and removes
  `SyncProcess`. Use `python manage.py migrate netbox_proxbox` after upgrading from
  v0.0.6b2.post1 or any release that had only applied through **0008**.

## Squashing and upgrades

- The squashed migration lists `replaces = [...]` so Django treats databases that already
  applied the old individual migrations as up to date without re-running operations.
- **Do not** apply this release if the old `netbox_proxbox` branch was only **partially**
  migrated past 0008 (some of 0009–0015 applied, not all). Finish the old chain first, or
  repair `django_migrations` per Django docs.

## Dependencies

- Inbound: Django migration runner uses these files during install and upgrade.
- Outbound: each migration depends on the historical state of `netbox_proxbox.models` and
  relevant NetBox app migrations (see `dependencies` in each file).

## Notes

- Review this directory before changing model fields or uniqueness rules.

## Links

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
