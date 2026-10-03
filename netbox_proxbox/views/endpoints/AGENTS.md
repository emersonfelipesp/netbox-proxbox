# Endpoint View Guide

Endpoint views manage connection configuration and operational actions for
Proxmox and companion public APIs. Preserve object permissions, enabled-state
checks, endpoint scoping, and explicit failure messages.

Sync actions must remain scoped server-side; never trust endpoint identifiers or
scope supplied only by a browser form. Credential updates must use the model's
encryption helpers and must not echo secret values. Network actions use the
shared request helpers so destination validation, redirect refusal, timeouts,
and TLS policy stay consistent.

Endpoint tabs may display reflected state but must not perform hidden writes on
GET. POST actions require focused permission, scope, disabled-state, and failure
tests.

Sensitive exports use the shared uncached user-flag gate before resolving
material. The request actor owns both queryset restriction and provider reveal;
supplied token values cannot replace that actor. Refuse inaccessible explicit
selections before serialization, keep safe exports token-free, preserve filters
and endpoint-status controls, and set no-store on protected responses. Export
token-creation helpers are removed; ordinary NetBox token management remains.

Protected exports return generic failures with no-store. Never render or log
provider exception text, partial rows, request tokens, or credential values.
Audit only the fixed result, actor ID, visible object IDs, model, normalized
format, and a server-generated correlation ID.

Endpoint list views refuse arbitrary ExportTemplate and model YAML rendering.
These paths receive credential-bearing model objects and cannot enforce the
provider actor contract. Use the dedicated safe and protected endpoint exports.
