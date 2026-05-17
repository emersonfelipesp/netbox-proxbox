"""Add proxmox-iso builder fields to PackerImageDefinition (PHASE7)."""

from __future__ import annotations

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("netbox_packer", "0001_initial"),
    ]

    operations = [
        # Make source_template_vmid optional (ISO builds don't clone from a template).
        migrations.AlterField(
            model_name="packerimagedefinition",
            name="source_template_vmid",
            field=models.PositiveIntegerField(
                blank=True,
                null=True,
                verbose_name="Source template VMID",
                help_text="Required for proxmox-clone builder type.",
            ),
        ),
        migrations.AddField(
            model_name="packerimagedefinition",
            name="iso_url",
            field=models.URLField(
                blank=True,
                max_length=512,
                verbose_name="ISO URL",
                help_text="Direct URL of the ISO image (proxmox-iso builder only).",
            ),
        ),
        migrations.AddField(
            model_name="packerimagedefinition",
            name="iso_checksum",
            field=models.CharField(
                blank=True,
                max_length=128,
                verbose_name="ISO checksum",
                help_text="SHA-256 checksum prefixed with 'sha256:' (proxmox-iso builder only).",
            ),
        ),
        migrations.AddField(
            model_name="packerimagedefinition",
            name="iso_storage",
            field=models.CharField(
                blank=True,
                max_length=255,
                verbose_name="ISO storage reference",
                help_text=(
                    "Proxmox storage reference for a pre-uploaded ISO "
                    "(e.g. local:iso/ubuntu-22.04.iso). Overrides iso_url if set."
                ),
            ),
        ),
    ]
