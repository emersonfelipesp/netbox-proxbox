# Version 0.0.30

## Summary

Version `0.0.30rc1` is the first release candidate for 0.0.30. It gives each
Proxmox endpoint an authoritative native NetBox cluster relation, models SSH
access as an endpoint-owned application service, and sends verified Cloud Image
SSH bindings to proxbox-api with durable ownership receipts.

This release requires the proxbox-api release that adds endpoint-owned cluster
bindings. That backend release must be released and deployed before the plugin.


## Native NetBox cluster binding

Each Proxmox endpoint can own one native NetBox cluster through a database-
enforced, one-to-one relation. A protected local synchronization action creates
or resolves the cluster and updates the endpoint, tracking row, and typed sync
state atomically. Names alone never establish ownership, existing ownership is
never silently reassigned, and endpoint and related-object permissions are
checked independently. Endpoint and cluster detail pages expose the relation
only when the caller can view the related object.

## Endpoint-owned SSH application services

SSH access can now follow an explicit chain:

`SSH Credential -> Application Service (type SSH) -> IP Address -> Proxmox Endpoint`

The SSH form can quick-add the endpoint IP address. Under an endpoint lock, it
reuses a matching SSH service or creates one automatically. The endpoint owns
the service, and each service has at most one SSH credential. Creating or
changing the chain requires the relevant endpoint, service, credential, and IP
permissions; reading secret material additionally requires credential reveal
access and the exact enabled `console` assignment.

Without netbox-openbao, credential material is encrypted locally with Fernet.
When netbox-openbao is enabled, an operator can select an existing SSH
credential or create a new one. The provider transaction assigns that
credential to the service for the primary `console` purpose. Provider-backed
credentials never fall back to local storage, and supported deletion removes
authorized assignments without deleting shared credentials.

## Verified Cloud Image SSH bindings

Cloud Image bake configuration now stores the target Proxmox node and the
proxbox-api-host identity-file path on the endpoint. For an enabled API and SSH
endpoint with the required write and Packer gates, NetBox verifies that the
selected inventory node belongs at the effective SSH host before sending the
complete binding: target node, host, username, port, identity file, and pinned
host-key fingerprint.

Before transmitting binding values, NetBox commits a SHA-256 management receipt
in a durable transaction. Missing ownership, receipt failures, invalid row
counts, or an outer uncommitted transaction block the push. A backend commit
followed by a timeout remains managed, and compare-and-set clearing preserves a
newer concurrent receipt.

## Fixes

- The selected SSH credential source now supplies the effective username and
  actual host consistently. A configured bake target requires renewed
  connection approval when that authority changes.
- Cloud Image value pushes now require a committed ownership receipt before
  outbound mutation.
- Active endpoint detail pages again show the caller-visible native cluster
  link.
- Failed endpoint or application-service API bulk deletion now rolls back its
  provider transaction, preserving OpenBao assignments when NetBox reports
  malformed, duplicate, missing, protected, or otherwise invalid object IDs.

## Upgrade notes

1. Release and deploy the proxbox-api release that adds endpoint-owned cluster
   bindings. Do this before installing `netbox-proxbox 0.0.30rc1`.
2. Install the plugin and run `python manage.py migrate netbox_proxbox`.
3. Run `python manage.py collectstatic --no-input` and restart every NetBox
   application and worker process.
4. Review each endpoint's native cluster ownership, SSH service chain, and
   Cloud Image target before enabling writes or Packer access.
5. Reapprove configured Cloud Image bake bindings when the selected SSH
   identity or effective host changed.

The release contains one plugin migration: `0107_v0_0_30_release`. It depends
on `0106_device_sync_scope_and_netbox_token_approval` and is atomic and
idempotent. It consolidates the three unpublished development migrations for
native cluster binding, endpoint-owned SSH services, and Cloud Image SSH
binding.

A database that already applied the unpublished
`0107_endpoint_native_cluster_binding` migration adopts its existing column,
constraint, and data. Its orphaned migration-recorder row is harmless. Reverse
migration removes the Cloud Image fields and SSH-service schema but retains the
native cluster ownership column and values so reapplication can adopt them.

## Compatibility baseline

| NetBox | netbox-proxbox | proxbox-api | netbox-sdk | proxmox-sdk |
|---|---|---|---|---|
| 4.5.8-4.7.0 GA | v0.0.30rc1 | proxbox-api 0.0.29 or later (the release that adds endpoint-owned cluster bindings) | v0.0.13 | v0.0.15 |

The plugin declares NetBox `4.5.8` through `4.7.99`; continuous integration
verifies the listed GA range through NetBox `4.7.0`. The backend must be
upgraded first because older proxbox-api releases do not implement the
endpoint-owned cluster contract required by this plugin release.
