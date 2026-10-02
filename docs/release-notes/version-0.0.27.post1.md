# Version 0.0.27.post1

## Summary

This post-release improves synchronization reliability and operator control for
large multi-cluster Proxmox estates. It adds configurable NetBox Device names
for synchronized Proxmox nodes, isolates synchronization failures by endpoint
and stage, bounds home-page status polling, adds a UI-configurable synchronization
job timeout, and documents the controls used to tune large deployments.

## Node Device naming

Global plugin settings now provide a node Device name template, with an
optional per-Proxmox-endpoint override. Supported placeholders are `{node}`,
`{cluster}`, `{cluster_slug}`, and `{endpoint}`. The default `{node}` template
preserves existing behavior. Validation rejects unsupported placeholders,
empty rendered names, and unsafe values before synchronization reaches NetBox.

## Synchronization resilience

- Cluster, datacenter, firewall, node, virtual-machine, and template stages
  isolate endpoint failures and retain actionable failure causes.
- Retryable backend responses honor bounded `Retry-After` guidance without
  allowing one endpoint to stall unrelated work indefinitely.
- Targeted synchronization stays within its requested scope and does not widen
  into a full-estate operation after a partial failure.
- Backend authentication, endpoint placement, and sync-state writes preserve
  exact endpoint identity throughout retries and reconciliation.

## Home status behavior

The home page coalesces duplicate status requests into a bounded burst and
reuses the current result while it is fresh. Slow or unavailable backend status
responses no longer create an unbounded request fan-out, and the UI continues
to expose an explicit degraded state.

## Large-estate tuning

**Proxbox > Settings** now exposes **Synchronization job timeout (seconds)**.
It defaults to 7,200 seconds, accepts 3,600–604,800 seconds, and applies to jobs
enqueued after the setting is saved. Already-running jobs retain the timeout
captured by RQ. The plugin settings and operator guide also document bounded
concurrency, batch, retry, and status-polling controls. Defaults preserve
existing small-estate behavior. Operators should increase limits gradually
while observing backend latency, NetBox database load, and per-stage failure
counts.

## Migration

Migration `0103_custom_fields_request_delay_help_text` is the only new migration
for this release. It adds the global and per-endpoint node Device name template
fields, adds the bounded synchronization job timeout setting, and clarifies that
the retained custom-field request delay setting is compatibility-only. Existing
node names remain unchanged until synchronization applies a non-default
template. The additive helper deliberately preserves the three new columns on
reverse because it cannot distinguish newly created columns from columns found
on a partial installation. Rolling migration state back is supported; a
forward reapply is idempotent. Operational recovery is therefore state-only,
not destructive column removal.

## Compatibility and upgrade

This release supports NetBox `4.5.8` through `4.7.0` GA and pairs with
`proxbox-api 0.0.23.post3`, `proxmox-sdk 0.0.15`, and `netbox-sdk 0.0.13`.

Current backend-runtime pairing: netbox-proxbox 0.0.27.post1 <-> proxbox-api 0.0.23.post3 <-> proxmox-sdk 0.0.15 <-> netbox-sdk 0.0.13. This netbox-sdk version is proxbox-api's REST dependency only and does not provide the semantic MCP bridge.

| NetBox | netbox-proxbox | proxbox-api | netbox-sdk | proxmox-sdk |
|---|---|---|---|---|
| 4.5.8-4.7.0 GA | v0.0.27.post1 | v0.0.23.post3 | v0.0.13 | v0.0.15 |

Deploy the backend first, then install `netbox-proxbox 0.0.27.post1`, run
`python manage.py migrate netbox_proxbox`, restart NetBox and RQ workers, and
verify one node and one virtual-machine synchronization before resuming
scheduled full-estate jobs.
