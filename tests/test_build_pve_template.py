"""Static contracts for the build-pve-template REST action on ProxmoxEndpoint."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_pve_template_serializer_module_exists() -> None:
    module = ROOT / "netbox_proxbox/api/serializers/pve_template.py"
    src = module.read_text()
    for token in (
        "PVETemplateBuildRequestSerializer",
        "PVETemplateBuildResponseSerializer",
        "vmid",
        "target_node",
        "pve_version_pin",
        "ssh_authorized_keys",
        "create_vm",
    ):
        assert token in src, f"missing token in pve_template.py serializer: {token!r}"


def test_pve_template_serializer_exported() -> None:
    init = (ROOT / "netbox_proxbox/api/serializers/__init__.py").read_text()
    assert "PVETemplateBuildRequestSerializer" in init
    assert "PVETemplateBuildResponseSerializer" in init


def test_build_pve_template_action_registered_on_viewset() -> None:
    views = (ROOT / "netbox_proxbox/api/views.py").read_text()
    for token in (
        'url_path="build-pve-template"',
        'url_path="cloud-image-build-pipeline"',
        "PVETemplateBuildRequestSerializer",
        "build_cloud_image_pipeline_via_backend",
        "build_pve_template_via_backend",
        '"endpoint_id"',
    ):
        assert token in views, f"missing token in api/views.py: {token!r}"


def test_build_pve_template_backend_helper_targets_correct_path() -> None:
    helper = (ROOT / "netbox_proxbox/api/build_pve_template.py").read_text()
    assert "/cloud/templates/images" in helper
    assert "get_fastapi_request_context" in helper
    assert "requests.post" in helper
    assert "build_pve_template_via_backend" in helper


def test_cloud_image_build_pipeline_serializer_supports_firewall_products() -> None:
    serializer = (ROOT / "netbox_proxbox/api/serializers/pve_template.py").read_text()
    assert "pfsense" in serializer
    assert "opnsense" in serializer
    assert "release_image" in serializer
    assert "source_tree" in serializer
