"""Source-contract tests for the ``ProxmoxStorage`` view module.

Storage list/detail/edit/delete plus the three child-tab views are referenced
across templates, ``__init__.py`` re-exports, and the URL conf. We pin the
public shape with AST so renaming or moving these classes is a noisy regression.

What is locked here:

* The eight public view classes are exported from ``__all__``.
* ``ProxmoxStorageListView`` registers at the empty-path list URL with
  ``detail=False`` — this is what makes ``ProxmoxStorageListView`` resolvable
  via the standard plugin URL conf.
* The three child-children tab views (Virtual Disks, Backups, Snapshots) are
  registered with the documented paths ``virtual-disks``, ``backups``,
  ``snapshots`` and have a ``ViewTab`` with the right permission.
* The detail view's ``request_timeout`` stays at 8 seconds (template asserts
  this is short enough to render even with backend latency).
* ``ProxmoxStorageFilterSet.nodes`` is declared explicitly as NetBox's
  ``MultiValueCharFilter`` so widening the model field to ``TextField`` cannot
  change repeated-query or OpenAPI behavior.
"""

from __future__ import annotations

import ast
from pathlib import Path

STORAGE_PATH = (
    Path(__file__).resolve().parents[1] / "netbox_proxbox" / "views" / "storage.py"
)
FILTERSETS_PATH = (
    Path(__file__).resolve().parents[1] / "netbox_proxbox" / "filtersets.py"
)
STORAGE_CONTENT_PATH = (
    Path(__file__).resolve().parents[1]
    / "netbox_proxbox"
    / "views"
    / "storage_content.py"
)


def _module() -> ast.Module:
    return ast.parse(STORAGE_PATH.read_text(encoding="utf-8"))


EXPECTED_PUBLIC = (
    "ProxmoxStorageView",
    "ProxmoxStorageListView",
    "ProxmoxStorageEditView",
    "ProxmoxStorageDeleteView",
    "ProxmoxStorageBulkDeleteView",
    "ProxmoxStorageVirtualDisksTabView",
    "ProxmoxStorageBackupsTabView",
    "ProxmoxStorageSnapshotsTabView",
)


def _find_class(module: ast.Module, name: str) -> ast.ClassDef:
    for node in ast.walk(module):
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    raise AssertionError(f"class {name} not found in storage.py")


def _register_calls(cls: ast.ClassDef) -> list[ast.Call]:
    return [
        d
        for d in cls.decorator_list
        if isinstance(d, ast.Call)
        and isinstance(d.func, ast.Name)
        and d.func.id == "register_model_view"
    ]


def test_public_classes_in_all():
    module = _module()
    public_assign = next(
        (
            n.value
            for n in module.body
            if isinstance(n, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "__all__" for t in n.targets)
        ),
        None,
    )
    assert isinstance(public_assign, ast.Tuple)
    exported = {e.value for e in public_assign.elts if isinstance(e, ast.Constant)}
    for name in EXPECTED_PUBLIC:
        assert name in exported, f"{name} dropped from storage.py __all__"


def test_each_public_class_exists():
    module = _module()
    for name in EXPECTED_PUBLIC:
        _find_class(module, name)


def test_list_view_registers_at_empty_path_with_detail_false():
    module = _module()
    cls = _find_class(module, "ProxmoxStorageListView")
    decos = _register_calls(cls)
    assert decos, "ProxmoxStorageListView must use register_model_view"

    matched = False
    for call in decos:
        keywords = {kw.arg: kw.value for kw in call.keywords}
        path = keywords.get("path")
        detail = keywords.get("detail")
        if (
            isinstance(path, ast.Constant)
            and path.value == ""
            and isinstance(detail, ast.Constant)
            and detail.value is False
        ):
            matched = True
            break
    assert matched, (
        "ProxmoxStorageListView must register at path='' with detail=False so the "
        "global storage list resolves under the standard plugin URL conf"
    )


def test_child_tab_paths_and_permissions_are_pinned():
    module = _module()
    expected = {
        "ProxmoxStorageVirtualDisksTabView": (
            "virtual-disks",
            "Virtual Disks",
            "virtualization.view_virtualdisk",
        ),
        "ProxmoxStorageBackupsTabView": (
            "backups",
            "Backups",
            "netbox_proxbox.view_vmbackup",
        ),
        "ProxmoxStorageSnapshotsTabView": (
            "snapshots",
            "Snapshots",
            "netbox_proxbox.view_vmsnapshot",
        ),
    }
    for class_name, (path, label, permission) in expected.items():
        cls = _find_class(module, class_name)

        decos = _register_calls(cls)
        assert decos, f"{class_name} must use register_model_view"
        paths = []
        for call in decos:
            for kw in call.keywords:
                if kw.arg == "path" and isinstance(kw.value, ast.Constant):
                    paths.append(kw.value.value)
        assert path in paths, f"{class_name} must register path={path!r}"

        tab_value = next(
            (
                n.value
                for n in cls.body
                if isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == "tab" for t in n.targets)
            ),
            None,
        )
        assert isinstance(tab_value, ast.Call)
        assert isinstance(tab_value.func, ast.Name) and tab_value.func.id == "ViewTab"
        keywords = {kw.arg: kw.value for kw in tab_value.keywords}
        assert isinstance(keywords["label"], ast.Constant)
        assert keywords["label"].value == label
        assert isinstance(keywords["permission"], ast.Constant)
        assert keywords["permission"].value == permission


def test_detail_view_request_timeout_is_short_enough():
    cls = _find_class(_module(), "ProxmoxStorageView")
    timeout_value = next(
        (
            n.value
            for n in cls.body
            if isinstance(n, ast.Assign)
            and any(
                isinstance(t, ast.Name) and t.id == "request_timeout" for t in n.targets
            )
        ),
        None,
    )
    assert isinstance(timeout_value, ast.Constant)
    assert isinstance(timeout_value.value, int)
    assert timeout_value.value <= 10, (
        "ProxmoxStorageView.request_timeout must stay short — the storage detail "
        "page renders inline and a slow backend should not block the request"
    )


def test_storage_content_uses_the_process_wide_bounded_fetcher():
    module = _module()
    source = STORAGE_PATH.read_text(encoding="utf-8")
    helper_source = STORAGE_CONTENT_PATH.read_text(encoding="utf-8")
    cls = _find_class(module, "ProxmoxStorageView")
    method_calls = {
        node.func.id
        for method_name in ("_fetch_storage_content_json", "_fetch_storage_content")
        for method in cls.body
        if isinstance(method, ast.FunctionDef) and method.name == method_name
        for node in ast.walk(method)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }

    assert "ThreadPoolExecutor" not in source
    assert "collect_completed_before_deadline" in method_calls
    assert "fetch_json_with_limits" in method_calls
    assert "format_content_detail" in method_calls
    assert "_CONTENT_FETCH_POOL = _BoundedContentFetchPool(" in helper_source
    assert "CONTENT_RESPONSE_MAX_BYTES = 1024 * 1024" in helper_source


def test_storage_content_keeps_the_64_node_page_cap():
    module = _module()
    max_nodes = next(
        (
            node.value
            for node in module.body
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "MAX_CONTENT_NODES"
                for target in node.targets
            )
        ),
        None,
    )

    assert isinstance(max_nodes, ast.Constant)
    assert max_nodes.value == 64


def test_storage_nodes_filter_explicitly_preserves_multi_value_semantics():
    module = ast.parse(FILTERSETS_PATH.read_text(encoding="utf-8"))
    imported_filter_names = {
        alias.name
        for node in module.body
        if isinstance(node, ast.ImportFrom) and node.module == "utilities.filters"
        for alias in node.names
    }
    assert "MultiValueCharFilter" in imported_filter_names

    cls = _find_class(module, "ProxmoxStorageFilterSet")
    nodes_filter = next(
        (
            node.value
            for node in cls.body
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == "nodes"
                for target in node.targets
            )
        ),
        None,
    )
    assert isinstance(nodes_filter, ast.Call)
    assert isinstance(nodes_filter.func, ast.Name)
    assert nodes_filter.func.id == "MultiValueCharFilter"
