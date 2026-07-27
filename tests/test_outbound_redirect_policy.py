"""Structural guard: no plugin HTTP call may follow redirects.

Following a redirect replays request headers — including ``X-Proxbox-API-Key``
and, on push paths, request bodies carrying downstream credentials — to
whatever origin the response names, including a plaintext-HTTP downgrade of the
original host. The remediated proxy paths refuse redirects explicitly, but the
plugin has dozens of other direct ``requests`` call sites, and a single new one
written with the library default (``allow_redirects=True``) silently reopens
the exfiltration class.

This test therefore scans **every** module under ``netbox_proxbox/`` with
``ast`` and requires each ``requests.<verb>()`` call to pass
``allow_redirects=False`` as a literal. Two deliberate exceptions:

* ``github.py`` — unauthenticated fetches of public GitHub content, where
  redirects are legitimate and no credential is attached.
* ``services/http_client.py`` — the shared client wrapper forwards its own
  ``allow_redirects`` parameter (which defaults to ``False`` and whose
  responses are checked by ``_checked_response``); the keyword must still be
  present on every underlying call.
"""

from __future__ import annotations

import ast
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1] / "netbox_proxbox"

HTTP_VERBS = {"get", "post", "put", "delete", "patch", "head", "options"}
REQUESTS_MODULE_ALIASES = {"requests", "http_requests"}

# Unauthenticated public-content fetches where redirects are expected.
ALLOWLISTED_FILES = {PLUGIN_ROOT / "github.py"}

# The wrapper forwards its own (default-False) parameter; keyword presence is
# still mandatory so a call can never fall back to the library default.
FORWARDING_FILES = {PLUGIN_ROOT / "services" / "http_client.py"}


def _requests_calls(tree: ast.AST):
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not isinstance(func, ast.Attribute) or func.attr not in HTTP_VERBS:
            continue
        if not isinstance(func.value, ast.Name):
            continue
        if func.value.id not in REQUESTS_MODULE_ALIASES:
            continue
        yield node


def _violations() -> list[str]:
    problems: list[str] = []
    for path in sorted(PLUGIN_ROOT.rglob("*.py")):
        if path in ALLOWLISTED_FILES:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for call in _requests_calls(tree):
            keyword = next(
                (kw for kw in call.keywords if kw.arg == "allow_redirects"),
                None,
            )
            location = f"{path.relative_to(PLUGIN_ROOT.parent)}:{call.lineno}"
            if keyword is None:
                problems.append(
                    f"{location} requests.{call.func.attr}() has no "
                    "allow_redirects=False (library default follows redirects "
                    "and replays credentialed headers)"
                )
                continue
            if path in FORWARDING_FILES:
                continue
            value = keyword.value
            if not (isinstance(value, ast.Constant) and value.value is False):
                problems.append(
                    f"{location} requests.{call.func.attr}() must pass the "
                    "literal allow_redirects=False"
                )
    return problems


def test_every_plugin_requests_call_refuses_redirects():
    problems = _violations()
    assert not problems, "\n".join(problems)


def test_the_scan_actually_sees_the_plugin_call_sites():
    """Guard the guard: an empty scan would pass vacuously."""
    seen = 0
    for path in sorted(PLUGIN_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        seen += sum(1 for _ in _requests_calls(tree))
    # The plugin has dozens of direct call sites; a collapse to near-zero
    # means the detection predicate no longer matches how requests is used.
    assert seen >= 40, f"only {seen} requests call sites detected"
