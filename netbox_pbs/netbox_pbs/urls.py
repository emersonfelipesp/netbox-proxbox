"""URL routes for netbox-pbs.

Most per-model URLs are wired by ``register_model_view`` decorators in
``netbox_pbs.views`` — NetBox's URL system materializes them when the
views module is imported. We import the views module here so list,
detail, edit, delete, and bulk-action routes are present in the plugin
URL namespace.

The reflected PBS objects (Node, Datastore, BackupGroup, Snapshot,
JobStatus) intentionally register only ``list`` and detail views; that
absence is the read-only contract.
"""

from django.urls import path

from netbox_pbs import views  # noqa: F401  (registers per-model URLs)


app_name = "netbox_pbs"

urlpatterns = [
    path("", views.PBSHomeView.as_view(), name="home"),
]
