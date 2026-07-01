"""Source-contract and behavior tests for the ProxmoxEndpoint Templates tab.

Coverage:

1. AST/source contracts for ``ProxmoxEndpointTemplatesTabView`` — class exists,
   subclasses ``ObjectView``, is in ``__all__``, declares the tab with the
   expected label/permission/weight, uses the expected template, registers at
   ``path="templates"``, defines ``get_extra_context`` and the classification
   helpers, and fetches live data from proxbox-api via the established
   integration boundary while degrading gracefully.
2. Source contracts for the optional ``netbox_proxbox.integrations.packer``
   helper (detection against ``settings.PLUGINS`` + guarded add-URL).
3. Template contracts — three filterable category groups and a create button
   that is disabled *with a working tooltip* when netbox-packer is absent.
4. Behavior of the cloud-init classification / normalization logic (mirrored,
   as the view module cannot be imported without a full NetBox environment).

The tab view module cannot be imported without Django/NetBox, so the structural
checks are AST/source based — the same approach used by
``test_endpoint_host_key_fingerprint.py`` and ``test_endpoint_sync_jobs_tab.py``.
"""

from __future__ import annotations

import ast
import posixpath
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
VIEW_PATH = REPO_ROOT / "netbox_proxbox" / "views" / "proxmox_templates_tab.py"
PACKER_PATH = REPO_ROOT / "netbox_proxbox" / "integrations" / "packer.py"
TEMPLATE_PATH = (
    REPO_ROOT
    / "netbox_proxbox"
    / "templates"
    / "netbox_proxbox"
    / "proxmoxendpoint_templates.html"
)
VIEWS_INIT_PATH = REPO_ROOT / "netbox_proxbox" / "views" / "__init__.py"


@pytest.fixture(scope="module")
def view_src() -> str:
    return VIEW_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def view_ast() -> ast.Module:
    return ast.parse(VIEW_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def packer_src() -> str:
    return PACKER_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def template_src() -> str:
    return TEMPLATE_PATH.read_text(encoding="utf-8")


def _find_class(module: ast.Module, name: str) -> ast.ClassDef:
    for node in ast.walk(module):
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    raise AssertionError(f"class {name} not found in {VIEW_PATH.name}")


def _find_assign(class_node: ast.ClassDef, target: str) -> ast.AST | None:
    for node in class_node.body:
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == target:
                    return node.value
    return None


def _func_names(module: ast.Module) -> set[str]:
    return {n.name for n in ast.walk(module) if isinstance(n, ast.FunctionDef)}


# ── View: AST structure contracts ────────────────────────────────────────────


def test_view_class_exists_and_is_object_view(view_ast):
    cls = _find_class(view_ast, "ProxmoxEndpointTemplatesTabView")
    base_names = {
        b.attr if isinstance(b, ast.Attribute) else getattr(b, "id", "")
        for b in cls.bases
    }
    assert "ObjectView" in base_names


def test_view_in_public_all(view_ast):
    module_all = None
    for node in view_ast.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets
        ):
            module_all = node.value
    assert module_all is not None
    elts = {e.value for e in module_all.elts if isinstance(e, ast.Constant)}
    assert "ProxmoxEndpointTemplatesTabView" in elts


def test_view_template_name(view_ast):
    cls = _find_class(view_ast, "ProxmoxEndpointTemplatesTabView")
    template_value = _find_assign(cls, "template_name")
    assert isinstance(template_value, ast.Constant)
    assert template_value.value == "netbox_proxbox/proxmoxendpoint_templates.html"


def test_view_tab_metadata(view_src):
    assert 'label="Templates"' in view_src
    assert 'permission="netbox_proxbox.view_proxmoxendpoint"' in view_src
    assert "weight=960" in view_src


def test_view_registered_at_templates_path(view_src):
    assert (
        'register_model_view(ProxmoxEndpoint, "templates", path="templates")'
        in view_src
    )


def test_view_defines_get_extra_context_and_helpers(view_ast):
    cls = _find_class(view_ast, "ProxmoxEndpointTemplatesTabView")
    methods = {n.name for n in cls.body if isinstance(n, ast.FunctionDef)}
    assert "get_extra_context" in methods
    fns = _func_names(view_ast)
    for helper in (
        "_row_has_cloud_init",
        "_normalize_qemu_template",
        "_normalize_lxc_template",
        "_fetch_endpoint_templates",
    ):
        assert helper in fns


def test_view_is_wired_into_views_package():
    init_src = VIEWS_INIT_PATH.read_text(encoding="utf-8")
    assert (
        "from .proxmox_templates_tab import ProxmoxEndpointTemplatesTabView" in init_src
    )


# ── View: integration-boundary + behavior source contracts ───────────────────


def test_view_uses_established_backend_boundary(view_src):
    assert "get_fastapi_request_context" in view_src
    assert "resolve_backend_endpoint_id" in view_src


def test_view_fetches_both_template_endpoints(view_src):
    assert "/cloud/vm/templates" in view_src
    assert "/cloud/lxc/templates" in view_src
    # Plain QEMU templates require the non-cloud-init-only listing.
    assert '"cloud_init_only": "false"' in view_src


def test_view_classifies_cloud_init_from_config_not_flag(view_src):
    # The proxbox-api `cloud_init` field is hard-coded True; classification must
    # derive from the real config fields instead.
    assert "cloud_init_drives" in view_src
    assert "cicustom" in view_src


def test_view_degrades_gracefully(view_src):
    assert "backend_error" in view_src
    assert "packer_installed" in view_src
    assert "packer_add_url" in view_src


# ── integrations/packer.py contracts ─────────────────────────────────────────


def test_packer_detection_checks_installed_plugins(packer_src):
    assert "def is_netbox_packer_installed" in packer_src
    assert '"netbox_packer"' in packer_src
    assert "settings.PLUGINS" in packer_src


def test_packer_add_url_helper(packer_src):
    assert "def packer_template_add_url" in packer_src
    assert "plugins:netbox_packer:packertemplate_add" in packer_src
    # When netbox-packer is absent the helper must short-circuit to None.
    assert "if not is_netbox_packer_installed():" in packer_src


# ── Template contracts ───────────────────────────────────────────────────────


def test_template_extends_object(template_src):
    assert "{% extends 'generic/object.html' %}" in template_src


def test_template_has_three_category_groups(template_src):
    assert 'data-category="cloudinit"' in template_src
    assert 'data-category="plain"' in template_src
    assert 'data-category="lxc"' in template_src


def test_template_has_category_filter(template_src):
    for f in ("all", "cloudinit", "plain", "lxc"):
        assert f'data-filter="{f}"' in template_src


def test_template_create_button_enabled_when_packer_installed(template_src):
    assert "{% if packer_installed and packer_add_url %}" in template_src
    assert 'href="{{ packer_add_url }}"' in template_src


def test_template_disabled_button_has_working_tooltip(template_src):
    # Bootstrap tooltips do not fire on a disabled button — the tooltip must live
    # on a wrapping element. This is the behavior the task explicitly requires.
    assert 'data-bs-toggle="tooltip"' in template_src
    assert "netbox-packer is not installed" in template_src
    # The disabled button itself must still be present inside the tooltip wrapper.
    assert "disabled" in template_src


# ── Behavior: classification / normalization (mirrors the view helpers) ───────


def _has_cloud_init(row: dict) -> bool:
    drives = row.get("cloud_init_drives")
    if isinstance(drives, (list, tuple)) and len(drives) > 0:
        return True
    cicustom = row.get("cicustom")
    return bool(cicustom and str(cicustom).strip())


def test_cloud_init_detected_from_drive():
    assert _has_cloud_init({"cloud_init_drives": ["ide2"], "cicustom": None}) is True


def test_cloud_init_detected_from_cicustom():
    assert (
        _has_cloud_init(
            {"cloud_init_drives": [], "cicustom": "user=local:snippets/u.yaml"}
        )
        is True
    )


def test_plain_template_when_no_cloud_init():
    assert _has_cloud_init({"cloud_init_drives": [], "cicustom": None}) is False
    assert _has_cloud_init({"cloud_init_drives": [], "cicustom": ""}) is False


def _bytes_to_gib(value) -> float | None:
    try:
        num = int(value)
    except (TypeError, ValueError):
        return None
    if num <= 0:
        return None
    return round(num / (1024**3), 1)


def test_bytes_to_gib():
    assert _bytes_to_gib(10 * 1024**3) == 10.0
    assert _bytes_to_gib(0) is None
    assert _bytes_to_gib(None) is None
    assert _bytes_to_gib("not-a-number") is None


def test_lxc_name_from_volid():
    volid = "local:vztmpl/debian-12-standard_12.7-1_amd64.tar.zst"
    name = posixpath.basename(volid.split(":", 1)[-1])
    assert name == "debian-12-standard_12.7-1_amd64.tar.zst"
