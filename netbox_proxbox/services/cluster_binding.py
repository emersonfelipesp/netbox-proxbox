"""Atomic local reconciliation of an endpoint's native cluster identity."""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import IntegrityError, OperationalError, transaction
from rest_framework.exceptions import APIException, PermissionDenied
from virtualization.models import Cluster

from netbox_proxbox.models import (
    ProxboxClusterSyncState,
    ProxmoxCluster,
    ProxmoxEndpoint,
)
from netbox_proxbox.services.cluster_binding_authority import (
    allow_cluster_binding_write,
)


class ClusterBindingConflict(APIException):
    """Ownership evidence is inconsistent and requires explicit operator review."""

    status_code = 409
    default_code = "cluster_binding_conflict"
    default_detail = (
        "Cluster ownership is ambiguous or conflicts with an existing relation. "
        "Review this endpoint's linked Proxmox cluster tracking records and the "
        "native cluster's endpoint before retrying; synchronization cannot reassign ownership."
    )


def require_visible(queryset, user, action: str, pk: int) -> None:
    """Require both a model grant and exact object scope, including add constraints."""
    model = queryset.model
    permission = f"{model._meta.app_label}.{action}_{model._meta.model_name}"
    if (
        not user.has_perm(permission)
        or not queryset.restrict(user, action).filter(pk=pk).exists()
    ):
        raise PermissionDenied("The required object permission is unavailable.")


def legacy_cluster_id(endpoint: ProxmoxEndpoint) -> int | None:
    """Adopt only one globally unambiguous tracking-linked core cluster."""
    linked = ProxmoxCluster.objects.filter(
        endpoint=endpoint, netbox_cluster__isnull=False
    )
    core_ids = set(linked.values_list("netbox_cluster_id", flat=True))
    if not core_ids:
        return None
    if len(core_ids) != 1:
        raise ClusterBindingConflict()
    core_id = core_ids.pop()
    if (
        ProxmoxCluster.objects.filter(netbox_cluster_id=core_id)
        .exclude(endpoint=endpoint)
        .exists()
    ):
        raise ClusterBindingConflict()
    return core_id


def _cluster(endpoint: ProxmoxEndpoint, user) -> tuple[Cluster, bool]:
    core_id = endpoint.netbox_cluster_id or legacy_cluster_id(endpoint)
    if core_id is None:
        if not user.has_perm("virtualization.add_cluster"):
            raise PermissionDenied(
                "Creating the endpoint's cluster requires add_cluster."
            )
        return Cluster(), True
    core = Cluster.objects.select_for_update().get(pk=core_id)
    require_visible(Cluster.objects.all(), user, "view", core.pk)
    require_visible(Cluster.objects.all(), user, "change", core.pk)
    if (
        ProxmoxEndpoint.objects.filter(netbox_cluster_id=core.pk)
        .exclude(pk=endpoint.pk)
        .exists()
    ):
        raise ClusterBindingConflict()
    if (
        ProxmoxCluster.objects.filter(endpoint=endpoint, netbox_cluster__isnull=False)
        .exclude(netbox_cluster=core)
        .exists()
    ):
        raise ClusterBindingConflict()
    if (
        ProxmoxCluster.objects.filter(netbox_cluster=core)
        .exclude(endpoint=endpoint)
        .exists()
    ):
        raise ClusterBindingConflict()
    return core, False


def _tracking(endpoint: ProxmoxEndpoint, core: Cluster, values: dict) -> ProxmoxCluster:
    """Keep one linked tracking identity across discovery renames."""
    linked = ProxmoxCluster.objects.filter(endpoint=endpoint, netbox_cluster=core)
    if linked.count() > 1:
        raise ClusterBindingConflict()
    tracking = linked.first()
    named = ProxmoxCluster.objects.filter(
        endpoint=endpoint, name=values["name"]
    ).first()
    if named is not None and tracking is not None and named.pk != tracking.pk:
        raise ClusterBindingConflict()
    tracking = tracking or named or ProxmoxCluster(endpoint=endpoint)
    tracking.netbox_cluster = core
    tracking.name = values["name"]
    tracking.mode = values["mode"]
    tracking.cluster_id = values.get("cluster_id", "")
    tracking.save()
    return tracking


def _sidecar(core: Cluster, tracking: ProxmoxCluster, values: dict) -> None:
    sidecar, _ = ProxboxClusterSyncState.objects.get_or_create(cluster=core)
    if sidecar.proxmox_cluster_id not in (None, tracking.pk):
        raise ClusterBindingConflict()
    sidecar.proxmox_cluster = tracking
    sidecar.proxmox_cluster_name = values["name"]
    sidecar.full_clean()
    sidecar.save()


def synchronize_cluster(
    endpoint_pk: int, user, values: dict
) -> tuple[Cluster, ProxmoxCluster, bool]:
    """Reconcile one exact authorized endpoint without credential or network access."""
    try:
        with transaction.atomic():
            endpoint = ProxmoxEndpoint.objects.select_for_update().get(pk=endpoint_pk)
            require_visible(ProxmoxEndpoint.objects.all(), user, "view", endpoint.pk)
            require_visible(ProxmoxEndpoint.objects.all(), user, "change", endpoint.pk)
            if not endpoint.enabled:
                raise PermissionDenied(
                    "Disabled endpoints cannot synchronize a cluster."
                )
            core, created = _cluster(endpoint, user)
            previous_native = (
                core.name,
                core.type_id,
                core.scope_type_id,
                core.scope_id,
                core.tenant_id,
            )
            core.name = values["name"]
            core.type = values["cluster_type"]
            if "site" in values:
                core.scope = values["site"]
            if "tenant" in values:
                core.tenant = values["tenant"]
            core.full_clean()
            core.save()
            require_visible(Cluster.objects.all(), user, "view", core.pk)
            require_visible(
                Cluster.objects.all(), user, "add" if created else "change", core.pk
            )
            ProxmoxEndpoint.objects.filter(pk=endpoint.pk).update(netbox_cluster=core)
            endpoint.netbox_cluster = core
            with allow_cluster_binding_write(endpoint.pk, core.pk):
                tracking = _tracking(endpoint, core, values)
                _sidecar(core, tracking, values)
            core._proxbox_binding_changed = not created and previous_native != (
                core.name,
                core.type_id,
                core.scope_type_id,
                core.scope_id,
                core.tenant_id,
            )
            return core, tracking, created
    except (
        IntegrityError,
        ValidationError,
        ProxmoxEndpoint.DoesNotExist,
        Cluster.DoesNotExist,
    ) as exc:
        raise ClusterBindingConflict() from exc
    except OperationalError as exc:
        if getattr(exc.__cause__, "sqlstate", None) in {"40P01", "40001"}:
            raise ClusterBindingConflict() from exc
        raise
