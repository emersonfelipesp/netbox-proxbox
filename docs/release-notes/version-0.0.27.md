# Version 0.0.27

## Standalone virtual machine consoles and hardened synchronization

Current backend-runtime pairing: netbox-proxbox 0.0.27rc17 <-> proxbox-api 0.0.23.post2 <-> proxmox-sdk 0.0.15 <-> netbox-sdk 0.0.13. This netbox-sdk version is proxbox-api's REST dependency only and does not provide the semantic MCP bridge.

This release adds a permission-gated Console tab directly to synchronized NetBox virtual machines. QEMU guests support noVNC and terminal sessions, and LXC guests support terminal sessions. The browser connects through the public proxbox-api relay without receiving Proxmox credentials, private topology, or reusable upstream tickets.

RC15 paired with `proxbox-api 0.0.23.post1` and failed the real-stack Page
Coverage gate because the expected backup inventory record was missing. RC16
pairs with post2, which restores that record, but its next Page Coverage run
failed because the mock returned no list-shaped node network response. RC17
retains post2 and adds Proxmox-compatible `{"data": [...]}` network envelopes
for `pve01`, `pve02`, and `pve03`.

- Restores node network synchronization in the real-stack Page Coverage gate
  by returning list-shaped Proxmox network data for every fixture node.

- Restores backup synchronization in the real-stack Page Coverage gate with
  `proxbox-api 0.0.23.post2`, which hydrates typed virtual-machine identity
  before filtering backup records.
- Resolves expected Proxmox VMIDs through the typed sync-state API during
  release validation, rejects incomplete, malformed, ambiguous, or
  ignored-filter responses, and verifies the linked NetBox virtual machine.
- Validates the canonical Proxbox home redirect during release checks, rejects
  ambiguous redirect and job-ID forms, and requires every polled Core Job
  resource to match the authoritative response header ID.
- Exposes the exact NetBox Core Job ID on successful Proxbox sync enqueue
  responses and uses that identity during release validation, avoiding
  first-page loss and concurrent same-name false positives under one bounded
  monotonic deadline.
- Gives disposable Page Coverage and Docker E2E Proxmox endpoints an explicit
  60-second request timeout and one bounded retry, avoiding hosted mock-server
  timeouts without changing production endpoint defaults.
- Bounds Proxmox fetch concurrency at one in disposable Page Coverage and
  Docker E2E stacks through the supported plugin settings API, preventing the
  lightweight mock server from dropping simultaneous VM configuration requests
  without changing production defaults.
- Exposes the existing endpoint `credential_storage_backend` field through the
  REST serializer, allowing an explicit `legacy_encrypted` override when
  netbox-openbao is unavailable without changing the global OpenBao setting.
- Keeps the disposable Page Coverage stack self-contained by selecting local
  encrypted storage on its singleton settings before any endpoint credentials,
  without weakening the OpenBao default used by production configuration.
- Runs public release metadata validation with the locked publish virtual
  environment, preventing hosted runners from selecting an unprovisioned
  system interpreter before TestPyPI or PyPI publication.
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

Deploy `proxbox-api 0.0.23.post2` before installing this plugin release. This
backend preserves the earlier duplicate virtual-machine reconciliation fix and
restores backup records by hydrating typed VM identity before backup filtering.

| NetBox | netbox-proxbox | proxbox-api | netbox-sdk | proxmox-sdk |
|---|---|---|---|---|
| 4.5.8-4.7.0 GA | v0.0.27rc17 | v0.0.23.post2 | v0.0.13 | v0.0.15 |
| 4.5.8-4.7.0 GA | v0.0.27rc16 | v0.0.23.post2 | v0.0.13 | v0.0.15 |
| 4.5.8-4.7.0 GA | v0.0.27rc15 | v0.0.23.post1 | v0.0.13 | v0.0.15 |
| 4.5.8-4.7.0 GA | v0.0.27rc14 | v0.0.23.post1 | v0.0.13 | v0.0.15 |
| 4.5.8-4.7.0 GA | v0.0.27rc13 | v0.0.23.post1 | v0.0.13 | v0.0.15 |
| 4.5.8-4.7.0 GA | v0.0.27rc12 | v0.0.23.post1 | v0.0.13 | v0.0.15 |
| 4.5.8-4.7.0 GA | v0.0.27rc11 | v0.0.23.post1 | v0.0.13 | v0.0.15 |
| 4.5.8-4.7.0 GA | v0.0.27rc10 | v0.0.23.post1 | v0.0.13 | v0.0.15 |
| 4.5.8-4.7.0 GA | v0.0.27rc9 | v0.0.22.post1 | v0.0.13 | v0.0.13 |
| 4.5.8-4.7.0 GA | v0.0.27rc8 | v0.0.22.post1 | v0.0.13 | v0.0.13 |
| 4.5.8-4.7.0 GA | v0.0.27rc7 | v0.0.22.post1 | v0.0.13 | v0.0.13 |
| 4.5.8-4.7.0 GA | v0.0.27rc6 | v0.0.22.post1 | v0.0.13 | v0.0.13 |
| 4.5.8-4.7.0 GA | v0.0.27rc5 | v0.0.22.post1 | v0.0.13 | v0.0.13 |
| 4.5.8-4.7.0 GA | v0.0.27rc4 | v0.0.22.post1 | v0.0.13 | v0.0.13 |
