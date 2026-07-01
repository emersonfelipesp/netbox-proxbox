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


def test_home_template_comment_is_not_multiline_inline_syntax():
    """Django's {# #} syntax only suppresses single-line comments; multi-line
    {# ... #} blocks are not recognised as comments and the raw text is emitted
    into the rendered HTML, which browsers can display visibly.  This test
    ensures the issue-#355 explanation comment uses the correct block-comment
    tag so it never leaks to the page.

    See https://github.com/emersonfelipesp/netbox-proxbox/issues/541
    """
    contents = _read("netbox_proxbox/templates/netbox_proxbox/home.html")
    # The comment text must NOT appear as a bare inline {# ... #} comment.
    assert "{# Dashboard hydration is inlined" not in contents
    # It must use the block comment tag that Django supports across multiple lines.
    assert "{% comment %}" in contents
    assert "Dashboard hydration is inlined" in contents
    assert "{% endcomment %}" in contents


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
    assert "companion_endpoint.connection_status" in partial
    assert "connection_status.label" in partial
    assert "data-service-status-url" in partial
    assert "companion_endpoint.fields" in partial
    assert "endpoint_group.plugin_package" in partial


def test_home_template_renders_latest_sync_jobs_table_and_view_all_button():
    contents = _read("netbox_proxbox/templates/netbox_proxbox/home.html")

    # Section heading and the iterated context list.
    assert "Latest Sync Jobs" in contents
    assert "latest_sync_jobs" in contents
    assert "{% for job in latest_sync_jobs %}" in contents
    # Per-job columns link to the job and show its status badge.
    assert "job.get_absolute_url" in contents
    assert "job.get_status_color" in contents
    # View-all button targets the Proxbox-filtered core job list.
    assert "sync_jobs_list_url" in contents
    assert "View all sync jobs" in contents
    # Empty state for fresh installs with no sync history.
    assert "No sync jobs have run yet." in contents


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


def test_proxmox_endpoint_detail_sync_now_button_contract():
    template_contents = _read(
        "netbox_proxbox/templates/netbox_proxbox/proxmoxendpoint.html"
    )
    view_contents = _read("netbox_proxbox/views/endpoints/proxmox_sync_now.py")

    assert "{% block extra_controls %}" in template_contents
    assert "proxmoxendpoint_sync_now" in template_contents
    assert 'method="post"' in template_contents
    assert "{% csrf_token %}" in template_contents
    assert "perms.core.add_job" in template_contents
    assert "object.enabled" in template_contents
    assert "Sync Now" in template_contents
    assert (
        '@register_model_view(ProxmoxEndpoint, "sync_now", path="sync-now")'
        in view_contents
    )
    assert 'http_method_names = ["post"]' in view_contents
    assert 'ProxmoxEndpoint.objects.restrict(request.user, "view")' in view_contents


def test_job_runtime_panel_renders_endpoint_runtime_cards():
    contents = _read(
        "netbox_proxbox/templates/netbox_proxbox/inc/job_runtime_panel.html"
    )

    assert "Proxbox sync summary" in contents
    assert "block.response.runtime_summary" in contents
    assert "block.response.endpoint_runtimes" in contents
    assert "endpoint_runtime.phases" in contents
    assert "phase.runtime_seconds" in contents
    assert "block.response.stages" in contents
    assert "Proxbox sync stages" in contents


def test_proxmox_vm_template_navigation_has_registered_views():
    view_contents = _read("netbox_proxbox/views/vm_template.py")
    init_contents = _read("netbox_proxbox/views/__init__.py")
    navigation_contents = _read("netbox_proxbox/navigation.py")
    page_coverage_contents = _read("tests/e2e/page_coverage_check.py")

    assert 'link="plugins:netbox_proxbox:proxmoxvmtemplate_list"' in navigation_contents
    assert (
        '@register_model_view(ProxmoxVMTemplate, "list", path="", detail=False)'
        in view_contents
    )
    assert "@register_model_view(ProxmoxVMTemplate)" in view_contents
    assert '@register_model_view(ProxmoxVMTemplate, "edit")' in view_contents
    assert (
        'default_return_url = "plugins:netbox_proxbox:proxmoxvmtemplate_list"'
        in view_contents
    )
    assert "ProxmoxVMTemplateListView" in init_contents
    assert "/plugins/proxbox/vm-templates/" in page_coverage_contents
    assert "proxmox-vm-template-detail" in page_coverage_contents


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
    inline_contents = _read("netbox_proxbox/static/netbox_proxbox/js/home_inline.js")
    assert 'element.dataset.bsToggle = "tooltip"' in contents
    assert "element.dataset.bsTitle = tooltip" in contents
    assert 'disabled: "badge text-bg-secondary"' in contents
    assert 'disabled: "Disabled"' in contents
    assert 'disabled: "badge text-bg-secondary"' in inline_contents
    assert 'disabled: "Disabled"' in inline_contents
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


def test_settings_page_exposes_reconciliation_engine_controls():
    template = _read("netbox_proxbox/templates/netbox_proxbox/settings.html")
    view = _read("netbox_proxbox/views/settings.py")
    form = _read("netbox_proxbox/forms/settings.py")

    assert "reconciliation_engine" in template
    assert "reconciliation_compare_strict" in template
    assert "reconciliation_engine" in view
    assert "reconciliation_compare_strict" in view
    assert "VM reconciliation engine" in form
    assert "Strict Rust comparison" in form


def test_endpoint_tables_use_record_pk_for_keepalive_reverse():
    contents = _read("netbox_proxbox/tables/__init__.py")
    assert "keepalive_status" in contents
    assert "record.pk" in contents


def test_proxmox_endpoint_table_disables_status_polling_for_disabled_rows():
    contents = _read("netbox_proxbox/tables/__init__.py")
    template_source = contents[
        contents.index("PROXMOX_STATUS_BADGE_TEMPLATE") : contents.index(
            "class ProxmoxEndpointTable"
        )
    ]
    disabled_branch = template_source[
        template_source.index("{% if not record.enabled %}") : template_source.index(
            "{% else %}"
        )
    ]

    assert "text-bg-secondary" in disabled_branch
    assert "Disabled" in disabled_branch
    assert "data-service-status-url" not in disabled_branch
    assert "data-service-status-url" in template_source
    assert "template_code=PROXMOX_STATUS_BADGE_TEMPLATE" in contents


def test_proxmox_endpoint_templates_skip_status_polling_when_disabled():
    detail_contents = _read(
        "netbox_proxbox/templates/netbox_proxbox/proxmoxendpoint.html"
    )
    home_card_contents = _read(
        "netbox_proxbox/templates/netbox_proxbox/home/proxmox_card.html"
    )

    assert "{% if object.enabled %}" in detail_contents
    assert "{% if object.enabled %}" in home_card_contents
    assert "data-service-status-url" in detail_contents
    assert "data-service-status-url" in home_card_contents
    assert 'class="badge text-bg-secondary"' in detail_contents
    assert 'class="badge text-bg-secondary p-1"' in home_card_contents
    assert "if (!url) return;" in detail_contents
    assert "data-proxmox-card-url" in home_card_contents
    assert "This Proxmox endpoint is disabled." in home_card_contents


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
    assert "reconciliation_engine" in template
    assert "encryption_enabled" in template
    assert "encryption_key" in template
    assert "inc/field.html" not in template
    assert "class SettingsView(" in view
    assert "encryption_key" in view
    assert "encryption_enabled" in view
    assert "reconciliation_engine" in view


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


def test_resource_list_views_use_netbox_pagination():
    """All custom list views must paginate via NetBox's EnhancedPaginator.

    Regression guard for the bug where the Virtual Machines page (and other
    Proxbox list pages) capped at 100 rows with no pagination controls.
    """
    contents = _read("netbox_proxbox/views/resource_list_views.py")
    assert (
        "from utilities.paginator import EnhancedPaginator, get_paginate_count"
        in contents
    )
    assert "def paginate_object_list(" in contents
    # The hard 100-row caps that truncated the list pages must be gone.
    assert "[:100]" not in contents
    # Each of the nine list tables feeds its queryset through the shared
    # paginator helper (1 helper definition + 9 call sites = 10 occurrences).
    assert contents.count("paginate_object_list(") >= 10


def test_resource_list_paginator_partial_exists_without_htmx():
    partial = _read("netbox_proxbox/templates/netbox_proxbox/inc/paginator.html")
    assert "proxbox_paginate_url" in partial
    assert "smart_pages" in partial
    assert "Per Page" in partial
    # The plugin paginator must stay plain GET navigation (no htmx coupling).
    assert "hx-" not in partial


def test_resource_list_page_templates_include_paginator():
    single_table_pages = [
        "netbox_proxbox/templates/netbox_proxbox/virtual_machines.html",
        "netbox_proxbox/templates/netbox_proxbox/lxc_containers.html",
        "netbox_proxbox/templates/netbox_proxbox/devices.html",
        "netbox_proxbox/templates/netbox_proxbox/virtual_disks.html",
        "netbox_proxbox/templates/netbox_proxbox/clusters.html",
    ]
    for path in single_table_pages:
        assert "netbox_proxbox/inc/paginator.html" in _read(path), path

    # The two aggregate pages paginate each table independently.
    interfaces_partial = _read(
        "netbox_proxbox/templates/netbox_proxbox/table/interfaces.html"
    )
    assert 'page_param="vm_page"' in interfaces_partial
    assert 'page_param="node_page"' in interfaces_partial

    ip_partial = _read(
        "netbox_proxbox/templates/netbox_proxbox/table/ip_addresses.html"
    )
    assert 'page_param="vm_page"' in ip_partial
    assert 'page_param="node_page"' in ip_partial


def test_cluster_summary_reverses_storages_tab_under_core_namespace():
    """Regression test for the Proxmox cluster summary crash.

    ``ClusterStoragesTabView`` is registered on the *core*
    ``virtualization.Cluster`` model via ``register_model_view``. NetBox builds
    such a view's URL name as ``<app_label>:<model>_<name>`` and only prepends
    ``plugins:`` when the model belongs to a plugin (see
    ``utilities.views.get_viewname``). ``Cluster`` is a core model, so the
    correct reverse target is ``virtualization:cluster_proxbox-storages`` — NOT
    ``plugins:netbox_proxbox:cluster_proxbox-storages``.

    The wrong namespace raised ``django.urls.exceptions.NoReverseMatch`` and
    returned HTTP 500 for ``/virtualization/clusters/<id>/summary/``.

    See https://github.com/emersonfelipesp/netbox-proxbox/issues/565
    """
    view_contents = _read("netbox_proxbox/views/cluster.py")
    template = _read(
        "netbox_proxbox/templates/netbox_proxbox/cluster/cluster_summary.html"
    )

    # The storages tab is attached to the core virtualization.Cluster model.
    assert "from virtualization.models import Cluster" in view_contents
    assert (
        '@register_model_view(Cluster, "proxbox-storages", path="storages")'
        in view_contents
    )

    # Therefore the summary template must reverse it under the core
    # virtualization namespace, never the plugin namespace.
    assert "virtualization:cluster_proxbox-storages" in template
    assert "plugins:netbox_proxbox:cluster_proxbox-storages" not in template


def test_proxmox_endpoint_settings_template_uses_tabs_not_stacked_cards():
    """The ProxmoxEndpoint Settings page groups the per-endpoint override
    sections into selectable Bootstrap tabs (Connection / Sync Modes / Sync
    Overwrite / Tenant Assignment) so operators select a section instead of
    scrolling through stacked cards.

    All four tab panes must stay in the DOM (Bootstrap only toggles display),
    so every form field still submits on save regardless of the active tab.
    """
    template = _read(
        "netbox_proxbox/templates/netbox_proxbox/proxmoxendpoint_settings.html"
    )

    # Bootstrap tab strip is present with the four expected panes.
    assert 'class="nav nav-tabs' in template
    for pane_id in (
        "proxbox-settings-connection",
        "proxbox-settings-sync-modes",
        "proxbox-settings-overwrite",
        "proxbox-settings-tenant",
    ):
        assert f'data-bs-target="#{pane_id}"' in template
        assert f'id="{pane_id}"' in template
    # Count the actual pane containers, not stray "tab-pane" occurrences in the
    # error-focus script's selector string.
    assert template.count('class="tab-pane') == 4

    # Every configuration section's fields must still be rendered so the whole
    # form submits regardless of which tab is active.
    for field in (
        "form.timeout",
        "form.max_retries",
        "form.retry_backoff",
        "form.enable_tenant_name_regex",
        "form.tenant_name_regex_rules",
        "form.enable_tenant_tag_assignment",
        "form.enable_tenant_from_cluster",
    ):
        assert f"render_field {field} " in template
    # The dynamic groups still drive the Sync Modes and Sync Overwrite panes.
    assert "sync_mode_field_groups" in template
    assert "overwrite_field_groups" in template
    # The changelog message stays outside the tab strip so it always submits.
    assert "form.changelog_message" in template


def test_proxmox_endpoint_settings_focuses_first_tab_with_validation_error():
    """When the Settings form redisplays with validation errors, an errored field
    may sit on an inactive tab and be invisible. The template ships an inline
    script that, on load, activates the first tab pane containing a ``.has-errors``
    element (the class NetBox's ``render_field`` adds to an errored field row).

    This is a template/contract assertion: it proves the script is present and
    keys off ``has-errors``; it does not exercise the runtime tab switch (that is
    confirmed once in a browser on staging, matching how this plugin already
    contract-tests its other inlined JS).
    """
    template = _read(
        "netbox_proxbox/templates/netbox_proxbox/proxmoxendpoint_settings.html"
    )

    # The behavior lives in an inline script inside the javascript block so it
    # works without collectstatic (the plugin's established inline-JS convention),
    # and calls the parent block so NetBox's own page scripts still load.
    assert "{% block javascript %}" in template
    assert "{{ block.super }}" in template

    # It keys off NetBox's errored-field marker class and scopes to the tab
    # content container.
    assert "has-errors" in template
    assert "proxbox-settings-tab-content" in template

    # It must switch tabs by clicking the nav button (NetBox does not expose
    # window.Tab) and must run after the DOM/tab data-api is ready.
    assert "DOMContentLoaded" in template
    assert ".click()" in template


def test_proxmox_endpoint_edit_subpages_keep_object_tab_strip():
    """The Settings and SSH edit sub-pages are NetBox ObjectEditViews, so
    `generic/object_edit.html` renders `{% block tabs %}` as a single Edit tab —
    hiding the object's other registered tabs (detail / SSH / Terminal / Sync
    Jobs / …). Both templates override that block to render the full object tab
    strip (primary detail tab + `{% model_view_tabs object %}`) so the operator
    can navigate back to the other tabs from an edit sub-page.
    """
    for tpl in (
        "netbox_proxbox/templates/netbox_proxbox/proxmoxendpoint_settings.html",
        "netbox_proxbox/templates/netbox_proxbox/proxmoxendpoint_ssh_settings.html",
    ):
        contents = _read(tpl)
        # Overrides the object-edit tabs block...
        assert "{% block tabs %}" in contents
        assert "{% endblock tabs %}" in contents
        # ...loads the tag library and renders the registered model-view tabs...
        assert "{% load tabs %}" in contents
        assert "{% model_view_tabs object %}" in contents
        # ...plus the primary detail tab linking to the object.
        assert "object.get_absolute_url" in contents


def test_proxmox_endpoint_edit_subpages_render_shared_object_header():
    """The Settings and SSH edit sub-pages render the SAME object header as the
    detail-style tabs (generic/object.html): breadcrumb + object identifier, the
    object title, created/updated subtitle, and the Bookmark/Subscribe/Edit/
    Delete controls — so switching between any of the object's tabs keeps
    identical header chrome. Only the header blocks are overridden; the edit form
    is left to object_edit.html.
    """
    for tpl in (
        "netbox_proxbox/templates/netbox_proxbox/proxmoxendpoint_settings.html",
        "netbox_proxbox/templates/netbox_proxbox/proxmoxendpoint_ssh_settings.html",
    ):
        contents = _read(tpl)
        # Header blocks overridden to match the detail page.
        assert "{% block page-header %}" in contents
        assert "{% block subtitle %}" in contents
        assert "{% block controls %}" in contents
        # Title is the object itself (matching the detail page), not "Settings for …".
        assert "{% block title %}{{ object }}{% endblock %}" in contents
        assert "Settings for" not in contents
        assert "SSH settings for" not in contents
        # The controls render the same action + bookmark/subscribe buttons.
        assert "{% action_buttons actions object %}" in contents
        assert "bookmark_button object" in contents
        assert "subscribe_button object" in contents
        assert "plugin_buttons object" in contents
        # Required NetBox tag libraries are loaded.
        for lib in ("buttons", "custom_links", "perms", "plugins", "helpers", "tabs"):
            assert "{% load " + lib + " %}" in contents
        # Breadcrumb + object identifier match the detail header.
        assert "action_url object 'list'" in contents
        assert 'object|meta:"app_label"' in contents
