"""PDMEndpoint detail and Sync Now views for netbox-proxbox."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import requests
from django.contrib import messages
from django.db.models import Q
from django.http import HttpRequest, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from netbox.views import generic
from utilities.views import register_model_view

from netbox_proxbox.models import PDMEndpoint
from netbox_proxbox.models.pdm_remote import PDMRemote, PDMRemoteTypeChoices
from netbox_proxbox.views.sync_helpers import _ProxboxSyncViewBase

if TYPE_CHECKING:
    pass

__all__ = ("PDMEndpointView", "PDMEndpointSyncNowView")

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Detail view — overrides whatever netbox_pdm registers so we can inject the
# "Discovered Remotes" table into the page context.
# ---------------------------------------------------------------------------


@register_model_view(PDMEndpoint)
class PDMEndpointView(generic.ObjectView):
    """Detail view for a PDM endpoint with the Discovered Remotes table."""

    queryset = PDMEndpoint.objects.all()

    def get_extra_context(self, request: HttpRequest, instance: PDMEndpoint) -> dict:
        from netbox_proxbox.tables.pdm_remote import PDMRemoteTable

        remotes_qs = PDMRemote.objects.filter(pdm_endpoint=instance).select_related(
            "linked_proxmox_endpoint",
            "linked_pbs_endpoint",
        )
        remotes_table = PDMRemoteTable(remotes_qs)
        remotes_table.configure(request)
        return {"remotes_table": remotes_table}


# ---------------------------------------------------------------------------
# Sync Now — calls the PDM REST API directly and updates PDMRemote rows.
# ---------------------------------------------------------------------------


@register_model_view(PDMEndpoint, "sync_now", path="sync-now")
class PDMEndpointSyncNowView(_ProxboxSyncViewBase):
    """POST: pull PDM /remotes into NetBox PDMRemote rows and auto-link to PVE/PBS."""

    http_method_names = ["post"]

    def post(self, request: HttpRequest, pk: int) -> HttpResponseRedirect:
        endpoint: PDMEndpoint = get_object_or_404(
            PDMEndpoint.objects.restrict(request.user, "view"),
            pk=pk,
        )
        redirect_url = endpoint.get_absolute_url()

        if not endpoint.enabled:
            messages.warning(
                request,
                _("Disabled PDM endpoints cannot run sync jobs."),
            )
            return HttpResponseRedirect(redirect_url)

        host = endpoint.host
        if not host:
            messages.error(
                request,
                _("PDM endpoint has no configured IP address or domain."),
            )
            return HttpResponseRedirect(redirect_url)

        try:
            synced, errors = _sync_pdm_remotes(endpoint)
        except Exception as exc:
            logger.error(
                "PDM sync failed for endpoint pk=%s (%s): %s",
                pk,
                host,
                exc,
            )
            messages.error(
                request,
                _("PDM sync failed: %(error)s") % {"error": str(exc)},
            )
            return HttpResponseRedirect(redirect_url)

        if errors:
            messages.warning(
                request,
                _(
                    "Synced %(count)d remote(s) from %(name)s with %(nerr)d error(s): %(errors)s"
                )
                % {
                    "count": synced,
                    "name": endpoint.name or host,
                    "nerr": len(errors),
                    "errors": "; ".join(errors[:3]),
                },
            )
        else:
            messages.success(
                request,
                _("Synced %(count)d remote(s) from PDM endpoint %(name)s.")
                % {"count": synced, "name": endpoint.name or host},
            )

        return HttpResponseRedirect(redirect_url)


# ---------------------------------------------------------------------------
# Internal helpers — not views, not exported.
# ---------------------------------------------------------------------------


def _sync_pdm_remotes(endpoint: PDMEndpoint) -> tuple[int, list[str]]:
    """Call PDM /remotes, upsert PDMRemote rows, return (synced_count, errors)."""
    host = endpoint.host
    port = endpoint.port
    token_id = endpoint.token_id
    token_secret = endpoint.token_secret  # NEVER log this value
    verify_ssl = endpoint.verify_ssl
    timeout = endpoint.timeout_seconds

    if not verify_ssl:
        logger.critical(
            "PDM endpoint pk=%s (%s:%s): SSL verification DISABLED. "
            "Credentials are transmitted to an unverified host. "
            "Set verify_ssl=True for production use.",
            endpoint.pk,
            host,
            port,
        )

    url = f"https://{host}:{port}/api2/json/pdm/remotes"
    # Proxmox API token format: PVEAPIToken=<token_id>=<token_secret>
    auth_header = f"PVEAPIToken={token_id}={token_secret}"

    try:
        response = requests.get(
            url,
            headers={"Authorization": auth_header},
            verify=verify_ssl,
            timeout=timeout,
            allow_redirects=False,
        )
        response.raise_for_status()
    except requests.exceptions.SSLError as exc:
        raise RuntimeError(
            f"SSL error connecting to PDM at {host}:{port}: {exc}"
        ) from exc
    except requests.exceptions.ConnectionError as exc:
        raise RuntimeError(f"Cannot connect to PDM at {host}:{port}: {exc}") from exc
    except requests.exceptions.Timeout:
        raise RuntimeError(
            f"Timeout connecting to PDM at {host}:{port} after {timeout}s"
        ) from None
    except requests.exceptions.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else "?"
        raise RuntimeError(
            f"PDM API error HTTP {status}; upstream body suppressed."
        ) from exc

    payload = response.json()
    remotes_data: list[dict] = payload.get("data") or []

    now = timezone.now()
    synced = 0
    errors: list[str] = []

    for raw in remotes_data:
        remote_id = raw.get("id") or raw.get("name") or "?"
        try:
            _upsert_pdm_remote(endpoint, raw, now)
            synced += 1
        except Exception as exc:
            logger.warning(
                "PDM endpoint pk=%s: failed to upsert remote %r: %s",
                endpoint.pk,
                remote_id,
                exc,
            )
            errors.append(f"{remote_id}: {exc}")

    return synced, errors


def _upsert_pdm_remote(endpoint: PDMEndpoint, data: dict, now: object) -> PDMRemote:
    """Create or update one PDMRemote from raw PDM API data."""
    remote_name: str = data.get("id") or data.get("name") or ""
    remote_type: str = (data.get("type") or "pve").lower()

    # Extract hostname and fingerprint from first node entry.
    nodes: list[dict] = data.get("nodes") or []
    if nodes and isinstance(nodes[0], dict):
        first_node = nodes[0]
        hostname: str = (
            first_node.get("hostname", "")
            or data.get("server", "")
            or data.get("hostname", "")
        )
        fingerprint: str = (
            first_node.get("fingerprint", "")
            or data.get("fingerprint", "")
            or data.get("fp", "")
        )
    else:
        hostname = data.get("server", "") or data.get("hostname", "")
        fingerprint = data.get("fingerprint", "") or data.get("fp", "")

    version: str = data.get("version", "") or ""

    # Auto-link to existing PVE/PBS endpoints by hostname.
    linked_proxmox_endpoint = None
    linked_pbs_endpoint = None

    if remote_type == PDMRemoteTypeChoices.PVE and hostname:
        linked_proxmox_endpoint = _find_proxmox_endpoint(hostname)
    elif remote_type == PDMRemoteTypeChoices.PBS and hostname:
        linked_pbs_endpoint = _find_pbs_endpoint(hostname)

    remote, _ = PDMRemote.objects.update_or_create(
        pdm_endpoint=endpoint,
        name=remote_name,
        defaults={
            "type": remote_type,
            "hostname": hostname,
            "fingerprint": fingerprint,
            "version": version,
            "linked_proxmox_endpoint": linked_proxmox_endpoint,
            "linked_pbs_endpoint": linked_pbs_endpoint,
            "last_seen_at": now,
        },
    )
    return remote


def _find_proxmox_endpoint(hostname: str):
    """Return the first ProxmoxEndpoint whose domain or IP matches hostname."""
    from netbox_proxbox.models import ProxmoxEndpoint

    return ProxmoxEndpoint.objects.filter(
        Q(domain=hostname) | Q(ip_address__address__startswith=hostname + "/")
    ).first()


def _find_pbs_endpoint(hostname: str):
    """Return the first PBSEndpoint whose domain or IP matches hostname."""
    try:
        from netbox_proxbox.models import PBSEndpoint
    except ImportError:
        return None

    return PBSEndpoint.objects.filter(
        Q(domain=hostname) | Q(ip_address__address__startswith=hostname + "/")
    ).first()
