"""No plugin view may declare `actions` as a dict.

NetBox 4.6 accepted a legacy `actions = {"add": {"add"}, ...}` mapping and
converted it internally, emitting a `FutureWarning` that named 4.7 as the
removal release. **NetBox 4.7 removed that conversion entirely.** There,
`ActionsMixin.get_permitted_actions()` iterates `self.actions` and reads
`action.permissions_required` off each element — so a dict yields its string
keys and the view raises `AttributeError: 'str' object has no attribute
'permissions_required'` on every render of that list.

An *empty* dict happens to survive (iterating it yields nothing), which is why
this was easy to miss: the read-only list views kept working while the ones with
buttons broke. The test suite missed it too — it renders detail views, and these
are list views and tabs.

`netbox.object_actions` exists in 4.5.8, 4.6.x and 4.7 alike, so the tuple form
is correct across the whole supported range rather than a 4.7-only migration.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parents[1] / "netbox_proxbox"


def _action_assignments() -> list[tuple[Path, int, ast.AST]]:
    """Class-body `actions = ...` only.

    Scoped to `ClassDef.body` deliberately: a method-local
    `actions = self.get_permitted_actions(...)` is an ordinary variable holding
    the *resolved* list, not the declaration NetBox reads off the view class.
    Walking every Assign in the module would flag those as violations.
    """
    found: list[tuple[Path, int, ast.AST]] = []
    for path in PACKAGE_ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            for statement in node.body:
                if not isinstance(statement, ast.Assign):
                    continue
                for target in statement.targets:
                    if isinstance(target, ast.Name) and target.id == "actions":
                        found.append((path, statement.lineno, statement.value))
    return found


def test_no_view_declares_actions_as_a_dict() -> None:
    offenders = [
        f"{path.relative_to(PACKAGE_ROOT.parent)}:{lineno}"
        for path, lineno, value in _action_assignments()
        if isinstance(value, ast.Dict)
    ]
    assert not offenders, (
        "NetBox 4.7 removed the legacy dict-actions conversion; these views would "
        f"raise AttributeError on every list render: {offenders}. Use a tuple of "
        "netbox.object_actions classes instead."
    )


def test_action_assignments_are_tuples_of_names() -> None:
    """The replacement must be ObjectAction classes, not strings in a tuple."""
    for path, lineno, value in _action_assignments():
        location = f"{path.relative_to(PACKAGE_ROOT.parent)}:{lineno}"
        assert isinstance(value, ast.Tuple), f"{location}: actions must be a tuple"
        for element in value.elts:
            assert isinstance(element, ast.Name), (
                f"{location}: actions entries must be ObjectAction classes, not "
                f"{ast.dump(element)[:60]}"
            )
