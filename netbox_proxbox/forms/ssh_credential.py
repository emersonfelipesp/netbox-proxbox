"""Forms for per-node SSH credentials used by hardware discovery."""

from __future__ import annotations

from django import forms
from django.views.decorators.debug import sensitive_variables
from utilities.forms.fields import DynamicModelChoiceField

from netbox.forms import NetBoxModelFilterSetForm, NetBoxModelForm
from netbox_proxbox.models import NodeSSHCredential, ProxmoxNode, ProxboxPluginSettings
from netbox_proxbox.models.ssh_credential import normalize_fingerprint
from netbox_proxbox.utils import encryption as enc_helpers


class _WriteOnlyTextarea(forms.Textarea):
    """Accept multiline input without ever redisplaying its secret value."""

    def format_value(self, value: object) -> None:
        """Suppress submitted and initial values during widget rendering."""
        return None


class NodeSSHCredentialForm(NetBoxModelForm):
    """Create or edit one Proxmox node SSH credential without echoing secrets."""

    node = DynamicModelChoiceField(
        queryset=ProxmoxNode.objects.all(),
        required=True,
        label="Proxmox node",
    )
    password = forms.CharField(
        required=False,
        widget=forms.PasswordInput(render_value=False),
        label="SSH password",
        help_text="Optional fallback password. Leave blank on edit to keep the stored value.",
    )
    private_key = forms.CharField(
        required=False,
        widget=_WriteOnlyTextarea(attrs={"rows": 8, "autocomplete": "off"}),
        label="SSH private key",
        help_text=(
            "Recommended authentication secret. Leave blank on edit to keep the "
            "stored value. For safety, submitted keys are never redisplayed after "
            "a validation error."
        ),
    )

    class Meta:
        model = NodeSSHCredential
        fields = (
            "node",
            "username",
            "port",
            "auth_method",
            "known_host_fingerprint",
            "sudo_required",
            "tags",
        )

    @sensitive_variables()
    def __init__(self, *args: object, **kwargs: object) -> None:
        """Surface undecryptable stored values without pre-filling secrets."""
        self._request = kwargs.pop("request", None)
        self._request_user = kwargs.pop("request_user", None)
        if self._request_user is None and self._request is not None:
            self._request_user = getattr(self._request, "user", None)
        if self._request_user is None:
            from netbox_proxbox.integrations.openbao_node_transaction import (
                current_node_request,
                current_node_request_actor,
            )

            self._request_user = current_node_request_actor()
            self._request = current_node_request()
        super().__init__(*args, **kwargs)
        instance = getattr(self, "instance", None)
        if (
            instance
            and getattr(instance, "pk", None)
            and instance.credential_encryption_state == "Recovery required"
        ):
            warning = (
                " Recovery required: at least one stored SSH secret cannot be "
                "decrypted. Enter a replacement secret or use destructive recovery."
            )
            self.fields["password"].help_text += warning
            self.fields["private_key"].help_text += warning

    def clean_known_host_fingerprint(self) -> str:
        """Normalize host-key fingerprints at form level for user feedback."""
        value = self.cleaned_data["known_host_fingerprint"]
        return normalize_fingerprint(value)

    def _storage_key(self) -> str:
        from netbox_proxbox.integrations.openbao import node_uses_openbao_storage

        if node_uses_openbao_storage(self.instance):
            return ""
        settings_obj = ProxboxPluginSettings.get_solo()
        key = settings_obj.encryption_key or ""
        if not key:
            raise forms.ValidationError(
                "Configure ProxboxPluginSettings.encryption_key before storing SSH secrets."
            )
        return key

    @sensitive_variables()
    def _apply_secret_inputs(self) -> None:
        password = self.cleaned_data.get("password")
        private_key = self.cleaned_data.get("private_key")
        if not password and not private_key:
            return
        key = self._storage_key()

        try:
            if password:
                self.instance.set_password(
                    password,
                    key=key,
                    user=self._request_user,
                    request=self._request,
                )
            if private_key:
                self.instance.set_private_key(
                    private_key,
                    key=key,
                    user=self._request_user,
                    request=self._request,
                )
        except (forms.ValidationError, enc_helpers.EncryptionError) as exc:
            raise forms.ValidationError(str(exc)) from exc

    @sensitive_variables()
    def _prepare_secret_context(self) -> None:
        node = self.cleaned_data.get("node")
        if node is not None:
            self.instance.node = node
        if self._request_user is not None:
            self.instance._openbao_actor_user = self._request_user

    @sensitive_variables()
    def _post_clean(self) -> None:
        """Encrypt write-only secret fields, then delegate to the NetBox chain.

        The encryption runs first because ``NodeSSHCredential.clean()`` requires
        the matching ``*_enc`` field to already be populated for the selected
        ``auth_method``, and ``super()._post_clean()`` is what triggers
        ``full_clean()``. Writing the secrets here is safe: ``construct_instance``
        only assigns fields listed in ``Meta.fields``, and ``password_enc`` /
        ``private_key_enc`` are deliberately excluded from it, so the delegated
        call cannot clobber what was just encrypted.

        Never reimplement this hook's body. ``NetBoxModelForm._post_clean()``
        populates ``instance._m2m_values``, which ``NetBoxModelForm._save_m2m()``
        reads unconditionally; skipping the ``super()`` call raises
        ``AttributeError`` on every save of a form that declares ``tags``.
        """
        if not self.errors:
            try:
                self._prepare_secret_context()
                self._apply_secret_inputs()
            except forms.ValidationError as exc:
                self.add_error(None, exc)

        super()._post_clean()


class NodeSSHCredentialFilterForm(NetBoxModelFilterSetForm):
    """Filter form for NodeSSHCredential list views."""

    model = NodeSSHCredential
    node = forms.ModelMultipleChoiceField(
        queryset=ProxmoxNode.objects.all(), required=False
    )
    username = forms.CharField(required=False)
    auth_method = forms.MultipleChoiceField(
        choices=NodeSSHCredential._meta.get_field("auth_method").choices,
        required=False,
    )
