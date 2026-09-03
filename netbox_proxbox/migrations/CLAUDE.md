# `netbox_proxbox.migrations`

> **Repository destination guardrail:** This guide inherits the hard rule in
> the repository-root `CLAUDE.md`. EdgeUno and the local EdgeUno vendor
> submodule are read-only reference sources, never change destinations. All
> development writes must target exactly
> `https://git.nmulti.cloud/emersonfelipesp/netbox-proxbox.git`; approved
> public promotion may target only
> `https://github.com/emersonfelipesp/netbox-proxbox.git`. Never mutate EdgeUno
> issues, PRs, branches, commits, tags, releases, packages, mirrors, or
> deployments, and never configure EdgeUno as a writable remote, upstream,
> fallback, or PR base.

This directory contains Django schema migrations for the plugin models.

## Idempotent additive operations (post-0036)

Additive schema operations in the post-``0036_add_overwrite_vm_type`` chain,
including current migration ``0082``, are wrapped through the helpers in
[`_idempotent_ops.py`](./_idempotent_ops.py) — ``add_field_idempotent()``
for ``AddField`` and ``create_model_idempotent()`` for ``CreateModel``.
Each helper returns a ``SeparateDatabaseAndState`` whose ``database_operations``
introspect the live schema and only invoke the actual schema change when
the target column / table is missing. The ``state_operations`` keep the
original ``AddField`` / ``CreateModel`` verbatim so Django's project state,
serializer parity, and ``makemigrations --check`` output match the
non-idempotent original.

Use these helpers for every new additive migration in this chain. Both
``0037_v0_0_15_release`` and ``0038_v0_0_16_release`` declare
``replaces = [...]`` covering every deleted migration from their
respective release branches; databases that fully applied the old
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
- **0038_v0_0_16_release** (v0.0.16+): Manually-constructed squash of migrations 0038–0047 (11 files, including the 0044 fork pair). Replaces: `0038_intent_permissions`, `0039_intent_custom_fields`, `0040_apply_job_full`, `0041_deletion_request_full`, `0042_pluginsettings_self_approve`, `0043_pluginsettings_warn_plaintext`, `0044_cloud_image_template`, `0044_overwrite_vm_proxmox_tags`, `0045_proxmoxendpoint_environment`, `0046_pluginsettings_embed_description_metadata`, `0047_legacy_lineage_schema_repair`. The repair RunPython from 0047 is omitted — all tables and columns are already covered by the idempotent ops in the squash.
- If an install was partially upgraded into the post-squash branch, use the repair migration chain in this directory rather than hand-editing `django_migrations`.

## Dependencies

- Inbound: Django migration runner uses these files during install and upgrade.
- Outbound: each migration depends on the historical state of `netbox_proxbox.models` and relevant NetBox app migrations (see `dependencies` in each file).

## Release Timeline

- **v0.0.10** (and earlier): Migrations 0001-0021 (21 files)
- **v0.0.11**: Migrations 0001-0021, 0022_squashed, 0023-0029 (28 files on disk — no 0011)
  - 0022_squashed adds 5 changes (FastAPI tokens, SSRF settings, backend logging, operational settings, constraint conversion) consolidated into one squashed migration
  - 0023 adds `encryption_key` to `ProxboxPluginSettings`
  - 0024 extends `Replication` with `endpoint`, `status`, and `raw_config`
  - 0025 adds extended storage-type fields to `ProxmoxStorage`
  - 0026 converts `VMBackup.encrypted` from BooleanField to CharField
  - 0027 converts `VMTaskHistory.pstart` to BigIntegerField
  - 0028 makes `FastAPIEndpoint.websocket_port` nullable (resets legacy 8800 default to NULL)
  - 0029 adds `primary_ip_preference` to `ProxboxPluginSettings`
- **v0.0.16**: Migrations 0001-0021, 0022_squashed, 0023-0029, 0030-0037, 0038_v0_0_16_release (squashed), 0048+ (on-disk chain has no 0011, no 0038–0047 individual files)
  - 0030-0036: incremental v0.0.12–v0.0.15 pre-release fields (VMTaskHistory status, ProxmoxEndpoint site/tenant/timeout, ProxboxPluginSettings controlled/overwrite fields)
  - 0037_v0_0_15_release: manually-constructed squash of the full v0.0.15 and develop branch delta (20 replaced migrations)
  - 0038_v0_0_16_release: manually-constructed squash of the full v0.0.16 intent/apply/deletion/cloud-image delta (11 replaced migrations)
- **v0.0.18** (current): same chain as v0.0.16 plus `0039_squashed_0039_0042_pve_9_2_firewall_sdn` (replaces individual 0039–0042; no `replaces = [...]` attribute per post-squash policy)
  - 0039_squashed_0039_0042_pve_9_2_firewall_sdn: manually-constructed squash of migrations 0039 (PVE firewall models), 0040 (endpoint `enabled` field + PBS/PDM gap fix), 0041 (SDN/datacenter models + `ProxmoxNode.location`), and 0042 (SDN prefix list constraint rename). Uses idempotent `create_model_idempotent` / `add_field_idempotent` helpers throughout. Constraint rename is handled by a `_fix_sdn_prefix_list_constraint` RunPython that inspects `information_schema.table_constraints` and is safe for all three DB states: fresh install, partial upgrade, and fully-upgraded.
  - 0045_repair_pbs_pdm_endpoint_enabled: database-only repair for v0.0.18 installs where the released individual `0040_endpoint_enabled` migration added `enabled` to Proxmox/NetBox/FastAPI endpoints but omitted `PBSEndpoint` and `PDMEndpoint`. This migration adds the missing columns idempotently when those tables already exist.
- **0059_cloud_customer_network_settings**: additive `ProxboxPluginSettings` fields for the operator-designated cloud-customer Prefix ID, bridge, VLAN tag, gateway, and lock flag. Uses `add_field_idempotent`; estate-specific values are populated by the `ensure_cloud_customer_network` management command, not by migration defaults or data migration.
- **0073_netboxendpoint_pushed_credential_fingerprint**: additive
  `NetBoxEndpoint.pushed_credential_fingerprint` (blank `CharField`) holding a
  keyed HMAC-SHA256 digest of the credentials the last **successful** push handed
  proxbox-api. Never a secret: `salted_hmac` keys off NetBox's `SECRET_KEY`, so
  the value is non-reversible and not comparable across installs. No data
  migration and no default beyond `""` — an empty fingerprint deliberately reads
  as "credentials changed" (see `views/CLAUDE.md`), so the upgrade window is
  fail-closed rather than back-filled with a guess. The writer catches
  `DatabaseError`, so a deployment that has not applied this migration yet logs a
  warning instead of failing the push.
- **0074_proxmoxendpoint_pushed_credential_fingerprint**: the Proxmox twin of
  0073 — additive `ProxmoxEndpoint.pushed_credential_fingerprint` (blank
  `CharField`, `add_field_idempotent`) recording the keyed HMAC-SHA256 digest of
  the credentials (`password`/`token_name`/`token_value`) the last successful
  push handed proxbox-api, under a **distinct salt** from the NetBox
  fingerprint. Consumed by the preflight's soft push budget: a rotated-in-place
  secret is invisible on the wire (`ProxmoxEndpointPublic` withholds the
  credential fields), so only this local receipt can tell a no-op refresh from a
  push that delivers a new secret. Empty reads as "push again" (one bounded
  extra request), never as a blocked run; the writer catches `DatabaseError`, so
  an unapplied migration degrades to the previous always-push behavior.
- **0075_fastapi_backend_key_target_fingerprint**: adds the internal SHA-256
  target fingerprint used to bind an encrypted FastAPI key to its primary and
  fallback HTTP authorities, TLS policy, and WebSocket policy. Existing rows
  intentionally remain blank and fail closed until the retained key is
  authenticated against the exact persisted target by commit-safe startup
  auto-configuration or an operator runs `proxbox_fix_tokens --fix`. Never add
  a data migration that silently fingerprints legacy rows; a mutable related
  `IPAddress` must be probed and authenticated under the same frozen target
  snapshot before trust is recorded.
- **0076_pluginsettings_hardware_discovery_sync_nic_macs**: additive,
  default-off `ProxboxPluginSettings.hardware_discovery_sync_nic_macs` feature
  gate. It uses `add_field_idempotent()` and deliberately has no data migration,
  so installations that already enabled hardware discovery do not begin native
  physical-NIC MAC writes during upgrade.
- **0077_ceph_runtime_timing_settings**: additive, idempotent DecimalFields on
  `ProxboxPluginSettings` for Ceph task timeout, polling interval, and durable
  operation lease. Existing rows receive safe defaults (`300.00`, `1.00`, and
  `360.00`); model and migration validators preserve the backend's bounded
  timing contract without an estate-specific data migration. The real-Django
  migration test applies 0076 → 0077 against an existing settings row and
  verifies all three defaults before restoring the latest state.
- **0078_sync_state_last_synced_role**: adds the nullable, scalar
  `ProxboxVirtualMachineSyncState.proxmox_last_synced_role_id` ownership
  snapshot with `add_field_idempotent()`. Its retry-safe data migration copies
  only positive signed-bigint IDs from the deprecated same-named VM custom
  field, uses the migration connection alias plus bounded 500-row bulk batches,
  creates a sidecar when needed, never overwrites an existing typed value, and
  leaves legacy data intact for rollback compatibility.
- **0079_storage_nodes_text**: widens `ProxmoxStorage.nodes` from a
  255-character column to `TextField` so a complete comma-separated membership
  list survives large Proxmox estates. The database operation is expand-only:
  reversing restores historical Django state but deliberately leaves the
  PostgreSQL `text` column in place, because narrowing after a long value exists
  would block rollback or require destructive truncation. Forward, rollback,
  and reapply preserve existing and newly long values. This number can collide
  with sibling feature branches and is intentionally renumbered only at merge;
  its real-Django test discovers the sole current plugin leaf and that leaf's
  direct plugin parent dynamically instead of pinning a numbered edge.
- **0080_metrics_influxdb_secret_ref_constraints** (the metrics-security leaf)
  blanks non-conforming InfluxDB URL/token
  metadata, disables rows missing a safe URL or required query-token reference,
  appends a persistent remediation marker to comments, and masks matching fields
  in historical `core.ObjectChange` snapshots before installing database checks.
  Those checks durably require every enabled row to retain a credential-free
  HTTP(S) URL and nonempty exact query-token reference while leaving the writer
  reference optional. The destructive scrub, quarantine, marker, and audit
  masking are intentionally not reversed; rollback removes only the checks. Its
  real-Django test discovers the plugin leaf and its sole in-app parent from the
  migration graph, so a merge-time renumber changes only the migration file.
- **0081_encrypted_secret_reset_permission**: updates
  `ProxboxPluginSettings.Meta.permissions` with the separate
  `reset_encrypted_secrets` destructive-recovery permission. It changes no
  ciphertext and performs no data migration. It was developed in parallel with
  the #295/#297 branches as a colliding 0079 and renumbered to 0081 (dependency
  `0080_metrics_influxdb_secret_ref_constraints`) at merge time. Tests find
  this migration by operation content rather than its number.
- **0082_proxmoxendpoint_allow_packer_template_builds**: adds the idempotent,
  default-off `ProxmoxEndpoint.allow_packer_template_builds` capability and the
  default-false, non-editable
  `packer_template_builds_backend_authorized` confirmation field. It has no
  permissive backfill: existing endpoints remain unable to create netbox-packer
  template images until an operator enables the narrow gate in addition to
  `allow_writes`, while the confirmation field records only later successful
  proxbox-api pushes and blocks deletion after a failed revocation.

## Hierarchy backends: never assume django-mptt columns

NetBox 4.7 migrated nested group models — `dcim.DeviceRole` among them — from
django-mptt to PostgreSQL `ltree`, **dropping `tree_id`, `lft`, `rght`, and
`level`**. There, `path` is maintained by per-table triggers and must not be
written from Python, and `sort_path` carries a default plus its own trigger.

`_v0_0_15_release_data.py::seed_default_vm_roles` used to aggregate
`Max("tree_id")` and pass all four MPTT columns as `get_or_create` defaults
unconditionally. On NetBox 4.7 that raised
`FieldError: Cannot resolve keyword 'tree_id' into field` while applying
`0037_v0_0_15_release`, so a **fresh install could not run `manage.py migrate`
at all** — the failure is invisible on 4.5/4.6 and on any database that had
already applied 0037.

The fix keys off the historical model's concrete field set
(`_model_has_mptt_columns()`), which is the only trustworthy signal inside a
data migration: the model there is rebuilt from migration state, not imported,
so there is no version string to branch on. A **partial** MPTT field set is
deliberately treated as non-MPTT — half-migrated state must not produce a create
referencing a column that is already gone.

Apply the same rule to any future data migration that touches a NetBox nested
group model (`DeviceRole`, `Region`, `SiteGroup`, `Location`, `TenantGroup`,
`RackRole`, wireless LAN groups, …): supply hierarchy bookkeeping only after
confirming the columns exist, and never write `path`. Guarded by
`tests/test_seed_default_vm_roles_hierarchy.py`, which drives the callable with
fake historical models for both generations.

## Notes

- Review this directory before changing model fields or uniqueness rules.
- The squashed 0022 migration handles PostgreSQL constraint removal safely using `DROP CONSTRAINT IF EXISTS` and explicit constraint naming.
- Sync-state migrations 0065/0066 must keep NetBox's inherited
  `last_updated` as the auto-managed row timestamp and store source timestamps
  in `proxmox_last_updated`. Raw legacy backend IDs must use non-FK-attname
  fields such as `proxmox_endpoint_raw_id` and `proxmox_cluster_raw_id`; do not
  resolve proxbox-api database IDs as plugin model primary keys during backfill.
- Migration 0066 is the original per-object backfill body. Do not replace it
  with a batched helper or mark it `atomic = False`; already-applied migration
  bodies must remain immutable after staging/prod rollout.
- Storage/bridge sync-state relation conversion is split across 0067-0069.
  0067 is additive schema only and retry-safe, 0068 is non-atomic data
  conversion that can rerun after a mid-migration failure, and 0068's reverse
  must copy preserved raw values or raw/FK IDs back into the legacy JSON columns
  before 0067 removes the new columns. 0068 must not materialize full target PK
  sets; it should resolve only referenced raw IDs in bounded batches. 0069 is
  the guarded atomic cleanup/promotion to final field names and must refuse to
  drop legacy JSON columns if unresolved values were not preserved first.
- Migration 0085 removes exactly the twelve VM-only reflection custom fields,
  strips those exact keys from historical `VirtualMachine.custom_field_data`,
  and removes `ProxboxPluginSettings.custom_fields_enabled`. Its reverse uses
  the explicit definition table in the migration and rebinds each definition
  to `virtualization.virtualmachine`. Do not broaden its name tuple to shared,
  intent, branch, netbox-packer, or netbox-proxy custom fields.
- Migration 0086 removes exactly the remaining thirty reflection custom fields
  and strips those keys, in bounded batches, from Device, Interface,
  Manufacturer, Site, DeviceRole, DeviceType, IPAddress, VLAN, Cluster,
  ClusterGroup, ClusterType, VirtualMachine, VirtualDisk, and VMInterface JSON.
  It does not backfill data. Its reverse restores the full canonical definition
  table and every available original content-type binding. At that historical
  boundary, `proxmox_node` and `proxmox_storage` survive
  because the intent pipeline still reads them as CREATE placement inputs;
  migration 0088 owns their later retirement. Other intent, branch,
  netbox-packer, and netbox-proxy fields remain out of scope for 0086.
- Migration 0087 removes the six hardware-discovery reflection custom fields
  that 0086 skipped: `hardware_chassis_manufacturer`,
  `hardware_chassis_product`, `hardware_chassis_serial`, `nic_duplex`,
  `nic_link`, and `nic_speed_gbps`. 0086's ownership check compares a field's
  label against its own definition table, and proxbox-api's inventory reconcile
  had rewritten all six -- not merely recased: `Chassis product name` became
  `Chassis Product`, and the chassis-manufacturer description moved from
  `dmidecode -t 1` to `-t 3`. The check failed closed, correctly, since it
  cannot tell a changed field from somebody else's.
- **0087's real guard is emptiness, not provenance.** This project's own two
  writers disagree about label and description, so neither is an ownership
  signal; and NetBox records no provenance at all -- there is no owner column,
  every attribute an operator can reach is mutable, and `ui_editable="hidden"`
  stops the edit form but not the REST API, so a hidden field can still be
  where an integration keeps data. Data **type** plus `ui_editable="hidden"`
  therefore only selects candidates. Any field holding a value anywhere keeps
  its definition, its bindings and its values, whoever wrote it. Deletion is
  reached only for a field of our type, not operator-editable, and empty
  everywhere. Do not weaken this to a shape check; shape cannot distinguish our
  field from an operator's, and emptiness makes that distinction unnecessary.
- **Only `None` and `""` are blank.** `custom_field_data` is raw JSON, so an
  integration can leave a list or an object in a field NetBox declares as text.
  An empty one of those is still something somebody stored, and an unexpected
  shape reads as data rather than absence. Do not extend the blank set.
- **The check runs three times, because one pass is a race.** The opening scan
  is an early exit, not the authority: the definitions are then locked with
  `select_for_update()` for the rest of the transaction so their metadata
  cannot be repurposed between check and delete, the scan is repeated under
  that lock, and `_strip_values` re-tests each key as it removes it so a value
  that landed in between is not lost. Removing any of the three reopens the
  window.
- Migration 0087's reverse carries the full production metadata --
  `ui_visible`, `ui_editable`, `weight`, `filter_logic`, `required`,
  `search_weight`, `group_name` -- and uses `get_or_create` so an
  operator-owned definition is never rewritten. It re-attaches the canonical
  binding only to a row it created or to one that is ours **and still
  empty**: forward leaves no record of what it skipped, and a populated
  field of our exact shape whose binding an operator had already removed is
  indistinguishable from one forward released, so rebinding it would expose
  that data as a Proxbox field. A row forward released is empty by
  construction and still gets its binding back. Like 0085
  and 0086, forward strips `custom_field_data` keys without journaling them, so
  values do not come back on reverse; with the emptiness gate there is nothing
  to journal. On this estate that was also confirmed directly -- all 44
  production devices and 1,459 interfaces carried no value for any of the six.
  Do not edit 0086 to fix this; it is applied on staging and production, and
  its skip is safe.
- Migration `0088_proxmox_vm_intent` is an additive, idempotent schema step for
  the plugin-owned `ProxmoxVMIntent` model. The separate
  `0089_remove_vm_intent_custom_fields` migration is the only new leaf and
  depends on the additive step. It retires exactly the ten superseded intent
  definitions. Its forward and reverse use the same three-stage emptiness,
  locking, binding-release, and populated-row protections as 0087; only the
  definition table and affected object types differ. The authoritative scan and
  stripping pass also lock affected VM and device rows with
  `select_for_update()` before reading and rewriting their JSON documents, using
  bounded iterator and bulk-update batches so a concurrent unrelated
  custom-field write cannot be overwritten. Migrations 0085-0087 are immutable.
- Migration `0090_proxbox_branch_intent` adds the plugin-owned branch safety
  gates with a soft branch primary-key and schema-ID reference; it deliberately
  has no dependency on the optional `netbox_branching` app. Migration
  `0091_remove_branch_intent_custom_fields` then retires the two superseded
  Branch definitions using 0089's complete three-stage emptiness and locking
  boundary. Forward and reverse are both no-ops when the Branch content type is
  absent. Migrations 0085-0089 remain immutable.

## Links

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
