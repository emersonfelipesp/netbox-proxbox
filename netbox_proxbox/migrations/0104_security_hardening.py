"""Release 0.0.29 schema: sensitive-data grants, connection-target approval,
secure transport defaults, and the backend settings-read grant.

This is the single migration for the 0.0.29 release. It consolidates the
unpublished development migrations that followed the immutable 0.0.27.post1
boundary (``0103_custom_fields_request_delay_help_text``):

* ``ProxboxSensitiveDataAccess`` holds default-off per-user sensitive-data
  grants. Nothing is backfilled.
* ``approved_connection_target_fingerprint`` on NetBox and Proxmox endpoints is
  internal, non-editable, and blank, so every existing endpoint requires an
  explicit approval before credentials are sent. Nothing is backfilled.
* ``FastAPIEndpoint.use_https`` and ``ProxmoxEndpoint.verify_ssl`` default to
  ``True``. This is state-only: Django applies field defaults in Python, so
  existing rows keep their stored values. The ``netbox_proxbox.W10x`` system
  checks report existing insecure endpoints.
* Plugin settings reads now require ``view_proxboxpluginsettings``. Released
  proxbox-api clients fall back to their own defaults when that read is denied,
  which can be more permissive than the configured SSRF policy. To keep
  existing installations safe across the upgrade, a view-only object
  permission on the settings model is granted to the users behind the NetBox
  API tokens already configured on enabled NetBox endpoints. It grants nothing
  else and is a no-op when no such token exists; the ``netbox_proxbox.W105``
  system check covers endpoints configured later. Reversal leaves the grant in
  place (it is view-only and harmless on the earlier schema).
"""

import django.db.models.deletion
import netbox.models.deletion
import taggit.managers
import utilities.json
from django.conf import settings
from django.db import migrations, models

PERMISSION_NAME = "Proxbox backend: read plugin settings"
_TOKEN_PREFIX = "nbt_"


def _backend_token_user_ids(apps, alias: str) -> set[int]:
    netbox_endpoint = apps.get_model("netbox_proxbox", "NetBoxEndpoint")
    token_model = apps.get_model("users", "Token")
    user_ids: set[int] = set()
    for endpoint in netbox_endpoint.objects.using(alias).filter(enabled=True):
        token = None
        if endpoint.token_id:
            token = (
                token_model.objects.using(alias).filter(pk=endpoint.token_id).first()
            )
        elif endpoint.token_key:
            key = str(endpoint.token_key).strip().removeprefix(_TOKEN_PREFIX)
            token = token_model.objects.using(alias).filter(key=key).first()
        if token is not None and token.user_id:
            user_ids.add(token.user_id)
    return user_ids


def _safe_settings_view_permission(permissions, content_type_id: int):
    """Return an existing enabled, unconstrained, view-only settings permission."""
    candidates = permissions.filter(
        name=PERMISSION_NAME, enabled=True, constraints__isnull=True
    ).order_by("pk")
    for candidate in candidates:
        object_types = list(candidate.object_types.values_list("pk", flat=True))
        if list(candidate.actions) == ["view"] and object_types == [content_type_id]:
            return candidate
    return None


def grant_backend_settings_read(apps, schema_editor) -> None:
    alias = schema_editor.connection.alias
    user_ids = _backend_token_user_ids(apps, alias)
    if not user_ids:
        return
    content_type_model = apps.get_model("contenttypes", "ContentType")
    permission_model = apps.get_model("users", "ObjectPermission")
    content_type, _ = content_type_model.objects.using(alias).get_or_create(
        app_label="netbox_proxbox", model="proxboxpluginsettings"
    )
    permission = _safe_settings_view_permission(
        permission_model.objects.using(alias), content_type.pk
    )
    if permission is None:
        # Never reuse a same-named permission with broader actions, other
        # object types, constraints, or a disabled state: create a new one.
        permission = permission_model.objects.using(alias).create(
            name=PERMISSION_NAME,
            description=(
                "Granted on upgrade so proxbox-api keeps reading the configured "
                "plugin settings; view only."
            ),
            enabled=True,
            actions=["view"],
        )
        permission.object_types.add(content_type)
    permission.users.add(*sorted(user_ids))


class Migration(migrations.Migration):
    dependencies = [
        ("netbox_proxbox", "0103_custom_fields_request_delay_help_text"),
        ("users", "0015_owner"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ProxboxSensitiveDataAccess",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False
                    ),
                ),
                ("created", models.DateTimeField(auto_now_add=True, null=True)),
                (
                    "last_updated",
                    models.DateTimeField(auto_now=True, blank=True, null=True),
                ),
                (
                    "custom_field_data",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        encoder=utilities.json.CustomFieldJSONEncoder,
                    ),
                ),
                (
                    "can_access_sensitive_data",
                    models.BooleanField(
                        default=False,
                        help_text="Allow sensitive credential disclosure within existing object and provider permissions. Only an active superuser may change this grant.",
                    ),
                ),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="proxbox_sensitive_data_access",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "tags",
                    taggit.managers.TaggableManager(
                        through="extras.TaggedItem", to="extras.Tag"
                    ),
                ),
            ],
            options={
                "ordering": ("user_id",),
                "verbose_name": "Proxbox sensitive data access",
                "verbose_name_plural": "Proxbox sensitive data access grants",
            },
            bases=(netbox.models.deletion.DeleteMixin, models.Model),
        ),
        *(
            migrations.AddField(
                model_name=model_name,
                name="approved_connection_target_fingerprint",
                field=models.CharField(
                    max_length=64,
                    blank=True,
                    default="",
                    editable=False,
                    help_text="Internal approval of the exact connection target. Target edits require explicit reapproval before credentials may be sent.",
                ),
            )
            for model_name in ("netboxendpoint", "proxmoxendpoint")
        ),
        migrations.AlterField(
            model_name="fastapiendpoint",
            name="use_https",
            field=models.BooleanField(default=True),
        ),
        migrations.AlterField(
            model_name="proxmoxendpoint",
            name="verify_ssl",
            field=models.BooleanField(default=True),
        ),
        migrations.RunPython(
            grant_backend_settings_read, reverse_code=migrations.RunPython.noop
        ),
    ]
