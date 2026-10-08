# API Guide
SSH secret APIs require the same fresh sensitive-data grant in addition to
API-token authentication, HTTPS, object visibility, and provider permissions.
New ObjectChange snapshots redact settings keys, credential material,
ciphertext, and provider references through a shared registry. Historical
snapshots are unchanged. Proxmox and NetBox endpoint target edits invalidate
`approved_connection_target_fingerprint`; credential payloads require exact
approval before resolution and again before transmission. Review the target
with GET and approve its fingerprint with PUT on the endpoint's
`connection-authority` API action. Approval requires sensitive-data access and
independent view/change access. Migration `0104_security_hardening`
leaves existing approvals blank. FastAPI target changes additionally require
sensitive authority before its existing authentication/adoption flow; disabled
backend target edits remain drafts.


Keep API behavior typed, permission-gated, and vendor-neutral. Use NetBox
serializers and viewsets for model resources. Operational endpoints must state
their permission, transport, failure, and secret-handling behavior in tests.

Secret-returning endpoints must require an authenticated API token with the
specific object permission and HTTPS outside development mode. Explicit
runtime encryption-key disclosure additionally requires an active superuser or
the per-user sensitive-data flag and independent view access to the settings
row. The flag does not grant that visibility; settings-change permission is
insufficient. Failed or missing settings-visibility lookups withhold the key.
Never include decrypted material in errors. Credentialed upstream
requests must reject redirects and use the shared destination-validation and
timeout policies.

`sensitive_data_access.py` owns superuser-only grant administration and the
secret-free, no-store caller readiness contract. All grant API methods, including
bulk requests and reads, require an active authenticated superuser. Neither
staff nor model permissions authorize grant management.
The superuser check is additive to NetBox's default permission classes. A
read-only API token must never authorize grant creation, update, or deletion,
even when its owner is a superuser.

Nested endpoint token serializers expose only token identity metadata. Never
serialize a core token key or its secret-dependent string representation.
Protected endpoint exports remain the explicit credential retrieval path.

Firecracker resource endpoints expose stable project-owned response shapes.
In explicit legacy mode, cloud-init intent preserves
`credential_reference_id` as an opaque external reference. With OpenBao
selected, the write-only `password` and `private_key` inputs create provider
credentials assigned to the parent VM; public `sshkeys` and `sshkeys_intent`
remain outside provider payloads.
FastAPI, PBS, PDM, and Firecracker host serializers expose only vendor-neutral
credential assignment readiness, detail, and lookup metadata. Token inputs are
write-only. Cloud-init exposes the same secret-free readiness and VM `login`
lookup shape. Their create, update, delete, and bulk mutations must begin the
provider transaction before NetBox enters its framework-owned atomic block and
must carry the authenticated request actor through that boundary.

Proxmox endpoint serializers resolve OpenBao SSH readiness from one response-
local metadata query restricted by the authenticated request actor's `reveal`
scope and the credential policy's group gate. Missing, dangling, unauthorized,
policy-denied, or wrong-type references fail closed. Serialization never reads
provider material.

`device_openbao_ssh_resolver.py` resolves the by-node SSH secrets fallback
against a netbox-openbao `ServiceEndpoint` + `Credential` pair on the node's
linked `dcim.Device`, gated by the same SSH-access check the local-credential
path applies. netbox-openbao is optional, checked with `apps.is_installed()`,
and its models are resolved per call with `apps.get_model()` — never a hard
import at module load time. The credential lookup is additionally scoped
through `Credential.objects.restrict(request.user, "reveal")`, the same
object permission netbox-openbao's own reveal API enforces, so a caller
authorized only for the local `NodeSSHCredential` path cannot reveal an
arbitrary device's OpenBao material through this fallback. More than one
credentialed SSH endpoint for a device is a denial (`PermissionDenied`); a
caller may narrow with an explicit `?port=`. There is deliberately no
further legacy fallback here: one would
require importing a non-public, environment-specific plugin, which
`scripts/check_public_boundary.py` refuses — with netbox-openbao absent,
without a matching endpoint, or predating the `ServiceEndpoint`/`Credential`
models this module expects (`apps.get_model()`'s `LookupError`, feature-
detected by `_get_openbao_model()`), the by-node secrets endpoint returns its
pre-existing 404.

`_credential_for_node_identifier()` and `_proxmox_node_for_identifier()` both
resolve *both* interpretations of `node_id` (own PK and linked-device PK) and
refuse (`_AmbiguousNodeIdentifier`, surfaced as 404) when they disagree about
which distinct row is meant — never silently preferring one.

The authoritative discovery, authentication, schema, invocation, and safety
contract is [`docs/api/semantic-mcp-bridge.md`](../../docs/api/semantic-mcp-bridge.md).
