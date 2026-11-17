# Version 0.0.32.post1

## Summary

This maintenance release aligns the plugin and command-line client with the
published `proxbox-api 0.0.31` contract. It adds the node inventory route,
simplifies the repair flow, supplies the required HA actor identity, restores
backend lookup filters, corrects Proxmox metrics endpoint resolution, and
removes or corrects command-line operations that targeted unavailable routes
or used the wrong request shape.

The release pairs with `proxbox-api 0.0.31`, which must be deployed before the
plugin. This release adds no database migration; migration
`0108_v0_0_31_schema_validation` remains the schema tip.

The certified NetBox range remains `4.5.8` through `4.7.99`, including NetBox
`4.7.0` GA.

## Release identity

The package and plugin source both identify this maintenance release as
`0.0.32.post1`.

## Backend contract alignment

The plugin REST API now serves Proxmox node records at both
`/api/plugins/proxbox/nodes/` and
`/api/plugins/proxbox/proxmox-nodes/`. Existing serializer hyperlinks and URL
names continue to use the `proxmox-nodes` route.

Sync-state repair now queues the full rebuild synchronization directly. It no
longer requests retired backend custom-field reconciliation or reports a
custom-field warning.

HA arm and disarm requests now send the authenticated NetBox username in the
`X-Proxbox-Actor` header required by the backend write contract. Every
audited write (HA, firewall, and Proxmox tag actions) now builds that header
value the same way: a name made only of printable Latin-1 characters other than
`%`, with no leading or trailing whitespace, is sent unchanged, and any other
name is percent-encoded as UTF-8. The
request is always sent, a raw and an encoded name cannot collide, and the
attribution stays exact.

Plugin REST filters now accept the backend's lookup keys for VM cloud-init
rows, Proxmox nodes, SDN route maps, and SDN prefix lists. These filters
prevent NetBox from silently ignoring the lookup and returning the first row
from an unrelated VM, cluster, route-map order, or prefix CIDR. The
`virtual_machine_id` filter matches the NetBox virtual machine primary key, and
the `proxmox_cluster_id` node filter matches the tracked Proxmox cluster
primary key.

Proxmox API metrics pulls now select `source=database` and translate the plugin
endpoint primary key to the backend endpoint primary key. This lets the backend
open its stored credential-bearing Proxmox session without exposing endpoint
credentials through the plugin REST response.

The `pxb extras custom-fields-create`, `pxb proxmox nodes lxc`, and `pxb
proxbox` commands have been removed because `proxbox-api 0.0.31` does not
provide their routes. `pxb proxmox viewer generate` now sends the backend's
typed query parameters instead of a JSON body. The command help states that the
backend must enable runtime code generation.

A deterministic source contract now checks literal client routes against all
313 published backend OpenAPI operations, documents conditionally mounted
routes, and checks every backend-issued lookup filter for the audited plugin
resources against the matching plugin filter set.
