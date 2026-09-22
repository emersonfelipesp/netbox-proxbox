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

The authoritative discovery, authentication, schema, invocation, and safety
contract is [`docs/api/semantic-mcp-bridge.md`](../../docs/api/semantic-mcp-bridge.md).
