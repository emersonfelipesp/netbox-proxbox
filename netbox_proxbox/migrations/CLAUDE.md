# `netbox_proxbox.migrations`

This directory contains Django schema migrations for the plugin models.

## Contents

- **0001–0008:** Historical chain (VM resources → endpoint models and early sync metadata).
- **0009_squashed_post_v006b2_to_v008:** Single squashed migration (replaces the former
  `0009_vmbackup` … `0013_make_domains_optional_and_require_host_target` chain from the
  pre-squash release line). It adds `VMBackup`, NetBox v2 token fields, endpoint identity
  constraints, optional domains, `VMSnapshot`, and removes legacy sync-process storage. Use
  `python manage.py migrate netbox_proxbox` after upgrading from v0.0.6b2.post1 or any release
  that had only applied through **0008**.
- **0010_squashed_plugin_settings_and_storage:** Single squashed migration (replaces
  `0010_proxbox_plugin_settings`, `0011_proxmoxstorage`,
  `0012_proxboxpluginsettings_proxbox_fetch_max_concurrency`). It creates the
  `ProxboxPluginSettings` singleton model (including `proxbox_fetch_max_concurrency`) and
  `ProxmoxStorage`. On upgrades from the old `v0.0.7` chain, it also backfills the missing
  `VMSnapshot` table before adding storage relations.
- **0011_storage_relations:** Adds endpoint and virtualization relations to storage records.
- **0012_fix_missing_storage_tables:** Repair migration that backfills storage and task-history
  tables or columns when older upgrade paths left them missing.
- **0013_proxmoxstorage_cluster_foreignkey:** Converts `ProxmoxStorage.cluster` from a string
  to a foreign key to `virtualization.Cluster`.
- **0014_alter_proxmoxstorage_options_and_more:** Updates `ProxmoxStorage` ordering and
  uniqueness after the foreign-key change.
- **0015_alter_vmbackup_unique_together_alter_vmbackup_vmid_and_more:** Final cleanup for
  `VMBackup`, `VMSnapshot`, and `VMTaskHistory` field/state alignment.

## Squashing and upgrades

- The squashed migration lists `replaces = [...]` so Django treats databases that already
  applied the old individual migrations as up to date without re-running operations.
- If an install was partially upgraded into the post-squash branch, use the repair migration
  chain in this directory rather than hand-editing `django_migrations`.

## Dependencies

- Inbound: Django migration runner uses these files during install and upgrade.
- Outbound: each migration depends on the historical state of `netbox_proxbox.models` and
  relevant NetBox app migrations (see `dependencies` in each file).

## Notes

- Review this directory before changing model fields or uniqueness rules.

## Links

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
