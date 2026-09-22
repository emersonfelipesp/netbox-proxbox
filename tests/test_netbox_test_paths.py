from pathlib import Path

from tests.netbox_test_paths import netbox_source_roots


def test_netbox_source_roots_prefers_explicit_configuration(
    monkeypatch, tmp_path: Path
) -> None:
    configured = tmp_path / "configured-netbox"
    monkeypatch.setenv("NETBOX_SOURCE_ROOT", str(configured))
    assert netbox_source_roots(tmp_path / "plugin") == (
        configured,
        tmp_path / "netbox" / "netbox",
    )


def test_netbox_source_roots_uses_ordinary_sibling_without_configuration(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("NETBOX_SOURCE_ROOT", raising=False)
    assert netbox_source_roots(tmp_path / "plugin") == (tmp_path / "netbox" / "netbox",)
