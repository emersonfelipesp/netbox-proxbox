# Version 0.0.26.post2

## Production console handoff and Proxmox operations

Current backend-runtime pairing: netbox-proxbox 0.0.26.post2 <-> proxbox-api 0.0.21.post6 <-> proxmox-sdk 0.0.13 <-> netbox-sdk 0.0.10. This netbox-sdk version is proxbox-api's REST dependency only and does not provide the semantic MCP bridge.

This post release restores the complete production browser-console path and packages the current reviewed Proxbox operations work.

- NetBox now invokes the VM/LXC console extension through the supported `buttons()` template-extension hook. The generated handoff opens the matching NMS route in a new tab with `noopener noreferrer` protection.
- The NMS route creates an authenticated, short-lived same-origin console session. QEMU guests use noVNC and LXC guests use the xterm terminal workflow provided by `proxbox-api 0.0.21.post6`.
- Adds independently configured Proxmox InfluxDB metrics models, settings, API endpoints, dashboards, and operating documentation.
- Adds a human-only review and purge page for soft-deleted Proxbox VM inventory.
- Documents the audited NetBox-to-Proxmox write path and isolates tenant-related test lanes.

No compatibility floor or ceiling changes in this release. NetBox `4.5.8` through official `4.7.0` GA remains supported.

| NetBox | netbox-proxbox | proxbox-api | netbox-sdk | proxmox-sdk |
|---|---|---|---|---|
| 4.5.8-4.7.0 GA | v0.0.26.post2 | v0.0.21.post6 | v0.0.10 | v0.0.13 |
