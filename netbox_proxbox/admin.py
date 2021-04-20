from django.contrib import admin
from .models import ProxmoxVM

@admin.register(ProxmoxVM)
class ProxmoxVMAdmin(admin.ModelAdmin):
    list_display = ("cluster", "node", "virtual_machine", "proxmox_vm_id")
