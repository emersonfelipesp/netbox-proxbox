"""Tests for the intent-direction ``netbox-metadata`` writer (#423).

The plugin-side mirror of ``proxbox_api.proxmox_to_netbox.description_metadata``:
when ``ProxboxPluginSettings.embed_description_metadata`` is on, intent payload
builders append a fenced ``netbox-metadata`` JSON block of NetBox FK ids to the
Proxmox description so a reflection sync with ``parse_description_metadata=True``
round-trips without drift.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import re
from pathlib import Path
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[1]
HELPER_PATH = REPO_ROOT / "netbox_proxbox" / "intent" / "description_metadata.py"
PAYLOAD_PATH = REPO_ROOT / "netbox_proxbox" / "intent" / "payload.py"


def _load_helper_module():
    """Load ``description_metadata.py`` without triggering ``netbox_proxbox/__init__.py``.

    The package ``__init__`` imports Django/NetBox primitives that aren't
    available in this lightweight test environment. The helper module itself
    only uses ``json``/``re``/``typing`` so it can be loaded directly.
    """
    spec = importlib.util.spec_from_file_location("_desc_md_under_test", HELPER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_HELPER = _load_helper_module()
build_description_with_metadata = _HELPER.build_description_with_metadata
collect_netbox_metadata = _HELPER.collect_netbox_metadata
embed_netbox_metadata = _HELPER.embed_netbox_metadata
render_netbox_metadata_block = _HELPER.render_netbox_metadata_block
strip_netbox_metadata = _HELPER.strip_netbox_metadata


def _vm(**relations):
    """Build a fake VM whose FK chains return ``relations[name].id``."""
    return SimpleNamespace(
        **{
            name: SimpleNamespace(id=value) if value is not None else None
            for name, value in relations.items()
        }
    )


def test_collect_returns_present_pk_ids_only():
    vm = _vm(role=1, tenant=13, site=None, platform=2, cluster=7, device=12)
    assert collect_netbox_metadata(vm) == {
        "role": 1,
        "tenant": 13,
        "platform": 2,
        "cluster": 7,
        "device": 12,
    }


def test_collect_drops_non_positive_and_non_integer_ids():
    vm = SimpleNamespace(
        role=SimpleNamespace(id=0),
        tenant=SimpleNamespace(id=-3),
        site=SimpleNamespace(id="13"),
        platform=SimpleNamespace(id=True),  # bool rejected by int check
        cluster=SimpleNamespace(id=7),
        device=None,
    )
    assert collect_netbox_metadata(vm) == {"cluster": 7}


def test_collect_returns_empty_dict_when_no_relations():
    vm = SimpleNamespace(role=None, tenant=None, site=None)
    assert collect_netbox_metadata(vm) == {}


def test_render_emits_canonical_fenced_block():
    block = render_netbox_metadata_block({"tenant": 13, "role": 1})
    assert block is not None
    # Sorted keys + fenced wrapper => byte-identical for equal PK sets.
    assert block == '```netbox-metadata\n{\n  "role": 1,\n  "tenant": 13\n}\n```'


def test_render_empty_metadata_returns_none():
    assert render_netbox_metadata_block({}) is None


def test_strip_removes_block_and_collapses_empty_to_none():
    text = '```netbox-metadata\n{"role": 1}\n```'
    assert strip_netbox_metadata(text) is None


def test_strip_preserves_operator_prose():
    text = 'Production database VM.\n\n```netbox-metadata\n{"role": 1}\n```\n'
    assert strip_netbox_metadata(text) == "Production database VM."


def test_strip_ignores_plain_text_netbox_role_lines():
    # The fenced block is the only thing that matches; loose
    # ``netbox-role:`` prose stays untouched.
    text = "netbox-role: webserver (legacy convention)"
    assert strip_netbox_metadata(text) == text


def test_embed_appends_block_after_blank_line():
    out = embed_netbox_metadata(
        "Production database VM.",
        '```netbox-metadata\n{"role": 1}\n```',
    )
    assert out == ('Production database VM.\n\n```netbox-metadata\n{"role": 1}\n```')


def test_embed_strips_pre_existing_block_before_appending():
    description = 'Production database VM.\n\n```netbox-metadata\n{"role": 99}\n```'
    new_block = '```netbox-metadata\n{"role": 1}\n```'
    out = embed_netbox_metadata(description, new_block)
    assert out == "Production database VM.\n\n" + new_block
    # And the result has exactly one fenced block.
    assert out.count("```netbox-metadata") == 1


def test_embed_returns_block_alone_when_description_empty():
    block = '```netbox-metadata\n{"role": 1}\n```'
    assert embed_netbox_metadata(None, block) == block
    assert embed_netbox_metadata("", block) == block


def test_embed_returns_stripped_description_when_block_is_none():
    assert (
        embed_netbox_metadata(
            'prose\n\n```netbox-metadata\n{"role": 1}\n```',
            None,
        )
        == "prose"
    )


def test_build_description_with_metadata_round_trip_is_idempotent():
    vm = _vm(role=1, tenant=13)
    once = build_description_with_metadata(vm, "Production VM.")
    twice = build_description_with_metadata(vm, once)
    assert once == twice
    assert once is not None and once.count("```netbox-metadata") == 1


def test_build_description_with_metadata_emits_parser_compatible_block():
    """The block emitted here must parse back via the proxbox-api regex."""
    vm = _vm(role=1, tenant=13, site=4)
    description = build_description_with_metadata(vm, "Prod VM.")
    assert description is not None
    fence_re = re.compile(
        r"^[ \t]*```[ \t]*netbox-metadata[ \t]*\r?\n(?P<body>.*?)\r?\n[ \t]*```[ \t]*$",
        re.IGNORECASE | re.DOTALL | re.MULTILINE,
    )
    match = fence_re.search(description)
    assert match is not None, "emitted block must match the parser regex"
    payload = json.loads(match.group("body"))
    assert payload == {"role": 1, "tenant": 13, "site": 4}


def test_build_description_returns_plain_text_when_no_pks():
    vm = SimpleNamespace(description=None)
    assert build_description_with_metadata(vm, "prose") == "prose"
    assert build_description_with_metadata(vm, None) is None


# --- Source-level contract tests for payload.py wiring ---


def _parse_payload() -> ast.Module:
    return ast.parse(PAYLOAD_PATH.read_text(encoding="utf-8"))


def test_payload_imports_description_metadata_helper():
    module = _parse_payload()
    found = False
    for node in ast.walk(module):
        if (
            isinstance(node, ast.ImportFrom)
            and node.module == "netbox_proxbox.intent.description_metadata"
        ):
            found = found or any(
                alias.name == "build_description_with_metadata" for alias in node.names
            )
    assert found, (
        "payload.py must import build_description_with_metadata from "
        "netbox_proxbox.intent.description_metadata"
    )


def test_payload_resolves_description_through_helper():
    text = PAYLOAD_PATH.read_text(encoding="utf-8")
    # Both payload builders use ``_resolve_description(vm)`` for the
    # description field; raw ``getattr(vm, "description", ...)`` would skip
    # the embedding gate.
    assert text.count('"description": _resolve_description(vm)') >= 2
    assert "_embed_description_metadata_setting" in text


def test_resolve_description_calls_helper_when_gate_is_on():
    """AST contract: ``_resolve_description`` must consult the gate setting
    and dispatch to ``build_description_with_metadata`` when enabled,
    otherwise return the plain text. This prevents the embedding from being
    accidentally bypassed or always-on without a test catching it.
    """
    module = _parse_payload()
    func = None
    for node in module.body:
        if isinstance(node, ast.FunctionDef) and node.name == "_resolve_description":
            func = node
            break
    assert func is not None, "payload.py must define _resolve_description"

    called_names = {
        node.func.id
        for node in ast.walk(func)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "_embed_description_metadata_setting" in called_names, (
        "_resolve_description must consult the embed gate"
    )
    assert "build_description_with_metadata" in called_names, (
        "_resolve_description must dispatch to build_description_with_metadata "
        "when the gate is on"
    )
