from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

app_name = 'proxbox'

router = DefaultRouter()
router.register('proxmox-endpoints', views.ProxmoxEndpointViewSet)
router.register('netbox-endpoints', views.NetBoxEndpointViewSet)
router.register('fastapi-endpoints', views.FastAPIEndpointViewSet)
router.register('sync-processes', views.SyncProcessViewSet)
router.register('vm-backups', views.VMBackupViewSet)
router.register('journal-entries', views.JournalEntryViewSet)

urlpatterns = [
    path('', include(router.urls)),
]