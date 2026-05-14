"""Cross-repo drift detector for the overwrite_* flag set.

The plugin (`netbox-proxbox`) and the backend (`proxbox-api`) each carry the
same canonical 24-flag list as a single source of truth:

- Plugin: `netbox_proxbox.constants.OVERWRITE_FIELDS`
- Backend: `proxbox_api.schemas.sync.SyncOverwriteFlags.model_fields`

A copy of the canonical names + order is committed to BOTH repos as
`contracts/overwrite_flags.json`. This test asserts that the local source of
truth on this side matches the manifest exactly. The mirror repo runs the same
test against its own source of truth. Any developer who changes flags on
either side must update both manifests; CI on both repos fails otherwise.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load_overwrite_fields() -> tuple[str, ...]:
    """Load `OVERWRITE_FIELDS` from `constants.py` without importing the package.

    The plugin's `__init__.py` requires a live NetBox install, which is not
    available during unit-test collection — bypass it by loading the
    constants module directly from disk.
    """
    spec = importlib.util.spec_from_file_location(
        "_netbox_proxbox_constants_contract",
        REPO_ROOT / "netbox_proxbox" / "constants.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return tuple(module.OVERWRITE_FIELDS)


def _load_manifest_fields() -> tuple[str, ...]:
    manifest_path = REPO_ROOT / "contracts" / "overwrite_flags.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    fields = payload["fields"]
    assert isinstance(fields, list) and all(isinstance(name, str) for name in fields)
    return tuple(fields)


def test_manifest_matches_constants_overwrite_fields() -> None:
    """Plugin source of truth must match the committed cross-repo manifest."""
    manifest_fields = _load_manifest_fields()
    constants_fields = _load_overwrite_fields()
    assert constants_fields == manifest_fields, (
        "OVERWRITE_FIELDS drifted from contracts/overwrite_flags.json. Update "
        "BOTH repo manifests (netbox-proxbox and proxbox-api) when changing flags."
    )


def test_manifest_field_count_is_canonical_24() -> None:
    """Sanity check: any change to flag count is intentional and reviewed."""
    manifest_fields = _load_manifest_fields()
    assert len(manifest_fields) == 24


def test_manifest_has_no_duplicate_fields() -> None:
    manifest_fields = _load_manifest_fields()
    assert len(manifest_fields) == len(set(manifest_fields))
