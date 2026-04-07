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

    def create_option(
        self,
        name: str,
        value: object,
        label: object,
        selected: bool,
        index: int,
        subindex: int | None = None,
        attrs: dict[str, object] | None = None,
    ) -> dict[str, object]:
        # form-check-input is rendered in bootstrap_checkbox_option.html (NetBox attrs.html skips class).
        """Create option."""
        return super().create_option(
            name, value, label, selected, index, subindex=subindex, attrs=attrs
        )
