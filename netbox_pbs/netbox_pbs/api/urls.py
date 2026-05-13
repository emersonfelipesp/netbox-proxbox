"""API URL routes for the netbox-pbs plugin.

One ``NetBoxRouter`` registers all six PBS viewsets at predictable basenames
(``pbsendpoint``, ``pbsnode``, ``pbsdatastore``, ``pbsbackupgroup``,
``pbssnapshot``, ``pbsjobstatus``) so reverse lookups resolve as
``plugins-api:netbox_pbs-api:<basename>-detail``.
"""

from netbox.api.routers import NetBoxRouter

from netbox_pbs.api import views

app_name = "netbox_pbs"

router = NetBoxRouter()
router.register("endpoints", views.PBSEndpointViewSet, basename="pbsendpoint")
router.register("nodes", views.PBSNodeViewSet, basename="pbsnode")
router.register("datastores", views.PBSDatastoreViewSet, basename="pbsdatastore")
router.register("backup-groups", views.PBSBackupGroupViewSet, basename="pbsbackupgroup")
router.register("snapshots", views.PBSSnapshotViewSet, basename="pbssnapshot")
router.register("job-status", views.PBSJobStatusViewSet, basename="pbsjobstatus")

urlpatterns = router.urls
