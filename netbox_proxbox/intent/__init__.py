"""NetBox -> Proxmox intent layer (Sub-PRs D..L for issue #377).

This package owns the GitOps-style intent path: it inspects a
netbox-branching branch flagged ``apply_to_proxmox=True``, validates
the proposed merge against the Proxmox cluster via proxbox-api, and
(in later sub-PRs) drives the actual apply. The validator landed in
Sub-PR D; CREATE/UPDATE/DELETE applies and the four-eyes
DeletionRequest workflow follow in F/G/H/I.

The reflection path (Proxmox -> NetBox) is unchanged and remains the
default. Nothing in this package mutates Proxmox by itself — apply
work is gated on the master flag, the typed confirmation phrase, the
per-branch ``apply_to_proxmox`` CF, RBAC, and (for DELETE) a separate
``authorize_deletion_request`` approver. See
``netbox-proxbox/CLAUDE.md`` for the full Safety Model.
"""

from netbox_proxbox.intent.merge_validator import validate_proxmox_intent
from netbox_proxbox.intent.plan_client import (
    PlanClientError,
    PlanClientResult,
    call_plan_endpoint,
)

__all__ = [
    "PlanClientError",
    "PlanClientResult",
    "call_plan_endpoint",
    "validate_proxmox_intent",
]
