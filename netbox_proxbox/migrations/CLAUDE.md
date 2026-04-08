# `netbox_proxbox.migrations`

This directory contains Django schema migrations for the plugin models.

## Contents

- **0001–0008:** Historical chain for the original VM resource and endpoint models.
- **0009_squashed_post_v006b2_to_v008:** Squashed migration that replaces the pre-squash `0009`-`0008` branch and introduces the VM backup and snapshot era.
- **0010_squashed_plugin_settings_and_storage:** Squashed migration for plugin settings and storage tables.
- **0012_fix_missing_storage_tables:** Repair migration for partially upgraded installs that were missing storage or task-history tables.
- **0013_proxmoxstorage_cluster_foreignkey:** Converts `ProxmoxStorage.cluster` from a string to a foreign key to `virtualization.Cluster`.
- **0014_alter_proxmoxstorage_options_and_more:** Updates `ProxmoxStorage` ordering and uniqueness after the foreign-key change.
- **0015_alter_vmbackup_unique_together_alter_vmbackup_vmid_and_more:** Final cleanup for `VMBackup`, `VMSnapshot`, and `VMTaskHistory` field/state alignment.
- **0016_proxmox_cluster_node_models:** Adds the current `ProxmoxCluster` and `ProxmoxNode` models.
- **0017_proxboxpluginsettings_ignore_ipv6_link_local:** Adds the plugin setting for IPv6 link-local handling.
- **0018_proxmoxcluster_tags_proxmoxnode_tags_and_more:** Adds tag fields and related model updates for clusters and nodes.
- **0019_backup_routine:** Adds the backup routine model and related relations.
- **0020_replication:** Adds the replication model and related relations.
- **0021_backuproutine_tags_replication_tags_and_more:** Adds tag fields to backup routine and replication models.
- **0022_squashed_populate_fastapi_tokens_to_convert_unique_together_to_constraints:** Squashed migration combining:
  - Populate FastAPI endpoint tokens for existing rows
  - Add SSRF protection settings (4 fields)
  - Add backend log file path configuration
  - Add operational settings (8 fields: concurrent requests, retries, caching, batching, VM concurrency, custom field delays)
  - Convert `unique_together` to named `UniqueConstraint` for ProxmoxStorage, ProxmoxStorageVirtualDisk, VMBackup, and VMSnapshot
  - Replaces original migrations 0022-0026 for databases that applied them individually

## Squashing and Upgrades

- The squashed migrations list `replaces = [...]` so Django treats databases that already applied the old individual migrations as up to date without re-running operations.
- There is no `0011` migration file in this checkout; the chain jumps from `0010` to `0012`.
- **0022_squashed_*** (v0.0.11+): Consolidates five individual migrations (0022-0026) into one. The `replaces` list allows existing databases that applied the old chain to recognize this as a replacement and skip re-running those operations.
- If an install was partially upgraded into the post-squash branch, use the repair migration chain in this directory rather than hand-editing `django_migrations`.

## Dependencies

- Inbound: Django migration runner uses these files during install and upgrade.
- Outbound: each migration depends on the historical state of `netbox_proxbox.models` and relevant NetBox app migrations (see `dependencies` in each file).

## Release Timeline

- **v0.0.10** (and earlier): Migrations 0001-0021 (21 files)
- **v0.0.11** (develop): Migrations 0001-0021, 0022_squashed (22 files)
  - Adds 5 changes (FastAPI tokens, SSRF settings, backend logging, operational settings, constraint conversion) consolidated into one squashed migration
  - Reduces individual migration file count from 27 (0001-0026, minus 0011) to 22

## Notes

- Review this directory before changing model fields or uniqueness rules.
- The squashed 0022 migration handles PostgreSQL constraint removal safely using `DROP CONSTRAINT IF EXISTS` and explicit constraint naming.

## Links

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
