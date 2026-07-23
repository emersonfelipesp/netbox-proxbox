"""Sync service for Proxmox firewall objects from proxbox-api.

Calls ``GET /proxmox/firewall/summary`` on proxbox-api to retrieve
datacenter-level firewall data (security groups with their rules, IP sets
with their entries, aliases, and datacenter firewall options) for every
configured Proxmox endpoint, then upserts the results into the six
firewall Django models.

After the datacenter pass, node-level firewall rules are synced for every
``ProxmoxNode`` row belonging to a successfully-resolved endpoint by calling
the per-node backend route.  Per-VM firewall sync is deferred until a reliable
per-VM ``vm_type`` (qemu vs lxc) source is available from the DB.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

import requests

from django.db import transaction

from netbox_proxbox.choices import (
    FirewallSyncStatusChoices,
    FirewallZoneChoices,
    FirewallScopeChoices,
)
from netbox_proxbox.models import (
    ProxmoxEndpoint,
    ProxmoxFirewallAlias,
    ProxmoxFirewallIPSet,
    ProxmoxFirewallIPSetEntry,
    ProxmoxFirewallOptions,
    ProxmoxFirewallRule,
    ProxmoxFirewallSecurityGroup,
)
from netbox_proxbox.services.backend_proxy import get_fastapi_request_context
from netbox_proxbox.services.endpoint_scope import enabled_backend_endpoint_scope

logger = logging.getLogger(__name__)

SYNC_TIMEOUT = 30

# Firewall zones returned by the backend that have no model representation.
# Rules in these zones are skipped silently.
_SKIP_ZONES: frozenset[str] = frozenset({"vnet"})


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class FirewallSyncResult:
    """Counters and outcome for a single firewall sync run."""

    success: bool = False
    error: str | None = None
    endpoint_id: int | None = None
    endpoint_name: str = ""
    endpoints_processed: int = 0

    security_groups_created: int = 0
    security_groups_updated: int = 0
    security_groups_stale: int = 0

    rules_created: int = 0
    rules_updated: int = 0
    rules_stale: int = 0

    ipsets_created: int = 0
    ipsets_updated: int = 0
    ipsets_stale: int = 0

    ipset_entries_created: int = 0
    ipset_entries_updated: int = 0
    ipset_entries_stale: int = 0

    aliases_created: int = 0
    aliases_updated: int = 0
    aliases_stale: int = 0

    options_created: int = 0
    options_updated: int = 0
    options_stale: int = 0

    per_endpoint: list[dict[str, object]] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Endpoint lookup
# ---------------------------------------------------------------------------


def _resolve_endpoint_by_cluster_name(cluster_name: str) -> ProxmoxEndpoint | None:
    """Return the single ProxmoxEndpoint whose cluster name matches, or ``None``.

    Cluster names are only unique **per endpoint**, not across the estate: two
    unrelated Proxmox installations can each hold a cluster named ``pve``. A
    backend response row names only the cluster, so when more than one endpoint
    claims that name there is no way to tell whose row this is — and guessing
    (the old ``.first()``) attributed one estate's firewall/CPU data to the
    other, or discarded a valid row as out-of-scope. Ambiguous therefore
    resolves to ``None`` (refused, logged with every claimant), mirroring the
    batch path's "ambiguous never widens" rule.
    """
    try:
        from netbox_proxbox.models import ProxmoxCluster  # noqa: PLC0415

        cluster_rows = list(
            ProxmoxCluster.objects.filter(name=cluster_name).select_related("endpoint")
        )
        claimant_ids = sorted(
            {row.endpoint_id for row in cluster_rows if row.endpoint_id}
        )
        if len(claimant_ids) > 1:
            logger.warning(
                "Refusing to resolve cluster %r: claimed by %d Proxmox endpoints "
                "(%s). Cluster names are only unique per endpoint, so this "
                "response row cannot be attributed safely.",
                cluster_name,
                len(claimant_ids),
                ", ".join(str(pk) for pk in claimant_ids),
            )
            return None
        cluster = next((row for row in cluster_rows if row.endpoint_id), None)
        if cluster is not None and bool(getattr(cluster.endpoint, "enabled", True)):
            return cluster.endpoint
    except Exception as exc:
        logger.warning("DB error resolving cluster %r: %s", cluster_name, exc)
    return ProxmoxEndpoint.objects.filter(name=cluster_name, enabled=True).first()


# ---------------------------------------------------------------------------
# Per-object upsert helpers
# ---------------------------------------------------------------------------


def _upsert_security_group(
    endpoint: ProxmoxEndpoint,
    raw: dict[str, object],
    synced_ids: set[int],
    result: FirewallSyncResult,
) -> ProxmoxFirewallSecurityGroup | None:
    """Upsert a ProxmoxFirewallSecurityGroup and track its ID."""
    name = raw.get("name") or raw.get("group")
    if not name:
        logger.debug(
            "Skipping security group with no name for endpoint %s", endpoint.pk
        )
        return None
    sg, created = ProxmoxFirewallSecurityGroup.objects.update_or_create(
        endpoint=endpoint,
        name=name,
        defaults={
            "comment": raw.get("comment") or "",
            "status": FirewallSyncStatusChoices.ACTIVE,
            "raw_config": raw,
        },
    )
    synced_ids.add(sg.pk)
    if created:
        result.security_groups_created += 1
    else:
        result.security_groups_updated += 1
    return sg


def _upsert_rule(
    endpoint: ProxmoxEndpoint,
    raw: dict[str, object],
    synced_ids: set[int],
    result: FirewallSyncResult,
    *,
    zone_override: str | None = None,
    sg_obj: ProxmoxFirewallSecurityGroup | None = None,
) -> None:
    """Upsert a ProxmoxFirewallRule."""
    # Skip "vnet" (and any other future skip zones) before applying the
    # caller's zone_override so the raw payload zone still gates the filter.
    raw_zone = raw.get("zone")
    if raw_zone in _SKIP_ZONES:
        return
    zone = zone_override or raw_zone or FirewallZoneChoices.DATACENTER
    if zone in _SKIP_ZONES:
        return

    pos_raw = raw.get("pos")
    if pos_raw is None:
        logger.debug("Skipping rule with no pos in zone %s", zone)
        return
    pos = int(pos_raw)

    enable_raw = raw.get("enable", 1)
    enable = bool(int(enable_raw)) if enable_raw is not None else True

    defaults = {
        "rule_type": raw.get("type") or "",
        "action": raw.get("action") or "",
        "enable": enable,
        "macro": raw.get("macro") or "",
        "iface": raw.get("iface") or "",
        "source": raw.get("source") or "",
        "dest": raw.get("dest") or "",
        "proto": raw.get("proto") or "",
        "dport": raw.get("dport") or "",
        "sport": raw.get("sport") or "",
        "log": raw.get("log") or "",
        "icmp_type": raw.get("icmp_type") or "",
        "comment": raw.get("comment") or None,
        "digest": raw.get("digest") or "",
        "status": FirewallSyncStatusChoices.ACTIVE,
        "raw_config": raw,
    }

    rule, created = ProxmoxFirewallRule.objects.update_or_create(
        endpoint=endpoint,
        zone=zone,
        pos=pos,
        proxmox_node=None,
        virtual_machine=None,
        security_group=sg_obj,
        defaults=defaults,
    )
    synced_ids.add(rule.pk)
    if created:
        result.rules_created += 1
    else:
        result.rules_updated += 1


def _upsert_ipset(
    endpoint: ProxmoxEndpoint,
    raw: dict[str, object],
    synced_sg_ids: set[int],
    synced_entry_ids: set[int],
    result: FirewallSyncResult,
) -> None:
    """Upsert a ProxmoxFirewallIPSet and its entries."""
    name = raw.get("name")
    if not name:
        return

    ipset, created = ProxmoxFirewallIPSet.objects.update_or_create(
        endpoint=endpoint,
        scope=FirewallScopeChoices.DATACENTER,
        name=name,
        virtual_machine=None,
        defaults={
            "comment": raw.get("comment") or None,
            "status": FirewallSyncStatusChoices.ACTIVE,
            "raw_config": raw,
        },
    )
    synced_sg_ids.add(ipset.pk)
    if created:
        result.ipsets_created += 1
    else:
        result.ipsets_updated += 1

    # Sync entries embedded in the response.
    for raw_entry in raw.get("entries") or []:
        cidr = raw_entry.get("cidr")
        if not cidr:
            continue
        nomatch_raw = raw_entry.get("nomatch", False)
        entry, e_created = ProxmoxFirewallIPSetEntry.objects.update_or_create(
            ipset=ipset,
            cidr=cidr,
            defaults={
                "comment": raw_entry.get("comment") or None,
                "nomatch": bool(nomatch_raw),
                "raw_config": raw_entry,
            },
        )
        synced_entry_ids.add(entry.pk)
        if e_created:
            result.ipset_entries_created += 1
        else:
            result.ipset_entries_updated += 1


def _upsert_alias(
    endpoint: ProxmoxEndpoint,
    raw: dict[str, object],
    synced_ids: set[int],
    result: FirewallSyncResult,
) -> None:
    """Upsert a ProxmoxFirewallAlias."""
    name = raw.get("name")
    cidr = raw.get("cidr") or raw.get("ip")
    if not name or not cidr:
        logger.debug(
            "Skipping alias with missing name or cidr for endpoint %s", endpoint.pk
        )
        return

    alias, created = ProxmoxFirewallAlias.objects.update_or_create(
        endpoint=endpoint,
        scope=FirewallScopeChoices.DATACENTER,
        name=name,
        virtual_machine=None,
        defaults={
            "cidr": cidr,
            "comment": raw.get("comment") or None,
            "status": FirewallSyncStatusChoices.ACTIVE,
        },
    )
    synced_ids.add(alias.pk)
    if created:
        result.aliases_created += 1
    else:
        result.aliases_updated += 1


def _upsert_options(
    endpoint: ProxmoxEndpoint,
    raw: dict[str, object] | None,
    synced_ids: set[int],
    result: FirewallSyncResult,
) -> None:
    """Upsert the datacenter-level ProxmoxFirewallOptions record."""
    if not raw:
        return

    enable_raw = raw.get("enable")
    enable = bool(int(enable_raw)) if enable_raw is not None else None

    extra = {
        k: v for k, v in raw.items() if k not in ("enable", "policy_in", "policy_out")
    }

    opts, created = ProxmoxFirewallOptions.objects.update_or_create(
        endpoint=endpoint,
        zone=FirewallZoneChoices.DATACENTER,
        proxmox_node=None,
        virtual_machine=None,
        defaults={
            "enable": enable,
            "policy_in": raw.get("policy_in") or "",
            "policy_out": raw.get("policy_out") or "",
            "options": extra,
            "status": FirewallSyncStatusChoices.ACTIVE,
            "raw_config": raw,
        },
    )
    synced_ids.add(opts.pk)
    if created:
        result.options_created += 1
    else:
        result.options_updated += 1


# ---------------------------------------------------------------------------
# Per-endpoint sync
# ---------------------------------------------------------------------------


def _sync_one_endpoint(
    endpoint: ProxmoxEndpoint,
    summary_entry: dict[str, object],
    result: FirewallSyncResult,
) -> None:
    """Upsert all datacenter-level firewall objects for one endpoint."""
    synced_sg_ids: set[int] = set()
    synced_rule_ids: set[int] = set()
    synced_ipset_ids: set[int] = set()
    synced_entry_ids: set[int] = set()
    synced_alias_ids: set[int] = set()
    synced_opts_ids: set[int] = set()

    with transaction.atomic():
        # -- Security groups and their embedded rules ----------------------
        for raw_sg in summary_entry.get("security_groups") or []:
            sg_obj = _upsert_security_group(endpoint, raw_sg, synced_sg_ids, result)
            if sg_obj is None:
                continue
            for raw_rule in raw_sg.get("rules") or []:
                _upsert_rule(
                    endpoint,
                    raw_rule,
                    synced_rule_ids,
                    result,
                    zone_override=FirewallZoneChoices.SECURITY_GROUP,
                    sg_obj=sg_obj,
                )

        # -- Datacenter-level rules ----------------------------------------
        for raw_rule in summary_entry.get("rules") or []:
            _upsert_rule(
                endpoint,
                raw_rule,
                synced_rule_ids,
                result,
                zone_override=FirewallZoneChoices.DATACENTER,
            )

        # -- IP sets (with embedded entries) ------------------------------
        for raw_ipset in summary_entry.get("ip_sets") or []:
            _upsert_ipset(
                endpoint, raw_ipset, synced_ipset_ids, synced_entry_ids, result
            )

        # -- Aliases -------------------------------------------------------
        for raw_alias in summary_entry.get("aliases") or []:
            _upsert_alias(endpoint, raw_alias, synced_alias_ids, result)

        # -- Options -------------------------------------------------------
        _upsert_options(
            endpoint,
            summary_entry.get("options"),
            synced_opts_ids,
            result,
        )

        # -- Stale detection: mark objects no longer in Proxmox -----------
        stale_sgs = (
            ProxmoxFirewallSecurityGroup.objects.filter(endpoint=endpoint)
            .exclude(pk__in=synced_sg_ids)
            .update(status=FirewallSyncStatusChoices.STALE)
        )
        result.security_groups_stale += stale_sgs

        # Only mark datacenter and security_group rules as stale
        # (node/VM rules were never synced from this call).
        stale_rules = (
            ProxmoxFirewallRule.objects.filter(
                endpoint=endpoint,
                zone__in=[
                    FirewallZoneChoices.DATACENTER,
                    FirewallZoneChoices.SECURITY_GROUP,
                ],
                proxmox_node=None,
                virtual_machine=None,
            )
            .exclude(pk__in=synced_rule_ids)
            .update(status=FirewallSyncStatusChoices.STALE)
        )
        result.rules_stale += stale_rules

        stale_ipsets = (
            ProxmoxFirewallIPSet.objects.filter(
                endpoint=endpoint,
                scope=FirewallScopeChoices.DATACENTER,
                virtual_machine=None,
            )
            .exclude(pk__in=synced_ipset_ids)
            .update(status=FirewallSyncStatusChoices.STALE)
        )
        result.ipsets_stale += stale_ipsets

        # Stale entries: entries whose parent ipset is still active but
        # the cidr is gone from the backend.
        if synced_ipset_ids:
            stale_entries = (
                ProxmoxFirewallIPSetEntry.objects.filter(ipset__in=synced_ipset_ids)
                .exclude(pk__in=synced_entry_ids)
                .delete()
            )
            result.ipset_entries_stale += stale_entries[0]

        stale_aliases = (
            ProxmoxFirewallAlias.objects.filter(
                endpoint=endpoint,
                scope=FirewallScopeChoices.DATACENTER,
                virtual_machine=None,
            )
            .exclude(pk__in=synced_alias_ids)
            .update(status=FirewallSyncStatusChoices.STALE)
        )
        result.aliases_stale += stale_aliases

        stale_opts = (
            ProxmoxFirewallOptions.objects.filter(
                endpoint=endpoint,
                zone=FirewallZoneChoices.DATACENTER,
                proxmox_node=None,
                virtual_machine=None,
            )
            .exclude(pk__in=synced_opts_ids)
            .update(status=FirewallSyncStatusChoices.STALE)
        )
        result.options_stale += stale_opts


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def sync_firewall(
    fastapi_url: str | None = None,
    auth_headers: dict[str, str] | None = None,
    fastapi_endpoint_id: int | None = None,
    endpoint_ids: list[int] | None = None,
) -> FirewallSyncResult:
    """Sync datacenter-level firewall objects for the Proxmox endpoints in scope.

    Calls ``GET /proxmox/firewall/summary`` which returns one entry per
    configured Proxmox endpoint.  Each entry is matched to a
    ``ProxmoxEndpoint`` row via its cluster name and upserted atomically.

    Args:
        fastapi_url: Optional base URL override (resolved from FastAPIEndpoint when omitted).
        auth_headers: Optional auth headers override.
        fastapi_endpoint_id: Optional `FastAPIEndpoint` pk pinning which backend
            row is resolved.  Only consulted when ``fastapi_url`` is omitted; it
            stops a multi-backend install from certifying one backend in the job
            preflight and then syncing against another.
        endpoint_ids: Optional plugin ``ProxmoxEndpoint`` pks narrowing the run.
            A job launched against one endpoint used to sync every enabled
            endpoint's firewall objects anyway, because this pass built its own
            all-enabled scope and never saw the job's selection.  Stale marking
            runs per resolved endpoint, so a narrowed run leaves out-of-scope
            rows untouched.  ``None`` keeps the all-enabled scope.

    Returns:
        FirewallSyncResult with per-model counters and success flag.
    """
    result = FirewallSyncResult()

    verify_ssl = True
    if not fastapi_url:
        ctx = get_fastapi_request_context(endpoint_id=fastapi_endpoint_id)
        if ctx is None or not ctx.http_url:
            result.error = "FastAPI endpoint not configured or has no URL"
            logger.error(result.error)
            return result
        fastapi_url = ctx.http_url
        verify_ssl = bool(ctx.verify_ssl)
        if auth_headers is None:
            auth_headers = ctx.headers or {}

    if auth_headers is None:
        auth_headers = {}

    scope_params, backend_id_by_pk, scope_error = enabled_backend_endpoint_scope(
        base_url=fastapi_url,
        auth_headers=auth_headers,
        backend_verify_ssl=verify_ssl,
        timeout=SYNC_TIMEOUT,
        endpoint_ids=endpoint_ids,
    )
    if scope_error:
        result.error = scope_error
        logger.error(result.error)
        return result
    if scope_params is None:
        result.success = True
        logger.info("No enabled Proxmox endpoints configured; skipping firewall sync")
        return result

    # The scope travels twice: once to the backend as `proxmox_endpoint_ids`,
    # and once here as the set of plugin pks whose response entries may be
    # written. The second leg is not redundant — a backend that ignores the
    # query filter (older release, or a bug) would otherwise hand back every
    # endpoint's clusters, and the by-cluster-name resolution below would
    # happily write firewall rows for endpoints outside this run's selection.
    allowed_endpoint_pks = set(backend_id_by_pk)

    # -----------------------------------------------------------------------
    # HTTP phase — fetch the summary before touching the DB.
    # -----------------------------------------------------------------------
    try:
        resp = requests.get(
            f"{fastapi_url}/proxmox/firewall/summary",
            params=scope_params,
            headers=auth_headers,
            verify=verify_ssl,
            timeout=SYNC_TIMEOUT,
        )
        resp.raise_for_status()
        summary_list = resp.json()
    except requests.RequestException as exc:
        result.error = f"HTTP error fetching firewall summary: {exc}"
        logger.error(result.error)
        return result

    if not isinstance(summary_list, list):
        result.error = f"Unexpected response type from /proxmox/firewall/summary: {type(summary_list).__name__}"
        logger.error(result.error)
        return result

    # -----------------------------------------------------------------------
    # DB phase — one atomic block per endpoint.
    # -----------------------------------------------------------------------
    resolved_endpoints: dict[int, ProxmoxEndpoint] = {}
    endpoint_started_at: dict[int, float] = {}
    per_endpoint_by_id: dict[int, dict[str, object]] = {}

    for entry in summary_list:
        cluster_name = entry.get("cluster_name") or ""
        endpoint = (
            _resolve_endpoint_by_cluster_name(cluster_name) if cluster_name else None
        )

        if endpoint is None:
            logger.warning(
                "Cannot resolve ProxmoxEndpoint for cluster_name=%r — skipping firewall sync for this entry",
                cluster_name,
            )
            continue

        if endpoint.pk not in allowed_endpoint_pks:
            logger.warning(
                "Skipping firewall summary entry for cluster_name=%r: "
                "endpoint %s is outside this run's endpoint scope",
                cluster_name,
                endpoint.pk,
            )
            continue

        ep_result: dict[str, object] = {
            "endpoint_id": endpoint.pk,
            "endpoint_name": str(endpoint),
        }
        endpoint_started_at[endpoint.pk] = time.monotonic()
        per_endpoint_by_id[endpoint.pk] = ep_result
        try:
            _sync_one_endpoint(endpoint, entry, result)
            ep_result["success"] = True
            result.endpoints_processed += 1
            resolved_endpoints[endpoint.pk] = endpoint
            logger.info(
                "Firewall sync for endpoint %s (%s): "
                "%d sg, %d rules, %d ipsets, %d entries, %d aliases, %d opts created/updated",
                endpoint.pk,
                endpoint,
                result.security_groups_created + result.security_groups_updated,
                result.rules_created + result.rules_updated,
                result.ipsets_created + result.ipsets_updated,
                result.ipset_entries_created + result.ipset_entries_updated,
                result.aliases_created + result.aliases_updated,
                result.options_created + result.options_updated,
            )
        except Exception as exc:
            ep_result["success"] = False
            ep_result["error"] = str(exc)
            logger.exception(
                "Error syncing firewall for endpoint %s (%s): %s",
                endpoint.pk,
                endpoint,
                exc,
            )
        finally:
            ep_result["runtime_seconds"] = round(
                time.monotonic() - endpoint_started_at[endpoint.pk],
                3,
            )

        result.per_endpoint.append(ep_result)

    # -----------------------------------------------------------------------
    # Node-level firewall sync — runs after datacenter pass so ProxmoxNode
    # rows already exist for newly-synced endpoints.
    # -----------------------------------------------------------------------
    if resolved_endpoints:
        from netbox_proxbox.models import ProxmoxNode  # noqa: PLC0415

        for endpoint in resolved_endpoints.values():
            nodes = ProxmoxNode.objects.filter(endpoint=endpoint).values_list(
                "name", flat=True
            )
            for node_name in nodes:
                backend_endpoint_id = backend_id_by_pk.get(endpoint.pk)
                if backend_endpoint_id is None:
                    logger.warning(
                        "Skipping node firewall sync for endpoint=%s node=%r: backend endpoint id not resolved",
                        endpoint.pk,
                        node_name,
                    )
                    continue
                try:
                    sync_node_firewall(
                        endpoint=endpoint,
                        node_name=node_name,
                        fastapi_url=fastapi_url,
                        auth_headers=auth_headers,
                        verify_ssl=verify_ssl,
                        backend_endpoint_id=backend_endpoint_id,
                    )
                except Exception as exc:
                    logger.warning(
                        "Node firewall sync failed for endpoint=%s node=%r: %s",
                        endpoint.pk,
                        node_name,
                        exc,
                    )
            ep_result = per_endpoint_by_id.get(endpoint.pk)
            if ep_result is not None:
                ep_result["runtime_seconds"] = round(
                    time.monotonic() - endpoint_started_at[endpoint.pk],
                    3,
                )

    result.success = (
        all(ep.get("success", False) for ep in result.per_endpoint)
        if result.per_endpoint
        else True
    )
    logger.info(
        "Firewall sync complete: %d endpoint(s) processed, success=%s",
        result.endpoints_processed,
        result.success,
    )
    return result


# ---------------------------------------------------------------------------
# Node-level and VM-level firewall helpers (PVE 9.2+)
# ---------------------------------------------------------------------------


def sync_node_firewall(
    endpoint: ProxmoxEndpoint,
    node_name: str,
    fastapi_url: str,
    auth_headers: dict[str, str],
    verify_ssl: bool = True,
    backend_endpoint_id: int | None = None,
) -> None:
    """Sync firewall rules for a single Proxmox node.

    Calls GET /proxmox/firewall/nodes/{node}/rules, then upserts
    ProxmoxFirewallRule rows with zone='node' and the matching
    ProxmoxNode FK set.
    """
    from netbox_proxbox.models import ProxmoxNode  # noqa: PLC0415

    if not bool(getattr(endpoint, "enabled", True)):
        logger.info("Skipping node firewall sync for disabled endpoint %s", endpoint.pk)
        return

    node_obj = ProxmoxNode.objects.filter(endpoint=endpoint, name=node_name).first()
    if node_obj is None:
        logger.debug(
            "Node %r not found in DB for endpoint %s — skipping node firewall sync",
            node_name,
            endpoint.pk,
        )
        return

    # Fetch node rules
    try:
        resp = requests.get(
            f"{fastapi_url}/proxmox/firewall/nodes/{node_name}/rules",
            params=(
                {"source": "database", "proxmox_endpoint_ids": str(backend_endpoint_id)}
                if backend_endpoint_id is not None
                else None
            ),
            headers=auth_headers,
            verify=verify_ssl,
            timeout=SYNC_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, list):
            logger.warning(
                "Node %r firewall rules response is not a list (got %s) — skipping node firewall sync",
                node_name,
                type(data).__name__,
            )
            return
        rules = data
    except requests.RequestException as exc:
        logger.warning("Failed to fetch node %r firewall rules: %s", node_name, exc)
        return

    synced_rule_ids: set[int] = set()

    with transaction.atomic():
        for raw in rules:
            pos_raw = raw.get("pos")
            if pos_raw is None:
                continue
            try:
                pos = int(pos_raw)
            except (ValueError, TypeError):
                logger.warning(
                    "Skipping node %r firewall rule with invalid pos=%r",
                    node_name,
                    pos_raw,
                )
                continue
            enable_raw = raw.get("enable", 1)
            try:
                enable = bool(int(enable_raw)) if enable_raw is not None else True
            except (ValueError, TypeError):
                logger.warning(
                    "Node %r firewall rule at pos=%s has invalid enable=%r; defaulting to enabled",
                    node_name,
                    pos,
                    enable_raw,
                )
                enable = True
            defaults = {
                "rule_type": raw.get("type") or "",
                "action": raw.get("action") or "",
                "enable": enable,
                "macro": raw.get("macro") or "",
                "iface": raw.get("iface") or "",
                "source": raw.get("source") or "",
                "dest": raw.get("dest") or "",
                "proto": raw.get("proto") or "",
                "dport": raw.get("dport") or "",
                "sport": raw.get("sport") or "",
                "log": raw.get("log") or "",
                "icmp_type": raw.get("icmp_type") or "",
                "comment": raw.get("comment") or None,
                "digest": raw.get("digest") or "",
                "status": FirewallSyncStatusChoices.ACTIVE,
                "raw_config": raw,
            }
            rule, _ = ProxmoxFirewallRule.objects.update_or_create(
                endpoint=endpoint,
                zone=FirewallZoneChoices.NODE,
                pos=pos,
                proxmox_node=node_obj,
                virtual_machine=None,
                security_group=None,
                defaults=defaults,
            )
            synced_rule_ids.add(rule.pk)

        # Mark removed node rules as stale
        ProxmoxFirewallRule.objects.filter(
            endpoint=endpoint,
            zone=FirewallZoneChoices.NODE,
            proxmox_node=node_obj,
        ).exclude(pk__in=synced_rule_ids).update(status=FirewallSyncStatusChoices.STALE)

    logger.debug(
        "Node %r firewall sync: %d rules upserted", node_name, len(synced_rule_ids)
    )


def sync_vm_firewall(
    endpoint: ProxmoxEndpoint,
    vmid: int,
    vm_type: str,
    fastapi_url: str,
    auth_headers: dict[str, str],
    verify_ssl: bool = True,
    backend_endpoint_id: int | None = None,
) -> None:
    """Sync firewall rules for a single Proxmox VM or container.

    Calls GET /proxmox/firewall/vms/{vmid}/rules (with vm_type query param),
    then upserts ProxmoxFirewallRule rows with zone='vm_qemu' or 'vm_lxc' and
    the matching VirtualMachine FK set.

    vm_type should be 'qemu' or 'lxc'.
    """
    if not bool(getattr(endpoint, "enabled", True)):
        logger.info("Skipping VM firewall sync for disabled endpoint %s", endpoint.pk)
        return

    if vm_type not in ("qemu", "lxc"):
        logger.warning(
            "sync_vm_firewall called with unknown vm_type=%r for vmid=%d — skipping",
            vm_type,
            vmid,
        )
        return

    from virtualization.models import VirtualMachine  # noqa: PLC0415

    vm_obj = VirtualMachine.objects.filter(
        custom_field_data__proxmox_vm_id=vmid
    ).first()
    if vm_obj is None:
        logger.debug(
            "VM with proxmox_vm_id=%d not found in DB — skipping VM firewall sync", vmid
        )
        return

    zone = (
        FirewallZoneChoices.VM_QEMU if vm_type == "qemu" else FirewallZoneChoices.VM_LXC
    )

    try:
        resp = requests.get(
            f"{fastapi_url}/proxmox/firewall/vms/{vmid}/rules",
            headers=auth_headers,
            verify=verify_ssl,
            timeout=SYNC_TIMEOUT,
            params={
                "vm_type": vm_type,
                **(
                    {
                        "source": "database",
                        "proxmox_endpoint_ids": str(backend_endpoint_id),
                    }
                    if backend_endpoint_id is not None
                    else {}
                ),
            },
        )
        resp.raise_for_status()
        data = resp.json()
        rules = data if isinstance(data, list) else []
    except requests.RequestException as exc:
        logger.warning("Failed to fetch VM %d firewall rules: %s", vmid, exc)
        return

    synced_rule_ids: set[int] = set()

    with transaction.atomic():
        for raw in rules:
            pos_raw = raw.get("pos")
            if pos_raw is None:
                continue
            pos = int(pos_raw)
            enable_raw = raw.get("enable", 1)
            enable = bool(int(enable_raw)) if enable_raw is not None else True
            defaults = {
                "rule_type": raw.get("type") or "",
                "action": raw.get("action") or "",
                "enable": enable,
                "macro": raw.get("macro") or "",
                "iface": raw.get("iface") or "",
                "source": raw.get("source") or "",
                "dest": raw.get("dest") or "",
                "proto": raw.get("proto") or "",
                "dport": raw.get("dport") or "",
                "sport": raw.get("sport") or "",
                "log": raw.get("log") or "",
                "icmp_type": raw.get("icmp_type") or "",
                "comment": raw.get("comment") or None,
                "digest": raw.get("digest") or "",
                "status": FirewallSyncStatusChoices.ACTIVE,
                "raw_config": raw,
            }
            rule, _ = ProxmoxFirewallRule.objects.update_or_create(
                endpoint=endpoint,
                zone=zone,
                pos=pos,
                proxmox_node=None,
                virtual_machine=vm_obj,
                security_group=None,
                defaults=defaults,
            )
            synced_rule_ids.add(rule.pk)

        ProxmoxFirewallRule.objects.filter(
            endpoint=endpoint,
            zone=zone,
            virtual_machine=vm_obj,
        ).exclude(pk__in=synced_rule_ids).update(status=FirewallSyncStatusChoices.STALE)

    logger.debug(
        "VM %d (%s) firewall sync: %d rules upserted",
        vmid,
        vm_type,
        len(synced_rule_ids),
    )
