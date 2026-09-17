# Plugin Package Guide

The `netbox_proxbox` package must remain a self-contained public NetBox plugin.
Imports at module load time may use NetBox, Django, declared dependencies, and
this package only. Optional companion integrations must be imported lazily and
must degrade safely when absent.

Keep secrets encrypted at rest and out of serializers, templates, change logs,
exceptions, and ordinary exports. Keep network access bounded by destination
validation, redirect refusal for credentialed requests, timeouts, and TLS
verification. Preserve NetBox object permissions on every UI and API action.

Model or serializer changes require focused source-contract tests and real-Django
coverage when behavior depends on the ORM, database constraints, permissions, or
template rendering. Persisted changes require additive migrations.

The public semantic bridge API and agent-safety contract are documented in
[`docs/api/semantic-mcp-bridge.md`](../docs/api/semantic-mcp-bridge.md).
