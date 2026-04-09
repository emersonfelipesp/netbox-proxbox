# `tests`

This directory contains the plugin's pytest test suite.

## Files And Ownership

- `conftest.py`: shared fixtures and compatibility stubs for Django/NetBox/requests so tests can run without a full NetBox install. Includes `StreamingHttpResponse` stubs and mock request helpers.
- `test_api_cluster.py`, `test_api_netbox_integration.py`, `test_api_source_contracts.py`: API layer, cluster serializer, and serializer contract checks.
- `test_backend_integration.py`, `test_backend_logs_view.py`, `test_job_stream.py`, `test_run_sync_stream.py`, `test_sse_contracts.py`: backend proxy, log view, stream, and SSE behavior.
- `test_cards.py`, `test_dashboard.py`, `test_keepalive_status.py`: dashboard/card hydration and service status checks.
- `test_cli_contracts.py`, `test_form_and_helper_source_contracts.py`, `test_frontend_contracts.py`: CLI, form/helper, and DOM/template/view contract coverage.
- `test_jobs.py`, `test_job_cancel.py`, `test_vm_sync_now_view.py`: job queueing, cancellation, and targeted VM sync behavior.
- `test_individual_sync_service.py`, `test_models_cluster.py`, `test_openapi_schema_service.py`, `test_proxmox_export_view.py`, `test_schedule_hints.py`, `test_schedule_sync_view.py`, `test_schemas.py`, `test_sync.py`, `test_sync_cluster.py`, `test_sync_now_cluster_node.py`, `test_utils.py`: service, model, schema, sync, and utility behavior.
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

## Links

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
