"""Contract tests for the human-only soft-deleted VM purge surface."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_purge_view_has_marker_and_status_filters_for_both_bulk_paths() -> None:
    source = _read("netbox_proxbox/views/soft_deleted_vms.py")

    assert "tags__slug=SOFT_DELETE_TAG_SLUG" in source
    assert "status=SOFT_DELETE_VM_STATUS" in source
    assert "filterset = SoftDeletedVirtualMachineFilterSet" in source
    assert 'get_permission_for_model(VirtualMachine, "delete")' in source


def test_purge_page_is_explicitly_netbox_only_and_human_confirmed() -> None:
    template = _read(
        "netbox_proxbox/templates/netbox_proxbox/soft_deleted_virtual_machines.html"
    )
    urls = _read("netbox_proxbox/urls.py")

    assert "Human confirmation required." in template
    assert "soft_deleted_vms_bulk_delete" in template
    assert 'name="_all"' in template
    assert 'name="soft_deleted_vms"' in urls
    assert 'name="soft_deleted_vms_bulk_delete"' in urls
    assert "requests" not in template.lower()


def test_purge_page_is_in_proxbox_virtualization_navigation() -> None:
    navigation = _read("netbox_proxbox/navigation.py")

    assert 'link="plugins:netbox_proxbox:soft_deleted_vms"' in navigation
    assert "soft_deleted_vms_item" in navigation
