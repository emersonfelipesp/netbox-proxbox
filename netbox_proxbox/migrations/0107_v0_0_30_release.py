"""Consolidate the endpoint binding, SSH service, and Cloud Image schema.

Forward application is idempotent for development databases that already
applied ``0107_endpoint_native_cluster_binding``. Its orphan migration-recorder
row is intentionally ignored because this migration has a distinct name and
depends directly on the published ``0106`` boundary.

Reversal removes the SSH-service foreign key and tables and all three Cloud
Image binding columns. It restores the former SSH source choices in migration
state. The endpoint ``netbox_cluster_id`` column, its constraint, and its values
remain physically present while the field leaves migration state, preserving
the cluster-binding downgrade contract; reapplication adopts that column and
does not overwrite an established owner.
"""

import django.contrib.postgres.fields
import django.core.validators
import django.db.models.deletion
import taggit.managers
import utilities.json
from django.db import migrations, models

from ._idempotent_ops import add_field_idempotent, create_model_idempotent


def backfill_cluster_bindings(apps, schema_editor) -> None:
    """Bind only globally unambiguous endpoint and native-cluster pairs."""
    alias = schema_editor.connection.alias
    endpoint = apps.get_model("netbox_proxbox", "ProxmoxEndpoint")
    tracking = apps.get_model("netbox_proxbox", "ProxmoxCluster")
    by_endpoint: dict[int, set[int]] = {}
    by_cluster: dict[int, set[int]] = {}
    retained = endpoint.objects.using(alias).exclude(netbox_cluster_id=None)
    for endpoint_id, cluster_id in retained.values_list(
        "pk", "netbox_cluster_id"
    ).iterator():
        by_cluster.setdefault(cluster_id, set()).add(endpoint_id)
    rows = tracking.objects.using(alias).exclude(netbox_cluster_id=None)
    for endpoint_id, cluster_id in rows.values_list(
        "endpoint_id", "netbox_cluster_id"
    ).iterator():
        by_endpoint.setdefault(endpoint_id, set()).add(cluster_id)
        by_cluster.setdefault(cluster_id, set()).add(endpoint_id)
    for endpoint_id, cluster_ids in by_endpoint.items():
        if len(cluster_ids) != 1:
            continue
        cluster_id = next(iter(cluster_ids))
        if len(by_cluster[cluster_id]) == 1:
            endpoint.objects.using(alias).filter(
                pk=endpoint_id, netbox_cluster__isnull=True
            ).update(netbox_cluster_id=cluster_id)
    if schema_editor.connection.in_atomic_block:
        # PostgreSQL defers existing FK constraint triggers until transaction
        # commit. Fire them before the schema editor runs deferred FK and index
        # DDL at exit, avoiding pending-trigger ALTER TABLE failures.
        with schema_editor.connection.cursor() as cursor:
            cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")


def _netbox_model_fields():
    return [
        (
            "id",
            models.BigAutoField(auto_created=True, primary_key=True, serialize=False),
        ),
        ("created", models.DateTimeField(auto_now_add=True, null=True)),
        ("last_updated", models.DateTimeField(auto_now=True, null=True)),
        (
            "custom_field_data",
            models.JSONField(
                blank=True,
                default=dict,
                encoder=utilities.json.CustomFieldJSONEncoder,
            ),
        ),
        (
            "tags",
            taggit.managers.TaggableManager(
                through="extras.TaggedItem", to="extras.Tag"
            ),
        ),
    ]


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_proxbox", "0106_device_sync_scope_and_netbox_token_approval")
    ]

    operations = [
        add_field_idempotent(
            "proxmoxendpoint",
            "netbox_cluster",
            models.OneToOneField(
                to="virtualization.cluster",
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="proxbox_endpoint",
                null=True,
                blank=True,
                editable=False,
                help_text=(
                    "Native NetBox cluster owned by this endpoint's synchronization."
                ),
            ),
        ),
        create_model_idempotent(
            name="ProxmoxEndpointService",
            fields=[
                *_netbox_model_fields(),
                (
                    "endpoint",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="application_services",
                        to="netbox_proxbox.proxmoxendpoint",
                        verbose_name="Proxmox endpoint",
                    ),
                ),
                ("name", models.CharField(max_length=100, verbose_name="Name")),
                (
                    "protocol",
                    models.CharField(
                        choices=[("tcp", "TCP"), ("udp", "UDP"), ("sctp", "SCTP")],
                        default="tcp",
                        max_length=8,
                        verbose_name="Protocol",
                    ),
                ),
                (
                    "ports",
                    django.contrib.postgres.fields.ArrayField(
                        base_field=models.PositiveIntegerField(
                            validators=[
                                django.core.validators.MinValueValidator(1),
                                django.core.validators.MaxValueValidator(65535),
                            ]
                        ),
                        size=None,
                        verbose_name="Ports",
                    ),
                ),
                ("description", models.CharField(blank=True, max_length=200)),
                ("comments", models.TextField(blank=True)),
                (
                    "ipaddresses",
                    models.ManyToManyField(
                        blank=True,
                        related_name="proxbox_application_services",
                        to="ipam.ipaddress",
                        verbose_name="IP addresses",
                    ),
                ),
            ],
            options={
                "verbose_name": "application service",
                "verbose_name_plural": "application services",
                "ordering": ("endpoint", "name"),
                "constraints": [
                    models.UniqueConstraint(
                        fields=("endpoint", "name"),
                        name=("netbox_proxbox_endpointservice_unique_endpoint_name"),
                    )
                ],
            },
        ),
        create_model_idempotent(
            name="ServiceSSHCredential",
            fields=[
                *_netbox_model_fields(),
                (
                    "service",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="ssh_credential",
                        to="netbox_proxbox.proxmoxendpointservice",
                        verbose_name="Proxmox application service",
                    ),
                ),
                (
                    "username",
                    models.CharField(max_length=64, verbose_name="SSH username"),
                ),
                (
                    "auth_method",
                    models.CharField(
                        choices=[
                            ("key", "SSH private key (recommended)"),
                            ("password", "Password (fallback)"),
                        ],
                        default="key",
                        max_length=8,
                        verbose_name="Authentication method",
                    ),
                ),
                (
                    "storage_backend",
                    models.CharField(
                        choices=[
                            (
                                "legacy_encrypted",
                                "Legacy Fernet-encrypted local storage",
                            ),
                            ("openbao", "OpenBao"),
                        ],
                        default="legacy_encrypted",
                        max_length=32,
                        verbose_name="Credential storage backend",
                    ),
                ),
                (
                    "password_enc",
                    models.TextField(blank=True, default="", editable=False),
                ),
                (
                    "private_key_enc",
                    models.TextField(blank=True, default="", editable=False),
                ),
                (
                    "openbao_password_credential_uuid",
                    models.UUIDField(blank=True, editable=False, null=True),
                ),
                (
                    "openbao_keypair_credential_uuid",
                    models.UUIDField(blank=True, editable=False, null=True),
                ),
                ("description", models.CharField(blank=True, max_length=200)),
            ],
            options={
                "verbose_name": "Service SSH credential",
                "verbose_name_plural": "Service SSH credentials",
                "ordering": ("service",),
            },
        ),
        add_field_idempotent(
            "proxmoxendpoint",
            "ssh_service",
            models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to="netbox_proxbox.proxmoxendpointservice",
                verbose_name="SSH application service",
                help_text=(
                    "Application service that owns this endpoint's SSH credential."
                ),
            ),
            remove_on_reverse=True,
        ),
        migrations.AlterField(
            model_name="proxmoxendpoint",
            name="ssh_credential_source",
            field=models.CharField(
                choices=[
                    ("dedicated", "Dedicated SSH credential"),
                    ("reuse_endpoint", "Reuse endpoint username/password"),
                    ("service", "SSH credential on an application service"),
                ],
                default="dedicated",
                help_text=(
                    "Choose an application-service credential, a dedicated endpoint "
                    "credential, or the endpoint's Proxmox username/password. Reuse "
                    "strips the realm (for example, root@pam becomes root); only "
                    "PAM-backed Proxmox users usually map to local SSH accounts."
                ),
                max_length=32,
                verbose_name="SSH credential source",
            ),
        ),
        add_field_idempotent(
            "proxmoxendpoint",
            "cloud_image_ssh_target_node",
            models.CharField(
                blank=True,
                default="",
                db_default="",
                help_text=(
                    "Proxmox node that the Cloud Image bake SSH host belongs to."
                ),
                max_length=255,
                verbose_name="Cloud Image SSH target node",
            ),
            remove_on_reverse=True,
        ),
        add_field_idempotent(
            "proxmoxendpoint",
            "cloud_image_ssh_identity_file",
            models.CharField(
                blank=True,
                default="",
                db_default="",
                help_text=(
                    "Absolute path on the proxbox-api host. proxbox-api validates "
                    "that the path is under PROXBOX_SSH_KEY_DIR."
                ),
                max_length=4096,
                verbose_name="Cloud Image SSH identity file",
            ),
            remove_on_reverse=True,
        ),
        add_field_idempotent(
            "proxmoxendpoint",
            "cloud_image_ssh_binding_fingerprint",
            models.CharField(
                blank=True,
                default="",
                db_default="",
                editable=False,
                help_text=(
                    "SHA-256 of the Cloud Image SSH binding NetBox last pushed; "
                    "empty means NetBox has not pushed one (an externally managed "
                    "backend binding is left untouched)."
                ),
                max_length=64,
            ),
            remove_on_reverse=True,
        ),
        migrations.RunPython(
            backfill_cluster_bindings,
            migrations.RunPython.noop,
        ),
    ]
