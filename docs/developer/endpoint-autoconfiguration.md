# Endpoint Auto-Configuration

This page is the implementation, operations, and test-traceability reference
for automatic `FastAPIEndpoint` and `NetBoxEndpoint` setup. The feature removes
the requirement to paste companion endpoint secrets into every Proxbox form
without turning discovery into a network scan.

## Trust Boundary

Auto-configuration is operator-bounded:

- Once a `FastAPIEndpoint` exists, its persisted domain or IP, port, HTTP/TLS
  flags, and WebSocket flags are the complete backend allowlist. The plugin does
  not try a different address when that target fails.
- Before a row exists, backend candidates can come only from
  `PLUGINS_CONFIG["netbox_proxbox"]["backend_url"]` or the two same-site names
  derived from NetBox's trusted public origin:
  `backend.proxbox.<site-domain>` and `proxbox.backend.<site-domain>`.
- Local NetBox candidates come from the trusted public origin and an explicitly
  configured NetBox endpoint. Token selection must be unique; ambiguous
  endpoint rows or service tokens stay pending.
- Identity, health, bootstrap, authentication, and registration requests never
  follow redirects. Discovery never scans an address range, subnet, DNS zone,
  or caller-supplied host.
- Disabled rows are inventory only and perform no discovery or credential
  traffic.

Saving a new URL or IP in the NetBox UI is the control that changes the
allowlist. A host that is not represented by that configuration is rejected
before any credential-bearing request.

## Credential State Machine

| Local/remote state | Result |
|---|---|
| Disabled endpoint | Save locally; make no HTTP or WebSocket request. |
| Enabled endpoint, empty backend, no submitted key | Generate a strong key, retain it encrypted locally, then register that same key once after commit. |
| Enabled endpoint, initialized backend, locally held key | Authenticate the encrypted key against the exact configured target, then record its target fingerprint. |
| Enabled endpoint, initialized backend, no locally held key | Remain pending; do not ask the backend to reveal a key and do not bootstrap another one. |
| Manual rotation with a non-empty submitted key | Authenticate the candidate synchronously against the exact configured target before replacing ciphertext. |
| Blank edit with no security transition | Preserve the existing ciphertext byte-for-byte. |
| Target, TLS, or WebSocket drift | Block runtime credential use until the newly persisted target authenticates successfully. |
| Redirect, malformed authority, conflict, timeout, TLS error, or rejection | Preserve the prior secret and remain fail-closed. |

Successful adoption records
`backend_key_target_fingerprint`, a credential-free SHA-256 binding over the
canonical HTTP target, fallback IP, TLS policy, and WebSocket target. Runtime
HTTP and WebSocket callers recompute it with fresh related-object data before
returning the key.

Database commits are part of the security boundary. Generated candidates are
retained locally before `transaction.on_commit` can register them remotely;
rolled-back outer transactions therefore send nothing. Singleton creation uses
a PostgreSQL advisory lock, making startup and RQ retries idempotent across
processes.

## Operator Outcomes

The token field is optional for normal creation, activation, and configured
target changes. It remains an explicit input for manual key rotation. A pending
row is safe: runtime requests stay blocked until the target and key are proved.

To recover a legacy blank fingerprint after reviewing the stored target, use
the management command described in
[Backend Setup](../installation/backend-setup.md#manual-token-management).
The command is read-only without `--fix`, never prints token fragments, and
never contacts a disabled endpoint.

## Requirements-to-Tests Matrix

The mocked suite covers pure parsing, request, source, and workflow contracts.
The real-NetBox suite covers ORM locking, encrypted fields, forms, serializers,
signals, transactions, and runtime consumers.

| Requirement | Primary automated evidence |
|---|---|
| Existing endpoint authorizes only its exact domain/IP, port, and TLS policy | `test_ui_endpoint_is_the_exact_discovery_allowlist`, `test_ui_ip_endpoint_is_the_exact_discovery_allowlist`, `test_target_change_without_key_authenticates_exact_ui_target` |
| Rowless discovery is bounded to explicit config and trusted same-site names | `test_missing_backend_row_uses_same_site_allowlist`, `test_missing_backend_row_accepts_only_explicitly_configured_ip`, `test_discovery_candidates_are_bounded_and_canonical_first` |
| Unlisted, malformed, injected, or drifted targets fail before credentials or HTTP | `test_mutated_related_ip_blocks_every_runtime_credential_path`, `test_direct_model_rejects_authority_injection_before_http`, `test_stale_sensitive_save_is_rejected_before_http`, pure authority tables in `test_backend_key_adoption.py` |
| Redirects cannot receive HTTP or WebSocket credentials | redirect cases in `test_backend_key_adoption.py`, `test_websocket_redirect_never_receives_the_backend_key` |
| Disabled endpoints are no-network inventory | `test_new_disabled_blank_is_local_only`, `test_new_disabled_explicit_candidate_is_rejected_without_http`, `test_disabled_replacement_is_rejected_without_http`, disabled storage/WebSocket/command cases |
| Empty backend bootstraps exactly one retained key | `test_new_enabled_blank_discovers_and_bootstraps_automatically`, `test_new_enabled_explicit_candidate_bootstraps_once`, `test_generated_candidate_is_retained_before_commit_bootstrap` |
| Initialized backend authenticates a held key and never invents a replacement | `test_existing_encrypted_key_repairs_blank_target_fingerprint`, `test_initialized_backend_without_local_key_remains_pending`, `test_valid_rotation_authenticates_once_and_persists` |
| NetBox endpoint and service token can be discovered without a mandatory Proxbox form secret | `test_local_netbox_and_unique_service_token_are_discovered`, `test_explicit_netbox_ip_and_service_token_are_discovered`, `test_existing_netbox_endpoint_discovers_unique_service_token` |
| Ambiguous endpoint/token state remains pending | `test_multiple_netbox_endpoints_block_automatic_selection`, `test_ambiguous_netbox_service_tokens_remain_pending` |
| Rollback, post-save failure, and retry cannot lose the only key | rollback/recovery tests in `test_backend_key_adoption_django.py`, including `test_bootstrap_candidate_recovers_after_outer_rollback`, `test_integrity_failure_after_bootstrap_is_recoverable`, and `test_post_save_failure_after_bootstrap_is_recoverable` |
| Concurrent/stale writes cannot move credentials across targets | `test_stale_sensitive_save_is_rejected_before_http`, `test_stale_nonsecurity_partial_save_cannot_revert_winner`, `test_update_fields_rejects_excluded_replacement_candidate` |
| UI, import, REST, and direct-model writes share one persistence gate | `test_form_commit_false_has_no_http_and_save_uses_model_gate`, `test_import_form_and_api_serializer_use_the_same_gate`, `test_api_blank_token_update_preserves_exact_ciphertext` |
| WebSocket trust is checked for the connection lifetime | handshake, busy-stream, queued-command, redirect, task-replacement, and endpoint-save cancellation cases in `test_backend_key_adoption_django.py` |
| Configuration parsing and orchestration fail closed outside ORM transitions | `TestEndpointAutoconfigurationHelpers` in `test_backend_key_adoption_django.py` |
| Release validation runs the correct mocked/real-Django split and publishes one package per tag | `tests/test_pytest_django_scope.py` |

## Coverage Gates

The fast mocked suite must run with `-p no:django`; otherwise pytest-django
imports `django.test` against the suite's lightweight module stubs and aborts
during collection. The release-candidate and PyPI-candidate jobs use the same
flag. The real-NetBox matrix keeps pytest-django enabled and enforces at least
85% branch coverage for `services.endpoint_autoconfiguration`:

```bash
pytest tests/test_sync_state_models.py tests/test_sync_state_contracts.py \
  tests/test_backend_key_adoption_django.py \
  --ds=netbox.settings --reuse-db --create-db \
  --cov=netbox_proxbox.services.endpoint_autoconfiguration \
  --cov-branch --cov-fail-under=85
```

Local disposable services may override `NETBOX_TEST_DB_HOST`,
`NETBOX_TEST_DB_PORT`, `NETBOX_TEST_REDIS_HOST`, and
`NETBOX_TEST_REDIS_PORT`. CI leaves them unset and uses its isolated service
containers.

## Related Documentation

- [Backend Setup](../installation/backend-setup.md)
- [Authentication](authentication.md)
- [Endpoint Data Exchange](endpoint-sync.md)
- [CI and E2E Workflows](ci-e2e-workflows.md)
