"""CRUD and list/detail views for Proxmox storage rows."""

from __future__ import annotations

import requests
from django.db import ProgrammingError
from django.http import HttpRequest
from netbox.views import generic
from utilities.views import ViewTab, register_model_view
from virtualization.models import VirtualDisk
from virtualization.tables import VirtualDiskTable

from netbox_proxbox.filtersets import (
    ProxmoxStorageFilterSet,
    VMBackupFilterSet,
    VMSnapshotFilterSet,
)
from netbox_proxbox.forms import (
    ProxmoxStorageFilterForm,
    ProxmoxStorageForm,
    VMBackupFilterForm,
    VMSnapshotFilterForm,
)
from netbox_proxbox.models import FastAPIEndpoint, ProxmoxStorage, VMBackup, VMSnapshot
from netbox_proxbox.schemas import ProxmoxStorageRecord, StorageContentRecord
from netbox_proxbox.schemas._formatters import iter_scalar_records
from netbox_proxbox.services.endpoint_scope import enabled_backend_endpoint_scope
from netbox_proxbox.tables import ProxmoxStorageTable, VMBackupTable, VMSnapshotTable
from netbox_proxbox.utils import get_backend_auth_headers, get_fastapi_url
from netbox_proxbox.views.error_utils import (
    extract_proxmox_backend_error_detail,
    parse_requests_response_json,
)

__all__ = (
    "ProxmoxStorageView",
    "ProxmoxStorageListView",
    "ProxmoxStorageEditView",
    "ProxmoxStorageDeleteView",
    "ProxmoxStorageBulkDeleteView",
    "ProxmoxStorageVirtualDisksTabView",
    "ProxmoxStorageBackupsTabView",
    "ProxmoxStorageSnapshotsTabView",
)


@register_model_view(ProxmoxStorage, "list", path="", detail=False)
class ProxmoxStorageListView(generic.ObjectListView):
    """Global list of synchronized Proxmox storage rows."""

    queryset = ProxmoxStorage.objects.all()
    table = ProxmoxStorageTable
    filterset = ProxmoxStorageFilterSet
    filterset_form = ProxmoxStorageFilterForm
    template_name = "netbox_proxbox/storage_list.html"
    actions = {
        "bulk_delete": {"delete"},
        "export": {"view"},
    }


@register_model_view(ProxmoxStorage)
class ProxmoxStorageView(generic.ObjectView):
    """Detail view for one Proxmox storage row."""

    queryset = ProxmoxStorage.objects.all()

    request_timeout = 8

    @staticmethod
    def _parse_nodes(value: str | None) -> list[str]:
        if not value:
            return []
        return ProxmoxStorageRecord(nodes=value).node_list()

    def _fetch_backend_json(
        self,
        *,
        base_url: str,
        auth_headers: dict[str, str],
        verify_ssl: bool,
        route: str,
        query_params: dict[str, str] | None = None,
    ) -> tuple[object | None, str | None]:
        response = requests.get(
            f"{base_url}{route}",
            params=query_params or None,
            headers=auth_headers,
            verify=verify_ssl,
            timeout=self.request_timeout,
        )
        response.raise_for_status()
        payload, json_err = parse_requests_response_json(response, log_label=route)
        return payload, json_err

    def get_extra_context(
        self, request: HttpRequest, instance: ProxmoxStorage
    ) -> dict[str, object]:
        """Render storage summary stats and live storage usage when available."""
        # Summary counts for the summary card (tab badges handle the full tables)
        try:
            disk_qs = VirtualDisk.objects.filter(
                custom_field_data__proxbox_storage_id=instance.pk
            )
            virtual_disks_count = disk_qs.count()
            virtual_disks_size = sum(disk.size or 0 for disk in disk_qs.only("size"))
        except ProgrammingError:
            virtual_disks_count = 0
            virtual_disks_size = 0

        backups_count = instance.vm_backups.count()
        backups_size = sum(b.size or 0 for b in instance.vm_backups.only("size"))
        snapshots_count = instance.vm_snapshots.count()

        storage_summary = {
            "virtual_disks_count": virtual_disks_count,
            "virtual_disks_size": virtual_disks_size,
            "backups_count": backups_count,
            "backups_size": backups_size,
            "snapshots_count": snapshots_count,
        }

        usage = None
        usage_detail = None
        content_records: list[dict[str, object]] = []

        fastapi_endpoint = FastAPIEndpoint.objects.restrict(
            request.user, "view"
        ).first()
        if fastapi_endpoint:
            fastapi_info = get_fastapi_url(fastapi_endpoint) or {}
            fastapi_url = fastapi_info.get("http_url")
            verify_ssl = bool(fastapi_info.get("verify_ssl", True))
            auth_headers = get_backend_auth_headers(fastapi_endpoint)
            if fastapi_url:
                scope_params, _, scope_error = enabled_backend_endpoint_scope(
                    base_url=fastapi_url,
                    auth_headers=auth_headers,
                    backend_verify_ssl=verify_ssl,
                    timeout=self.request_timeout,
                )
                if scope_error:
                    usage_detail = scope_error
                elif scope_params is None:
                    usage_detail = "No enabled Proxmox endpoints configured; skipping storage status."

                try:
                    if scope_params is not None and usage_detail is None:
                        storage_payload, storage_err = self._fetch_backend_json(
                            base_url=fastapi_url,
                            auth_headers=auth_headers,
                            verify_ssl=verify_ssl,
                            route="/proxmox/storage",
                            query_params=scope_params,
                        )
                        if storage_err:
                            usage_detail = storage_err
                        else:
                            for record in iter_scalar_records(storage_payload):
                                typed_record = ProxmoxStorageRecord.model_validate(
                                    record
                                )
                                if typed_record.effective_name != instance.name:
                                    continue
                                if (
                                    typed_record.cluster
                                    and typed_record.cluster != instance.cluster.name
                                ):
                                    continue
                                usage = typed_record.to_usage_dict().model_dump()
                                break

                        for node in self._parse_nodes(instance.nodes):
                            content_payload, content_err = self._fetch_backend_json(
                                base_url=fastapi_url,
                                auth_headers=auth_headers,
                                verify_ssl=verify_ssl,
                                route=f"/proxmox/nodes/{node}/storage/{instance.name}/content",
                                query_params=scope_params,
                            )
                            if content_err:
                                continue
                            for record in iter_scalar_records(content_payload):
                                content_records.append(
                                    StorageContentRecord.model_validate(
                                        record
                                    ).model_dump()
                                )

                except requests.exceptions.RequestException as exc:
                    detail, _ = extract_proxmox_backend_error_detail(
                        exc,
                        proxmox_host=None,
                        proxmox_port=None,
                        backend_url=f"{fastapi_url}/proxmox",
                    )
                    usage_detail = detail
        else:
            usage_detail = "No FastAPI endpoint is visible to your account."

        return {
            "storage_summary": storage_summary,
            "storage_usage": usage,
            "storage_usage_detail": usage_detail,
            "storage_content_count": len(content_records),
        }


@register_model_view(ProxmoxStorage, "add", detail=False)
@register_model_view(ProxmoxStorage, "edit")
class ProxmoxStorageEditView(generic.ObjectEditView):
    """Create or edit a Proxmox storage row."""

    queryset = ProxmoxStorage.objects.all()
    form = ProxmoxStorageForm
    default_return_url = "plugins:netbox_proxbox:proxmoxstorage_list"


@register_model_view(ProxmoxStorage, "delete")
class ProxmoxStorageDeleteView(generic.ObjectDeleteView):
    """Delete a single Proxmox storage row."""

    queryset = ProxmoxStorage.objects.all()
    default_return_url = "plugins:netbox_proxbox:proxmoxstorage_list"


@register_model_view(ProxmoxStorage, "bulk_delete", detail=False)
class ProxmoxStorageBulkDeleteView(generic.BulkDeleteView):
    """Bulk delete Proxmox storage rows from the list page."""

    queryset = ProxmoxStorage.objects.all()
    filterset = ProxmoxStorageFilterSet
    table = ProxmoxStorageTable
    default_return_url = "plugins:netbox_proxbox:proxmoxstorage_list"


@register_model_view(ProxmoxStorage, "virtual_disks", path="virtual-disks")
class ProxmoxStorageVirtualDisksTabView(generic.ObjectChildrenView):
    """Storage detail tab listing virtual disks on this storage."""

    queryset = ProxmoxStorage.objects.all()
    child_model = VirtualDisk
    table = VirtualDiskTable
    tab = ViewTab(
        label="Virtual Disks",
        badge=lambda obj: VirtualDisk.objects.filter(
            custom_field_data__proxbox_storage_id=obj.pk
        ).count(),
        permission="virtualization.view_virtualdisk",
        weight=1000,
    )

    def get_children(self, request: HttpRequest, parent: ProxmoxStorage):
        """Return virtual disks linked to this storage via the proxbox_storage_id custom field."""
        return (
            VirtualDisk.objects.restrict(request.user, "view")
            .filter(custom_field_data__proxbox_storage_id=parent.pk)
            .select_related("virtual_machine")
        )


@register_model_view(ProxmoxStorage, "backups", path="backups")
class ProxmoxStorageBackupsTabView(generic.ObjectChildrenView):
    """Storage detail tab listing VM backups stored on this storage."""

    queryset = ProxmoxStorage.objects.all()
    child_model = VMBackup
    table = VMBackupTable
    filterset = VMBackupFilterSet
    filterset_form = VMBackupFilterForm
    actions = {
        "bulk_delete": {"delete"},
        "export": {"view"},
    }
    tab = ViewTab(
        label="Backups",
        badge=lambda obj: obj.vm_backups.count(),
        permission="netbox_proxbox.view_vmbackup",
        weight=1100,
    )

    def get_children(self, request: HttpRequest, parent: ProxmoxStorage):
        """Return backups on this storage visible to the current user."""
        return (
            VMBackup.objects.restrict(request.user, "view")
            .filter(proxmox_storage=parent)
            .select_related("virtual_machine", "proxmox_storage")
        )


@register_model_view(ProxmoxStorage, "snapshots", path="snapshots")
class ProxmoxStorageSnapshotsTabView(generic.ObjectChildrenView):
    """Storage detail tab listing VM snapshots on this storage."""

    queryset = ProxmoxStorage.objects.all()
    child_model = VMSnapshot
    table = VMSnapshotTable
    filterset = VMSnapshotFilterSet
    filterset_form = VMSnapshotFilterForm
    actions = {
        "bulk_delete": {"delete"},
        "export": {"view"},
    }
    tab = ViewTab(
        label="Snapshots",
        badge=lambda obj: obj.vm_snapshots.count(),
        permission="netbox_proxbox.view_vmsnapshot",
        weight=1200,
    )

    def get_children(self, request: HttpRequest, parent: ProxmoxStorage):
        """Return snapshots on this storage visible to the current user."""
        return (
            VMSnapshot.objects.restrict(request.user, "view")
            .filter(proxmox_storage=parent)
            .select_related("virtual_machine", "proxmox_storage")
        )
