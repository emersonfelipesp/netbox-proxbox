"""Shared validation for public Proxbox configuration fields."""

from __future__ import annotations

import re
from string import Formatter
from itertools import chain
from typing import Iterable

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

NODE_DEVICE_NAME_PLACEHOLDERS = frozenset(
    {"node", "cluster", "cluster_slug", "endpoint"}
)
_DNS_NAME_PATTERN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?$")
_DNS_LABEL_PATTERN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?$")
_FORMATTER = Formatter()


def slugify_cluster_name(value: str) -> str:
    """Return the backend-compatible DNS-label-safe cluster slug."""

    slug = re.sub(r"[^a-z0-9]+", "-", (value or "").strip().lower()).strip("-")
    return slug or "cluster"


def _validate_rendered_node_device_name(name: str) -> None:
    if not name or len(name) > 64 or not _DNS_NAME_PATTERN.fullmatch(name):
        raise ValidationError(
            _(
                "Rendered node device name must be 1-64 DNS-safe letters, digits, hyphens, or dots."
            )
        )
    labels = name.split(".")
    if any(
        not label or len(label) > 63 or not _DNS_LABEL_PATTERN.fullmatch(label)
        for label in labels
    ):
        raise ValidationError(
            _("Rendered node device name contains an invalid DNS label.")
        )


def validate_node_device_name_template(value: str) -> None:
    """Validate the restricted node Device name format language."""

    template = str(value or "").strip()
    if not template:
        raise ValidationError(_("Node device name template must not be blank."))
    fields: set[str] = set()
    try:
        parsed = list(_FORMATTER.parse(template))
    except ValueError as error:
        raise ValidationError(
            _("Invalid node device name template: %(error)s"), params={"error": error}
        ) from error
    for _literal, field_name, format_spec, conversion in parsed:
        if field_name is None:
            continue
        if field_name not in NODE_DEVICE_NAME_PLACEHOLDERS:
            raise ValidationError(
                _("Unknown node device name placeholder: %(field)s."),
                params={"field": field_name},
            )
        if format_spec:
            raise ValidationError(
                _("Node device name placeholders do not support format specs.")
            )
        if conversion:
            raise ValidationError(
                _("Node device name placeholders do not support conversions.")
            )
        fields.add(field_name)
    if "node" not in fields:
        raise ValidationError(_("Node device name template must contain {node}."))
    _validate_rendered_node_device_name(
        template.format(
            node="node",
            cluster="cluster",
            cluster_slug="cluster",
            endpoint="endpoint",
        )
    )


def render_node_device_name(
    template: str, *, node: str, cluster: str, endpoint: str
) -> str:
    """Render and validate a node Device name using backend semantics."""

    rendered = template.format(
        node=node,
        cluster=cluster,
        cluster_slug=slugify_cluster_name(cluster),
        endpoint=endpoint,
    )
    _validate_rendered_node_device_name(rendered)
    return rendered


def validate_node_device_name_inventory(
    template: str,
    rows: Iterable[tuple[str, str | None, str]],
) -> None:
    """Validate a template against bounded synchronized inventory values."""

    validate_node_device_name_template(template)
    for node, cluster_value, endpoint in rows:
        cluster = str(cluster_value or "")
        try:
            render_node_device_name(
                template,
                node=str(node),
                cluster=cluster,
                endpoint=str(endpoint),
            )
        except ValidationError as error:
            rendered = template.format(
                node=node,
                cluster=cluster,
                cluster_slug=slugify_cluster_name(cluster),
                endpoint=endpoint,
            )
            raise ValidationError(
                _(
                    "Node device name template renders node '%(node)s' in cluster "
                    "'%(cluster)s' as %(length)d characters: %(error)s"
                ),
                params={
                    "node": node,
                    "cluster": cluster or "(none)",
                    "length": len(rendered),
                    "error": error,
                },
            ) from error


def effective_node_device_name_template(endpoint_override: object) -> str:
    """Resolve an endpoint override against the current global template."""

    override = str(endpoint_override or "").strip()
    if override:
        return override

    from netbox_proxbox.models import ProxboxPluginSettings

    return str(ProxboxPluginSettings.get_solo().node_device_name_template).strip()


def validate_endpoint_node_device_name_template(
    template: str, *, endpoint_id: object | None, endpoint_name: str
) -> None:
    """Validate an endpoint's effective template against its name and nodes."""

    from netbox_proxbox.models import ProxmoxNode

    effective_template = effective_node_device_name_template(template)
    normalized_endpoint_name = str(endpoint_name or "")
    inventory: Iterable[tuple[str, str | None, str]] = ()
    if endpoint_id is not None:
        rows = ProxmoxNode.objects.filter(endpoint_id=endpoint_id).values_list(
            "name", "proxmox_cluster__name"
        )
        inventory = (
            (node, cluster, normalized_endpoint_name) for node, cluster in rows
        )
    sentinel = (("node", "cluster", normalized_endpoint_name),)
    validate_node_device_name_inventory(
        effective_template,
        chain(sentinel, inventory),
    )


def validate_global_node_device_name_template(template: str) -> None:
    """Validate the global template against nodes whose endpoints inherit it."""

    from netbox_proxbox.models import ProxmoxEndpoint, ProxmoxNode

    node_rows = ProxmoxNode.objects.filter(
        endpoint__node_device_name_template=""
    ).values_list("name", "proxmox_cluster__name", "endpoint__name")
    endpoint_names = ProxmoxEndpoint.objects.filter(
        node_device_name_template=""
    ).values_list("name", flat=True)
    sentinels = (
        ("node", "cluster", str(endpoint_name or ""))
        for endpoint_name in endpoint_names
    )
    validate_node_device_name_inventory(template, chain(sentinels, node_rows))
