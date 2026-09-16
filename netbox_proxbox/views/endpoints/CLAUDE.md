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
