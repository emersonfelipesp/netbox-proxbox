from django.contrib import admin
from .models import VmResources

@admin.register(VmResources)
class VmResourcesAdmin(admin.ModelAdmin):
    list_display = ("cluster", "node", "virtual_machine", "proxmox_vm_id")
