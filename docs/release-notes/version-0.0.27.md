# Version 0.0.27

## Standalone virtual machine consoles and hardened synchronization

Current backend-runtime pairing: netbox-proxbox 0.0.27rc1 <-> proxbox-api 0.0.22.post1 <-> proxmox-sdk 0.0.13 <-> netbox-sdk 0.0.13. This netbox-sdk version is proxbox-api's REST dependency only and does not provide the semantic MCP bridge.

This release adds a permission-gated Console tab directly to synchronized NetBox virtual machines. QEMU guests support noVNC and terminal sessions, and LXC guests support terminal sessions. The browser connects through the public proxbox-api relay without receiving Proxmox credentials, private topology, or reusable upstream tickets.

- Authorizes each console request against the exact NetBox virtual machine and Proxbox endpoint.
- Restores durable endpoint bindings and fails closed when a target cannot be proved.
- Supports the certified NetBox 4.5.8 through 4.7.0 GA matrix with real-Django compatibility coverage.
- Adds pull-based Proxmox metrics and deterministic reconciliation with the existing InfluxDB source.
- Preserves bounded session lifetimes, origin checks, redacted diagnostics, and server-side TLS policy.

Deploy `proxbox-api 0.0.22.post1` before installing this plugin release.

| NetBox | netbox-proxbox | proxbox-api | netbox-sdk | proxmox-sdk |
|---|---|---|---|---|
| 4.5.8-4.7.0 GA | v0.0.27rc1 | v0.0.22.post1 | v0.0.13 | v0.0.13 |
