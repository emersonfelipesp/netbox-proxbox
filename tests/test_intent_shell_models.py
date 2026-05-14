"""Sub-PR B (#379): shell model contract.

The shells exist so migration ``0038_intent_permissions`` can attach the seven
intent RBAC permissions to real ContentTypes. Both models are promoted to
their full schemas in later sub-PRs (E for ApplyJob, H for DeletionRequest);
the contract here pins what they MUST already provide today.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MODELS_DIR = REPO_ROOT / "netbox_proxbox" / "models"


def _imports_names(module_path: Path) -> set[str]:
    tree = ast.parse(module_path.read_text())
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                names.add(alias.asname or alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.asname or alias.name.split(".", 1)[0])
    return names


def test_models_init_reexports_apply_job_and_deletion_request():
    init_text = (MODELS_DIR / "__init__.py").read_text()
    assert "from netbox_proxbox.models.apply_job import ProxmoxApplyJob" in init_text
    assert (
        "from netbox_proxbox.models.deletion_request import DeletionRequest"
        in init_text
    )
    assert '"ProxmoxApplyJob"' in init_text
    assert '"DeletionRequest"' in init_text


def test_apply_job_module_imports_netbox_model():
    """``ProxmoxApplyJob`` must subclass NetBoxModel so registrations work."""
    names = _imports_names(MODELS_DIR / "apply_job.py")
    assert "NetBoxModel" in names


def test_deletion_request_module_imports_netbox_model():
    names = _imports_names(MODELS_DIR / "deletion_request.py")
    assert "NetBoxModel" in names


def test_apply_job_class_subclasses_netbox_model():
    tree = ast.parse((MODELS_DIR / "apply_job.py").read_text())
    cls = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef) and node.name == "ProxmoxApplyJob"
    )
    bases = {b.id for b in cls.bases if isinstance(b, ast.Name)}
    assert "NetBoxModel" in bases


def test_deletion_request_class_subclasses_netbox_model():
    tree = ast.parse((MODELS_DIR / "deletion_request.py").read_text())
    cls = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef) and node.name == "DeletionRequest"
    )
    bases = {b.id for b in cls.bases if isinstance(b, ast.Name)}
    assert "NetBoxModel" in bases
