"""Read-only API serializers for the intent workflow models.

``DeletionRequest`` and ``ProxmoxApplyJob`` have multi-step approval/state
workflows that are intentionally guarded in the Django UI layer. These
serializers expose the full state for read access only; the corresponding
ViewSets are wired as read-only (GET/HEAD/OPTIONS) so no write path bypasses
the UI-side guards.
"""

from __future__ import annotations

from netbox.api.serializers import NetBoxModelSerializer
from rest_framework import serializers

from netbox_proxbox.models import DeletionRequest, ProxmoxApplyJob


class DeletionRequestSerializer(NetBoxModelSerializer):
    """Read-only view of a pending Proxmox deletion awaiting four-eyes approval."""

    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_proxbox-api:deletionrequest-detail",
    )

    class Meta:
        model = DeletionRequest
        fields = (
            "id",
            "url",
            "display",
            "name",
            "state",
            "vmid",
            "node",
            "kind",
            "branch_id",
            "branch_name",
            "requested_by",
            "authorizer",
            "reject_reason",
            "executor_run_uuid",
            "metadata_snapshot",
            "requested_at",
            "approved_at",
            "executed_at",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "name", "state", "vmid", "node", "kind")
        read_only_fields = ("__all__",)


class ProxmoxApplyJobSerializer(NetBoxModelSerializer):
    """Read-only view of a NetBox→Proxmox intent apply run."""

    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:netbox_proxbox-api:proxmoxapplyjob-detail",
    )

    class Meta:
        model = ProxmoxApplyJob
        fields = (
            "id",
            "url",
            "display",
            "name",
            "state",
            "branch_id",
            "branch_name",
            "user",
            "run_uuid",
            "per_vm_results",
            "started_at",
            "finished_at",
            "tags",
            "custom_fields",
            "created",
            "last_updated",
        )
        brief_fields = ("id", "url", "display", "name", "state", "run_uuid")
        read_only_fields = ("__all__",)
