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
    "all",
]

INTERVAL_UNIT_VALUES = ["minutes", "hours", "days", "weeks"]


def _list_sync_jobs_output_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "count": {"type": "integer", "minimum": 0},
            "scheduled_jobs": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer", "minimum": 1},
                        "pk": {"type": "integer", "minimum": 1},
                        "name": {"type": ["string", "null"]},
                        "sync_types": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "schedule": {
                            "type": ["string", "null"],
                            "format": "date-time",
                        },
                        "interval": {"type": ["integer", "null"], "minimum": 1},
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
            "sync_types": {
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
            "interval_value": {
                "type": ["integer", "null"],
                "minimum": 1,
                "description": (
                    "Set with interval_unit; omit both for a one-shot job."
                ),
            },
            "interval_unit": {
                "type": ["string", "null"],
                "enum": [*INTERVAL_UNIT_VALUES, None],
                "description": (
                    "Set with interval_value; omit both for a one-shot job."
                ),
            },
            "proxmox_endpoint_ids": {
                "type": "array",
                "items": {"type": "integer", "minimum": 1},
                "minItems": 1,
                "uniqueItems": True,
            },
            "netbox_endpoint_ids": {
                "type": "array",
                "items": {"type": "integer", "minimum": 1},
                "minItems": 1,
                "uniqueItems": True,
            },
        },
        "required": ["sync_types"],
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
                    '"all" sync type must be selected by itself. Recurrence value '
                    "and unit must be set together. Explicit endpoint scopes must "
                    "contain at least one ID; omit a scope to select all."
                ),
                "method": "POST",
                "path": "sync/schedule/",
                "effect": "destructive",
                "inputSchema": _schedule_sync_input_schema(),
                "outputSchema": {
                    "type": "object",
                    "properties": {
                        "ok": {"const": True},
                        "job_id": {"type": ["integer", "null"], "minimum": 1},
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
