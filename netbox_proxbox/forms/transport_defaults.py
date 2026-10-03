"""Keep secure transport defaults when a CSV import omits a column.

A Django ``BooleanField`` cleans a missing value to ``False``, and NetBox's
bulk import binds every declared form field. An import that simply leaves out
``use_https`` or ``verify_ssl`` would therefore create a new endpoint with HTTPS
or certificate verification turned off, silently defeating the secure model
defaults. This mixin restores the model default for an omitted column on new
rows while honouring an explicit ``false``.
"""

from __future__ import annotations

__all__ = ("SecureTransportImportDefaultsMixin",)


class SecureTransportImportDefaultsMixin:
    """Restore model defaults for omitted security-relevant boolean columns."""

    secure_default_fields: tuple[str, ...] = ()

    def clean(self) -> dict[str, object]:
        """Apply the model default to each omitted security column on create."""
        # NetBox form hooks may return None; always work on self.cleaned_data.
        super().clean()
        cleaned_data = self.cleaned_data
        instance = getattr(self, "instance", None)
        if instance is not None and getattr(instance, "pk", None) is not None:
            return cleaned_data
        submitted = getattr(self, "data", None) or {}
        model = self._meta.model
        for field_name in self.secure_default_fields:
            if field_name in submitted or field_name not in self.fields:
                continue
            cleaned_data[field_name] = model._meta.get_field(field_name).default
        return cleaned_data
