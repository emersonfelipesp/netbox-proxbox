"""AST-based contract tests for the PR C2b PBS REST API surface.

Pin the read-only enforcement on the API side: only ``PBSEndpointViewSet``
exposes full CRUD; the five reflected viewsets restrict ``http_method_names``
to ``("get", "head", "options")`` so POST/PUT/PATCH/DELETE return 405.

We verify the contract via AST rather than booting NetBox so the per-commit
gate runs offline.
"""

from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PKG_DIR = REPO_ROOT / "netbox_pbs"
API_DIR = PKG_DIR / "api"
API_VIEWS = API_DIR / "views.py"
API_URLS = API_DIR / "urls.py"
API_SERIALIZERS = API_DIR / "serializers.py"


READ_ONLY_VIEWSETS = (
    "PBSNodeViewSet",
    "PBSDatastoreViewSet",
    "PBSBackupGroupViewSet",
    "PBSSnapshotViewSet",
    "PBSJobStatusViewSet",
)
ALL_VIEWSETS = ("PBSEndpointViewSet", *READ_ONLY_VIEWSETS)
ALL_SERIALIZERS = (
    "PBSEndpointSerializer",
    "PBSNodeSerializer",
    "PBSDatastoreSerializer",
    "PBSBackupGroupSerializer",
    "PBSSnapshotSerializer",
    "PBSJobStatusSerializer",
)


def _find_class(module: ast.Module, name: str) -> ast.ClassDef | None:
    for node in module.body:
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    return None


def _http_method_names_value(class_node: ast.ClassDef) -> tuple[str, ...] | None:
    """Return the tuple/list literal assigned to ``http_method_names`` if any."""
    for stmt in class_node.body:
        if not isinstance(stmt, ast.Assign):
            continue
        for target in stmt.targets:
            if isinstance(target, ast.Name) and target.id == "http_method_names":
                value = stmt.value
                # Direct tuple/list literal
                if isinstance(value, (ast.Tuple, ast.List)):
                    return tuple(
                        elt.value for elt in value.elts if isinstance(elt, ast.Constant)
                    )
                # Module-level constant reference (e.g. _READ_ONLY_HTTP_METHODS)
                if isinstance(value, ast.Name):
                    module = class_node  # placeholder; resolved below
                    return _resolve_module_constant(module, value.id)
    return None


def _resolve_module_constant(
    class_node: ast.ClassDef, name: str
) -> tuple[str, ...] | None:
    # Walk up to module by re-parsing the file the class came from.
    # Simpler: scan API_VIEWS module-level constants.
    module = ast.parse(API_VIEWS.read_text(encoding="utf-8"))
    for stmt in module.body:
        if not isinstance(stmt, ast.Assign):
            continue
        for target in stmt.targets:
            if isinstance(target, ast.Name) and target.id == name:
                value = stmt.value
                if isinstance(value, (ast.Tuple, ast.List)):
                    return tuple(
                        elt.value for elt in value.elts if isinstance(elt, ast.Constant)
                    )
    return None


def test_pbs_endpoint_viewset_is_full_crud():
    module = ast.parse(API_VIEWS.read_text(encoding="utf-8"))
    cls = _find_class(module, "PBSEndpointViewSet")
    assert cls is not None, "missing PBSEndpointViewSet"
    # No http_method_names restriction => full CRUD
    assert _http_method_names_value(cls) is None, (
        "PBSEndpointViewSet must not restrict http_method_names"
    )


def test_reflected_viewsets_restrict_to_read_only_http_methods():
    module = ast.parse(API_VIEWS.read_text(encoding="utf-8"))
    for viewset in READ_ONLY_VIEWSETS:
        cls = _find_class(module, viewset)
        assert cls is not None, f"missing {viewset}"
        methods = _http_method_names_value(cls)
        assert methods is not None, (
            f"{viewset} must restrict http_method_names to read-only verbs"
        )
        assert set(methods) <= {"get", "head", "options"}, (
            f"{viewset} http_method_names must be a subset of "
            f"(get, head, options); got {methods}"
        )


def test_all_viewsets_inherit_from_netbox_model_viewset():
    """Every viewset must use NetBoxModelViewSet so permission + pagination work."""
    module = ast.parse(API_VIEWS.read_text(encoding="utf-8"))
    for viewset in ALL_VIEWSETS:
        cls = _find_class(module, viewset)
        assert cls is not None, f"missing {viewset}"
        base_names = [
            base.id if isinstance(base, ast.Name) else None for base in cls.bases
        ]
        assert "NetBoxModelViewSet" in base_names, (
            f"{viewset} must inherit from NetBoxModelViewSet; got {base_names}"
        )


def test_api_urls_register_all_six_viewsets():
    text = API_URLS.read_text(encoding="utf-8")
    expected_basenames = {
        "PBSEndpointViewSet": "pbsendpoint",
        "PBSNodeViewSet": "pbsnode",
        "PBSDatastoreViewSet": "pbsdatastore",
        "PBSBackupGroupViewSet": "pbsbackupgroup",
        "PBSSnapshotViewSet": "pbssnapshot",
        "PBSJobStatusViewSet": "pbsjobstatus",
    }
    for viewset, basename in expected_basenames.items():
        assert viewset in text, f"api/urls.py must register {viewset}"
        assert f'basename="{basename}"' in text, (
            f"api/urls.py must use basename='{basename}' for {viewset}"
        )


def test_pbs_endpoint_serializer_marks_token_value_write_only():
    """``token_value`` must never appear in API responses."""
    text = API_SERIALIZERS.read_text(encoding="utf-8")
    # The simplest contract pin: the write_only=True attribute appears on the
    # token_value field declaration.
    assert "token_value = serializers.CharField(write_only=True)" in text, (
        "PBSEndpointSerializer.token_value must be declared write_only"
    )


def test_serializers_module_defines_one_serializer_per_model():
    text = API_SERIALIZERS.read_text(encoding="utf-8")
    for serializer in ALL_SERIALIZERS:
        assert f"class {serializer}(" in text, f"missing {serializer}"
