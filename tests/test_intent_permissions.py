"""Tests for Sub-PR B (#379): the seven NetBox→Proxmox intent RBAC permissions.

Two halves:

1. **AST contract tests** (always run): pin the helper-function names + return
   strings in ``netbox_proxbox.views.proxbox_access`` and the
   ``Meta.permissions`` tuples on the shell ``ProxmoxApplyJob`` and
   ``DeletionRequest`` models. These run without bootstrapping NetBox.

2. **Runtime tests** (skipped if Django/NetBox not importable): exercise the
   actual permission rows created by migration ``0038_intent_permissions``
   and verify ``user.has_perm()`` resolution.
"""

from __future__ import annotations

import ast
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
NETBOX_ROOT = REPO_ROOT.parent / "netbox" / "netbox"

INTENT_PERMS = (
    "intent_create_vm",
    "intent_update_vm",
    "intent_delete_vm",
    "intent_create_lxc",
    "intent_update_lxc",
    "intent_delete_lxc",
)

INTENT_HELPERS = {
    "permission_intent_create_vm": "netbox_proxbox.intent_create_vm",
    "permission_intent_update_vm": "netbox_proxbox.intent_update_vm",
    "permission_intent_delete_vm": "netbox_proxbox.intent_delete_vm",
    "permission_intent_create_lxc": "netbox_proxbox.intent_create_lxc",
    "permission_intent_update_lxc": "netbox_proxbox.intent_update_lxc",
    "permission_intent_delete_lxc": "netbox_proxbox.intent_delete_lxc",
    "permission_authorize_deletion_request": (
        "netbox_proxbox.authorize_deletion_request"
    ),
}


# --- AST contract tests (no Django) ---------------------------------------


def _parse(path: Path) -> ast.AST:
    return ast.parse(path.read_text())


def test_proxbox_access_exports_seven_intent_helpers():
    """``proxbox_access.__all__`` must list every intent helper."""
    module = _parse(REPO_ROOT / "netbox_proxbox" / "views" / "proxbox_access.py")
    all_tuple = None
    for node in ast.iter_child_nodes(module):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets
        ):
            all_tuple = node.value
            break
    assert all_tuple is not None, "proxbox_access.py must define __all__"
    names = {elt.value for elt in all_tuple.elts if isinstance(elt, ast.Constant)}
    for helper in INTENT_HELPERS:
        assert helper in names, f"{helper} missing from proxbox_access.__all__"


def test_apply_job_meta_permissions():
    """``ProxmoxApplyJob.Meta.permissions`` must declare the six intent verbs."""
    module = _parse(REPO_ROOT / "netbox_proxbox" / "models" / "apply_job.py")
    perms = _extract_meta_permissions(module, class_name="ProxmoxApplyJob")
    codenames = {codename for codename, _label in perms}
    assert codenames == set(INTENT_PERMS), (
        f"ProxmoxApplyJob.Meta.permissions codenames must be {set(INTENT_PERMS)}, "
        f"got {codenames}"
    )


def test_deletion_request_meta_permissions():
    """``DeletionRequest.Meta.permissions`` must declare ``authorize_deletion_request``."""
    module = _parse(REPO_ROOT / "netbox_proxbox" / "models" / "deletion_request.py")
    perms = _extract_meta_permissions(module, class_name="DeletionRequest")
    codenames = {codename for codename, _label in perms}
    assert codenames == {"authorize_deletion_request"}, (
        "DeletionRequest.Meta.permissions must hold exactly "
        "'authorize_deletion_request' so it can be granted independently of "
        f"intent_delete_*; got {codenames}"
    )


def test_migration_0038_lists_both_models():
    """Release migration must CreateModel both shells with matching permissions.

    Accepts either raw ``migrations.CreateModel(name=...)`` calls or the
    idempotent wrapper ``create_model_idempotent(name=...)`` introduced by
    issue #454 so the chain stays reporter-safe. Originally shipped as
    ``0038_intent_permissions``; now consolidated into the
    ``0038_v0_0_16_release`` squash.
    """
    module = _parse(
        REPO_ROOT / "netbox_proxbox" / "migrations" / "0038_v0_0_16_release.py"
    )
    create_calls = [
        node
        for node in ast.walk(module)
        if isinstance(node, ast.Call)
        and (
            (isinstance(node.func, ast.Attribute) and node.func.attr == "CreateModel")
            or (
                isinstance(node.func, ast.Name)
                and node.func.id == "create_model_idempotent"
            )
        )
    ]
    names = {
        kw.value.value
        for call in create_calls
        for kw in call.keywords
        if kw.arg == "name" and isinstance(kw.value, ast.Constant)
    }
    assert {"ProxmoxApplyJob", "DeletionRequest"} <= names, (
        f"Migration 0038 must CreateModel both ProxmoxApplyJob and "
        f"DeletionRequest; got {names}"
    )


def _extract_meta_permissions(
    module: ast.AST, *, class_name: str
) -> tuple[tuple[str, str], ...]:
    """Pull ``Meta.permissions`` literal off a model class in an AST module."""
    for node in ast.walk(module):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for inner in node.body:
                if isinstance(inner, ast.ClassDef) and inner.name == "Meta":
                    for stmt in inner.body:
                        if (
                            isinstance(stmt, ast.Assign)
                            and any(
                                isinstance(t, ast.Name) and t.id == "permissions"
                                for t in stmt.targets
                            )
                            and isinstance(stmt.value, (ast.Tuple, ast.List))
                        ):
                            return tuple(
                                (elt.elts[0].value, elt.elts[1].value)
                                for elt in stmt.value.elts
                                if isinstance(elt, (ast.Tuple, ast.List))
                                and len(elt.elts) >= 2
                                and isinstance(elt.elts[0], ast.Constant)
                                and isinstance(elt.elts[1], ast.Constant)
                            )
    raise AssertionError(f"{class_name}.Meta.permissions tuple not found in module AST")


# --- Runtime tests (require Django + NetBox) ------------------------------

for candidate in (REPO_ROOT, NETBOX_ROOT):
    candidate_str = str(candidate)
    if candidate.exists() and candidate_str not in sys.path:
        sys.path.insert(0, candidate_str)

try:
    import django
except ModuleNotFoundError:
    django = None  # type: ignore[assignment]

if django is not None:
    os.environ.setdefault("NETBOX_CONFIGURATION", "tests.netbox_test_configuration")
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "netbox.settings")
    try:
        django.setup()
    except Exception:  # pragma: no cover - depends on external test services
        django = None  # type: ignore[assignment]


if django is not None:
    from django.contrib.auth.models import Permission
    from django.contrib.contenttypes.models import ContentType
    from django.test import TestCase
    from utilities.testing import create_test_user

    from netbox_proxbox.views.proxbox_access import (
        permission_authorize_deletion_request,
        permission_intent_create_lxc,
        permission_intent_create_vm,
        permission_intent_delete_lxc,
        permission_intent_delete_vm,
        permission_intent_update_lxc,
        permission_intent_update_vm,
    )

    HELPER_FUNCS = {
        "permission_intent_create_vm": permission_intent_create_vm,
        "permission_intent_update_vm": permission_intent_update_vm,
        "permission_intent_delete_vm": permission_intent_delete_vm,
        "permission_intent_create_lxc": permission_intent_create_lxc,
        "permission_intent_update_lxc": permission_intent_update_lxc,
        "permission_intent_delete_lxc": permission_intent_delete_lxc,
        "permission_authorize_deletion_request": permission_authorize_deletion_request,
    }

    class IntentPermissionHelperReturnsTest(TestCase):
        """Each helper returns the dotted ``app_label.codename`` string."""

        def test_all_seven_helpers_return_expected_string(self):
            for name, expected in INTENT_HELPERS.items():
                self.assertEqual(
                    HELPER_FUNCS[name](),
                    expected,
                    f"{name}() must return {expected!r}",
                )

    class IntentPermissionRowsExistTest(TestCase):
        """Migration 0038 must register all seven permission rows."""

        def test_intent_apply_job_perms_exist(self):
            ct = ContentType.objects.get(
                app_label="netbox_proxbox", model="proxmoxapplyjob"
            )
            for codename in INTENT_PERMS:
                self.assertTrue(
                    Permission.objects.filter(
                        content_type=ct, codename=codename
                    ).exists(),
                    f"{codename} must exist on netbox_proxbox.proxmoxapplyjob",
                )

        def test_authorize_deletion_request_perm_exists(self):
            ct = ContentType.objects.get(
                app_label="netbox_proxbox", model="deletionrequest"
            )
            self.assertTrue(
                Permission.objects.filter(
                    content_type=ct, codename="authorize_deletion_request"
                ).exists(),
                "authorize_deletion_request must exist on "
                "netbox_proxbox.deletionrequest (distinct from intent_delete_*)",
            )

    class IntentPermissionGrantResolvesTest(TestCase):
        """Granting a permission must make ``user.has_perm()`` return True."""

        def test_grant_then_check(self):
            user = create_test_user(username="intent-operator")
            ct = ContentType.objects.get(
                app_label="netbox_proxbox", model="proxmoxapplyjob"
            )
            perm = Permission.objects.get(content_type=ct, codename="intent_create_vm")
            user.user_permissions.add(perm)
            user = type(user).objects.get(pk=user.pk)
            self.assertTrue(user.has_perm("netbox_proxbox.intent_create_vm"))

        def test_default_user_lacks_perms(self):
            user = create_test_user(username="intent-bystander")
            user = type(user).objects.get(pk=user.pk)
            for helper, expected in INTENT_HELPERS.items():
                self.assertFalse(
                    user.has_perm(expected),
                    f"Default user must not hold {expected}",
                )

    # Runtime tests defined above when Django/NetBox is bootstrapped.
