"""Tests for ``netbox_proxbox.services.backend_path``.

A NetBox device name such as ``../extras`` used to be interpolated directly into
an authenticated proxbox-api URL. URL normalisation collapses the ``..``
segment, so the request reached a different backend route than intended. The
helper must reject hostile values, and every backend URL that embeds a node,
storage, guest type, or VMID must route that value through it.
"""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_PATH = REPO_ROOT / "netbox_proxbox" / "services" / "backend_path.py"


def _load():
    spec = importlib.util.spec_from_file_location(
        "_backend_path_under_test", BACKEND_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


backend_path = _load()


@pytest.mark.parametrize(
    "value",
    [
        "pve1",
        "pve-node-02",
        "node_3",
        "pve1.example.net",
        "PVE01",
        "a",
    ],
)
def test_valid_identifiers_are_accepted_unchanged(value: str) -> None:
    assert backend_path.safe_path_segment(value) == value


@pytest.mark.parametrize(
    "value",
    [
        "",
        "   ",
        None,
        ".",
        "..",
        "../extras",
        "..%2fextras",
        "%2e%2e",
        "pve1/../../auth",
        "a/b",
        "a\\b",
        "pve1?x=1",
        "pve1#frag",
        "pve 1",
        "pve1\r\nX-Injected: 1",
        "pve1\x00",
        "-leading-dash",
        ".hidden",
        "a..b",
        "pvе1",  # Cyrillic "е" lookalike
        "x" * 254,
    ],
)
def test_hostile_identifiers_are_rejected(value: object) -> None:
    with pytest.raises(backend_path.UnsafeBackendPathSegment):
        backend_path.safe_path_segment(value)


def test_unsafe_segment_is_a_value_error() -> None:
    assert issubclass(backend_path.UnsafeBackendPathSegment, ValueError)


@pytest.mark.parametrize("value", ["qemu", "lxc", "QEMU", " lxc "])
def test_vm_type_allow_list(value: str) -> None:
    assert backend_path.safe_vm_type(value) in {"qemu", "lxc"}


@pytest.mark.parametrize("value", ["", "openvz", "qemu/../x", "../qemu", "qemu1", None])
def test_vm_type_rejects_everything_else(value: object) -> None:
    with pytest.raises(backend_path.UnsafeBackendPathSegment):
        backend_path.safe_vm_type(value)


@pytest.mark.parametrize("value", [100, "100", 999999999, " 4242 "])
def test_vmid_accepts_positive_integers(value: object) -> None:
    assert backend_path.safe_vmid(value) == str(int(str(value).strip()))


@pytest.mark.parametrize(
    "value",
    [0, -1, "", "abc", "100/../1", "1e3", "１２３", 1_000_000_000, True, None, 1.5],
)
def test_vmid_rejects_non_positive_or_non_integer(value: object) -> None:
    with pytest.raises(backend_path.UnsafeBackendPathSegment):
        backend_path.safe_vmid(value)


def test_prepared_url_stays_under_proxmox_prefix() -> None:
    requests = pytest.importorskip("requests")
    if not hasattr(requests, "Request"):
        pytest.skip("the mocked suite replaces requests with a stub")
    base = "https://backend.example.test"
    node = backend_path.safe_path_segment("pve1.example.net")
    url = f"{base}/proxmox/{node}/qemu/{backend_path.safe_vmid(100)}/config"

    prepared = requests.Request("GET", url).prepare()

    assert prepared.url == f"{base}/proxmox/pve1.example.net/qemu/100/config"


# --- Every backend URL site must validate its interpolated identifiers. ---

_GUARDED_FILES = (
    "netbox_proxbox/views/vm_config.py",
    "netbox_proxbox/services/sync_vm_template.py",
    "netbox_proxbox/views/storage.py",
    "netbox_proxbox/services/sync_firewall.py",
    "netbox_proxbox/views/operational.py",
    "netbox_proxbox/api/proxmox_tags.py",
    "netbox_proxbox/views/vm_ha.py",
)
_RAW_IDENTIFIER_NAMES = frozenset(
    {"node", "node_name", "storage_name", "vm_type", "proxmox_type", "vmid"}
)


def _raw_identifier_interpolations(path: Path) -> list[str]:
    """Return ``/proxmox/`` f-strings that interpolate a raw identifier name."""
    offenders: list[str] = []
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.JoinedStr):
            continue
        literal = "".join(
            part.value
            for part in node.values
            if isinstance(part, ast.Constant) and isinstance(part.value, str)
        )
        if "/proxmox/" not in literal and "/storage/" not in literal:
            continue
        for part in node.values:
            if (
                isinstance(part, ast.FormattedValue)
                and isinstance(part.value, ast.Name)
                and part.value.id in _RAW_IDENTIFIER_NAMES
            ):
                offenders.append(f"{path.name}:{node.lineno} {{{part.value.id}}}")
    return offenders


@pytest.mark.parametrize("relative", _GUARDED_FILES)
def test_backend_urls_never_interpolate_raw_identifiers(relative: str) -> None:
    path = REPO_ROOT / relative
    source = path.read_text(encoding="utf-8")

    assert "netbox_proxbox.services.backend_path" in source, relative
    assert _raw_identifier_interpolations(path) == []


def test_guard_detects_a_raw_interpolation(tmp_path: Path) -> None:
    """Mutation check: the AST guard must flag the original defect shape."""
    sample = tmp_path / "sample.py"
    sample.write_text(
        'url = f"{base}/proxmox/{node}/{vm_type}/{vmid}/config"\n', encoding="utf-8"
    )

    assert len(_raw_identifier_interpolations(sample)) == 3
