"""The plugin's migration graph must have exactly one leaf.

Two branches that each add a migration against the same parent merge cleanly at
the text level -- different filenames, no overlapping lines -- and then leave
Django with two leaf nodes, at which point *every* `manage.py migrate` refuses
to run:

    CommandError: Conflicting migrations detected; multiple leaf nodes in the
    migration graph: (0084_proxboxpluginsettings_console_url,
    0084_remove_vm_reflection_custom_fields in netbox_proxbox).

That is a deploy-stopping, whole-plugin failure produced by a merge order rather
than by either change, so neither branch's own CI can see it. It happened here
when the console-URL migration and the reflection-custom-field removal landed in
the same window. This guard reads the graph the same way Django does -- from the
declared dependencies -- so a second leaf fails in the mocked suite instead of on
the first environment that tries to migrate.
"""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "netbox_proxbox" / "migrations"
APP_LABEL = "netbox_proxbox"


def _migration_modules() -> list[Path]:
    return sorted(
        path
        for path in MIGRATIONS_DIR.glob("*.py")
        # Leading-underscore modules are data helpers the loader skips.
        if not path.name.startswith("_")
    )


def _declared_dependencies(path: Path) -> set[str]:
    """Return this migration's dependencies on its own app."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(
            isinstance(target, ast.Name) and target.id == "dependencies"
            for target in node.targets
        ):
            continue
        for element in getattr(node.value, "elts", []):
            parts = [
                item.value
                for item in getattr(element, "elts", [])
                if isinstance(item, ast.Constant)
            ]
            if len(parts) == 2 and parts[0] == APP_LABEL:
                found.add(parts[1])
    return found


def test_migration_graph_has_exactly_one_leaf() -> None:
    modules = _migration_modules()
    names = {path.stem for path in modules}
    depended_on: set[str] = set()
    for path in modules:
        for dependency in _declared_dependencies(path):
            # A dependency naming a migration that does not exist is its own
            # deploy-stopping bug, and silently ignoring it here would let this
            # guard pass on a graph Django cannot even load.
            assert dependency in names, f"{path.name} depends on missing {dependency}"
            depended_on.add(dependency)

    leaves = sorted(names - depended_on)
    assert len(leaves) == 1, (
        "the migration graph must have exactly one leaf, or `manage.py migrate` "
        f"refuses to run for the whole plugin; found {len(leaves)}: {leaves}. "
        "This normally means two branches added a migration against the same "
        "parent. Renumber the later one and depend it on the earlier."
    )
    assert leaves == ["0108_v0_0_31_schema_validation"]


def test_release_migration_replaces_development_lineage() -> None:
    names = {path.stem for path in _migration_modules()}

    assert "0107_v0_0_30_release" in names
    assert "0107_endpoint_native_cluster_binding" not in names
    assert "0108_ssh_service_chain" not in names
    assert "0109_proxmoxendpoint_cloud_image_ssh_binding" not in names
    release = MIGRATIONS_DIR / "0107_v0_0_30_release.py"
    assert _declared_dependencies(release) == {
        "0106_device_sync_scope_and_netbox_token_approval"
    }


# A companion "migration numbers are unique" check was deliberately *not* added.
# This repository already carries several shared numbers -- 0043, 0057 and 0059
# each name two or three migrations -- and they are perfectly healthy, because
# their declared dependencies still linearise them into one chain. The number is
# a filename convention; the dependency graph is the thing Django loads, and the
# single leaf above is the property whose violation actually stops a deploy.
# Asserting on the numbers would fail on a correct tree and teach the next
# person to silence this file.


def test_post_candidate_validation_is_one_new_migration_after_frozen_release() -> None:
    validation = MIGRATIONS_DIR / "0108_v0_0_31_schema_validation.py"
    assert _declared_dependencies(validation) == {"0107_v0_0_30_release"}
    source = ast.parse(validation.read_text(encoding="utf-8"))
    operations = [
        node
        for node in ast.walk(source)
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "operations"
            for target in node.targets
        )
    ]
    assert len(operations) == 1
    assert len(operations[0].value.elts) == 1
    assert operations[0].value.elts[0].func.attr == "RunPython"


def test_deployed_candidate_migration_keeps_its_immutable_bytes() -> None:
    deployed = MIGRATIONS_DIR / "0107_v0_0_30_release.py"
    assert (
        hashlib.sha256(deployed.read_bytes()).hexdigest()
        == "31e9a4edadb68f79d704273ab7b972034b5dc488e565e9aaf0463a85258e6429"
    )
    assert not deployed.stat().st_mode & 0o111


def test_validation_reverse_is_a_noop() -> None:
    tree = ast.parse(
        (MIGRATIONS_DIR / "0108_v0_0_31_schema_validation.py").read_text(
            encoding="utf-8"
        )
    )
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
    assert len(calls) == 1
    assert calls[0].args[0].id == "finalize_release_schema"
    assert calls[0].args[1].attr == "noop"


def test_validation_migration_has_its_own_atomic_boundary() -> None:
    tree = ast.parse(
        (MIGRATIONS_DIR / "0108_v0_0_31_schema_validation.py").read_text(
            encoding="utf-8"
        )
    )
    migration = tree.body[-1]
    assignment = next(
        item
        for item in migration.body
        if isinstance(item, ast.Assign) and item.targets[0].id == "atomic"
    )
    assert assignment.value.value is True
