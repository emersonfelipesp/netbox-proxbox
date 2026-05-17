"""Empty NetBox plugin navigation menu for netbox-packer.

Menu items land with the UI views in PHASE3.
"""

from __future__ import annotations

from netbox.plugins import PluginMenu


menu = PluginMenu(
    label="Packer",
    groups=(),
    icon_class="mdi mdi-package-variant",
)
