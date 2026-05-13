"""Persisted models for the netbox-pbs plugin.

PR C1 ships only the singleton ``PBSPluginSettings`` model. Domain models
(``PBSEndpoint``, ``PBSNode``, ``PBSDatastore``, ``PBSBackupGroup``,
``PBSSnapshot``, ``PBSJobStatus``) land in PR C2.
"""

from netbox_pbs.models.plugin_settings import PBSPluginSettings

__all__ = ["PBSPluginSettings"]
