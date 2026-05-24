"""Source contracts for Firecracker Cloud inventory support."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text()


def test_firecracker_models_are_separate_from_proxmox_vm_type_choices():
    models_src = _read("netbox_proxbox/models/firecracker.py")
    choices_src = _read("netbox_proxbox/choices.py")

    assert "class FirecrackerHostPool(NetBoxModel)" in models_src
    assert "class FirecrackerHost(NetBoxModel)" in models_src
    assert "class FirecrackerImageTemplate(NetBoxModel)" in models_src
    assert "class FirecrackerMicroVM(NetBoxModel)" in models_src
    assert "provision_firecracker_microvm" in models_src
    assert 'return f"firecracker:{self.pk}"' in models_src

    proxmox_vm_choices = choices_src.split("class ProxmoxVMTypeChoices", 1)[1]
    assert "FIRECRACKER" not in proxmox_vm_choices
    assert 'QEMU = "qemu"' in proxmox_vm_choices
    assert 'LXC = "lxc"' in proxmox_vm_choices


def test_firecracker_migration_creates_inventory_tables():
    migration_src = _read("netbox_proxbox/migrations/0041_firecracker_cloud.py")

    for model_name in (
        "FirecrackerHostPool",
        "FirecrackerHost",
        "FirecrackerImageTemplate",
        "FirecrackerMicroVM",
    ):
        assert f'name="{model_name}"' in migration_src

    assert "kernel_image_sha256" in migration_src
    assert "rootfs_image_sha256" in migration_src
    assert "agent_token_enc" in migration_src
    assert "provision_firecracker_microvm" in migration_src


def test_firecracker_api_surface_is_registered():
    urls_src = _read("netbox_proxbox/api/urls.py")
    views_src = _read("netbox_proxbox/api/views.py")
    serializers_src = _read("netbox_proxbox/api/serializers/firecracker.py")
    filtersets_src = _read("netbox_proxbox/filtersets.py")

    for route in (
        "firecracker-host-pools",
        "firecracker-hosts",
        "firecracker-image-templates",
        "firecracker-microvms",
        "resources/firecracker-microvms/",
    ):
        assert route in urls_src

    assert "FirecrackerMicroVMsAPIView" in views_src
    assert "instance_ref" in views_src
    assert '"kind": "firecracker"' in views_src
    assert "FirecrackerMicroVMSerializer" in serializers_src
    assert "token_configured" in serializers_src
    assert "FirecrackerMicroVMFilterSet" in filtersets_src
