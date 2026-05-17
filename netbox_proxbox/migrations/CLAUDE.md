# `netbox_proxbox.migrations`

This directory contains Django schema migrations for the plugin models.

## Idempotent additive operations (post-0036)

Every additive schema operation in the post-``0036_add_overwrite_vm_type``
chain (``0037`` through ``0046``) is wrapped through the helpers in
[`_idempotent_ops.py`](./_idempotent_ops.py) — ``add_field_idempotent()``
for ``AddField`` and ``create_model_idempotent()`` for ``CreateModel``.
Each helper returns a ``SeparateDatabaseAndState`` whose ``database_operations``
introspect the live schema and only invoke the actual schema change when
the target column / table is missing. The ``state_operations`` keep the
original ``AddField`` / ``CreateModel`` verbatim so Django's project state,
serializer parity, and ``makemigrations --check`` output match the
non-idempotent original.

Use these helpers for every new additive migration in this chain. The
consolidated ``0037_v0_0_15_release`` migration also declares
``replaces = [...]`` covering every deleted migration from both the
v0.0.15 and develop branches; databases that fully applied the old
lineage are marked applied without re-running operations.

This combined policy (``replaces`` + idempotent ops) makes the chain
safe to run against:

* Clean v0.0.15+ installs (helpers no-op the existence check, then run
  Django's normal schema add).
* Reporter-style partial-legacy installs (helpers skip the columns or
  tables the legacy lineage already added, then run the rest).
* Fully-applied legacy installs (``replaces`` short-circuits the squash;
  helpers never run).

See [`_idempotent_ops.py`](./_idempotent_ops.py) for the wrapper
contract and issue #454 for the bug history.

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
- **0023** (v0.0.11+): Adds `encryption_key` to `ProxboxPluginSettings`. Databases that have not yet run this migration will return HTTP 500 on `GET /api/plugins/proxbox/settings/` because the ORM always selects all model columns. Run `manage.py migrate netbox_proxbox` to apply.
- **0024** (v0.0.11+): Adds `endpoint` FK, `status` field, and `raw_config` JSON field to `Replication`; adds choice sets for replication status and job type.
- **0025** (v0.0.11+): Adds new fields to `ProxmoxStorage` (extended storage-type columns for NFS, CIFS, Ceph, PBS, and filesystem backends).
- **0026** (v0.0.11+): Converts `VMBackup.encrypted` from `BooleanField` to `CharField` — stores the encryption fingerprint string instead of a simple flag.
- **0027** (v0.0.11+): Converts `VMTaskHistory.pstart` from `IntegerField` to `BigIntegerField` to accommodate large kernel start-time values.
- **0028** (v0.0.11+): Makes `FastAPIEndpoint.websocket_port` nullable with `default=None`. A data migration resets existing rows where `websocket_port=8800` (the old hardcoded default) to `NULL` so the URL-builder falls back to the HTTP port.
- **0029** (v0.0.11+): Adds `primary_ip_preference` (`CharField`, choices `ipv4`/`ipv6`, default `ipv4`) to `ProxboxPluginSettings`. Controls which IP family Proxbox selects as the VM primary IP. Databases missing this migration will return HTTP 500 on `GET /plugins/proxbox/settings/` because the ORM selects all model columns. Run `manage.py migrate netbox_proxbox` to apply.
- If an install was partially upgraded into the post-squash branch, use the repair migration chain in this directory rather than hand-editing `django_migrations`.

## Dependencies

- Inbound: Django migration runner uses these files during install and upgrade.
- Outbound: each migration depends on the historical state of `netbox_proxbox.models` and relevant NetBox app migrations (see `dependencies` in each file).

## Release Timeline

- **v0.0.10** (and earlier): Migrations 0001-0021 (21 files)
- **v0.0.11** (current): Migrations 0001-0021, 0022_squashed, 0023-0029 (28 files on disk — no 0011)
  - 0022_squashed adds 5 changes (FastAPI tokens, SSRF settings, backend logging, operational settings, constraint conversion) consolidated into one squashed migration
  - 0023 adds `encryption_key` to `ProxboxPluginSettings`
  - 0024 extends `Replication` with `endpoint`, `status`, and `raw_config`
  - 0025 adds extended storage-type fields to `ProxmoxStorage`
  - 0026 converts `VMBackup.encrypted` from BooleanField to CharField
  - 0027 converts `VMTaskHistory.pstart` to BigIntegerField
  - 0028 makes `FastAPIEndpoint.websocket_port` nullable (resets legacy 8800 default to NULL)
  - 0029 adds `primary_ip_preference` to `ProxboxPluginSettings`

## Notes

- Review this directory before changing model fields or uniqueness rules.
- The squashed 0022 migration handles PostgreSQL constraint removal safely using `DROP CONSTRAINT IF EXISTS` and explicit constraint naming.

## Links

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
