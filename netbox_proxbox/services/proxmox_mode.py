"""Shared Proxmox endpoint mode derivation helpers."""

from __future__ import annotations

from collections.abc import Iterable, Sized

from netbox_proxbox.choices import ProxmoxModeChoices


def derive_proxmox_endpoint_mode(
    cluster_record: object | None,
    node_records: Iterable[object],
) -> str:
    """Return endpoint mode from cluster topology only.

    Quorum is a health signal, not a topology signal. A one-node topology is
    treated as standalone even when Proxmox reports a named cluster record.
    """
    node_count = (
        len(node_records)
        if isinstance(node_records, Sized)
        else sum(1 for _node in node_records)
    )

    if cluster_record is not None and node_count > 1:
        return ProxmoxModeChoices.PROXMOX_MODE_CLUSTER
    if node_count == 1:
        return ProxmoxModeChoices.PROXMOX_MODE_STANDALONE
    return ProxmoxModeChoices.PROXMOX_MODE_UNDEFINED
