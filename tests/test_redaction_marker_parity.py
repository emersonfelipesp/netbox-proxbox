"""The public scrubber must be at least as strict as the internal one.

``views/error_utils.py`` redacts credentials on their way into the **job log**;
``netbox_proxbox/anonymize.py`` redacts them on their way into a **public issue
tracker**. The second audience is strictly less trusted, so any field name the
first one treats as a credential must also be redacted by the second.

The two cannot share code today: reaching ``error_utils`` executes
``netbox_proxbox.views.__init__``, which needs Django, while ``anonymize`` is
deliberately importable without it (``tests/test_bug_report.py`` relies on
that). ``error_utils`` itself is pure, so consolidating them is tracked as
follow-up work; until then this test is what stops the two vocabularies from
drifting apart.

The check is **behavioural**, not a string comparison: markers are read out of
``error_utils`` and then actually pushed through ``anonymize``. Comparing two
literal lists would pass while the regex that consumes them was broken.
"""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
import sys

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_SECRET = "s3cr3tcanaryvalue"


def _load_anonymize():
    path = _ROOT / "netbox_proxbox" / "anonymize.py"
    spec = importlib.util.spec_from_file_location("netbox_proxbox.anonymize", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules["netbox_proxbox.anonymize"] = module
    spec.loader.exec_module(module)
    return module


def _error_utils_markers() -> tuple[str, ...]:
    """Read ``_SENSITIVE_KEY_MARKERS`` out of error_utils without importing it.

    Importing would pull in ``netbox_proxbox.views.__init__`` and therefore
    Django, which the mocked suite does not have.
    """
    source = (_ROOT / "netbox_proxbox" / "views" / "error_utils.py").read_text()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        targets = []
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        for target in targets:
            if isinstance(target, ast.Name) and target.id == "_SENSITIVE_KEY_MARKERS":
                return tuple(ast.literal_eval(node.value))
    pytest.fail("error_utils no longer defines _SENSITIVE_KEY_MARKERS")


def test_markers_were_actually_found():
    """Guard the guard: an empty marker list would make the sweep vacuous."""
    markers = _error_utils_markers()
    assert len(markers) >= 8, markers
    assert "token" in markers
    assert "password" in markers


@pytest.mark.parametrize("marker", _error_utils_markers())
def test_every_internal_marker_is_redacted_publicly(marker):
    """A key the job-log redactor treats as secret must not reach GitHub."""
    scrub = _load_anonymize().Anonymizer().scrub
    for line in (f"{marker}={_SECRET}", f"{marker}: {_SECRET}"):
        assert _SECRET not in scrub(line), f"{marker!r} survives as {line!r}"


@pytest.mark.parametrize(
    "field",
    [
        # Field and setting names that belong to this plugin specifically. They
        # are not in error_utils' generic list, so nothing else pins them.
        "token_value",
        "token_secret",
        "encryption_key",
        "proxbox_api_key",
        "passphrase",
        "auth",
        "session",
        "host_key",
    ],
)
def test_plugin_specific_credential_fields_are_redacted(field):
    scrub = _load_anonymize().Anonymizer().scrub
    assert _SECRET not in scrub(f"{field}={_SECRET}")
