# `tests`

This directory contains the plugin's pytest test suite.

## Files And Ownership

- `conftest.py`: shared fixtures and compatibility stubs for Django/NetBox/requests so tests can run without a full NetBox install. Includes `StreamingHttpResponse` stubs and mock request helpers.
- `test_api_cluster.py`, `test_api_netbox_integration.py`, `test_api_source_contracts.py`: API layer, cluster serializer, and serializer contract checks. `test_api_source_contracts.py` also covers the ten non-model `APIView` classes (`HomeAPIView`, `DashboardAPIView`, resource views, `ScheduleSyncAPIView`, `BackendLogsAPIView`): class existence, base class, permission class assignment, HTTP methods, URL registration, API root keys, and serializer field contracts.
- `test_backend_integration.py`, `test_backend_logs_view.py`, `test_job_stream.py`, `test_run_sync_stream.py`, `test_sse_contracts.py`: backend proxy, log view, stream, and SSE behavior.
- `test_cards.py`, `test_dashboard.py`, `test_keepalive_status.py`: dashboard/card hydration and service status checks.
- `test_cli_contracts.py`, `test_form_and_helper_source_contracts.py`, `test_frontend_contracts.py`: CLI, form/helper, and DOM/template/view contract coverage.
- `test_jobs.py`, `test_job_cancel.py`, `test_vm_sync_now_view.py`: job queueing, cancellation, and targeted VM sync behavior.
- `test_individual_sync_service.py`, `test_models_cluster.py`, `test_openapi_schema_service.py`, `test_proxmox_export_view.py`, `test_schedule_hints.py`, `test_schedule_sync_view.py`, `test_schemas.py`, `test_sync.py`, `test_sync_cluster.py`, `test_sync_now_cluster_node.py`, `test_utils.py`: service, model, schema, sync, and utility behavior.
- `test_version.py`: AST-based pin on `ProxboxConfig.version`, `min_version`, `max_version`. Fails loudly when one drifts so docs and release notes stay aligned.
- `test_signals.py`: AST contract for the three `@receiver(post_save)` handlers in `netbox_proxbox/signals.py` that bootstrap the proxbox-api backend.
- `test_services_http_client.py`: behavior tests for `RequestsHttpClient` exception translation (`HttpConnectionError`, `HttpTimeoutError`, `HttpSslError`) and the singleton accessor; uses `unittest.mock` against `requests.get/post/put/delete`.
- `test_views_error_utils.py`: behavior tests for `parse_requests_response_json`, `extract_backend_error_detail`, and `extract_proxmox_backend_error_detail` covering connection-refused, timeout, HTML-on-error, generic-detail-with-message, and Python-exception-append branches.
- `test_services_sync_backup_routines.py`: behavior tests for the `_get_backup_routine_id_from_job_id` helper and the early-exit error paths of `sync_backup_routines`. Stubs Django/NetBox via importlib + `sys.modules`.
- `test_services_backend_context.py`: AST contract for `get_fastapi_request_context` / `get_fastapi_endpoint_with_token` signatures and the three endpoint-resolution branches in `services/backend_context.py`.
- `test_views_vm_config.py`: AST contract for `ProxmoxVMConfigTabView` — `register_model_view` path/name, `ObjectView` base, `ViewTab` label/permission, and the helper extractors.
- `test_views_storage.py`: AST contract for the eight `ProxmoxStorage*` view classes — `__all__` membership, list-view `path=""` registration, child-tab paths/labels/permissions, and the detail view's short `request_timeout`.
- `test_vm_sync_device_flag_enforcement.py`: pins PR #342. Asserts the six `overwrite_device_*` fields are in `OVERWRITE_FIELDS` and that `_build_base_query_params` serializes per-endpoint device-flag values into the SSE query string.
- `test_backup_replication_views.py`: view coverage for backup routine and replication list/detail pages.
- `test_home_context.py`: tests for home page context assembly.
- `test_stack_setup.py`, `test_stack_sync_polling.py`: integration-level stack setup and sync polling behavior tests.
- `test_templatetags.py`: tests for custom Proxbox template tag helpers.
- `e2e/`: stack-oriented tests that exercise the proxbox-api and NetBox integration flow end to end.
- `netbox_test_configuration.py`: NetBox settings stub used during tests.

## Dependencies

- Inbound: CI pipeline and local `pytest` invocations.
- Outbound: the plugin views, JS, templates, and utility modules under `netbox_proxbox/`.

## Notes

- Tests rely heavily on compatibility stubs in `conftest.py` rather than a live NetBox database.
- When changing view, job-enqueue, or template contracts, update both the runtime code and those stubs.
- `test_frontend_contracts.py` guards against accidental regressions in public-facing attribute names and JS function signatures.
- **Optional-dependency tests:** `test_sse_schema_mirror.py` is a contract-mirror test that requires `proxbox-api` on the import path. It uses `pytest.importorskip("proxbox_api...")` and is silently skipped in the standard CI matrix; the nightly contracts workflow installs `proxbox-api` from PyPI and runs this file explicitly so cross-repo overwrite-flag drift is detected.
- **AST-based source contracts** (e.g. `test_version.py`, `test_signals.py`, `test_services_backend_context.py`, `test_views_vm_config.py`, `test_views_storage.py`) parse the relevant module with `ast` and never bootstrap Django. Use this pattern when the runtime cost of starting NetBox would dominate the test value — it is the same approach as `test_proxmox_endpoint_settings_view.py`.
- **Coverage:** `pyproject.toml` defines `[tool.coverage.run]` with `source = ["netbox_proxbox"]` and `branch = true`, plus `[tool.coverage.report]` with `exclude_lines` for `TYPE_CHECKING` and `pragma: no cover` markers. CI invokes `pytest --cov=netbox_proxbox`.

## Links

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
