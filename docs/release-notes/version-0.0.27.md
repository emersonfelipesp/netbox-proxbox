# Version 0.0.27

## Standalone virtual machine consoles and hardened synchronization

Current backend-runtime pairing: netbox-proxbox 0.0.27rc5 <-> proxbox-api 0.0.22.post1 <-> proxmox-sdk 0.0.13 <-> netbox-sdk 0.0.13. This netbox-sdk version is proxbox-api's REST dependency only and does not provide the semantic MCP bridge.

This release adds a permission-gated Console tab directly to synchronized NetBox virtual machines. QEMU guests support noVNC and terminal sessions, and LXC guests support terminal sessions. The browser connects through the public proxbox-api relay without receiving Proxmox credentials, private topology, or reusable upstream tickets.

- Authorizes each console request against the exact NetBox virtual machine and Proxbox endpoint.
- Restores durable endpoint bindings and fails closed when a target cannot be proved.
- Supports the certified NetBox 4.5.8 through 4.7.0 GA matrix with real-Django compatibility coverage.
- Adds pull-based Proxmox metrics and deterministic reconciliation with the existing InfluxDB source.
- Preserves bounded session lifetimes, origin checks, redacted diagnostics, and server-side TLS policy.
- Restores the published `0085_remove_vm_reflection_custom_fields` migration byte-for-byte so package deployment preserves immutable migration history.
- Keeps public release promotion limited to exact repository-linked package provenance; deployment authorization and host evidence remain outside this public repository.
- Adds `credential_reference_id` additively for existing schemas, copies populated historical references without dropping the downgrade-compatible column, and fails closed on structurally ambiguous predecessors. Fresh installs receive the generic field from the sanitized `0064` migration source.
- Resolves the companion RPC plugin's selected backend before considering the sole-backend fallback and refuses to create monitoring rows when selection remains ambiguous.
- Removes the retired external SSH-credential fallback. Every enabled API + SSH node must have a local `NodeSSHCredential`; disabled and API-only nodes are reported separately and do not block the upgrade. Run `python manage.py audit_node_ssh_credentials --fail-on-missing`, create local credentials for every blocker, and do not restart NetBox until the command exits successfully with zero blockers. Requests for nodes without a local credential now return HTTP 404 with an actionable provisioning message.
- Replaces the generic VM console endpoint-unavailable response with stable diagnostics that distinguish backend connectivity from missing, disabled, drifted, or inconsistent NetBox endpoint and node relations.
- Shows exact administrator remedies and, when the caller has core Job add permission, a CSRF-protected **Repair all enabled endpoints** action with an explicit warning that the full synchronization can reconcile stale NetBox inventory outside the displayed VM.

Deploy `proxbox-api 0.0.22.post1` before installing this plugin release.

| NetBox | netbox-proxbox | proxbox-api | netbox-sdk | proxmox-sdk |
|---|---|---|---|---|
| 4.5.8-4.7.0 GA | v0.0.27rc5 | v0.0.22.post1 | v0.0.13 | v0.0.13 |
| 4.5.8-4.7.0 GA | v0.0.27rc4 | v0.0.22.post1 | v0.0.13 | v0.0.13 |
