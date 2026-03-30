"""Form widgets used by Proxbox plugin forms."""

from __future__ import annotations

from django import forms

__all__ = ("BootstrapCheckboxSelectMultiple",)


class BootstrapCheckboxSelectMultiple(forms.CheckboxSelectMultiple):
    """
    Checkbox list using NetBox ``form-check`` / ``form-check-input`` / ``form-check-label``
    pattern (same as core templates such as ``object_list.html``).
    """

    template_name = "netbox_proxbox/widgets/bootstrap_checkbox_select.html"
    option_template_name = "netbox_proxbox/widgets/bootstrap_checkbox_option.html"

    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(
            name, value, label, selected, index, subindex=subindex, attrs=attrs
        )
        opt_attrs = option.setdefault("attrs", {})
        existing = opt_attrs.get("class", "")
        if isinstance(existing, (list, tuple)):
            parts = list(existing)
        else:
            parts = [existing] if existing else []
        if "form-check-input" not in parts:
            parts.insert(0, "form-check-input")
        opt_attrs["class"] = " ".join(p for p in parts if p)
        return option
