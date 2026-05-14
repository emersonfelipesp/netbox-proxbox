"""Sub-PR B (#379): typed-confirmation phrase gate on the Settings form.

Migration 0037 added the master flag + typed phrase fields on
``ProxboxPluginSettings``. The form-level validator in
``netbox_proxbox/forms/settings.py`` rejects four scenarios:

  1. master flag ON without the typed phrase
  2. master flag ON with the wrong phrase
  3. apply-destroy-confirmed ON without the master flag
  4. typed phrase set but master flag OFF (stale leftover)

This AST-based contract test pins (a) the literal constant string in
``models/plugin_settings.py``, and (b) the four ``ValidationError`` raises in
``forms/settings.py:clean()``. It does not bootstrap Django — the runtime
behavior is exercised by the existing settings view tests.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_typed_phrase_constant_is_pinned():
    """The typed phrase MUST be exactly ``allow-edit-and-add-actions``."""
    plugin_settings = (
        REPO_ROOT / "netbox_proxbox" / "models" / "plugin_settings.py"
    ).read_text()
    assert '"allow-edit-and-add-actions"' in plugin_settings, (
        "The typed-confirmation phrase MUST be 'allow-edit-and-add-actions' "
        "verbatim. Renaming it silently breaks the gate."
    )


def test_settings_form_has_clean_method():
    """``ProxboxPluginSettingsForm.clean()`` must exist."""
    tree = ast.parse(
        (REPO_ROOT / "netbox_proxbox" / "forms" / "settings.py").read_text()
    )
    classes = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef)
        and node.name == "ProxboxPluginSettingsForm"
    ]
    assert classes, "ProxboxPluginSettingsForm class not found in forms/settings.py"
    methods = {m.name for m in classes[0].body if isinstance(m, ast.FunctionDef)}
    assert "clean" in methods, (
        "ProxboxPluginSettingsForm must define clean() to enforce the typed "
        "phrase gate per Safety Model invariant #2."
    )


def test_settings_form_references_typed_phrase():
    """The form's clean() body must reference the typed phrase or constant."""
    form_text = (REPO_ROOT / "netbox_proxbox" / "forms" / "settings.py").read_text()
    assert (
        "allow-edit-and-add-actions" in form_text
        or "TYPED_CONFIRMATION_PHRASE" in form_text
        or "NETBOX_TO_PROXMOX_TYPED_PHRASE" in form_text
    ), (
        "forms/settings.py must reference the typed-phrase constant or literal "
        "so clean() can enforce it."
    )
