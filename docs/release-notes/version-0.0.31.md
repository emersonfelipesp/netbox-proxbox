# Version 0.0.31

## Summary

Version `0.0.31` adds native NetBox cluster binding for Proxmox endpoints,
endpoint-owned SSH application services, and verified Cloud Image SSH bindings.
It also makes the browser console work after an ordinary synchronization, adds
an option for full node network topology synchronization, and includes
integration fixes, raised dependency security floors, and fail-closed
validation of the release schema. Deploy proxbox-api `0.0.29` before upgrading the plugin.

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

## Browser console and synchronization

- The browser console now finds its backend. The backend request context
  dropped the WebSocket base that the endpoint configuration computes, so the
  console reported "No trusted proxbox-api endpoint matches this synchronized
  guest" for every guest and every endpoint configuration. The context now
  carries the browser and server WebSocket bases as typed fields. The console
  requires **Use WebSocket** to be enabled on the FastAPI endpoint, because the
  stored backend target covers the WebSocket host and port only in that state;
  a changed WebSocket host or port is treated as target drift.
- A new strict boolean
  `PLUGINS_CONFIG["netbox_proxbox"]["sync_node_interfaces"]` option, defaulting
  to `False`, forwards full node network topology synchronization to both the
  Network Interfaces stage and full update. It requires proxbox-api `0.0.20` or
  later. When enabled, bridges, bonds, Open vSwitch bridges, bonds, and internal
  ports, VLAN interfaces, and their Bridge, LAG, and Parent relationships are
  reconciled. Linux bond membership additionally depends on the backend network
  parser. Restart every NetBox application and worker process after changing
  the option.
- Successful full and selected-VM batch synchronization now resolves VM
  sync-state endpoint, node, and cluster relations from the exact current-run
  endpoint map and run stamp only after corroborating the VM's protected native
  cluster ownership. The cluster relation comes from the native-linked tracking
  row. When the VM has a native device, node selection comes from its unique
  same-endpoint device link and the recorded name must select the same node. A
  VM without a native device may fill only a null node relation from a unique
  same-endpoint name; the resolver never replaces an existing node from that
  fallback. Resolution repairs fully corroborated drift after relocation and
  leaves missing, ambiguous, stale, or contradictory identity unchanged with
  bounded job evidence. Browser consoles no longer require manual relation
  repair after an ordinary successful, corroborated sync.

On NetBox 4.5 and 4.6, a protected or otherwise refused delete of an endpoint,
application service, or service SSH credential from its object page is now
refused cleanly instead of returning HTTP 500. Every refused delete discards
the change events it queued. Plugin settings saved with an explicit primary key
are inserted correctly, and the backend capability probe keeps its request
timeout bounded in a form security linting can verify.

## Dependency security

Dependency floors now clear every published advisory that has a patched
release:

- The `cli` extra and the documentation requirements declare
  `aiohttp>=3.14.4` and `multidict>=6.9.1`. The development extra and
  dependency group declare `virtualenv>=21.14.9`, and the documentation
  requirements declare `certifi>=2026.10.19`.
- certifi is deliberately not a runtime dependency of the plugin, because it
  belongs to the NetBox environment that the plugin is installed into. Upgrade
  certifi in that environment to `2026.10.19` or later (GHSA-6q48-6c7w-9gw2)
  through the normal NetBox upgrade path.
- The development lock moves to aiohttp 3.14.5, certifi 2026.10.19, multidict
  7.1.0, and virtualenv 21.14.12. The pinned publish toolchain moves to
  packaging 26.3, which that virtualenv requires.
- Every NetBox compatibility-matrix input pins Pillow 13.0.0 and
  strawberry-graphql 0.327.2. Every hash lock pins certifi 2026.10.19, plus
  aiohttp 3.14.5 and multidict 7.1.0 where a companion installs them. The floor
  regression test also checks these transitive lock pins.

Two upstream advisories have no patched release yet and remain open residual
risk: Pillow GHSA-654x-cwwv-5j9c (11.2.1 through 13.0.0; Arrow export can
expose stale heap memory when `PILLOW_ALIGNMENT` is greater than 1) and
virtualenv GHSA-4f8h-vr72-p32c (21.14.8 and later; temporary app-data can leave
dangling seed package links when symlink seeding is configured). This project
uses neither feature. Until fixes are published, do not enable
`PILLOW_ALIGNMENT` with Arrow export, and use the default copy seeding or a
private persistent app-data directory for virtualenv.

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
