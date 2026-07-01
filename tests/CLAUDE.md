# `tests`

This directory contains the plugin's pytest test suite.

## Files And Ownership

- `conftest.py`: shared fixtures and compatibility stubs for Django/NetBox/requests so tests can run without a full NetBox install. Includes `StreamingHttpResponse` stubs and mock request helpers.
- `test_api_cluster.py`, `test_api_netbox_integration.py`, `test_api_source_contracts.py`: API layer, cluster serializer, and serializer contract checks. `test_api_source_contracts.py` also covers the ten non-model `APIView` classes (`HomeAPIView`, `DashboardAPIView`, resource views, `ScheduleSyncAPIView`, `BackendLogsAPIView`): class existence, base class, permission class assignment, HTTP methods, URL registration, API root keys, and serializer field contracts.
- `test_backend_integration.py`, `test_backend_logs_view.py`, `test_job_stream.py`, `test_run_sync_stream.py`, `test_sse_contracts.py`: backend proxy, log view, stream, and SSE behavior.
- `test_cards.py`, `test_dashboard.py`, `test_keepalive_status.py`: dashboard/card hydration and service status checks.
- `test_cli_contracts.py`, `test_form_and_helper_source_contracts.py`, `test_frontend_contracts.py`: CLI, form/helper, and DOM/template/view contract coverage.
- `test_jobs.py`, `test_job_cancel.py`, `test_vm_sync_now_view.py`: job queueing, cancellation, and targeted VM sync behavior.
- `test_individual_sync_service.py`, `test_models_cluster.py`, `test_models_overwrites.py`, `test_openapi_schema_service.py`, `test_proxmox_export_view.py`, `test_schedule_hints.py`, `test_schedule_sync_view.py`, `test_schemas.py`, `test_sync.py`, `test_sync_cluster.py`, `test_sync_now_cluster_node.py`, `test_utils.py`: service, model, schema, sync, overwrite-field, and utility behavior.
- `test_sdn_models.py`: source and migration contracts for `ProxmoxSdnFabric`, `ProxmoxSdnRouteMap`, and `ProxmoxSdnPrefixList` — model file existence, required/optional fields, `UniqueConstraint` presence, `NetBoxModel` base, `models/__init__` exports, `choices.py` `SdnFabricTypeChoices`, navigation items and URLs, views (list views, `register_model_view`), filtersets, tables, forms, and the `sync_sdn` service (`SdnSyncResult` dataclass, backend endpoint paths). References the consolidated squash migration `0039_squashed_0039_0042_pve_9_2_firewall_sdn.py`.
- `test_datacenter_models.py`: source and migration contracts for `ProxmoxDatacenterCpuModel` — model file existence, required fields, `UniqueConstraint` presence, `NetBoxModel` base, `models/__init__` exports, navigation items and URLs, views, filtersets, tables, forms, and the `sync_datacenter` service. References the consolidated squash migration `0039_squashed_0039_0042_pve_9_2_firewall_sdn.py`.
- `test_version.py`: AST-based pin on `ProxboxConfig.version`, `min_version`, `max_version`, plus docs-contract checks for current release metadata, backend pairing, and compatibility-table rows. Fails loudly when one drifts so docs and release notes stay aligned.
- `test_signals.py`: AST contract for the three `@receiver(post_save)` handlers in `netbox_proxbox/signals.py` that bootstrap the proxbox-api backend.
- `test_services_http_client.py`: behavior tests for `RequestsHttpClient` exception translation (`HttpConnectionError`, `HttpTimeoutError`, `HttpSslError`) and the singleton accessor; uses `unittest.mock` against `requests.get/post/put/delete`.
- `test_views_error_utils.py`: behavior tests for `parse_requests_response_json`, `extract_backend_error_detail`, and `extract_proxmox_backend_error_detail` covering connection-refused, timeout, HTML-on-error, generic-detail-with-message, and Python-exception-append branches.
- `test_services_sync_backup_routines.py`: behavior tests for the `_get_backup_routine_id_from_job_id` helper and the early-exit error paths of `sync_backup_routines`. Stubs Django/NetBox via importlib + `sys.modules`.
- `test_services_backend_context.py`: AST contract for `get_fastapi_request_context` / `get_fastapi_endpoint_with_token` signatures and the three endpoint-resolution branches in `services/backend_context.py`.
- `test_views_vm_config.py`: AST contract for `ProxmoxVMConfigTabView` — `register_model_view` path/name, `ObjectView` base, `ViewTab` label/permission, and the helper extractors.
- `test_views_storage.py`: AST contract for the eight `ProxmoxStorage*` view classes — `__all__` membership, list-view `path=""` registration, child-tab paths/labels/permissions, and the detail view's short `request_timeout`.
- `test_proxmox_endpoint_settings_view.py`: AST contract for the Proxmox endpoint Settings tab registration, permissions, form usage, and context wiring.
- `test_endpoint_templates_tab.py`: AST/source + behavior contracts for the endpoint **Templates** tab. Covers `ProxmoxEndpointTemplatesTabView` structure (`ObjectView` base, `__all__`, `template_name`, `ViewTab` label/permission/weight, `path="templates"`, `get_extra_context` + classification helpers, wiring into `views/__init__.py`), the live-fetch source contract (`/cloud/vm/templates` with `cloud_init_only=false` + `/cloud/lxc/templates`, `get_fastapi_request_context`/`resolve_backend_endpoint_id`, cloud-init derived from `cloud_init_drives`/`cicustom`, graceful `backend_error` degradation), the `integrations/packer.py` detection + guarded add-URL helpers, template contracts (three `data-category` groups, category filter, packer create button disabled **with a working tooltip** when netbox-packer is absent), and mirrored behavior tests for cloud-init classification / byte→GiB / LXC name derivation. Pure AST/source based — no NetBox bootstrap.
- `test_endpoint_create_instance.py`: AST/source + local-stub behavior contracts for the Templates-tab **Create new instance** wizard. Covers the registered `create-instance` view, POST-only permission gate, `allow_writes` early exit, direct proxbox-api QEMU/LXC payload builders, cloud-init validation, VMID collision retry, actor/idempotency headers, verbatim backend 403 surfacing, template Actions columns, disabled-button tooltip, wizard steps, CSRF/fetch contract, and unsafe-JS exclusions. No real provisioning is performed.
- `test_overwrite_flags_contract.py`, `test_overwrite_vm_type_contract.py`, `test_sync_params_flag_flattening.py`: contract coverage for the overwrite flag field set, VM type overwrite behavior, and sync query parameter flattening.
- `test_vm_sync_device_flag_enforcement.py`: pins PR #342. Asserts the six `overwrite_device_*` fields are in `OVERWRITE_FIELDS` and that `_build_base_query_params` serializes per-endpoint device-flag values into the SSE query string.
- `test_settings_view_encryption.py`: tests Settings view encryption-key handling and sensitive-field behavior.
- `test_settings_view_hardware_discovery.py`: GET/POST handling of the `hardware_discovery_enabled` flag on Settings — initial population, save path, default-False fallback, and `update_fields` membership.
- `test_node_ssh_credential_model.py`: `normalize_fingerprint` accept/reject behavior, Fernet-backed `set_password` / `get_password` and `set_private_key` / `get_private_key` round-trips, `EncryptionKeyMissing` and `DecryptionFailed` exits, and AST contract on `models/ssh_credential.py` (NetBoxModel base, required fields, `OneToOneField(ProxmoxNode)`, auth-method choices, `clean()` calling `normalize_fingerprint`).
- `test_node_ssh_credential_api.py`: `_NetBoxTokenCanViewNodeSSHCredential.has_permission()` NetBox-token permission checks, `_credential_for_node_identifier()` ProxmoxNode/NetBox-device lookup compatibility, `_metadata_payload()` redaction, AST contract on the by-node viewset (`_ProxboxDashboardPermission` for metadata, NetBox-token permission for secrets, HTTPS-required guard in non-DEBUG, 503 on missing encryption key), and `api/urls.py` route registration for both endpoints.
- `test_node_ssh_credential_ui.py`: source contracts for the SSH credential UI CRUD routes, registered generic views, navigation entry, Settings hardware-discovery flag rendering, write-only secret form fields, and credential-specific table defaults.
- `test_hardware_discovery_custom_fields_migration.py`: migration `0049_register_hardware_discovery_cfs` registers all six custom fields with correct types, content-type bindings (`dcim.device` / `dcim.interface`), `ui_editable="hidden"`, `filter_logic="disabled"`, idempotency, unregister path, and dependency chain.
- `test_backup_replication_views.py`: view coverage for backup routine and replication list/detail pages.
- `test_home_context.py`: tests for home page context assembly.
- `test_stack_setup.py`, `test_stack_sync_polling.py`: integration-level stack setup and sync polling behavior tests.
- `test_templatetags.py`: tests for custom Proxbox template tag helpers.
- `e2e/`: stack-oriented tests that exercise the proxbox-api and NetBox integration flow end to end.
- `management/`: tests for Django management commands. `conftest.py` installs `django.core.management.base` and `django.contrib.auth` stubs at conftest import time so command modules can be imported without bootstrapping Django. `test_proxbox_sync.py` covers the `proxbox_sync` command — enqueue happy path, `--user` override, missing-user / missing-FastAPI / unreachable-backend errors, and `--wait` polling (terminal success and terminal failure).
- `netbox_test_configuration.py`: NetBox settings stub used during tests.

## Dependencies

- Inbound: CI pipeline and local `pytest` invocations.
- Outbound: the plugin views, JS, templates, and utility modules under `netbox_proxbox/`.

## Notes

- Tests rely heavily on compatibility stubs in `conftest.py` rather than a live NetBox database.
- When changing view, job-enqueue, or template contracts, update both the runtime code and those stubs.
- `test_frontend_contracts.py` guards against accidental regressions in public-facing attribute names and JS function signatures.
- **Wire-contract tests:** `test_sse_schema_mirror.py` validates local REST/SSE schema mirrors against `contracts/proxbox_api_sse_schema.json`. It must not import or install `proxbox-api`; the plugin and backend communicate over HTTP, not direct Python calls.
- **AST-based source contracts** (e.g. `test_version.py`, `test_signals.py`, `test_services_backend_context.py`, `test_proxmox_endpoint_settings_view.py`, `test_views_vm_config.py`, `test_views_storage.py`) parse the relevant module with `ast` and never bootstrap Django. Use this pattern when the runtime cost of starting NetBox would dominate the test value.
- **Coverage:** `pyproject.toml` defines `[tool.coverage.run]` with `source = ["netbox_proxbox"]` and `branch = true`, plus `[tool.coverage.report]` with `exclude_lines` for `TYPE_CHECKING` and `pragma: no cover` markers. CI invokes `pytest --cov=netbox_proxbox`.

## Links

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
