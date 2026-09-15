"""Source contracts for the data-protection calendar UI."""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "netbox_proxbox"
LIST_TEMPLATES = (
    "vmbackup_list.html",
    "vmsnapshot_list.html",
    "replication_list.html",
    "backup_routine_list.html",
)


def _source(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_data_protection_views_are_defined_and_exported() -> None:
    source = _source("netbox_proxbox/views/data_protection.py")
    exports = _source("netbox_proxbox/views/__init__.py")

    assert "class DataProtectionCalendarMixin" in source
    assert "class DataProtectionView" in source
    assert "DataProtectionCalendarMixin" in exports
    assert "DataProtectionView" in exports


def test_list_views_mix_in_calendar_configuration() -> None:
    for module_name in ("vm_backup", "vm_snapshot", "replication", "backup_routine"):
        source = _source(f"netbox_proxbox/views/{module_name}.py")
        assert "DataProtectionCalendarMixin" in source
        assert "calendar_kind" in source
        assert "calendar_url_name" in source


def test_list_templates_include_calendar_before_parent_content() -> None:
    for template_name in LIST_TEMPLATES:
        source = _source(f"netbox_proxbox/templates/netbox_proxbox/{template_name}")
        include_index = source.index("inc/data_protection_calendar.html")
        block_super_index = source.index("{{ block.super }}", include_index)
        assert include_index < block_super_index


def test_urls_and_navigation_are_wired() -> None:
    urls = _source("netbox_proxbox/urls.py")
    navigation = _source("netbox_proxbox/navigation.py")

    assert '"data-protection/"' in urls
    assert 'name="data_protection"' in urls
    assert 'link="plugins:netbox_proxbox:data_protection"' in navigation
    group = navigation[navigation.rindex('"Data Protection",') :]
    assert group.index("data_protection_item") < group.index("backups_item")


def test_templates_and_stylesheet_exist_without_new_scripts() -> None:
    required = (
        PACKAGE / "templates/netbox_proxbox/data_protection.html",
        PACKAGE / "templates/netbox_proxbox/inc/data_protection_calendar.html",
        PACKAGE / "templates/netbox_proxbox/inc/data_protection_calendar_event.html",
        PACKAGE / "static/netbox_proxbox/css/data_protection_calendar.css",
    )
    for path in required:
        assert path.is_file()
        if path.suffix == ".html":
            assert "<script" not in path.read_text(encoding="utf-8").casefold()


def test_timestamp_sources_query_only_the_visible_window() -> None:
    source = _source("netbox_proxbox/views/data_protection.py")

    assert 'f"{timestamp_field}__gte"' in source
    assert 'f"{timestamp_field}__lt"' in source
    assert ".values(" in source
    assert '.order_by(timestamp_field, "pk")' in source
    assert "CALENDAR_SOURCE_LIMIT" in source
    assert "materialize_source_rows" in source
    assert "timezone.localtime" in source


def test_calendar_templates_expose_limits_and_accessible_date_semantics() -> None:
    calendar = _source(
        "netbox_proxbox/templates/netbox_proxbox/inc/data_protection_calendar.html"
    )
    event = _source(
        "netbox_proxbox/templates/netbox_proxbox/inc/data_protection_calendar_event.html"
    )

    assert '<caption class="visually-hidden">' in calendar
    assert "aria-label=\"{{ cell.date|date:'l, j F Y' }}\"" in calendar
    assert 'aria-current="date"' in calendar
    assert "calendar.truncation" in calendar
    assert "cell.hidden_count" in calendar
    assert "node's local time" in calendar
    assert '<span class="visually-hidden">' in event
    for kind in ("Backup", "Snapshot", "Replication", "Routine"):
        assert f'{{% trans "{kind}" %}}' in event


def test_combined_filter_submission_does_not_keep_a_stale_anchor() -> None:
    template = _source("netbox_proxbox/templates/netbox_proxbox/data_protection.html")

    assert 'name="cal_view"' in template
    assert 'name="cal_date"' not in template
    assert "(node local time)" in template


def test_combined_view_uses_login_and_queryset_restrictions() -> None:
    tree = ast.parse(_source("netbox_proxbox/views/data_protection.py"))
    view_class = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "DataProtectionView"
    )

    assert any(
        isinstance(base, ast.Name) and base.id == "ConditionalLoginRequiredMixin"
        for base in view_class.bases
    )
    source = _source("netbox_proxbox/views/data_protection.py")
    for model_name in ("VMBackup", "VMSnapshot", "Replication", "BackupRoutine"):
        assert f"{model_name}.objects.restrict(request.user" in source


def test_combined_filter_form_uses_netbox_dynamic_fields_and_date_picker() -> None:
    source = _source("netbox_proxbox/forms/data_protection.py")

    assert source.count("DynamicModelMultipleChoiceField(") == 3
    assert "VirtualMachine.objects.all()" in source
    assert source.count("DatePicker()") == 2
