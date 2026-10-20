# Endpoint ownership of native clusters

Each Proxmox endpoint has one nullable, read-only `netbox_cluster` relation to
NetBox's native `virtualization.Cluster`. Each native cluster belongs to at most
one endpoint. Synchronization fills this relation automatically and keeps the
same native cluster and tracking record when Proxmox reports a new cluster name.
The endpoint detail page and the native cluster page show clickable relations
only when the caller can view the related object, including clusters without a
typed sync-state sidecar.

The local reconciliation action is
`POST /api/plugins/proxbox/endpoints/proxmox/{plugin_pk}/sync-cluster/`:

```json
{
  "name": "actual-proxmox-cluster-name",
  "mode": "cluster",
  "cluster_id": "optional-source-identity",
  "cluster_type": 1,
  "site": 2,
  "tenant": null
}
```

`mode` accepts `cluster` or `standalone`. The name, mode, and native cluster type
are required; source identity, site, and tenant are optional. Site and tenant
accept null to clear placement. Omitting placement preserves the current value.
The response contains `cluster` (the native ClusterSerializer representation),
`proxmox_cluster` (the plugin tracking primary key), `created` (a boolean), and
`changed` (a boolean). `changed` reports substantive native name, type, site, or
tenant changes made by an update; it excludes timestamps. Creation reports
`created=true` and `changed=false`. A repeated unchanged update reports both
flags as false. Backend counters give creation precedence, then report an update
when either this flag or subsequent metadata reconciliation identifies a change.
Creation returns HTTP 201; a repeated reconciliation returns HTTP 200.

The action requires authentication, a write-enabled API token when token
credentials are used, and view/change permissions on the exact endpoint.
Creating a native cluster requires its add permission and permission to view the
created object. Updating requires view/change access to the exact existing
cluster. Referenced type, site, and tenant objects must be visible to the caller.
Disabled endpoints cannot use this action. It performs only local database
writes and never resolves credentials or calls Proxmox.

The action explicitly derives authority to maintain its exact tracking row and
typed sidecar from the endpoint and native-cluster permissions. Separate tracking
or sidecar add/change permissions are not required, and their independent object
constraints do not limit this derived maintenance operation. This delegation is
one way: ordinary tracking CRUD cannot claim a native cluster or populate the
endpoint relation, even for a superuser. Use the protected action for claims.
Ordinary tracking edits may maintain metadata or clear obsolete evidence without
changing the authoritative endpoint relation. Referenced endpoints and clusters
must be visible. Ordinary sidecar writes may repeat the existing ownership link
and update reflection metadata, but cannot replace or clear ownership. Full stale
sidecar saves preserve the current server-owned link.

Supported writers use endpoint, native cluster, tracking row, then typed sidecar
locks in that order. Preflight reloads the locked endpoint before selecting a
tracking identity. Sidecar-only metadata writers use the native-cluster and
sidecar suffix of this order. Ordinary endpoint saves preserve the current
relation under their existing row lock, including saves of objects loaded before
synchronization or native-cluster deletion. Concurrent deletion and recognized
database serialization conflicts produce a controlled HTTP 409; retry after the
inventory state has settled.

The endpoint relation is authoritative. When it is absent, an existing native
cluster can be adopted only through globally unambiguous tracking links for that
endpoint. A matching name alone never establishes ownership. A native cluster
owned by another endpoint is never adopted or mutated. If native uniqueness
rules prevent a separate cluster with the reported name, the action returns an
actionable HTTP 409 conflict. Endpoint, cluster, tracking, and typed sidecar
changes share one transaction, so any permission or ownership failure rolls back
all changes.

The additive migration fills only endpoint/core pairs for which both directions
are globally unique in existing linked tracking records. Ambiguous history stays
unclaimed. Operators should review the exact endpoint and linked tracking
inventory, then explicitly clear or remove obsolete tracking relations through
validated CRUD before retrying. An existing tracking record cannot silently move
to another endpoint or native cluster, and synchronization cannot reassign an
established endpoint relation. Unlinked historical tracking rows may remain.
Do not delete native clusters to resolve ownership conflicts: they may contain
production devices and virtual machines.

Reversing the additive migration retains the physical endpoint ownership column
and its values. Reapplication preserves every retained direct owner, even when
legacy tracking changed while the older schema was active. A conflicting legacy
candidate stays unclaimed; unrelated unambiguous pairs can still be backfilled.
Review conflicting tracking evidence through the validated recovery steps above.
Reversal and reapplication do not provide an ownership transfer mechanism.

The 0.0.30 release migration consolidates the unpublished cluster-binding,
SSH-service-chain, and Cloud Image development migrations. A staging database
that already applied `0107_endpoint_native_cluster_binding` keeps that old name
as an ignored orphan row in Django's migration recorder. The release migration
uses a distinct name, detects the existing ownership column and constraint, and
runs the idempotent backfill without replacing a retained owner.

After the immutable 0107 has committed, the new 0108 migration validates the
resulting PostgreSQL schema against historical model state. Its final operation
drains any framework-deferred DDL queued within 0108 before checking the physical
postcondition; normal 0107 foreign-key and index DDL has already completed in
0107's separate transaction. The endpoint ownership
column must have the expected native-ID type and nullability, an enforcing
single-column, nonpartial, nonexpression unique index with ordinary NULL-distinct
semantics, and a validated foreign key to the native cluster primary key. The
release also checks its SSH-service fields, credential and automatic M2M tables,
declared uniqueness, foreign keys, indexes, generated IDs, and database defaults.
Missing, invalid, wrong-target, or incompatible adopted objects fail the migration;
the validator does not silently repair them.

An expected good constraint does not excuse an incompatible additional one.
The validator also rejects extra uniqueness, checks, exclusions, and foreign keys
that change the new endpoint fields or release-owned service tables. Predicate
and expression dependencies are included. A true whole-row CHECK or expression
also touches the new endpoint fields, even when PostgreSQL records no named
column dependency. Bounded catalog-token inspection distinguishes an actual
whole-row reference from an ordinary scalar expression slot or automatic table
dependency; an uninspectable representation fails closed. Unrelated preexisting
endpoint policy constraints remain outside this release's validation scope.

The four checked tables are locked in deterministic order with PostgreSQL
`SHARE UPDATE EXCLUSIVE` locks through transaction completion. These locks block
both ordinary and concurrent index DDL while permitting ordinary row writes.
Lock acquisition uses a transaction-local timeout of at most five seconds and
preserves a shorter existing timeout. Contention fails the migration explicitly;
release the conflicting schema operation and retry after preserving its evidence.
The previous timeout is restored after successful validation, and rollback
discards the temporary timeout after failure.

The secret-free marker
`PROXBOX_RELEASE_0107_SCHEMA_VALIDATED_V1 (transaction commit pending)` means that
this physical postcondition passed inside the migration transaction. Retain the
exact installed source identity, the marker, the subsequent successful migration
result, and the complete command's exit status together. The marker alone is not
a committed-migration receipt. A validation or deferred-DDL error rolls back this
0108 migration's changes and leaves its recorder row unapplied. An earlier
0107 transaction can remain committed; the two migrations do not roll back as
one unit. Preserve the full error
and existing data, investigate the exact malformed schema, and obtain an explicit
reviewed repair before retrying the same migration. Do not fake its recorder row,
delete retained ownership, or remove constraints merely to make validation pass.

A unique endpoint/core pair is different from a unique tracking row. Several
historical rows for one identical pair permit the migration to backfill the
endpoint relation, but synchronization still refuses to choose one tracking row.
Identify the canonical row from its node and typed-sidecar references. Preserve
that row and explicitly clear the native-cluster link on the obsolete duplicates
through validated tracking CRUD. Keep the canonical row's source name aligned
with the current discovery result; an unrelated unlinked row with that name also
requires review and correction before retrying. Clearing obsolete tracking
evidence does not transfer or erase the endpoint's native-cluster ownership.

For this coordinated rollout, deploy the backend that requires the atomic claim
first. Verify its exact deployed revision and confirm that every old backend
process has drained before installing this plugin. Until the action is available,
the new backend fails synchronization before creating or changing a native
cluster. Install the plugin migration, then retry synchronization and verify both
directions of the endpoint/native-cluster relation. Do not run an older backend
that repairs links by cluster name against the new ownership model.

Deleting an endpoint preserves its native cluster. Deleting a native cluster
preserves the endpoint and clears its relation, as well as the corresponding
tracking links. Typed sidecars follow the native cluster lifecycle.


## Post-candidate validation boundary

Release 0.0.31rc1 adds only `0108_v0_0_31_schema_validation` after the applied,
immutable `0107_v0_0_30_release`. Keep every numbered migration through 0107
byte- and mode-identical. The unchanged private `_release_0107_schema.py`
checks objects introduced by 0107; its marker identifies that invariant while
the actual migration executing it is 0108. It must remain 0108's last operation.
The source-bound full function audit and native qualification belong to this new
migration boundary, not a relabeling of the earlier pre-candidate experiment.

The 0107 and 0108 transactions commit separately. A failure in 0108 preserves
an already committed 0107 and leaves 0108 unrecorded. Do not claim joint rollback,
rewrite deployed history, or silently repair an unexpected schema. Reverse of
0108 is a no-op for schema/data; reapply validates again. Preserve actual recorder
and data evidence for explicit reviewed recovery. The original 0107 reverse
controls remain historical and do not prove that 0108 removes those objects.
