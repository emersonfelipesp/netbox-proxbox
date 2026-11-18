# Version 0.0.32.post2

## Summary

This maintenance release pairs netbox-proxbox `0.0.32.post2` with
proxbox-api `0.0.32`. The paired backend contract adds `talos` as a supported
cloud-provisioning product type for direct image imports. The plugin's backend
route contract remains unchanged: all 313 published HTTP operations resolve,
and every audited plugin REST path and filter used by the backend remains
available.

Deploy proxbox-api `0.0.32` before the plugin. The certified NetBox range
remains `4.5.8` through `4.7.99`, including NetBox `4.7.0` GA. The paired
proxmox-sdk and netbox-sdk versions remain `0.0.15` and `0.0.13` respectively.

## Talos product type

The proxbox-api `0.0.32` cloud-provisioning schema accepts `talos` as a product
type. This is an enum and validation change in the backend; it adds no backend
HTTP operation and requires no plugin REST route or filter change. The
generated `0.0.32` route fixture is therefore byte-identical to the `0.0.31`
route fixture.

## Cluster tracking repair

Multi-endpoint installations upgraded from releases that predate
endpoint-scoped cluster discovery can contain a tracking row on every endpoint
for every Proxmox cluster. Those rows can remain linked to native NetBox
clusters by name and block both the cluster and device synchronization stages
with ownership conflicts.

The cluster and node pass now uses the current endpoint's live,
backend-scoped cluster name to release only stale native links owned by that
endpoint. It also clears sidecar pointers to those released rows. The repair
runs in its own transaction, never deletes a tracking row, never transfers
ownership, never writes another endpoint's rows or a foreign native cluster,
and refuses ambiguous evidence. Valid installations converge in one full
synchronization pass, and a second pass is idempotent.

## Documentation screenshot readiness

The documentation-screenshot workflow now uses the shared deadline-aware
readiness helper. NetBox keeps its 20-minute startup allowance, while the
Proxmox mock and backend use their shorter service deadlines. The workflow
fails early when a service reports a terminal or unhealthy state instead of
waiting through a fixed retry loop. This change affects CI and documentation
capture only; it does not change plugin runtime behavior.

## Database migrations

There is no migration in this release. The plugin migration directory is
unchanged from `0.0.32.post1`, and
`0108_v0_0_31_schema_validation` remains the schema tip.

## Upgrade

1. Deploy and qualify proxbox-api `0.0.32`.
2. Install netbox-proxbox `0.0.32.post2`.
3. Run the normal `collectstatic` command and restart every deployment-owned
   NetBox application and worker process.
4. Run a full synchronization. Upgraded multi-endpoint installations repair
   eligible stale cluster tracking during the cluster and node pass.

Running the normal migration command is safe, but this release has no new
migration to apply.

## Compatibility

| NetBox | netbox-proxbox | proxbox-api | proxbox-api internal netbox-sdk (REST only) | proxmox-sdk |
|---|---|---|---|---|
| 4.5.8-4.7.0 GA | v0.0.32.post2 | v0.0.32 | v0.0.13 | v0.0.15 |
