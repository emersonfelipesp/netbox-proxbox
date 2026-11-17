"""Contract tests for the ``X-Proxbox-Actor`` header value encoding."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from urllib.parse import unquote

import pytest

_MODULE_PATH = (
    Path(__file__).resolve().parents[1] / "netbox_proxbox" / "utils" / "actor_header.py"
)
_SPEC = importlib.util.spec_from_file_location("actor_header_under_test", _MODULE_PATH)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)
header_safe_actor = _MODULE.header_safe_actor


def _decode(value: str) -> str:
    """Decode the way a receiver must: only values that contain ``%``."""
    return unquote(value) if "%" in value else value


@pytest.mark.parametrize("username", ["admin", "ops.team@example.org", "josé.ops"])
def test_printable_latin1_names_are_sent_unchanged(username: str) -> None:
    assert header_safe_actor(username) == username


@pytest.mark.parametrize(
    "username",
    [
        "用户",
        "%E7%94%A8%E6%88%B7",
        "100%",
        "line\r\nbreak",
        "tab\tname",
        "ops\x7f",
        "\u00a0ops",
        "ops\u00a0",
        " ops",
        "ops ",
    ],
)
def test_other_names_are_encoded_header_safe_and_reversible(username: str) -> None:
    encoded = header_safe_actor(username)

    assert "%" in encoded
    assert encoded.isascii()
    assert "\r" not in encoded and "\n" not in encoded
    encoded.encode("latin-1")
    assert _decode(encoded) == username


def test_encoded_and_raw_names_never_collide() -> None:
    assert header_safe_actor("用户") != header_safe_actor("%E7%94%A8%E6%88%B7")


@pytest.mark.parametrize(
    "username",
    ["admin", "josé.ops", "first last", "用户", "\u00a0ops", " ops", "ops ", "100%"],
)
def test_real_http_client_accepts_every_encoded_actor(username: str) -> None:
    """The value must survive request preparation in the client the plugin uses."""
    requests = pytest.importorskip("requests")
    if not hasattr(requests, "Request"):
        pytest.skip("requests is stubbed in this environment")

    prepared = requests.Request(
        "POST",
        "https://backend.example/proxmox/cluster/ha/arm",
        headers={"X-Proxbox-Actor": header_safe_actor(username)},
    ).prepare()

    assert _decode(prepared.headers["X-Proxbox-Actor"]) == username
