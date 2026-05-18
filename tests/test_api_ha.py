"""Source-contract tests for the HA REST shim under `netbox_proxbox.api.ha`.

Pins the two `APIView` classes, the URL registration in
`netbox_proxbox/api/urls.py`, and the proxbox-api endpoints they call.
The tests parse the relevant modules with ``ast`` so they run without
loading Django or NetBox.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
HA_API_PATH = REPO_ROOT / "netbox_proxbox" / "api" / "ha.py"
URLS_PATH = REPO_ROOT / "netbox_proxbox" / "api" / "urls.py"
ROOT_VIEW_PATH = REPO_ROOT / "netbox_proxbox" / "api" / "views.py"


def _find_class(module: ast.Module, name: str) -> ast.ClassDef:
    for node in ast.walk(module):
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    raise AssertionError(f"class {name} not found")


def test_ha_api_module_exposes_two_apiviews() -> None:
    module = ast.parse(HA_API_PATH.read_text(encoding="utf-8"))
    summary = _find_class(module, "HAClusterSummaryAPIView")
    vm = _find_class(module, "HAVMResourceAPIView")
    base_names = {
        b.attr if isinstance(b, ast.Attribute) else getattr(b, "id", "")
        for b in summary.bases
    } | {
        b.attr if isinstance(b, ast.Attribute) else getattr(b, "id", "")
        for b in vm.bases
    }
    assert "APIView" in base_names


def test_ha_api_calls_expected_proxbox_endpoints() -> None:
    source = HA_API_PATH.read_text(encoding="utf-8")
    assert "/proxmox/cluster/ha/summary" in source
    assert "/proxmox/cluster/ha/resources/by-vm/" in source
    assert "get_fastapi_request_context" in source
    assert "translate_request_exception" in source


def test_ha_api_translates_upstream_404_to_503() -> None:
    """Match the user-facing copy used by the HTML views in views/ha.py."""
    source = HA_API_PATH.read_text(encoding="utf-8")
    assert "upgrade proxbox-api to v0.0.12 or later" in source
    assert "HTTP_503_SERVICE_UNAVAILABLE" in source


def test_urls_register_ha_routes() -> None:
    source = URLS_PATH.read_text(encoding="utf-8")
    assert 'path("ha/summary/"' in source
    assert "HAClusterSummaryAPIView" in source
    assert 'name="api-ha-summary"' in source
    assert "ha/vm/<int:vmid>/" in source
    assert "HAVMResourceAPIView" in source
    assert 'name="api-ha-vm-resource"' in source


def test_root_view_advertises_ha_endpoints() -> None:
    source = ROOT_VIEW_PATH.read_text(encoding="utf-8")
    assert '"ha"' in source
    assert '"summary": f"{base}/ha/summary/"' in source
    assert '"vm": f"{base}/ha/vm/"' in source
