"""Post-sync VM tenant assignment driven by operator-defined regex rules.

The feature is disabled by default. Operators opt in globally via
``ProxboxPluginSettings.enable_tenant_name_regex`` and may override the toggle
and the rule list per ``ProxmoxEndpoint``. Existing tenant assignments are
never overwritten — the resolver only fills the field when it is currently
empty.
"""

from __future__ import annotations

import logging
import re

from netbox_proxbox.sync_params import effective_tenant_regex_for_endpoint


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
