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
    assert "netbox_proxbox/js/home.js" in contents
    assert "htmx.org" not in contents
    assert 'id="sync-progress-container"' in contents
    assert 'id="sync-progress-label"' in contents
    assert 'id="sync-progress-state"' in contents
    assert "progress-bar progress-bar-striped progress-bar-animated" in contents
    assert 'method="post"' in contents
    assert "{% csrf_token %}" in contents
    assert 'type="submit"' in contents
    assert "data-sync-url" in contents
    assert "data-sync-kind" in contents


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
    assert "setBadgeState(element, payload.status, payload.detail" in contents
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


def test_vm_sync_now_view_contract():
    contents = _read("netbox_proxbox/views/vm_sync_now.py")
    assert (
        'register_model_view(VirtualMachine, "proxbox_sync_now", path="proxbox-sync-now")'
        in contents
    )
    assert "sync_types=[SyncTypeChoices.VIRTUAL_MACHINES]" in contents
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


def test_endpoint_tables_use_record_pk_for_keepalive_reverse():
    contents = _read("netbox_proxbox/tables/__init__.py")
    assert "keepalive_status" in contents
    assert "record.pk" in contents


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
    assert "inc/field.html" not in template
    assert "class SettingsView(" in view


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
    assert 'name="netbox_token"' in contents


def test_lxc_and_storage_pages_are_wired_in_urls_navigation_and_templates():
    urls = _read("netbox_proxbox/urls.py")
    navigation = _read("netbox_proxbox/navigation.py")
    lxc_template = _read("netbox_proxbox/templates/netbox_proxbox/lxc_containers.html")
    storage_template = _read(
        "netbox_proxbox/templates/netbox_proxbox/storage_list.html"
    )
    views_module = _read("netbox_proxbox/views/__init__.py")
    sync_view = _read("netbox_proxbox/views/sync.py")

    assert 'name="lxc_containers"' in urls
    assert 'path("sync/storage/", views.sync_storage, name="sync_storage")' in urls
    assert 'link="plugins:netbox_proxbox:lxc_containers"' in navigation
    assert 'link="plugins:netbox_proxbox:proxmoxstorage_list"' in navigation
    assert "Sync LXC Containers" in lxc_template
    assert "sync_storage" in storage_template
    assert "class LXCContainersView(" in views_module
    assert "class SyncStorageView(" in sync_view
