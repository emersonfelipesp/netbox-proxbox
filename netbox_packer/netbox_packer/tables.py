"""django-tables2 layouts for netbox-packer UI views."""

from __future__ import annotations

import django_tables2 as tables
from netbox.tables import NetBoxTable
from netbox.tables.columns import BooleanColumn

from netbox_packer.models import (
    PackerImageBuild,
    PackerImageDefinition,
)


_BUILD_STATUS_BADGE = """
{% if value == "completed" %}
  <span class="badge text-bg-green">{{ record.get_status_display }}</span>
{% elif value == "running" %}
  <span class="badge text-bg-blue">{{ record.get_status_display }}</span>
{% elif value == "failed" %}
  <span class="badge text-bg-red">{{ record.get_status_display }}</span>
{% elif value == "cancelled" %}
  <span class="badge text-bg-yellow">{{ record.get_status_display }}</span>
{% else %}
  <span class="badge text-bg-secondary">{{ record.get_status_display }}</span>
{% endif %}
"""

_LAST_BUILD_STATUS_BADGE = """
{% with build=record.builds.first %}
  {% if build %}
    {% if build.status == "completed" %}
      <span class="badge text-bg-green">{{ build.get_status_display }}</span>
    {% elif build.status == "running" %}
      <span class="badge text-bg-blue">{{ build.get_status_display }}</span>
    {% elif build.status == "failed" %}
      <span class="badge text-bg-red">{{ build.get_status_display }}</span>
    {% elif build.status == "cancelled" %}
      <span class="badge text-bg-yellow">{{ build.get_status_display }}</span>
    {% else %}
      <span class="badge text-bg-secondary">{{ build.get_status_display }}</span>
    {% endif %}
  {% else %}
    <span class="text-muted">&mdash;</span>
  {% endif %}
{% endwith %}
"""


class PackerImageDefinitionTable(NetBoxTable):
    name = tables.Column(linkify=True)
    proxmox_endpoint = tables.Column(linkify=True)
    target_cluster = tables.Column(linkify=True)
    enabled = BooleanColumn()
    last_build_at = tables.TemplateColumn(
        template_code=(
            "{% load helpers %}"
            "{% with build=record.builds.first %}"
            "{% if build %}{{ build.started_at|placeholder }}{% else %}"
            '<span class="text-muted">&mdash;</span>{% endif %}{% endwith %}'
        ),
        verbose_name="Last build",
        orderable=False,
    )
    last_build_status = tables.TemplateColumn(
        template_code=_LAST_BUILD_STATUS_BADGE,
        verbose_name="Last status",
        orderable=False,
    )

    class Meta(NetBoxTable.Meta):
        model = PackerImageDefinition
        fields = (
            "pk",
            "id",
            "name",
            "os_family",
            "os_release",
            "builder_type",
            "proxmox_endpoint",
            "target_cluster",
            "target_node",
            "provisioner_recipe",
            "enabled",
            "last_build_at",
            "last_build_status",
            "tags",
            "actions",
        )
        default_columns = (
            "name",
            "os_family",
            "os_release",
            "builder_type",
            "proxmox_endpoint",
            "target_node",
            "provisioner_recipe",
            "enabled",
            "last_build_at",
            "last_build_status",
            "tags",
        )


class PackerImageBuildTable(NetBoxTable):
    id = tables.Column(linkify=True)
    definition = tables.Column(linkify=True)
    status = tables.TemplateColumn(
        template_code=_BUILD_STATUS_BADGE,
        verbose_name="Status",
        order_by=("status",),
    )
    proxmox_endpoint = tables.Column(linkify=True)
    created_by = tables.Column(linkify=True)
    cloud_image_template = tables.Column(linkify=True)

    class Meta(NetBoxTable.Meta):
        model = PackerImageBuild
        fields = (
            "pk",
            "id",
            "definition",
            "status",
            "backend_build_id",
            "proxmox_endpoint",
            "target_node",
            "output_vmid",
            "output_name",
            "image_version",
            "started_at",
            "completed_at",
            "created_by",
            "cloud_image_template",
            "tags",
            "actions",
        )
        default_columns = (
            "id",
            "definition",
            "status",
            "proxmox_endpoint",
            "target_node",
            "output_vmid",
            "output_name",
            "image_version",
            "started_at",
            "completed_at",
            "created_by",
            "cloud_image_template",
        )
