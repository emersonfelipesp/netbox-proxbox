# `tests`

This directory contains the plugin's pytest test suite.

## Files And Ownership

- `conftest.py`: shared fixtures and compatibility stubs for Django/NetBox/requests so tests can run without a full NetBox install. Includes `StreamingHttpResponse` stubs and mock request helpers.
- `test_sync.py`: tests for the sync views in `views/sync.py`. Covers POST polling, SSE stream proxy responses, stream error frames, missing FastAPI context, and generator crash handling.
- `test_frontend_contracts.py`: ensures key strings, DOM hooks, and JS functions exist across templates, JS, and views. Validates SSE stream support (`data-sync-stream-url`, `streamSyncEvents`, `formatStreamMessage`, `await response.text()`).
- `test_cards.py`, `test_keepalive_status.py`, `test_utils.py`: targeted tests for cards, keepalive status checks, and URL/host utilities.
- `test_api_netbox_integration.py`, `test_api_source_contracts.py`: API layer and serializer contract checks.
- `test_form_and_helper_source_contracts.py`: form and helper source-level checks.
- `test_proxmox_export_view.py`: Proxmox export view contract checks.
- `netbox_test_configuration.py`: NetBox settings stub used during tests.

## Dependencies

- Inbound: CI pipeline and local `pytest` invocations.
- Outbound: the plugin views, JS, templates, and utility modules under `netbox_proxbox/`.

## Notes

- Tests rely heavily on compatibility stubs in `conftest.py` rather than a live NetBox database. When changing response contracts (especially streaming responses), update both the view code and `conftest.py` stubs.
- `test_frontend_contracts.py` guards against accidental regressions in public-facing attribute names and JS function signatures.

## Links

- Parent: [`../CLAUDE.md`](../CLAUDE.md)
