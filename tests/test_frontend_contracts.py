"""Tests for test_frontend_contracts."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text()


def test_runtime_code_no_longer_depends_on_django_htmx():
    runtime_files = [
        "netbox_proxbox/views/keepalive_status.py",
        "netbox_proxbox/views/cards.py",
        "netbox_proxbox/views/sync.py",
        "netbox_proxbox/websocket_client.py",
        "netbox_proxbox/templates/netbox_proxbox/home.html",
        "netbox_proxbox/templates/netbox_proxbox/home/proxmox_card.html",
        "netbox_proxbox/templates/netbox_proxbox/home/netbox_card.html",
        "netbox_proxbox/templates/netbox_proxbox/home/fastapi_card.html",
        "netbox_proxbox/templates/netbox_proxbox/table/devices.html",
        "netbox_proxbox/templates/netbox_proxbox/table/virtual_machines.html",
    ]

    for path in runtime_files:
        contents = _read(path)
        assert "django_htmx" not in contents
        assert "hx-" not in contents


def test_home_template_uses_plugin_vanilla_js_entrypoint():
    contents = _read("netbox_proxbox/templates/netbox_proxbox/home.html")
    assert "netbox_proxbox/home/quick_schedule_banner.html" in contents
    assert "netbox_proxbox/partials/home_sync_actions_dropdown.html" in contents
    assert "netbox_proxbox/home/job_live_summary.html" in contents
    assert "active_proxbox_job" in contents
    assert "job_log_assets.html" in contents
    # Issue #355: home dashboard hydration is inlined via the
    # `inline_static_script` template tag instead of loaded as a {% static %}
    # ES module, so logos and cluster cards render even when collectstatic
    # was skipped after a plugin install/upgrade.
    assert "inline_static_script 'netbox_proxbox/js/home_inline.js'" in contents
    assert "{% load proxbox_tags %}" in contents
    assert "htmx.org" not in contents
    assert 'id="sync-progress-container"' in contents
    assert 'id="sync-progress-label"' in contents
    assert 'id="sync-progress-state"' in contents
    assert "progress-bar progress-bar-striped progress-bar-animated" in contents
    assert (
        '{% include "netbox_proxbox/partials/home_sync_actions_dropdown.html" %}'
        in contents
    )
    assert "data-sync-url" not in contents
    assert "data-sync-kind" not in contents


def test_home_sync_actions_dropdown_partial_renders_single_control_block():
    contents = _read(
        "netbox_proxbox/templates/netbox_proxbox/partials/home_sync_actions_dropdown.html"
    )

    assert "dropdown-toggle" in contents
    assert "dropdown-menu" in contents
    assert "Sync Actions" in contents
    assert contents.count("Sync Actions") == 1
    assert "data-sync-url" in contents
    assert "data-sync-kind" in contents
    assert "sync-full-update-button" in contents


def test_home_template_exposes_prefilled_endpoint_quick_add_buttons():
    contents = _read("netbox_proxbox/templates/netbox_proxbox/home.html")

    assert "netbox_quick_add_url" in contents
    assert "fastapi_quick_add_url" in contents
    assert "Quick add NetBox Endpoint" in contents
    assert "Quick add FastAPI Endpoint" in contents
    assert "Open blank form" in contents
    assert "localhost" in contents
    assert "127.0.0.1/32" in contents
    assert "token mode" in contents


def test_home_template_renders_companion_plugin_endpoint_groups():
    contents = _read("netbox_proxbox/templates/netbox_proxbox/home.html")
    partial = _read(
        "netbox_proxbox/templates/netbox_proxbox/home/companion_endpoint_card.html"
    )

    assert "companion_endpoint_groups" in contents
    assert "Additional Proxbox Plugin Endpoints" in contents
    assert "companion_endpoint_card.html" in contents
    assert "endpoint_group.plugin_name" in partial
    assert "companion_endpoint.fields" in partial
    assert "endpoint_group.plugin_package" in partial


def test_home_quick_schedule_banner_posts_to_quick_schedule_url():
    contents = _read(
        "netbox_proxbox/templates/netbox_proxbox/home/quick_schedule_banner.html"
    )
    assert "plugins:netbox_proxbox:schedule_sync_quick" in contents
    assert "netbox_proxbox/inc/schedule_sync_form_fields_quick.html" in contents
    assert "proxboxQuickScheduleBody" in contents
    assert 'class="collapse' in contents
    assert 'data-bs-toggle="collapse"' in contents


def test_home_loads_quick_schedule_css_with_form_media():
    contents = _read("netbox_proxbox/templates/netbox_proxbox/home.html")
    assert "quick_schedule_home.css" in contents


def test_vm_and_backup_templates_do_not_reference_removed_stream_routes():
    vm_template = _read("netbox_proxbox/templates/netbox_proxbox/virtual_machines.html")
    backup_template = _read(
        "netbox_proxbox/templates/netbox_proxbox/vmbackup_list.html"
    )

    assert "sync_virtual_machines_stream" not in vm_template
    assert "sync_vm_backups_stream" not in backup_template
    assert "plugins:netbox_proxbox:sync_virtual_machines" in vm_template
    assert "plugins:netbox_proxbox:sync_vm_backups" in backup_template


def test_netbox_endpoint_edit_template_supports_v1_and_v2_tokens():
    contents = _read("netbox_proxbox/templates/netbox_proxbox/netboxendpoint_edit.html")
    assert "id_token_version" in contents
    assert "id_token" in contents
    assert "netbox-v1-token-field" in contents
    assert "netbox-v2-token-fields" in contents
    assert 'tokenVersionField.value === "v2"' in contents
    assert 'tokenField.value !== ""' in contents


def test_netbox_endpoint_home_card_uses_configured_token_state():
    contents = _read("netbox_proxbox/templates/netbox_proxbox/home/netbox_card.html")
    assert "object.token_version_label" in contents
    assert "object.has_configured_token" in contents


def test_home_javascript_passes_error_detail_to_badge_state():
    """Sync buttons POST via native forms; home.js handles status badges and Proxmox cards."""
    contents = _read("netbox_proxbox/static/netbox_proxbox/js/home.js")
    assert "setBadgeState(element, payload.status, statusDetail(payload))" in contents
    assert "payload.warnings" in contents
    assert "renderServiceStatusMessage" in contents
    assert "-connection-error-" in contents
    assert 'setBadgeState(element, "error", error.message' in contents
    assert "proxmox-connection-error-" in contents
    assert "payload.detail && badge" in contents
    assert 'document.addEventListener("DOMContentLoaded"' in contents
    assert "refreshStatusBadges" in contents
    assert "hydrateProxmoxCards" in contents
    assert "fetchJson" in contents
    assert "initializeWebSocket" in contents


def test_vm_detail_sync_now_button_contract():
    extension_contents = _read("netbox_proxbox/template_content.py")
    button_contents = _read(
        "netbox_proxbox/templates/netbox_proxbox/inc/vm_sync_now_button.html"
    )

    assert "virtualization.virtualmachine" in extension_contents
    assert "vm_sync_now_button.html" in extension_contents
    assert "proxbox-sync-now/" in extension_contents
    assert 'method="post"' in button_contents
    assert "{% csrf_token %}" in button_contents
    assert "Sync Now" in button_contents


def test_firewall_push_and_preview_ui_contracts():
    extension_contents = _read("netbox_proxbox/template_content.py")
    view_contents = _read("netbox_proxbox/views/firewall.py")
    api_view_contents = _read("netbox_proxbox/api/views.py")
    push_button = _read(
        "netbox_proxbox/templates/netbox_proxbox/inc/firewall_push_button.html"
    )
    push_assets = _read(
        "netbox_proxbox/templates/netbox_proxbox/inc/firewall_push_assets.html"
    )
    preview_panel = _read(
        "netbox_proxbox/templates/netbox_proxbox/inc/firewall_preview_panel.html"
    )
    bulk_button = _read(
        "netbox_proxbox/templates/netbox_proxbox/buttons/firewall_bulk_push.html"
    )
    runtime_js = _read("netbox_proxbox/static/netbox_proxbox/js/firewall_push.js")
    filtersets = _read("netbox_proxbox/filtersets.py")
    qemu_wrappers = _read("netbox_proxbox/intent/firewall_vm_qemu.py")
    lxc_wrappers = _read("netbox_proxbox/intent/firewall_vm_lxc.py")
    vnet_wrappers = _read("netbox_proxbox/intent/firewall_vnet.py")
    api_preview_source = api_view_contents[
        api_view_contents.index("    def preview(") : api_view_contents.index(
            "def _actor_from_request",
        )
    ]
    right_page_source = extension_contents[
        extension_contents.index("    def right_page(") : extension_contents.index(
            "def _firewall_api_action_url",
        )
    ]

    assert "ProxmoxFirewallPushTemplateExtension" in extension_contents
    assert "right_page" in extension_contents
    assert "firewall_push_assets.html" in extension_contents
    assert "api_push_url" in extension_contents
    assert "api_preview_url" in extension_contents
    assert "user.has_perm(permission_run_proxmox_action())" in right_page_source
    assert "FirewallBulkPushAction" in view_contents
    assert 'name = "bulk_push"' in view_contents
    assert 'path="push-selected"' in view_contents
    assert 'restrict(request.user, "change")' in view_contents
    assert "preview_firewall_object" in api_view_contents
    assert 'url_path="preview"' in api_view_contents
    assert 'url_path="push"' in api_view_contents
    assert (
        "request.user.has_perm(permission_run_proxmox_action())" in api_preview_source
    )
    assert "data-firewall-push-form" in push_button
    assert "data-firewall-api-url" in push_button
    assert "firewall_push.js" not in push_button
    assert "firewall_push.js" in push_assets
    assert "data-firewall-preview-panel" in preview_panel
    assert "data-firewall-preview-url" in preview_panel
    assert "firewall_push.js" not in preview_panel
    assert '"status",' in filtersets
    assert "validate_vm_firewall_scope(" in qemu_wrappers
    assert "validate_vm_firewall_scope(" in lxc_wrappers
    assert "validate_vnet_firewall_scope(" in vnet_wrappers
    assert "del endpoint, vmid, node" not in qemu_wrappers
    assert "del endpoint, vmid, node" not in lxc_wrappers
    assert "del endpoint, vnet" not in vnet_wrappers
    assert "table-warning" in runtime_js
    assert "X-CSRFToken" in runtime_js
    assert "fetch(apiUrl" in runtime_js
    assert "{% formaction %}" in bulk_button


def test_job_live_poll_alert_spans_the_card_width_and_keeps_streaming_messages():
    contents = _read(
        "netbox_proxbox/templates/netbox_proxbox/inc/job_live_poll_alert.html"
    )

    assert "card border-info shadow-sm nb-job-live-card" in contents
    assert "Queued" in contents
    assert "data-proxbox-job-live-state-pill" in contents
    assert 'class="card-body d-flex flex-column gap-2"' in contents
    assert 'class="nb-job-progress-wrap w-100"' in contents
    assert 'class="progress nb-job-progress-track w-100"' in contents
    assert 'style="width: 100%; transition: width 0.3s ease;"' in contents
    assert "min-width: 2rem" not in contents
    assert 'role="log"' in contents
    assert 'aria-live="polite"' in contents
    assert "data-proxbox-job-live-root" in contents
    assert "data-proxbox-job-live-status" in contents
    assert "data-proxbox-job-live-progress-bar" in contents
    assert "data-proxbox-job-live-log" in contents
    assert "EventSource(streamUrl)" not in contents
    assert 'addEventListener("message"' not in contents
    assert 'handleSSEFrame("message", data)' not in contents
    assert 'if (status === "completed")' not in contents
    assert 'status === "errored"' not in contents
    assert "sessionStorage" not in contents
    assert "bg-warning" in contents


def test_job_live_assets_loads_shared_panel_script():
    contents = _read("netbox_proxbox/templates/netbox_proxbox/inc/job_log_assets.html")
    assert "job_log_view.css" in contents
    assert "job_log_view.js" in contents
    assert "job_live_panel.js" in contents


def test_job_live_panel_script_is_the_shared_runtime_controller():
    contents = _read("netbox_proxbox/static/netbox_proxbox/js/job_live_panel.js")

    assert "NbProxboxJobLivePanel" in contents
    assert "localStorage" in contents
    assert "storage" in contents
    assert "summaryRoot.open = true" in contents
    assert "summaryRoot.open = false" in contents
    assert "isQueuedLikeStatus" in contents
    assert "isRunningLikeStatus" in contents
    assert "applyStatusPresentation" in contents
    assert "collapseSummaryIfNeeded" in contents
    assert "EventSource(streamUrl)" in contents
    assert "data-proxbox-job-live-summary-status" in contents
    assert "data-proxbox-job-live-root" in contents
    assert "data-proxbox-job-live-state-pill" in contents
    assert 'addEventListener("discovery"' in contents
    assert 'addEventListener("substep"' in contents
    assert 'addEventListener("item_progress"' in contents
    assert 'addEventListener("phase_summary"' in contents
    assert 'addEventListener("error_detail"' in contents
    assert "handleDiscoveryFrame" in contents
    assert "handleSubstepFrame" in contents
    assert "handleItemProgressFrame" in contents
    assert "handlePhaseSummaryFrame" in contents
    assert "handleErrorDetailFrame" in contents
    assert "isGenericProgressMessage" in contents
    assert "describeStepProgress" in contents
    assert "isStepProgressPayload" in contents
    assert 'msg === "sync progress"' in contents


def test_job_live_panel_styles_make_queued_state_visually_distinct():
    contents = _read("netbox_proxbox/static/netbox_proxbox/css/job_log_view.css")

    assert "nb-job-live-card-queued" in contents
    assert "bs-warning-rgb" in contents
    assert "nb-job-phase-board" in contents
    assert "nb-job-phase-item" in contents
    assert "nb-job-error-board" in contents


def test_home_job_live_summary_wraps_the_shared_live_panel_in_a_details_element():
    contents = _read(
        "netbox_proxbox/templates/netbox_proxbox/home/job_live_summary.html"
    )

    assert "<details" in contents
    assert "nb-proxbox-job-live-summary" in contents
    assert "data-proxbox-job-live-summary-status" in contents
    assert "data-proxbox-job-live-summary-detail" in contents
    assert "Live job updates" not in contents
    assert "job_live_poll_alert.html" in contents


def test_job_log_view_uses_netbox_status_colors():
    contents = _read("netbox_proxbox/static/netbox_proxbox/js/job_log_view.js")
    assert "text-bg-success text-uppercase" in contents
    assert "text-bg-blue text-uppercase" in contents
    assert "text-bg-warning text-uppercase" in contents
    assert "text-bg-danger text-uppercase" in contents
    assert "bg-warning" in contents
    assert "bg-danger" in contents
    assert "network-interfaces" in contents
    assert "ip-addresses" in contents


def test_backend_logs_page_javascript_supports_errors_tab_and_copy_button():
    contents = _read("netbox_proxbox/static/netbox_proxbox/js/logs.js")

    assert 'params.append("errors_only", "true");' in contents
    assert 'params.append("newer_than_id", this.newestLoadedId);' in contents
    assert 'params.append("older_than_id", this.oldestLoadedId);' in contents
    assert 'params.append("level", this.currentLevel);' in contents
    assert 'this.currentTab === "errors"' in contents
    assert "copyLogsToClipboard()" in contents
    assert "navigator.clipboard.writeText(text)" in contents
    assert "this.displayedLogs" in contents
    assert "cachedLogs" not in contents
    assert "scheduleOperationFetch()" in contents
    assert "Client: level=" in contents
    assert "Backend: operation=" in contents
    assert "updateLevelFilterState()" in contents
    assert "setTab(tabKey, options = {})" in contents
    assert "saveBackendLogFilePath()" in contents
    assert "backendLogFilePathInput" in contents
    assert "saveLogPathUrl" in contents
    assert "getLogLevelPriority" not in contents


def test_backend_logs_template_exposes_tabs_and_copy_button():
    contents = _read("netbox_proxbox/templates/netbox_proxbox/logs.html")

    assert 'id="logsTabs"' in contents
    assert 'data-log-tab="errors"' in contents
    assert 'id="copyLogsBtn"' in contents
    assert 'id="backendLogFilePathInput"' in contents
    assert 'id="saveBackendLogFilePathBtn"' in contents
    assert "Copy to clipboard" in contents
    assert "Errors" in contents


def test_combined_interface_views_import_vm_interface_directly():
    contents = _read("netbox_proxbox/views/__init__.py")
    assert (
        "from virtualization.models import VMInterface, VirtualMachine" in contents
        or "from virtualization.models import VirtualMachine, VMInterface" in contents
    )
    assert "from virtualization.models import Interface as VMInterface" not in contents


def test_ip_address_view_prefetches_generic_assigned_objects():
    contents = _read("netbox_proxbox/views/__init__.py")
    assert 'prefetch_related("assigned_object")' in contents
    assert 'select_related("assigned_object")' not in contents


def test_vm_sync_now_view_contract():
    contents = _read("netbox_proxbox/views/vm_sync_now.py")
    assert (
        'register_model_view(VirtualMachine, "proxbox_sync_now", path="proxbox-sync-now")'
        in contents
    )
    assert "SyncTypeChoices.VIRTUAL_MACHINES" in contents
    assert "SyncTypeChoices.VIRTUAL_MACHINES_BACKUPS" in contents
    assert "SyncTypeChoices.VIRTUAL_MACHINES_SNAPSHOTS" in contents
    assert "netbox_vm_ids=[str(vm.pk)]" in contents


def test_common_badge_state_supports_hover_tooltip_details():
    contents = _read("netbox_proxbox/static/netbox_proxbox/js/common.js")
    assert 'element.dataset.bsToggle = "tooltip"' in contents
    assert "element.dataset.bsTitle = tooltip" in contents
    assert "export function getCsrfToken()" in contents
    assert "querySelector(\"input[name='csrfmiddlewaretoken']\")" in contents


def test_websocket_and_polling_modules_expose_sync_completion_hooks():
    websocket_contents = _read("netbox_proxbox/static/netbox_proxbox/js/websocket.js")
    polling_contents = _read("netbox_proxbox/static/netbox_proxbox/js/polling.js")

    assert "onSyncEnd(listener)" in websocket_contents
    assert "notifySyncEnd(syncObject)" in websocket_contents
    assert 'this.send("Full Update Sync")' in websocket_contents
    assert "callbacks = {}" in polling_contents
    assert "onComplete" in polling_contents
    assert "onError" in polling_contents


def _ensure_endpoint_template_has_status(template_path: str, service_slug: str) -> None:
    contents = _read(template_path)
    assert "data-service-status-url" in contents
    assert "endpoint-status.js" in contents
    assert service_slug in contents


def test_endpoint_templates_expose_live_badges():
    _ensure_endpoint_template_has_status(
        "netbox_proxbox/templates/netbox_proxbox/proxmoxendpoint.html",
        "proxmox",
    )
    _ensure_endpoint_template_has_status(
        "netbox_proxbox/templates/netbox_proxbox/netboxendpoint.html",
        "netbox",
    )
    _ensure_endpoint_template_has_status(
        "netbox_proxbox/templates/netbox_proxbox/fastapiendpoint.html",
        "fastapi",
    )


def test_proxmox_endpoint_list_template_loads_static_for_status_script():
    contents = _read(
        "netbox_proxbox/templates/netbox_proxbox/proxmoxendpoint_list.html"
    )
    assert "{% load static %}" in contents
    assert "endpoint-status.js" in contents
    # export-secrets-modal JS must be inlined (not an external file reference) so it
    # is served without requiring collectstatic.
    assert "export-secrets-modal.js" not in contents
    assert "TOKEN_API_URL" in contents
    assert "loadV1Tokens" in contents


def test_fastapi_openapi_tab_view_and_template_contract():
    view_contents = _read("netbox_proxbox/views/endpoints/fastapi.py")
    template_contents = _read(
        "netbox_proxbox/templates/netbox_proxbox/fastapiendpoint_openapi.html"
    )

    assert (
        'register_model_view(FastAPIEndpoint, "openapi", path="openapi")'
        in view_contents
    )
    assert 'label="OpenAPI"' in view_contents
    assert "get_cached_openapi_schema" in view_contents
    assert 'request.GET.get("refresh", "")' in view_contents

    assert "OpenAPI Schema" in template_contents
    assert "Endpoints" in template_contents
    assert "openapi_data.schema.operations" in template_contents
    assert "?refresh=1" in template_contents
    assert "Forced Refresh" in template_contents
    assert "Last Refreshed" in template_contents


def test_endpoint_tables_use_record_pk_for_keepalive_reverse():
    contents = _read("netbox_proxbox/tables/__init__.py")
    assert "keepalive_status" in contents
    assert "record.pk" in contents


def test_community_surface_excludes_discord_and_telegram_links():
    paths = [
        "README.md",
        "netbox_proxbox/navigation.py",
        "netbox_proxbox/urls.py",
        "netbox_proxbox/views/__init__.py",
        "netbox_proxbox/views/external_pages.py",
        "netbox_proxbox/templates/netbox_proxbox/community.html",
        "netbox_proxbox/static/netbox_proxbox/CLAUDE.md",
    ]
    forbidden = (
        "discord",
        "telegram",
        "discord.gg",
        "discord.com",
        "t.me/netboxbr",
        "netboxbr",
        "9N3V4mp",
        "X6Fudv",
    )

    for path in paths:
        contents = _read(path).lower()
        for token in forbidden:
            assert token.lower() not in contents


def test_settings_page_is_wired_in_urls_navigation_and_template():
    urls = _read("netbox_proxbox/urls.py")
    navigation = _read("netbox_proxbox/navigation.py")
    template = _read("netbox_proxbox/templates/netbox_proxbox/settings.html")
    view = _read("netbox_proxbox/views/settings.py")

    assert 'path("settings/", views.SettingsView.as_view(), name="settings")' in urls
    assert 'link="plugins:netbox_proxbox:settings"' in navigation
    assert "Plugin Settings" in template
    assert "use_guest_agent_interface_name" in template
    assert "proxbox_fetch_max_concurrency" in template
    assert "ignore_ipv6_link_local_addresses" in template
    assert "primary_ip_preference" in template
    assert "backend_log_file_path" in template
    assert "encryption_enabled" in template
    assert "encryption_key" in template
    assert "inc/field.html" not in template
    assert "class SettingsView(" in view
    assert "encryption_key" in view
    assert "encryption_enabled" in view


def test_proxmox_list_template_exposes_import_export_controls_and_warning_modal():
    contents = _read(
        "netbox_proxbox/templates/netbox_proxbox/proxmoxendpoint_list.html"
    )
    assert "proxmoxendpoint_bulk_import" in contents
    assert "proxmoxendpoint_export" in contents
    assert "Export JSON" in contents
    assert "Export YAML" in contents
    assert "Export with secrets" in contents
    assert 'name="format"' in contents
    assert (
        "This export includes Proxmox passwords and token values in plain text"
        in contents
    )
    # Token version selector fields.
    assert 'name="token_version"' in contents
    assert 'name="token_id"' in contents
    assert 'name="token_key"' in contents
    assert 'name="token_secret"' in contents
    # v1 sub-mode: select vs manual.
    assert 'name="v1_mode"' in contents
    assert 'name="v1_manual_token"' in contents
    # Quick add button.
    assert "Quick add token" in contents
    # Security warning for quick-add.
    assert "Delete it or store it securely after this export" in contents


def _assert_singleton_list_template_export_controls(
    template_path: str, url_prefix: str, warning_text: str
) -> None:
    """Shared checks for singleton endpoint list templates with full export UI."""
    contents = _read(template_path)
    assert f"{url_prefix}_bulk_import" in contents
    assert f"{url_prefix}_export" in contents
    assert "Export JSON" in contents
    assert "Export YAML" in contents
    assert "Export with secrets" in contents
    assert 'name="format"' in contents
    assert warning_text in contents
    # Token version selector fields.
    assert 'name="token_version"' in contents
    assert 'name="token_id"' in contents
    assert 'name="token_key"' in contents
    assert 'name="token_secret"' in contents
    # v1 sub-mode: select vs manual.
    assert 'name="v1_mode"' in contents
    assert 'name="v1_manual_token"' in contents
    # Quick add button.
    assert "Quick add token" in contents
    assert f"{url_prefix}_quick_add_token" in contents
    # Security warning for quick-add.
    assert "Delete it or store it securely after this export" in contents
    # JS must be inlined (not external).
    assert "TOKEN_API_URL" in contents
    assert "loadV1Tokens" in contents


def test_netbox_endpoint_list_template_exposes_import_export_controls():
    _assert_singleton_list_template_export_controls(
        "netbox_proxbox/templates/netbox_proxbox/netboxendpoint_list.html",
        url_prefix="netboxendpoint",
        warning_text="includes NetBox token credentials in plain text",
    )


def test_fastapi_endpoint_list_template_exposes_import_export_controls():
    _assert_singleton_list_template_export_controls(
        "netbox_proxbox/templates/netbox_proxbox/fastapiendpoint_list.html",
        url_prefix="fastapiendpoint",
        warning_text="includes FastAPI backend tokens in plain text",
    )


def test_singleton_import_confirm_template_exists():
    contents = _read(
        "netbox_proxbox/templates/netbox_proxbox/singleton_import_confirm.html"
    )
    assert "confirm_override" in contents
    assert "Override existing" in contents
    assert "Cancel" in contents
    assert "return_url" in contents
    assert "post_items" in contents


def test_lxc_and_storage_pages_are_wired_in_urls_navigation_and_templates():
    urls = _read("netbox_proxbox/urls.py")
    navigation = _read("netbox_proxbox/navigation.py")
    lxc_template = _read("netbox_proxbox/templates/netbox_proxbox/lxc_containers.html")
    storage_template = _read(
        "netbox_proxbox/templates/netbox_proxbox/storage_list.html"
    )
    storage_detail_template = _read(
        "netbox_proxbox/templates/netbox_proxbox/proxmoxstorage.html"
    )
    views_module = _read("netbox_proxbox/views/__init__.py")
    sync_view = _read("netbox_proxbox/views/sync.py")

    assert 'name="lxc_containers"' in urls
    assert 'path("sync/storage/", views.sync_storage, name="sync_storage")' in urls
    assert 'link="plugins:netbox_proxbox:lxc_containers"' in navigation
    assert 'link="plugins:netbox_proxbox:proxmoxstorage_list"' in navigation
    assert "Sync LXC Containers" in lxc_template
    assert "sync_storage" in storage_template
    assert "Storage Summary" in storage_detail_template
    assert "class LXCContainersView(" in views_module
    assert "class SyncStorageView(" in sync_view


def test_vm_resource_pages_gate_native_vm_type_field_for_netbox_45():
    utils = _read("netbox_proxbox/utils.py")
    views = _read("netbox_proxbox/views/resource_list_views.py")

    assert "def has_virtual_machine_type_field(" in utils
    assert "def filter_queryset_by_proxmox_vm_type(" in utils
    assert "def vm_type_select_related_fields(" in utils
    assert "filter_queryset_by_proxmox_vm_type(" in views
    assert "vm_type_select_related_fields(VirtualMachine)" in views
    assert 'Q(virtual_machine_type__slug="qemu-virtual-machine")' not in views
    assert 'Q(virtual_machine_type__slug="lxc-container")' not in views
    assert '"virtual_machine_type",' not in views


def test_replication_page_is_wired_in_urls_navigation_and_vm_tabs():
    urls = _read("netbox_proxbox/urls.py")
    navigation = _read("netbox_proxbox/navigation.py")
    views_module = _read("netbox_proxbox/views/__init__.py")
    replication_views = _read("netbox_proxbox/views/replication.py")
    replication_template = _read(
        "netbox_proxbox/templates/netbox_proxbox/replication_list.html"
    )

    assert "replications/<int:pk>/" in urls
    assert 'replications/",' in urls
    assert 'get_model_urls("netbox_proxbox", "replication")' in urls
    assert 'get_model_urls("netbox_proxbox", "replication", detail=False)' in urls
    assert 'link="plugins:netbox_proxbox:replication_list"' in navigation
    assert "ReplicationTabView" in views_module
    assert (
        'register_model_view(VirtualMachine, "replications", path="replications")'
        in replication_views
    )
    assert 'label="Replications"' in replication_views
    assert "Sync Replications" in replication_template


def test_interface_and_ip_pages_are_wired_in_urls_navigation_and_templates():
    urls = _read("netbox_proxbox/urls.py")
    navigation = _read("netbox_proxbox/navigation.py")
    views_module = _read("netbox_proxbox/views/__init__.py")
    interfaces_page = _read("netbox_proxbox/templates/netbox_proxbox/interfaces.html")
    ip_addresses_page = _read(
        "netbox_proxbox/templates/netbox_proxbox/ip_addresses.html"
    )
    interfaces_template = _read(
        "netbox_proxbox/templates/netbox_proxbox/table/interfaces.html"
    )
    ip_addresses_template = _read(
        "netbox_proxbox/templates/netbox_proxbox/table/ip_addresses.html"
    )
    sync_view = _read("netbox_proxbox/views/sync.py")

    assert (
        'path("interfaces/", views.InterfacesView.as_view(), name="interfaces")' in urls
    )
    assert (
        'path("ip-addresses/", views.IPAddressesView.as_view(), name="ip_addresses")'
        in urls
    )
    assert "sync/network-interfaces/" in urls
    assert "sync/ip-addresses/" in urls
    assert 'link="plugins:netbox_proxbox:interfaces"' in navigation
    assert 'link="plugins:netbox_proxbox:ip_addresses"' in navigation
    assert "class InterfacesView(" in views_module
    assert "class IPAddressesView(" in views_module
    assert 'values_list("object_id", flat=True)[:500]' not in views_module
    assert "virtualization:vminterface" in interfaces_template
    assert "dcim:interface" in interfaces_template
    assert "if node_interface_ids:" not in views_module
    assert "class SyncNetworkInterfacesView(" in sync_view
    assert "class SyncIPAddressesView(" in sync_view
    assert "Sync Interfaces" in interfaces_page
    assert "Sync IP Addresses" in ip_addresses_page
    assert "Total IPs" in ip_addresses_template


def test_proxmox_storage_detail_template_exists():
    detail_template = _read(
        "netbox_proxbox/templates/netbox_proxbox/proxmoxstorage.html"
    )
    assert "Proxmox Storage" in detail_template
    assert "Storage Usage (Live)" in detail_template
    assert "inc/panels/tags.html" in detail_template
    assert "inc/panels/custom_fields.html" in detail_template
