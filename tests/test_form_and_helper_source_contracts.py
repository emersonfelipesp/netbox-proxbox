from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text()


def test_forms_do_not_depend_on_super_clean_return_value():
    forms_dir = REPO_ROOT / "netbox_proxbox" / "forms"

    for path in forms_dir.glob("*.py"):
        contents = path.read_text()
        assert "= super().clean()" not in contents, (
            f"Unsafe clean() assignment in {path.name}"
        )


def test_netbox_endpoint_form_reads_from_self_cleaned_data():
    contents = _read("netbox_proxbox/forms/netbox.py")
    assert "super().clean()" in contents
    assert "cleaned_data = self.cleaned_data" in contents


def test_runtime_code_does_not_chain_get_fastapi_url_dict_access():
    plugin_dir = REPO_ROOT / "netbox_proxbox"
    chained_get_pattern = re.compile(r"get_fastapi_url\([^\n]*\)\.get\(")

    for path in plugin_dir.rglob("*.py"):
        contents = path.read_text()
        assert not chained_get_pattern.search(contents), (
            f"Chained get_fastapi_url(...).get(...) found in {path}"
        )


def test_runtime_code_validates_fastapi_url_helper_payload_shape():
    runtime_files = [
        "netbox_proxbox/views/__init__.py",
        "netbox_proxbox/views/cards.py",
        "netbox_proxbox/views/keepalive_status.py",
        "netbox_proxbox/views/sync.py",
        "netbox_proxbox/websocket_client.py",
    ]

    for path in runtime_files:
        contents = _read(path)
        assert "or {}" in contents, (
            f"Expected defensive default for helper payload in {path}"
        )
        assert "isinstance(" in contents, (
            f"Expected type check for helper payload in {path}"
        )
