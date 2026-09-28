"""Source contracts for large multi-cluster tuning documentation."""

from __future__ import annotations

import ast
import re
from decimal import Decimal
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]

GUIDE_PATH = "docs/configuration/large-multi-cluster-deployments.md"
PLUGIN_SETTINGS_PATH = "docs/configuration/plugin-settings.md"
PLUGIN_SETTINGS_MODEL_PATH = "netbox_proxbox/models/plugin_settings.py"

# Backend env vars referenced by the tuning guide and plugin-settings tables.
TUNING_BACKEND_ENV_ALLOWLIST = frozenset(
    {
        "PROXBOX_NETBOX_TIMEOUT",
        "PROXBOX_NETBOX_MAX_RETRIES",
        "PROXBOX_NETBOX_RETRY_DELAY",
        "PROXBOX_NETBOX_MAX_CONCURRENT",
        "PROXBOX_NETBOX_WRITE_CONCURRENCY",
        "PROXBOX_FETCH_MAX_CONCURRENCY",
        "PROXBOX_PROXMOX_FETCH_CONCURRENCY",
        "PROXBOX_VM_SYNC_MAX_CONCURRENCY",
        "PROXBOX_BULK_BATCH_SIZE",
        "PROXBOX_BULK_BATCH_DELAY_MS",
        "PROXBOX_BACKUP_BATCH_SIZE",
        "PROXBOX_BACKUP_BATCH_DELAY_MS",
        "PROXBOX_INTERFACE_BATCH_SIZE",
        "PROXBOX_INTERFACE_BATCH_DELAY_MS",
        "PROXBOX_GUEST_AGENT_TIMEOUT",
        "PROXBOX_NODE_DEVICE_NAME_TEMPLATE",
        "PROXBOX_RATE_LIMIT",
    }
)

# Other proxbox-api env vars documented in plugin-settings.md outside the guide.
PLUGIN_SETTINGS_EXTRA_BACKEND_ENV = frozenset(
    {
        "PROXBOX_DELETE_ORPHANS",
        "PROXBOX_NETBOX_GET_CACHE_TTL",
        "PROXBOX_NETBOX_GET_CACHE_MAX_ENTRIES",
        "PROXBOX_NETBOX_GET_CACHE_MAX_BYTES",
        "PROXBOX_DEBUG_CACHE",
        "PROXBOX_EXPOSE_INTERNAL_ERRORS",
        "PROXBOX_NETBOX_OPENAPI_PERSIST",
        "PROXBOX_CEPH_TASK_TIMEOUT",
        "PROXBOX_CEPH_TASK_POLL_INTERVAL",
        "PROXBOX_CEPH_RUN_LEASE_SECONDS",
        "PROXBOX_ENCRYPTION_KEY",
    }
)

DOCUMENTED_BACKEND_ENV_ALLOWLIST = (
    TUNING_BACKEND_ENV_ALLOWLIST | PLUGIN_SETTINGS_EXTRA_BACKEND_ENV
)

GUIDE_DEFAULT_FIELDS = frozenset(
    {
        "proxmox_timeout",
        "proxmox_max_retries",
        "proxmox_retry_backoff",
        "netbox_timeout",
        "netbox_max_retries",
        "netbox_retry_delay",
        "netbox_max_concurrent",
        "netbox_write_concurrency",
        "proxbox_fetch_max_concurrency",
        "proxmox_fetch_concurrency",
        "vm_sync_max_concurrency",
        "bulk_batch_size",
        "bulk_batch_delay_ms",
        "backup_batch_size",
        "backup_batch_delay_ms",
        "interface_batch_size",
        "interface_batch_delay_ms",
    }
)

_PROXBOX_ENV_TOKEN_RE = re.compile(r"PROXBOX_[A-Z0-9_]+")
_GUIDE_TABLE_ROW_RE = re.compile(
    r"^\|\s*`([a-z_]+)`\s*\|\s*`([^`]+)`",
)


def _read(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def _eval_default_literal(node: ast.AST) -> int | float | bool | str | None:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        if node.func.id == "Decimal" and node.args:
            inner = _eval_default_literal(node.args[0])
            if isinstance(inner, str):
                return float(inner)
            if isinstance(inner, (int, float)):
                return float(inner)
    try:
        value = ast.literal_eval(node)
    except (ValueError, SyntaxError, TypeError):
        return None
    if isinstance(value, Decimal):
        return float(value)
    return value


def _plugin_settings_model_defaults() -> dict[str, int | float | bool | str]:
    source = _read(PLUGIN_SETTINGS_MODEL_PATH)
    tree = ast.parse(source, filename=PLUGIN_SETTINGS_MODEL_PATH)
    defaults: dict[str, int | float | bool | str] = {}
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name != "ProxboxPluginSettings":
            continue
        for stmt in node.body:
            if not isinstance(stmt, ast.Assign):
                continue
            if len(stmt.targets) != 1 or not isinstance(stmt.targets[0], ast.Name):
                continue
            field_name = stmt.targets[0].id
            if not isinstance(stmt.value, ast.Call):
                continue
            for keyword in stmt.value.keywords:
                if keyword.arg != "default":
                    continue
                default_value = _eval_default_literal(keyword.value)
                if default_value is not None and isinstance(
                    default_value, (int, float, bool, str)
                ):
                    defaults[field_name] = default_value
    return defaults


def _guide_reference_section(guide_text: str) -> str:
    marker = "## Recommended starting profile"
    if marker in guide_text:
        return guide_text.split(marker, maxsplit=1)[0]
    return guide_text


def _parse_guide_table_defaults(guide_text: str) -> dict[str, float]:
    documented: dict[str, float] = {}
    for line in _guide_reference_section(guide_text).splitlines():
        match = _GUIDE_TABLE_ROW_RE.match(line)
        if not match:
            continue
        field_name, raw_default = match.groups()
        if field_name not in GUIDE_DEFAULT_FIELDS:
            continue
        numeric = re.match(r"^([0-9]+(?:\.[0-9]+)?)", raw_default.strip())
        if not numeric:
            continue
        documented[field_name] = float(numeric.group(1))
    return documented


def _proxbox_env_tokens(text: str) -> set[str]:
    return set(_PROXBOX_ENV_TOKEN_RE.findall(text))


def _numeric_equal(model_value: int | float | bool | str, documented: float) -> bool:
    if isinstance(model_value, bool):
        return False
    if isinstance(model_value, str):
        return False
    return float(model_value) == documented


def test_custom_fields_request_delay_marked_compatibility_only():
    model = _read(PLUGIN_SETTINGS_MODEL_PATH)
    form = _read("netbox_proxbox/forms/settings.py")
    migration = _read(
        "netbox_proxbox/migrations/0103_custom_fields_request_delay_help_text.py"
    )
    plugin_docs = _read(PLUGIN_SETTINGS_PATH)

    assert "has no effect on sync behavior" in model
    assert "has no effect" in form
    assert "custom_fields_request_delay" in migration
    assert "Compatibility only" in plugin_docs
    assert "PROXBOX_CUSTOM_FIELDS_REQUEST_DELAY" not in plugin_docs


def test_custom_fields_request_delay_env_not_documented_under_docs():
    docs_root = REPO_ROOT / "docs"
    text_suffixes = {".md", ".markdown", ".rst", ".txt", ".adoc"}
    for path in docs_root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in text_suffixes:
            continue
        text = path.read_text(encoding="utf-8")
        assert "PROXBOX_CUSTOM_FIELDS_REQUEST_DELAY" not in text, (
            f"docs must not advertise a nonexistent env override: {path.relative_to(REPO_ROOT)}"
        )


def test_large_multi_cluster_guide_linked_in_nav_and_configuration_index():
    mkdocs = _read("mkdocs.yml")
    index = _read("docs/configuration/index.md")
    guide = _read(GUIDE_PATH)

    assert "configuration/large-multi-cluster-deployments.md" in mkdocs, (
        "mkdocs nav must include the tuning guide"
    )
    assert "large-multi-cluster-deployments.md" in index
    assert "PROXBOX_RATE_LIMIT" in guide
    assert "3000" in guide


def test_guide_table_defaults_match_plugin_settings_model():
    guide = _read(GUIDE_PATH)
    model_defaults = _plugin_settings_model_defaults()
    guide_defaults = _parse_guide_table_defaults(guide)

    assert guide_defaults, "expected at least one numeric default row in the guide"
    missing_from_model = set(guide_defaults) - set(model_defaults)
    assert not missing_from_model, (
        f"guide documents fields without model defaults: {sorted(missing_from_model)}"
    )

    mismatches: list[str] = []
    for field_name, documented in sorted(guide_defaults.items()):
        model_value = model_defaults[field_name]
        if not _numeric_equal(model_value, documented):
            mismatches.append(f"{field_name}: guide={documented} model={model_value}")
    assert not mismatches, (
        "documented defaults diverge from ProxboxPluginSettings:\n"
        + "\n".join(mismatches)
    )


def test_backend_env_tokens_in_allowlist():
    guide_tokens = _proxbox_env_tokens(_read(GUIDE_PATH))
    plugin_settings_tokens = _proxbox_env_tokens(_read(PLUGIN_SETTINGS_PATH))

    assert guide_tokens <= TUNING_BACKEND_ENV_ALLOWLIST, (
        f"guide mentions unexpected backend env vars: {sorted(guide_tokens - TUNING_BACKEND_ENV_ALLOWLIST)}"
    )
    assert plugin_settings_tokens <= DOCUMENTED_BACKEND_ENV_ALLOWLIST, (
        "plugin-settings mentions unexpected backend env vars: "
        f"{sorted(plugin_settings_tokens - DOCUMENTED_BACKEND_ENV_ALLOWLIST)}"
    )


def test_llms_pointer_keeps_fan_out_qualification():
    llms = (REPO_ROOT / "llms.txt").read_text()
    pointer = next(
        line
        for line in llms.splitlines()
        if "large-multi-cluster-deployments.md" in line
    )
    assert "most sync stages" in pointer
    assert "fan out" in pointer
