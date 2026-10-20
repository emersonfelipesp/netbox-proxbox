"""Secret-free Cloud Image SSH node-to-host verification."""

from __future__ import annotations

from collections.abc import Iterable
from ipaddress import ip_interface


def normalize_host(value: object) -> str:
    """Normalize an IP, CIDR, or case-insensitive host name for comparison."""
    text = str(getattr(value, "address", value) or "").strip().rstrip(".")
    try:
        return str(ip_interface(text).ip)
    except ValueError:
        return text.casefold()


def _candidate_nodes(endpoint: object) -> Iterable[object]:
    """Return inventory nodes owned directly or through this endpoint's cluster."""
    endpoint_id = getattr(endpoint, "pk", None)
    if endpoint_id is None:
        return ()
    from django.db.models import Q

    from netbox_proxbox.models import ProxmoxNode

    return ProxmoxNode.objects.filter(
        Q(endpoint_id=endpoint_id) | Q(proxmox_cluster__endpoint_id=endpoint_id)
    ).only("name", "ip_address")


def cloud_image_ssh_target_matches_host(
    endpoint: object,
    *,
    target_node: object | None = None,
    ssh_host: object | None = None,
) -> bool:
    """Return whether inventory proves the selected node is reached by SSH host."""
    wanted_node = str(
        target_node
        if target_node is not None
        else getattr(endpoint, "cloud_image_ssh_target_node", "")
    ).strip()
    wanted_host = normalize_host(
        ssh_host if ssh_host is not None else getattr(endpoint, "ssh_host", "")
    )
    if not wanted_node or not wanted_host:
        return False
    matching_names = {
        str(getattr(node, "name", "") or "").strip().casefold()
        for node in _candidate_nodes(endpoint)
        if normalize_host(getattr(node, "ip_address", "")) == wanted_host
    }
    return len(matching_names) == 1 and matching_names == {wanted_node.casefold()}
