"""Declarative bridge v1 manifest for semantic Proxbox API operations."""

from __future__ import annotations

from typing import Any

SYNC_TYPE_VALUES = [
    "virtual-machines",
    "storage",
    "vm-disks",
    "vm-backups",
    "vm-snapshots",
    "devices",
    "network-interfaces",
    "vm-interfaces",
    "ip-addresses",
    "sdn",
    "backup-routines",
    "replications",
    "task-history",
]

INTERVAL_UNIT_VALUES = ["minutes", "hours", "days", "weeks"]
MAX_POSITIVE_SIGNED_64_BIT_INTEGER = 9_223_372_036_854_775_807
MAX_EXACT_JSON_FLOAT_INTEGER = 9_007_199_254_740_991
MAX_PERSISTED_INTERVAL_MINUTES = 2_147_483_647
MCP_BRIDGE_ACTIVATION_SCHEMA_VERSION = 1
MCP_BRIDGE_ACTIVATION_STATE = "blocked"
MCP_BRIDGE_EXPECTED_SDK_VERSION: str | None = None
MCP_BRIDGE_EXPECTED_SDK_COMMIT: str | None = None
MCP_BRIDGE_EXPECTED_MODULE_ORIGIN = "netbox_sdk/plugin_bridge.py"
MCP_BRIDGE_REQUIRED_CONTRACTS = [
    "lossless-json-integer-identity",
    "bounded-rfc3339-normalization",
]
MCP_BRIDGE_BLOCK_REASON = (
    "No released netbox-sdk version has passed the immutable paired bridge gate yet."
)
INTERVAL_MINUTE_MULTIPLIERS = {
    "minutes": 1,
    "hours": 60,
    "days": 60 * 24,
    "weeks": 60 * 24 * 7,
}
INTERVAL_VALUE_MAXIMUMS = {
    unit: MAX_PERSISTED_INTERVAL_MINUTES // multiplier
    for unit, multiplier in INTERVAL_MINUTE_MULTIPLIERS.items()
}


def mcp_bridge_activation_record() -> dict[str, Any]:
    """Return the checked consumer activation record exposed to static tests."""
    return {
        "schema_version": MCP_BRIDGE_ACTIVATION_SCHEMA_VERSION,
        "state": MCP_BRIDGE_ACTIVATION_STATE,
        "expected_version": MCP_BRIDGE_EXPECTED_SDK_VERSION,
        "expected_commit": MCP_BRIDGE_EXPECTED_SDK_COMMIT,
        "module_origin": MCP_BRIDGE_EXPECTED_MODULE_ORIGIN,
        "required_contracts": list(MCP_BRIDGE_REQUIRED_CONTRACTS),
        "reason": MCP_BRIDGE_BLOCK_REASON,
    }


def mcp_bridge_is_active() -> bool:
    """Activate discovery only for one complete immutable SDK identity."""
    expected_version = MCP_BRIDGE_EXPECTED_SDK_VERSION
    expected_commit = MCP_BRIDGE_EXPECTED_SDK_COMMIT
    has_version = (
        isinstance(expected_version, str)
        and bool(expected_version)
        and len(expected_version) <= 100
        and expected_version.strip() == expected_version
    )
    has_commit = (
        isinstance(expected_commit, str)
        and len(expected_commit) == 40
        and all(character in "0123456789abcdef" for character in expected_commit)
    )
    return (
        MCP_BRIDGE_ACTIVATION_STATE == "active"
        and has_version
        and has_commit
        and MCP_BRIDGE_EXPECTED_MODULE_ORIGIN == "netbox_sdk/plugin_bridge.py"
        and MCP_BRIDGE_REQUIRED_CONTRACTS
        == [
            "lossless-json-integer-identity",
            "bounded-rfc3339-normalization",
        ]
    )


def _list_sync_jobs_output_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "count": {
                "type": "integer",
                "minimum": 0,
                "maximum": MAX_POSITIVE_SIGNED_64_BIT_INTEGER,
            },
            "scheduled_jobs": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": MAX_POSITIVE_SIGNED_64_BIT_INTEGER,
                        },
                        "pk": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": MAX_POSITIVE_SIGNED_64_BIT_INTEGER,
                        },
                        "name": {"type": ["string", "null"]},
                        "sync_types": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "schedule": {
                            "type": ["string", "null"],
                            "format": "date-time",
                        },
                        "interval": {
                            "type": ["integer", "null"],
                            "minimum": 1,
                            "maximum": MAX_PERSISTED_INTERVAL_MINUTES,
                        },
                        "status": {"type": "string"},
                    },
                    "required": [
                        "id",
                        "pk",
                        "name",
                        "sync_types",
                        "schedule",
                        "interval",
                        "status",
                    ],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["count", "scheduled_jobs"],
        "additionalProperties": False,
    }


def _schedule_sync_input_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "sync_stages": {
                "type": "array",
                "items": {"type": "string", "enum": SYNC_TYPE_VALUES},
                "minItems": 1,
                "uniqueItems": True,
            },
            "job_name": {"type": "string", "maxLength": 200},
            "schedule_at": {
                "type": ["string", "null"],
                "format": "date-time",
            },
            "recurrence": {
                "type": "object",
                "properties": {
                    unit: {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": INTERVAL_VALUE_MAXIMUMS[unit],
                    }
                    for unit in INTERVAL_UNIT_VALUES
                },
                "minProperties": 1,
                "maxProperties": 1,
                "additionalProperties": False,
                "description": (
                    "Exactly one bounded unit/value member; omit for a one-shot job."
                ),
            },
            "proxmox_endpoint_ids": {
                "type": "array",
                "items": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": MAX_POSITIVE_SIGNED_64_BIT_INTEGER,
                    "description": (
                        "Use an integer JSON literal for IDs above "
                        f"{MAX_EXACT_JSON_FLOAT_INTEGER}; decimal-form numbers are "
                        "accepted only while exactly representable by IEEE 754."
                    ),
                },
                "minItems": 1,
                "uniqueItems": True,
            },
        },
        "required": ["sync_stages"],
        "additionalProperties": False,
    }


def build_mcp_bridge_manifest() -> dict[str, Any]:
    """Return the semantic bridge manifest backed by existing DRF views."""
    return {
        "schema_version": "1",
        "plugin": "proxbox",
        "tools": [
            {
                "name": "list_sync_jobs",
                "title": "List Proxbox sync jobs",
                "description": (
                    "List active, failed, and recurring Proxbox synchronization jobs "
                    "visible to the current NetBox principal."
                ),
                "method": "GET",
                "path": "sync/schedule/",
                "effect": "read",
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                    "additionalProperties": False,
                },
                "outputSchema": _list_sync_jobs_output_schema(),
                "annotations": {
                    "readOnlyHint": True,
                    "destructiveHint": False,
                    "idempotentHint": True,
                    "openWorldHint": False,
                },
            },
            {
                "name": "schedule_sync",
                "title": "Schedule a Proxbox synchronization",
                "description": (
                    "Queue an immediate, future, or recurring Proxbox synchronization "
                    "through the existing permission-gated scheduling API. "
                    "Reconciliation may delete stale NetBox inventory records. The "
                    "bridge calls use explicit concrete sync stages; a full sync is "
                    "the exact complete stage list. Stage selection controls the "
                    "thirteen backend SSE reconciliation stages; invariant endpoint "
                    "preflight plus cluster/node, firewall, datacenter, and VM-template "
                    "reconciliation still run before them for every MCP-scheduled job "
                    "(VM templates may be disabled by sync mode). "
                    "Recurrence contains exactly one "
                    "bounded unit/value member. An explicit Proxmox endpoint scope "
                    "must contain at least one ID; omit it to select all."
                ),
                "method": "POST",
                "path": "sync/schedule/",
                "effect": "destructive",
                "inputSchema": _schedule_sync_input_schema(),
                "outputSchema": {
                    "type": "object",
                    "properties": {
                        "ok": {"const": True},
                        "job_id": {
                            "type": ["integer", "null"],
                            "minimum": 1,
                            "maximum": MAX_POSITIVE_SIGNED_64_BIT_INTEGER,
                        },
                        "message": {"type": "string"},
                    },
                    "required": ["ok", "job_id", "message"],
                    "additionalProperties": False,
                },
                "annotations": {
                    "readOnlyHint": False,
                    "destructiveHint": True,
                    "idempotentHint": False,
                    "openWorldHint": True,
                },
            },
        ],
    }
