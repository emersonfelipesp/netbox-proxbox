"""Serializers for the Proxbox sync-job listing.

Both are thin subclasses of core's own ``JobSerializer`` rather than a
hand-written schema, so a Proxbox sync job serialises **byte-identically** to
the same row on ``/api/core/jobs/``. A consumer that already parses core job
rows needs no second parser, and a NetBox release that adds a field to the job
representation adds it here too.
"""

from __future__ import annotations

from core.api.serializers_.jobs import JobSerializer

__all__ = (
    "ProxboxSyncJobListSerializer",
    "ProxboxSyncJobSerializer",
)


class ProxboxSyncJobSerializer(JobSerializer):
    """The complete core job representation, including ``log_entries``."""

    class Meta(JobSerializer.Meta):
        pass


class ProxboxSyncJobListSerializer(JobSerializer):
    """The same representation minus ``log_entries``, for list responses.

    Log entries are unbounded and dominate the payload: a single full-sync row
    on a production instance reaches 130 KB, and a page of them is most of the
    response. Dropping them from the list is what makes this endpoint cheaper
    than the client-side scan it replaces. The detail route still returns them,
    and ``?include_log_entries=true`` restores them here.
    """

    class Meta(JobSerializer.Meta):
        fields = [
            field for field in JobSerializer.Meta.fields if field != "log_entries"
        ]
