"""netbox-proxbox 0.0.33 release migration.

Adds the Proxmox VE 9.3 stable guest and cluster identity fields and the exact
hostname allowlist for Proxmox ISO URL downloads. This is the single schema
migration of the 0.0.33 release; it consolidates the development-only
``0110_storage_download_allowed_hosts`` migration, which was never published.
"""

from django.core.validators import RegexValidator
from django.db import migrations, models

from netbox_proxbox.migrations._idempotent_ops import add_field_idempotent


class Migration(migrations.Migration):
    dependencies = [("netbox_proxbox", "0108_v0_0_31_schema_validation")]

    operations = [
        add_field_idempotent(
            model_name="proxmoxcluster",
            field_name="proxmox_cluster_uid",
            field=models.CharField(
                blank=True,
                db_default="",
                default="",
                help_text="Stable cluster-id reported by Proxmox VE 9.3 or later.",
                max_length=64,
                validators=[
                    RegexValidator(
                        regex=r"^[^\s\x00-\x1f\x7f]+\Z",
                        message=(
                            "Cluster UID cannot contain whitespace or control characters."
                        ),
                    )
                ],
                verbose_name="Proxmox cluster UID",
            ),
        ),
        add_field_idempotent(
            model_name="proxboxvirtualmachinesyncstate",
            field_name="proxmox_cluster_uid",
            field=models.CharField(
                blank=True,
                db_default="",
                default="",
                max_length=64,
                validators=[
                    RegexValidator(
                        regex=r"^[^\s\x00-\x1f\x7f]+\Z",
                        message=(
                            "Cluster UID cannot contain whitespace or control characters."
                        ),
                    )
                ],
            ),
        ),
        add_field_idempotent(
            model_name="proxboxvirtualmachinesyncstate",
            field_name="proxmox_vm_uid",
            field=models.CharField(
                blank=True,
                db_index=True,
                db_default="",
                default="",
                max_length=20,
                validators=[
                    RegexValidator(
                        regex=r"^[a-z2-7]{20}$",
                        message="Enter a valid 20-character Proxmox guest UID.",
                    )
                ],
            ),
        ),
        migrations.AddConstraint(
            model_name="proxboxvirtualmachinesyncstate",
            constraint=models.UniqueConstraint(
                fields=("proxmox_cluster_uid", "proxmox_vm_uid"),
                condition=(
                    ~models.Q(proxmox_vm_uid="") & ~models.Q(proxmox_cluster_uid="")
                ),
                name="netbox_proxbox_vm_sync_unique_cluster_guest_uid",
            ),
        ),
        add_field_idempotent(
            model_name="proxboxpluginsettings",
            field_name="storage_download_allowed_hosts",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text=(
                    "Exact hostnames allowed for Proxmox ISO URL downloads, one per "
                    "entry. Downloads use HTTPS port 443 only; an empty list denies "
                    "every download. Allow only trusted vendor hosts that do not "
                    "provide open redirects."
                ),
                verbose_name="Storage download allowed hosts",
            ),
        ),
    ]
