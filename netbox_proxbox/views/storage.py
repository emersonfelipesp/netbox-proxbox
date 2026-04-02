"""CRUD and list/detail views for Proxmox storage rows."""

from __future__ import annotations

import requests
from django.db import ProgrammingError
from netbox.views import generic
from utilities.views import register_model_view

from netbox_proxbox.filtersets import ProxmoxStorageFilterSet
from netbox_proxbox.forms import ProxmoxStorageFilterForm, ProxmoxStorageForm
from netbox_proxbox.models import FastAPIEndpoint, ProxmoxStorage
from netbox_proxbox.schemas import ProxmoxStorageRecord, StorageContentRecord
from netbox_proxbox.schemas._formatters import iter_scalar_records
from netbox_proxbox.utils import get_backend_auth_headers, get_fastapi_url
from netbox_proxbox.views.error_utils import (
    extract_proxmox_backend_error_detail,
    parse_requests_response_json,
)
from netbox_proxbox.tables import ProxmoxStorageTable

__all__ = (
    "ProxmoxStorageView",
    "ProxmoxStorageListView",
    "ProxmoxStorageEditView",
    "ProxmoxStorageDeleteView",
    "ProxmoxStorageBulkDeleteView",
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

    def get_extra_context(self, request, instance):
        """Render related backups/snapshots/disks and live storage usage when available."""
        vm_backups = (
            instance.vm_backups.restrict(request.user, "view")
            .select_related("virtual_machine", "proxmox_storage")
            .order_by("-creation_time", "virtual_machine__name")
        )
        vm_snapshots = (
            instance.vm_snapshots.restrict(request.user, "view")
            .select_related("virtual_machine", "proxmox_storage")
            .order_by("-snaptime", "virtual_machine__name")
        )
        disk_relation_warning = None
        try:
            disk_qs = instance.virtual_disks.all()
            if hasattr(disk_qs, "restrict"):
                disk_qs = disk_qs.restrict(request.user, "view")
            virtual_disks = list(
                disk_qs.select_related("virtual_machine").order_by(
                    "virtual_machine__name", "name"
                )
            )
        except ProgrammingError:
            # Keep page usable if the through-table migration is missing.
            virtual_disks = []
            disk_relation_warning = (
                "Virtual disk mapping table is unavailable. "
                "Run NetBox migrations to enable storage-to-disk relationships."
            )

        # Calculate storage summary statistics
        virtual_disks_count = len(virtual_disks)
        virtual_disks_size = sum(disk.size or 0 for disk in virtual_disks)
        backups_count = vm_backups.count()
        backups_size = sum(backup.size or 0 for backup in vm_backups)
        snapshots_count = vm_snapshots.count()

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
                try:
                    storage_payload, storage_err = self._fetch_backend_json(
                        base_url=fastapi_url,
                        auth_headers=auth_headers,
                        verify_ssl=verify_ssl,
                        route="/proxmox/storage",
                        query_params={"source": "database"},
                    )
                    if storage_err:
                        usage_detail = storage_err
                    else:
                        for record in iter_scalar_records(storage_payload):
                            typed_record = ProxmoxStorageRecord.model_validate(record)
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
                            query_params={"source": "database"},
                        )
                        if content_err:
                            continue
                        for record in iter_scalar_records(content_payload):
                            content_records.append(
                                StorageContentRecord.model_validate(record).model_dump()
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
            "vm_backups": vm_backups,
            "vm_snapshots": vm_snapshots,
            "virtual_disks": virtual_disks,
            "disk_relation_warning": disk_relation_warning,
            "storage_summary": storage_summary,
            "storage_usage": usage,
            "storage_usage_detail": usage_detail,
            "storage_content_count": len(content_records),
        }


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
