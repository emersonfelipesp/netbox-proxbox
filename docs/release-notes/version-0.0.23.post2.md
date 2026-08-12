# Version 0.0.23.post2

netbox-proxbox `0.0.23.post2` adds bounded endpoint auto-configuration and
credential establishment for the Proxbox backend. It retains the existing
backend runtime pairing and supports NetBox `4.5.8` through `4.6.99`
(validated against `4.5.8` through `4.5.10` and `4.6.0` through `4.6.5`).

Current backend-runtime pairing: netbox-proxbox 0.0.23.post2 <-> proxbox-api (guest-VM-interface writer build / next release) <-> proxmox-sdk 0.0.12 <-> netbox-sdk 0.0.10. This netbox-sdk version is proxbox-api's REST dependency only and does not provide the semantic MCP bridge.

## Compatibility

| NetBox | netbox-proxbox | proxbox-api | proxbox-api internal netbox-sdk (REST only) | proxmox-sdk |
|--------|----------------|-------------|------------|-------------|
| >=4.5.8 | v0.0.23.post2 | guest-VM-interface writer build / next release | v0.0.10 | v0.0.12 |

Migration `0075_fastapi_backend_key_target_fingerprint` adds the durable,
credential-free target binding for existing and new backend rows. Run the
normal NetBox migration step during upgrade. No companion-backend upgrade is
required.

## Endpoint auto-configuration

- Operators may create or enable a Proxbox backend without pasting an API key.
  After the row commits, the plugin probes only the exact URL or IP, port, and
  TLS policy saved in that row. A healthy empty backend can complete its
  one-time key bootstrap automatically; an initialized backend without a
  locally held key remains pending and requires explicit recovery.
- When no backend row exists, startup discovery is limited to plugin-configured
  targets and same-site names derived from NetBox's trusted public origin. It
  does not scan the network, accept arbitrary user-supplied discovery targets,
  or follow redirects.
- NetBox endpoint configuration can be derived from the trusted local public
  origin, and the corresponding token is established through the already
  authenticated backend boundary rather than exposed in the UI.

## Security behavior

- The persisted endpoint is the complete discovery allowlist. Any IP or domain
  that is not the configured target or an explicitly derived same-site target
  is rejected before credentials are sent.
- Backend ciphertext is bound to a credential-free fingerprint covering the
  canonical HTTP target, fallback IP, TLS flags, and WebSocket target. Target
  drift fails closed until the operator explicitly re-establishes trust.
- Disabled endpoints never perform discovery or network access. HTTP and
  WebSocket authentication reject redirects, and ambient proxy settings are
  disabled for the credential-bearing WebSocket client.

## Operations

On startup, a successfully configured installation logs backend key
verification and the NetBox endpoint push. A configuration that cannot be
proved safe logs a `pending` result and continues serving NetBox without
attempting an untrusted connection.

The complete state machine, operator outcomes, requirements-to-tests matrix,
and real-Django branch-coverage gate are maintained in
[Endpoint Auto-Configuration](../developer/endpoint-autoconfiguration.md).
