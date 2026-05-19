"""Source contracts for VMSnapshot model and detail template (issue #472).

Guards against a regression where ``vmsnapshot.html`` called the non-existent
``get_bg_color`` Django template filter instead of the NetBox-standard
``get_<field>_color()`` instance-method pattern.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _src(path: str) -> str:
    return (REPO_ROOT / path).read_text()


# ── Model method contracts ─────────────────────────────────────────────────────


def _method_names_in_class(source: str, class_name: str) -> list[str]:
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return [
                n.name
                for n in ast.walk(node)
                if isinstance(n, ast.FunctionDef)
            ]
    return []


def test_vmsnapshot_model_has_get_status_color():
    src = _src("netbox_proxbox/models/vm_snapshot.py")
    methods = _method_names_in_class(src, "VMSnapshot")
    assert "get_status_color" in methods, (
        "VMSnapshot must define get_status_color() following the NetBox "
        "get_<field>_color() convention for badge rendering."
    )


def test_vmsnapshot_model_has_get_subtype_color():
    src = _src("netbox_proxbox/models/vm_snapshot.py")
    methods = _method_names_in_class(src, "VMSnapshot")
    assert "get_subtype_color" in methods, (
        "VMSnapshot must define get_subtype_color() following the NetBox "
        "get_<field>_color() convention for badge rendering."
    )


def test_vmsnapshot_model_color_methods_use_choices_colors():
    src = _src("netbox_proxbox/models/vm_snapshot.py")
    assert "ProxmoxSnapshotStatusChoices.colors.get" in src, (
        "get_status_color() must look up the color via "
        "ProxmoxSnapshotStatusChoices.colors.get(self.status)."
    )
    assert "ProxmoxSnapshotSubtypeChoices.colors.get" in src, (
        "get_subtype_color() must look up the color via "
        "ProxmoxSnapshotSubtypeChoices.colors.get(self.subtype)."
    )


# ── Template contracts ─────────────────────────────────────────────────────────


def test_vmsnapshot_template_does_not_use_get_bg_color():
    src = _src(
        "netbox_proxbox/templates/netbox_proxbox/vmsnapshot.html"
    )
    assert "get_bg_color" not in src, (
        "vmsnapshot.html must not call the non-existent 'get_bg_color' "
        "Django template filter. Use bg_color=object.get_status_color "
        "and bg_color=object.get_subtype_color instead."
    )


def test_vmsnapshot_template_uses_get_status_color():
    src = _src(
        "netbox_proxbox/templates/netbox_proxbox/vmsnapshot.html"
    )
    assert "object.get_status_color" in src, (
        "vmsnapshot.html must use bg_color=object.get_status_color "
        "for the Status badge."
    )


def test_vmsnapshot_template_uses_get_subtype_color():
    src = _src(
        "netbox_proxbox/templates/netbox_proxbox/vmsnapshot.html"
    )
    assert "object.get_subtype_color" in src, (
        "vmsnapshot.html must use bg_color=object.get_subtype_color "
        "for the Subtype badge."
    )
