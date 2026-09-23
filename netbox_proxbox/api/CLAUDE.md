# API Guide

Keep API behavior typed, permission-gated, and vendor-neutral. Use NetBox
serializers and viewsets for model resources. Operational endpoints must state
their permission, transport, failure, and secret-handling behavior in tests.

Secret-returning endpoints must require an authenticated API token with the
specific object permission and HTTPS outside development mode. Never return an
encryption key or include decrypted material in errors. Credentialed upstream
requests must reject redirects and use the shared destination-validation and
timeout policies.

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
