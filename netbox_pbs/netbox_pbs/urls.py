"""URL routes for netbox-pbs.

Per-model URLs are registered via ``register_model_view`` decorators in
``netbox_pbs.views``; they materialize when included through
``utilities.urls.get_model_urls``. ``views`` is imported as a side effect
so the decorators run before ``get_model_urls`` queries the registry.

The reflected PBS objects (Node, Datastore, BackupGroup, Snapshot,
JobStatus) intentionally register only ``list`` and detail views; that
absence is the read-only contract.
"""

from django.urls import include, path

from utilities.urls import get_model_urls

from netbox_pbs import views  # noqa: F401  (registers per-model URLs)


app_name = "netbox_pbs"

urlpatterns = [
    path("", views.PBSHomeView.as_view(), name="home"),
    # PBSEndpoint — full CRUD
    path(
        "endpoints/",
        include(get_model_urls("netbox_pbs", "pbsendpoint", detail=False)),
    ),
    path(
        "endpoints/<int:pk>/",
        include(get_model_urls("netbox_pbs", "pbsendpoint")),
    ),
    # PBSNode — read-only list + detail
    path(
        "nodes/",
        include(get_model_urls("netbox_pbs", "pbsnode", detail=False)),
    ),
    path(
        "nodes/<int:pk>/",
        include(get_model_urls("netbox_pbs", "pbsnode")),
    ),
    # PBSDatastore — read-only list + detail
    path(
        "datastores/",
        include(get_model_urls("netbox_pbs", "pbsdatastore", detail=False)),
    ),
    path(
        "datastores/<int:pk>/",
        include(get_model_urls("netbox_pbs", "pbsdatastore")),
    ),
    # PBSBackupGroup — read-only list + detail
    path(
        "backup-groups/",
        include(get_model_urls("netbox_pbs", "pbsbackupgroup", detail=False)),
    ),
    path(
        "backup-groups/<int:pk>/",
        include(get_model_urls("netbox_pbs", "pbsbackupgroup")),
    ),
    # PBSSnapshot — read-only list + detail
    path(
        "snapshots/",
        include(get_model_urls("netbox_pbs", "pbssnapshot", detail=False)),
    ),
    path(
        "snapshots/<int:pk>/",
        include(get_model_urls("netbox_pbs", "pbssnapshot")),
    ),
    # PBSJobStatus — read-only list + detail
    path(
        "job-status/",
        include(get_model_urls("netbox_pbs", "pbsjobstatus", detail=False)),
    ),
    path(
        "job-status/<int:pk>/",
        include(get_model_urls("netbox_pbs", "pbsjobstatus")),
    ),
]
