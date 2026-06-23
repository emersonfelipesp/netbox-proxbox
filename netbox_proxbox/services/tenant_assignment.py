"""Post-sync VM tenant assignment driven by operator-defined rules.

The feature is disabled by default. Operators opt in globally via
``ProxboxPluginSettings.enable_tenant_name_regex`` and may override the toggle
and the rule list per ``ProxmoxEndpoint``. Existing tenant assignments are
never overwritten — the resolver only fills the field when it is currently
empty.
"""

from __future__ import annotations

import logging
import re

from netbox_proxbox.sync_params import (
    effective_tenant_from_cluster_for_endpoint,
    effective_tenant_regex_for_endpoint,
    effective_tenant_tag_assignment_for_endpoint,
)

CLOUD_CUSTOMER_MARKER_SLUG = "cloud-customer"
TENANT_TAG_PREFIX = "tenant-"
CLOUD_CUSTOMERS_GROUP_NAME = "Cloud Customers"
CLOUD_CUSTOMERS_GROUP_SLUG = "cloud-customers"


def _endpoint_id_for_vm(vm: object) -> int | None:
    """Resolve the ProxmoxEndpoint pk for a given VirtualMachine.

    Chain: vm.cluster → ProxmoxCluster(netbox_cluster=vm.cluster).endpoint_id.
    Returns ``None`` if the VM is not tied to a known Proxmox cluster.
    """
    cluster = getattr(vm, "cluster", None)
    if cluster is None:
        return None
    try:
        from netbox_proxbox.models import ProxmoxCluster
    except (ImportError, RuntimeError):
        return None
    proxmox_cluster = ProxmoxCluster.objects.filter(netbox_cluster=cluster).first()
    if proxmox_cluster is None:
        return None
    return getattr(proxmox_cluster, "endpoint_id", None)


def maybe_assign_tenant_from_regex(
    vm: object,
    *,
    endpoint_id: int | None = None,
    logger: logging.Logger | None = None,
) -> bool:
    """Apply first-match-wins tenant regex resolution to ``vm``.

    Returns ``True`` when a tenant was assigned, ``False`` otherwise.

    Semantics:
    - Resolver is a no-op when disabled at the effective scope.
    - Resolver never overwrites an existing ``vm.tenant`` assignment.
    - If a rule matches but the tenant slug is no longer present in NetBox,
      a warning is logged and resolution stops (operator intent was specific).
    """
    log = logger or logging.getLogger(__name__)
    if endpoint_id is None:
        endpoint_id = _endpoint_id_for_vm(vm)
    enabled, rules = effective_tenant_regex_for_endpoint(endpoint_id)
    if not enabled or not rules:
        return False
    if getattr(vm, "tenant_id", None) is not None:
        return False
    name = getattr(vm, "name", "") or ""
    try:
        from tenancy.models import Tenant
    except (ImportError, RuntimeError):
        return False
    for rule in rules:
        pattern = rule.get("pattern") if isinstance(rule, dict) else None
        slug = rule.get("tenant_slug") if isinstance(rule, dict) else None
        if not isinstance(pattern, str) or not isinstance(slug, str):
            continue
        try:
            if not re.search(pattern, name):
                continue
        except re.error:
            log.warning(
                "[tenant-regex] vm=%s rule pattern=%r is not a valid regex; skipping.",
                name,
                pattern,
            )
            continue
        tenant = Tenant.objects.filter(slug=slug).first()
        if tenant is None:
            log.warning(
                "[tenant-regex] vm=%s matched pattern=%r but tenant_slug=%r "
                "no longer exists; skipping.",
                name,
                pattern,
                slug,
            )
            return False
        vm.tenant = tenant
        vm.save(update_fields=["tenant"])
        log.info(
            "[tenant-regex] vm=%s → tenant=%s (pattern=%r)",
            name,
            tenant.slug,
            pattern,
        )
        return True
    return False


def _vm_tag_slugs(vm: object, tag_model: type[object]) -> list[str]:
    """Return NetBox tag slugs attached to ``vm``."""
    tags_manager = getattr(vm, "tags", None)
    all_tags = getattr(tags_manager, "all", None)
    if not callable(all_tags):
        return []
    slugs: list[str] = []
    for tag in all_tags():
        if not isinstance(tag, tag_model) and not getattr(tag, "slug", None):
            continue
        slug = str(getattr(tag, "slug", "") or "").strip()
        if slug:
            slugs.append(slug)
    return slugs


def maybe_assign_tenant_from_tags(
    vm: object,
    *,
    endpoint_id: int | None = None,
    logger: logging.Logger | None = None,
) -> bool:
    """Assign a tenant from the ``cloud-customer`` + ``tenant-<slug>`` tag pair."""
    log = logger or logging.getLogger(__name__)
    if endpoint_id is None:
        endpoint_id = _endpoint_id_for_vm(vm)
    if not effective_tenant_tag_assignment_for_endpoint(endpoint_id):
        return False
    if getattr(vm, "tenant_id", None) is not None:
        return False

    try:
        from extras.models import Tag
        from tenancy.models import Tenant, TenantGroup
    except (ImportError, RuntimeError):
        return False

    name = getattr(vm, "name", "") or ""
    tag_slugs = _vm_tag_slugs(vm, Tag)
    if CLOUD_CUSTOMER_MARKER_SLUG not in tag_slugs:
        return False

    tenant_tag_slugs = [
        slug for slug in tag_slugs if slug.startswith(TENANT_TAG_PREFIX)
    ]
    if not tenant_tag_slugs:
        return False
    if len(tenant_tag_slugs) > 1:
        log.warning(
            "[tenant-tags] vm=%s has ambiguous tenant tags=%s; skipping.",
            name,
            sorted(tenant_tag_slugs),
        )
        return False

    tenant_tag_slug = tenant_tag_slugs[0]
    tenant_slug = tenant_tag_slug[len(TENANT_TAG_PREFIX) :]
    if not tenant_slug:
        return False

    tenant = Tenant.objects.filter(slug=tenant_slug).first()
    if tenant is None:
        group, group_created = TenantGroup.objects.get_or_create(
            slug=CLOUD_CUSTOMERS_GROUP_SLUG,
            defaults={"name": CLOUD_CUSTOMERS_GROUP_NAME},
        )
        if group_created:
            log.info(
                "[tenant-tags] created tenant group slug=%s",
                CLOUD_CUSTOMERS_GROUP_SLUG,
            )
        tenant, tenant_created = Tenant.objects.get_or_create(
            slug=tenant_slug,
            defaults={"name": tenant_slug.title(), "group": group},
        )
        if tenant_created:
            log.info(
                "[tenant-tags] created tenant slug=%s group=%s",
                tenant_slug,
                CLOUD_CUSTOMERS_GROUP_SLUG,
            )

    vm.tenant = tenant
    vm.save(update_fields=["tenant"])
    log.info(
        "[tenant-tags] vm=%s → tenant=%s (tag=%s)",
        name,
        tenant.slug,
        tenant_tag_slug,
    )
    return True


def maybe_assign_tenant_from_cluster(
    vm: object,
    *,
    endpoint_id: int | None = None,
    logger: logging.Logger | None = None,
) -> bool:
    """Assign a VM tenant from its cluster tenant as a final fallback."""
    log = logger or logging.getLogger(__name__)
    if endpoint_id is None:
        endpoint_id = _endpoint_id_for_vm(vm)
    if not effective_tenant_from_cluster_for_endpoint(endpoint_id):
        return False
    if getattr(vm, "tenant_id", None) is not None:
        return False

    cluster = getattr(vm, "cluster", None)
    if cluster is None or getattr(cluster, "tenant_id", None) is None:
        return False
    tenant = getattr(cluster, "tenant", None)
    if tenant is None:
        return False

    vm.tenant = tenant
    vm.save(update_fields=["tenant"])
    log.info(
        "[tenant-cluster] vm=%s → tenant=%s (cluster=%s)",
        getattr(vm, "name", "") or "",
        getattr(tenant, "slug", getattr(cluster, "tenant_id", "")),
        getattr(cluster, "name", getattr(cluster, "pk", "")),
    )
    return True
