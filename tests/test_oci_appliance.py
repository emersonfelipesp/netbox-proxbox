"""Contracts for the testing-only OCI appliance."""

from pathlib import Path
import re

import pytest
from packaging.version import Version

from scripts import resolve_oci_versions


ROOT = Path(__file__).parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_image_has_proxmox_lxc_init_and_health_contract() -> None:
    dockerfile = _read("Dockerfile.oci")

    assert "RUN ln -s /usr/local/sbin/proxbox-stack-init /sbin/init" in dockerfile
    assert "EXPOSE 8080 8800" in dockerfile
    assert 'CMD ["/usr/local/sbin/proxbox-stack-healthcheck"]' in dockerfile


def test_image_installs_exact_resolved_releases() -> None:
    dockerfile = _read("Dockerfile.oci")

    assert '"netbox-proxbox==${NETBOX_PROXBOX_VERSION}"' in dockerfile
    assert '"proxbox-api==${PROXBOX_API_VERSION}"' in dockerfile
    assert "PROXBOX_API_PYTHON=3.13" in dockerfile


def test_stateful_services_use_declared_volumes() -> None:
    dockerfile = _read("Dockerfile.oci")

    assert "PROXBOX_DATABASE_PATH=/var/lib/proxbox-api/database.db" in dockerfile
    assert 'VOLUME ["/var/lib/postgresql", "/var/lib/redis", ' in dockerfile
    assert '"/var/lib/proxbox-api", "/var/lib/proxbox-stack"]' in dockerfile


def test_plugin_is_enabled_and_targets_embedded_backend() -> None:
    configuration = _read("oci/netbox-configuration.py")
    backend = _read("oci/bin/proxbox-stack-backend")

    assert 'PLUGINS = ["netbox_proxbox"]' in configuration
    assert '"backend_url": "http://127.0.0.1:8800"' in configuration
    assert 'API_TOKEN_PEPPERS = {1: _secret("api-token-pepper"' in configuration
    assert "${PROXBOX_BIND_HOST:-127.0.0.1}" in backend


def test_release_workflow_pins_third_party_actions() -> None:
    workflow = _read(".github/workflows/oci-appliance.yml")
    action_references = re.findall(r"uses: ([^\s]+)@([^\s]+)", workflow)

    assert action_references
    assert all(
        re.fullmatch(r"[0-9a-f]{40}", revision) for _, revision in action_references
    )
    assert "group: oci-appliance-publication" in workflow
    assert "cancel-in-progress: false" in workflow


def test_resolver_skips_prerelease_yanked_and_incompatible_files(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        resolve_oci_versions,
        "_metadata",
        lambda _package: {
            "releases": {
                "1.0.0": [{"yanked": False, "requires_python": ">=3.12"}],
                "1.1.0": [{"yanked": True, "requires_python": ">=3.12"}],
                "1.2.0": [{"yanked": False, "requires_python": ">=3.15"}],
                "2.0.0rc1": [{"yanked": False, "requires_python": ">=3.12"}],
            }
        },
    )

    assert resolve_oci_versions.latest_compatible(
        "example", Version("3.14")
    ) == Version("1.0.0")


def test_resolver_fails_when_no_compatible_stable_artifact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        resolve_oci_versions,
        "_metadata",
        lambda _package: {
            "releases": {
                "1.0.0": [{"yanked": True, "requires_python": ">=3.12"}],
                "2.0.0": [{"yanked": False, "requires_python": ">=3.15"}],
            }
        },
    )

    with pytest.raises(RuntimeError, match="no stable example artifact"):
        resolve_oci_versions.latest_compatible("example", Version("3.14"))
