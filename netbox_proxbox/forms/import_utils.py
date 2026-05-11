"""Shared helpers for endpoint CSV import forms."""

from __future__ import annotations

from django import forms
from django.utils.translation import gettext_lazy as _


class NullableCSVIntegerField(forms.IntegerField):
    """Integer CSV field that accepts common serialized null strings."""

    null_strings = {"none", "null"}

    def to_python(self, value: object) -> int | None:
        """Treat exported null sentinels as empty values before integer parsing."""
        if isinstance(value, str) and value.strip().lower() in self.null_strings:
            value = ""
        return super().to_python(value)


_ENDPOINT_SIGNATURES = {
    "fastapi": {
        "label": _("FastAPI endpoint"),
        "headers": {
            "use_https",
            "use_websocket",
            "websocket_domain",
            "websocket_port",
            "server_side_websocket",
        },
    },
    "netbox": {
        "label": _("NetBox endpoint"),
        "headers": {
            "token_version",
            "token_key",
            "token_secret",
        },
    },
    "proxmox": {
        "label": _("Proxmox endpoint"),
        "headers": {
            "mode",
            "version",
            "repoid",
            "username",
            "password",
            "token_name",
            "token_value",
            "timeout",
            "max_retries",
            "retry_backoff",
        },
    },
}


def validate_endpoint_import_headers(form: forms.Form, expected: str) -> None:
    """Raise a clear error when an endpoint export is posted to the wrong importer."""
    headers = set(getattr(form, "headers", {}) or {})
    if not headers and hasattr(form, "data"):
        headers = {str(key) for key in form.data}
    headers.discard("id")

    for endpoint_type, signature in _ENDPOINT_SIGNATURES.items():
        if endpoint_type == expected:
            continue

        matched_headers = sorted(headers & signature["headers"])
        if not matched_headers:
            continue

        fields = ", ".join(matched_headers[:5])
        if len(matched_headers) > 5:
            fields = f"{fields}, ..."
        raise forms.ValidationError(
            _(
                "This import data looks like a {label} export because it contains "
                "these endpoint-specific columns: {fields}. Use the matching "
                "endpoint import page instead."
            ).format(label=signature["label"], fields=fields)
        )
