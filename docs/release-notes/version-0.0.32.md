# Version 0.0.32

## Summary

Version `0.0.32rc1` is a maintenance release candidate that strengthens the
public end-to-end validation workflow. It resolves the selected plugin package,
backend source, and immutable container-image prerequisites once before the
compatibility matrix expands. Unavailable inputs are refused instead of being
replaced with a different backend runtime. Required containers that terminate
or become unhealthy stop validation immediately, while slow but valid startups
remain inside the existing monotonic deadlines.

Plugin runtime behavior, models, migrations, and dependencies are unchanged
from `0.0.31`. This release moves the supported backend pairing to proxbox-api
`0.0.31` and adds no migration.

## End-to-end prerequisite admission

The public Docker validation workflow now admits its selected package, source,
and image inputs before creating matrix jobs. Each admitted package URL is
bound to its distribution hash, each selected image is retained by immutable
digest, and development source selection retains its resolved identity. The
matrix consumes those admitted values without falling back to another package,
runtime, or image after refusal.

Readiness checks now stop as soon as a required service reaches a terminal or
unhealthy state. Services that are still starting continue to use the existing
per-service monotonic deadlines, so a valid slow startup is not treated as a
terminal failure.

## Upgrade notes

There is no database migration. Deploy proxbox-api `0.0.31` first, then upgrade
the plugin from `0.0.31` using the normal procedure and restart the
deployment-owned NetBox application and worker processes. The plugin runtime
and dependency set are unchanged. The latest netbox-proxbox and proxbox-api
releases are published and deployed as a pair.

## Compatibility

The supported pairing is proxbox-api `0.0.31`, with proxmox-sdk `0.0.15` and
netbox-sdk `0.0.13`. The netbox-sdk dependency belongs to proxbox-api's REST
client and does not provide the semantic MCP bridge.

| NetBox | netbox-proxbox | proxbox-api | netbox-sdk | proxmox-sdk |
|---|---|---|---|---|
| 4.5.8-4.7.0 GA | v0.0.32rc1 | v0.0.31 | v0.0.13 | v0.0.15 |

The declared stable NetBox range remains `4.5.8` through `4.7.99`, with actual
GA matrix evidence at `4.7.0`.
