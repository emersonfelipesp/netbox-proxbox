"""Forms for per-node SSH credentials used by hardware discovery."""

from __future__ import annotations

from django import forms
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

    def clean_known_host_fingerprint(self) -> str:
        """Normalize host-key fingerprints at form level for user feedback."""
        value = self.cleaned_data["known_host_fingerprint"]
        return normalize_fingerprint(value)

    def _encryption_key(self) -> str:
        settings_obj = ProxboxPluginSettings.get_solo()
        key = settings_obj.encryption_key or ""
        if not key:
            raise forms.ValidationError(
                "Configure ProxboxPluginSettings.encryption_key before storing SSH secrets."
            )
        return key

    def _apply_secret_inputs(self) -> None:
        password = self.cleaned_data.get("password")
        private_key = self.cleaned_data.get("private_key")
        if not password and not private_key:
            return
        key = self._encryption_key()
        try:
            if password:
                self.instance.password_enc = enc_helpers.encrypt(password, key=key)
            if private_key:
                self.instance.private_key_enc = enc_helpers.encrypt(
                    private_key, key=key
                )
        except enc_helpers.EncryptionError as exc:
            raise forms.ValidationError(str(exc)) from exc

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
