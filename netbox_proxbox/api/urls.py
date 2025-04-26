from netbox.api.routers import NetBoxRouter
from django.urls import path, include
from . import views

app_name = 'proxbox'

# Create endpoints router
endpoints_router = NetBoxRouter()
endpoints_router.APIRootView = views.ProxBoxEndpointsView
endpoints_router.register('proxmox', views.ProxmoxEndpointViewSet, basename='proxmox-endpoint')
endpoints_router.register('netbox', views.NetBoxEndpointViewSet, basename='netbox-endpoint')
endpoints_router.register('fastapi', views.FastAPIEndpointViewSet, basename='fastapi-endpoint')

# Create main router
router = NetBoxRouter()
router.APIRootView = views.ProxBoxRootView

router.register('sync-processes', views.SyncProcessViewSet)
router.register('backups', views.VMBackupViewSet)
router.register('journal-entries', views.JournalEntryViewSet)

urlpatterns = [
    path('endpoints/', include((endpoints_router.urls, 'endpoints'), namespace='endpoints')),
    path('', include(router.urls)),
]