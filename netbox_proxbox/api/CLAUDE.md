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
Cloud-init intent uses `credential_reference_id` as an opaque external reference;
the plugin does not import or assume a credential-provider implementation.

The authoritative discovery, authentication, schema, invocation, and safety
contract is [`docs/api/semantic-mcp-bridge.md`](../../docs/api/semantic-mcp-bridge.md).
