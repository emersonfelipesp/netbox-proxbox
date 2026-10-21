# Version 0.0.31

## Summary

Version `0.0.31` adds native NetBox cluster binding for Proxmox endpoints,
endpoint-owned SSH application services, and verified Cloud Image SSH bindings.
It also includes integration fixes and fail-closed validation of the release
schema. Deploy proxbox-api `0.0.29` before upgrading the plugin.

## Native cluster binding

Each Proxmox endpoint can own one native NetBox Cluster. The protected
`sync-cluster` action reconciles the endpoint, native cluster, tracking row, and
typed synchronization state in one transaction. It requires the established
endpoint and core permissions, does not claim a cluster by name alone, and does
not silently reassign an existing owner.

## Endpoint-owned SSH application services

SSH access now uses an endpoint-owned application-service chain:

`SSH Credential` -> `Application Service (type SSH)` -> `IP Address` ->
`Proxmox Endpoint`

The endpoint form can add the endpoint IP quickly and automatically creates or
reuses the matching SSH service. Credential material can use local
Fernet-encrypted storage or the optional netbox-openbao integration. Secret
reads remain permission-gated, and provider-backed writes and assignment
changes remain transactional.

## Verified Cloud Image SSH bindings

Cloud Image builds can bind a selected Proxmox node and backend identity-file
path to the endpoint. The plugin verifies that the selected node belongs at the
effective SSH address before sending the complete binding. Managed value pushes
write a durable SHA-256 receipt before transmission, making failed or timed-out
updates retryable without treating unverified state as current. Closing a gate
or clearing the configured binding revokes managed backend state without
exposing credentials.

## Integration fixes

This release keeps optional companion imports lazy, improves endpoint and
credential ownership checks, preserves response-local service-monitoring
readiness, and includes fixes across synchronization, operational endpoint
selection, OpenBao-backed credential handling, and NetBox 4.5 through 4.7
compatibility.

## Migrations and upgrade

The release contains two migrations at this boundary:

- `0107_v0_0_30_release` creates the native cluster ownership, endpoint-owned
  SSH service, and Cloud Image SSH binding schema.
- `0108_v0_0_31_schema_validation` validates the physical objects created by
  0107 and does not repair unexpected schema automatically.

The migrations run in separate transactions. If 0108 fails, 0107 can remain
committed while 0108 remains unapplied. Preserve the database schema, data, and
migration-recorder evidence, then obtain a reviewed repair before retrying.
Reversing 0108 is a no-op for schema and data; reapplying it validates again.

Back up the database and configuration before upgrading. Deploy proxbox-api
`0.0.29` first, install netbox-proxbox `0.0.31`, run migrations and
`collectstatic`, and restart all NetBox application and worker processes.

## Compatibility

The released runtime pairing is netbox-proxbox `0.0.31`, proxbox-api `0.0.29`,
proxmox-sdk `0.0.15`, and netbox-sdk `0.0.13`. The netbox-sdk dependency belongs
to proxbox-api's REST client and does not provide the semantic MCP bridge.

| NetBox | netbox-proxbox | proxbox-api | netbox-sdk | proxmox-sdk |
|---|---|---|---|---|
| 4.5.8-4.7.0 GA | v0.0.31 | v0.0.29 | v0.0.13 | v0.0.15 |

The declared stable NetBox range is `4.5.8` through `4.7.99`, with dedicated
GA matrix evidence at `4.7.0`.

## Candidate history

- `0.0.31rc1` added `0108_v0_0_31_schema_validation` after the immutable 0107
  migration.
- `0.0.31rc2` aligned the proxbox-api `0.0.29` pairing and release-validation
  defaults without changing application behavior or migration bytes.
