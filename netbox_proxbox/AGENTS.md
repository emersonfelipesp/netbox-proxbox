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

`security_checks.py` registers database-tagged Django system checks
(`netbox_proxbox.W101`–`W105`, plus `W100` when an inspection fails for any
reason other than unmigrated tables; `W105` reports a NetBox token configured
for proxbox-api that cannot read the plugin settings) for enabled backend endpoints on plain HTTP or
unverified TLS, enabled Proxmox endpoints without TLS verification, and a
legacy raw plugin encryption key. They run for `migrate` and
`check --database default` only, return nothing before the plugin tables exist,
and never rewrite rows; new endpoints default to HTTPS and TLS verification.
