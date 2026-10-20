# Version 0.0.31

## Summary

Version `0.0.31rc1` prepares the next release boundary after the applied
`0.0.30rc1` candidate. It preserves every numbered migration through
`0107_v0_0_30_release` and adds only
`0108_v0_0_31_schema_validation`. The existing endpoint, SSH-service, and
Cloud Image behavior and dependency versions remain unchanged.

## Fail-closed physical schema validation

The new migration validates the physical objects introduced by 0107 against
historical model state. Nullable native-cluster ownership must have a correctly
typed column, enforcing single-column NULL-distinct uniqueness, and a validated
foreign key to the correct native Cluster primary key. Service, credential, and
M2M fields and declared constraints must also match. A good expected object does
not excuse conflicting additional checks, exclusions, or uniqueness. Whole-row
expressions are included without rejecting unrelated scalar endpoint policies.

The validator acquires bounded deterministic table locks, drains any deferred
DDL, and checks the final invariant in the same 0108 transaction. It refuses
malformed schema; it does not silently repair it. The retained helper and marker
name identify the 0107 objects being checked, not a rewrite or rerun of 0107.
Retain the exact source, marker, successful 0108 migration result, and complete
command status together; the marker alone does not prove commit.

## Upgrade and recovery

A database already at the immutable 0.0.30rc1 migration applies only 0108.
A database at 0106 or a fresh database first applies the unchanged 0107, then
0108. These are separate migration transactions. If 0108 fails, 0107 can remain
committed and recorded while 0108 remains unapplied. The entire two-migration
upgrade is not an atomic rollback unit. Preserve the actual schema, data,
recorder state, and failure evidence; obtain a reviewed explicit repair before
retrying 0108. Never fake its recorder row or rewrite the applied 0107.

Reversing 0108 is a no-op for the 0107 schema and existing ownership, SSH-service,
credential, M2M, and Cloud Image data. Reapplication validates those objects again.
Reversing the older 0107 has its original historical behavior and is a separate
operation, not a database restore.

Back up the applicable database and retain the prior application/configuration
identities before migration. Database restore is separately approved and must
not run automatically after a validation failure. Install this candidate only
through the normal release and deployment gates. Run migration, static
collection, and restart the deployment-owned NetBox application and worker
cohort after a successful upgrade.

## Compatibility

This candidate requires proxbox-api 0.0.29 or later (the release that adds endpoint-owned cluster bindings),
released and deployed before the plugin. The backend-first fail-closed rollout
and permission/ownership requirements remain unchanged.

| NetBox | netbox-proxbox | proxbox-api | netbox-sdk | proxmox-sdk |
|---|---|---|---|---|
| 4.5.8-4.7.0 GA | v0.0.31rc1 | proxbox-api 0.0.29 or later (the release that adds endpoint-owned cluster bindings) | v0.0.13 | v0.0.15 |

The declared stable NetBox range remains `4.5.8` through `4.7.99`, with actual
GA matrix evidence at `4.7.0`. This source preparation establishes no new
certification or hosted CI result.
