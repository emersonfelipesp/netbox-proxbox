"""Persisted models for the netbox-pbs plugin.

PR C2 adds the six read-only PBS domain models. PBSEndpoint owns NetBox
credentials for the PBS API; the rest mirror PBS state and have no
``allow_writes`` flag because v1 is strictly PBS → NetBox.
"""

from netbox_pbs.models.pbs_backup_group import PBSBackupGroup
from netbox_pbs.models.pbs_datastore import PBSDatastore
from netbox_pbs.models.pbs_endpoint import PBSEndpoint
from netbox_pbs.models.pbs_job_status import PBSJobStatus
from netbox_pbs.models.pbs_node import PBSNode
from netbox_pbs.models.pbs_snapshot import PBSSnapshot
from netbox_pbs.models.plugin_settings import PBSPluginSettings

__all__ = [
    "PBSBackupGroup",
    "PBSDatastore",
    "PBSEndpoint",
    "PBSJobStatus",
    "PBSNode",
    "PBSSnapshot",
    "PBSPluginSettings",
]
