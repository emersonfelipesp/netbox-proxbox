# Squashes netbox_proxbox migrations from v0.0.6b2.post1 (after 0008) through v0.0.8.
# Replaces: 0009_vmbackup through 0015_remove_syncprocess (inclusive of merge migrations).

import django.db.models.deletion
import netbox.models.deletion
import netbox_proxbox.fields
import taggit.managers
import utilities.json
from django.db import migrations, models


class Migration(migrations.Migration):
    replaces = [
        ("netbox_proxbox", "0009_vmbackup"),
        ("netbox_proxbox", "0010_alter_fastapiendpoint_options_and_more"),
        ("netbox_proxbox", "0010_netboxendpoint_token_v2_support"),
        ("netbox_proxbox", "0011_merge_0010_heads"),
        ("netbox_proxbox", "0011_merge_20260328_1454"),
        ("netbox_proxbox", "0012_merge_0011_merge_0010_heads_0011_merge_20260328_1454"),
        ("netbox_proxbox", "0013_make_domains_optional_and_require_host_target"),
        ("netbox_proxbox", "0014_vmsnapshot"),
        ("netbox_proxbox", "0015_remove_syncprocess"),
    ]

    dependencies = [
        ("extras", "0134_owner"),
        ("ipam", "0086_gfk_indexes"),
        ("netbox_proxbox", "0008_alter_proxmoxendpoint_unique_together_and_more"),
        ("users", "0015_owner"),
        ("virtualization", "0048_populate_mac_addresses"),
        ("virtualization", "0052_gfk_indexes"),
    ]

    operations = [
        migrations.CreateModel(
            name="VMBackup",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False
                    ),
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
                ("storage", models.CharField(max_length=255, null=True)),
                ("subtype", models.CharField(default="undefined", max_length=255)),
                ("format", models.CharField(default="undefined", max_length=255)),
                ("creation_time", models.DateTimeField(blank=True, null=True)),
                ("size", models.BigIntegerField(blank=True, null=True)),
                ("notes", models.TextField(blank=True, null=True)),
                ("volume_id", models.CharField(blank=True, max_length=255, null=True)),
                ("vmid", models.IntegerField(blank=True, null=True)),
                ("used", models.BigIntegerField(blank=True, null=True)),
                ("encrypted", models.BooleanField(default=False)),
                (
                    "verification_state",
                    models.CharField(blank=True, max_length=255, null=True),
                ),
                (
                    "verification_upid",
                    models.CharField(blank=True, max_length=255, null=True),
                ),
                (
                    "tags",
                    taggit.managers.TaggableManager(
                        through="extras.TaggedItem", to="extras.Tag"
                    ),
                ),
                (
                    "virtual_machine",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="backups",
                        to="virtualization.virtualmachine",
                    ),
                ),
            ],
            options={
                "verbose_name": "VM Backup",
                "verbose_name_plural": "VM Backups",
                "ordering": ("storage", "virtual_machine", "creation_time"),
                "unique_together": {
                    (
                        "storage",
                        "virtual_machine",
                        "subtype",
                        "format",
                        "creation_time",
                        "volume_id",
                        "vmid",
                    )
                },
            },
        ),
        migrations.AddField(
            model_name="netboxendpoint",
            name="token_key",
            field=models.CharField(
                blank=True,
                help_text="Key portion of a NetBox v2 API token.",
                max_length=255,
                verbose_name="Token Key",
            ),
        ),
        migrations.AddField(
            model_name="netboxendpoint",
            name="token_secret",
            field=models.CharField(
                blank=True,
                help_text="Secret portion of a NetBox v2 API token.",
                max_length=255,
                verbose_name="Token Secret",
            ),
        ),
        migrations.AddField(
            model_name="netboxendpoint",
            name="token_version",
            field=models.CharField(
                choices=[("v1", "v1 Token"), ("v2", "v2 Token")],
                default="v1",
                help_text=(
                    "Choose whether to authenticate using a v1 token or a v2 token "
                    "key/secret pair."
                ),
                max_length=2,
                verbose_name="Token Version",
            ),
        ),
        migrations.AlterModelOptions(
            name="fastapiendpoint",
            options={"ordering": ("name", "pk")},
        ),
        migrations.AlterModelOptions(
            name="netboxendpoint",
            options={"ordering": ("name", "pk")},
        ),
        migrations.AlterModelOptions(
            name="proxmoxendpoint",
            options={"ordering": ("name", "pk")},
        ),
        migrations.AlterModelOptions(
            name="syncprocess",
            options={"ordering": ("-created", "-pk")},
        ),
        migrations.AlterUniqueTogether(
            name="fastapiendpoint",
            unique_together=set(),
        ),
        migrations.AlterUniqueTogether(
            name="netboxendpoint",
            unique_together=set(),
        ),
        migrations.AlterUniqueTogether(
            name="proxmoxendpoint",
            unique_together=set(),
        ),
        migrations.AlterField(
            model_name="proxmoxendpoint",
            name="token_name",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AlterField(
            model_name="proxmoxendpoint",
            name="token_value",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AddConstraint(
            model_name="fastapiendpoint",
            constraint=models.UniqueConstraint(
                fields=("name", "ip_address"),
                name="netbox_proxbox_fastapiendpoint_identity",
            ),
        ),
        migrations.AddConstraint(
            model_name="netboxendpoint",
            constraint=models.UniqueConstraint(
                fields=("name", "ip_address"),
                name="netbox_proxbox_netboxendpoint_identity",
            ),
        ),
        migrations.AddConstraint(
            model_name="proxmoxendpoint",
            constraint=models.UniqueConstraint(
                fields=("name", "ip_address", "domain"),
                name="netbox_proxbox_proxmoxendpoint_identity",
            ),
        ),
        migrations.AlterField(
            model_name="fastapiendpoint",
            name="domain",
            field=netbox_proxbox.fields.DomainField(
                blank=True,
                help_text="Domain name of the ProxBox backend service.",
                max_length=253,
                null=True,
                verbose_name="Domain",
            ),
        ),
        migrations.AlterField(
            model_name="netboxendpoint",
            name="domain",
            field=netbox_proxbox.fields.DomainField(
                blank=True,
                help_text="Domain name of the remote NetBox API.",
                max_length=253,
                null=True,
                verbose_name="Domain",
            ),
        ),
        migrations.CreateModel(
            name="VMSnapshot",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False
                    ),
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
                ("name", models.CharField(max_length=255)),
                ("description", models.TextField(blank=True, null=True)),
                ("vmid", models.IntegerField()),
                ("node", models.CharField(max_length=255)),
                ("snaptime", models.DateTimeField(blank=True, null=True)),
                ("parent", models.CharField(blank=True, max_length=255, null=True)),
                ("subtype", models.CharField(default="qemu", max_length=255)),
                ("status", models.CharField(default="active", max_length=255)),
                (
                    "tags",
                    taggit.managers.TaggableManager(
                        through="extras.TaggedItem", to="extras.Tag"
                    ),
                ),
                (
                    "virtual_machine",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="snapshots",
                        to="virtualization.virtualmachine",
                    ),
                ),
            ],
            options={
                "verbose_name": "VM Snapshot",
                "verbose_name_plural": "VM Snapshots",
                "ordering": ("virtual_machine", "node", "name"),
                "unique_together": {("vmid", "name", "node")},
            },
            bases=(netbox.models.deletion.DeleteMixin, models.Model),
        ),
        migrations.DeleteModel(
            name="SyncProcess",
        ),
    ]
