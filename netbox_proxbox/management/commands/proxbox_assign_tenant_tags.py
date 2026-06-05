"""Django management command to allocate NetBox Tenants from Proxmox tags.

Scans every NetBox ``virtualization.VirtualMachine`` (both QEMU VMs and LXC
containers, which are stored as VirtualMachine rows) that carries the
``cloud-customer`` marker tag and applies the same first-fill, non-destructive
tag-based assignment used post-sync, allocating each object to the tenant named
by its single ``tenant-<slug>`` tag (auto-creating the tenant under the
``cloud-customers`` TenantGroup if missing).

This is the sync-path-independent reconcile for already-synced objects: the
post-sync hook only fires when a batch/manual sync touches an object, so this
command is the headless way to allocate existing inventory after tagging.

Usage:
    python manage.py proxbox_assign_tenant_tags [--dry-run]

``--dry-run`` reports candidate objects without writing. A live run respects
``ProxboxPluginSettings.enable_tenant_tag_assignment`` (and any per-endpoint
override) exactly like the post-sync hook, and never overwrites an existing
tenant assignment.

Exit codes:
    0  completed (with or without assignments)
    non-zero  unexpected error
"""

from __future__ import annotations

import logging
from argparse import ArgumentParser

from django.core.management.base import BaseCommand

from netbox_proxbox.services.tenant_assignment import (
    CLOUD_CUSTOMER_MARKER_SLUG,
    TENANT_TAG_PREFIX,
    maybe_assign_tenant_from_tags,
)

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Command implementation."""

    help = (
        "Allocate NetBox Tenants to Proxmox-synced VMs/LXC from the "
        "'cloud-customer' + 'tenant-<slug>' tag convention."
    )

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report candidate objects and intended assignments without saving.",
        )

    def handle(self, *args: object, **options: object) -> None:
        from virtualization.models import VirtualMachine

        dry_run = bool(options.get("dry_run"))
        queryset = (
            VirtualMachine.objects.filter(tags__slug=CLOUD_CUSTOMER_MARKER_SLUG)
            .distinct()
            .order_by("name")
        )

        scanned = 0
        assigned = 0
        skipped = 0
        for vm in queryset.iterator():
            scanned += 1
            if dry_run:
                tag_slugs = [str(t.slug) for t in vm.tags.all()]
                tenant_tags = [s for s in tag_slugs if s.startswith(TENANT_TAG_PREFIX)]
                current = getattr(vm, "tenant", None)
                self.stdout.write(
                    f"  {vm.name}: tenant_tags={tenant_tags or '-'} "
                    f"current_tenant={getattr(current, 'slug', None) or '-'}"
                )
                continue
            if maybe_assign_tenant_from_tags(vm):
                assigned += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  {vm.name} -> {getattr(vm.tenant, 'slug', None)}"
                    )
                )
            else:
                skipped += 1

        verb = "would scan" if dry_run else "scanned"
        summary = f"proxbox_assign_tenant_tags: {verb} {scanned} tagged object(s)"
        if not dry_run:
            summary += f"; assigned {assigned}; skipped {skipped}"
        self.stdout.write(self.style.SUCCESS(summary))
