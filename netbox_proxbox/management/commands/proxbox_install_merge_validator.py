"""Print the NetBox ``configuration.py`` snippet that registers the
proxbox merge_validator with ``netbox_branching``.

NetBox plugins cannot mutate ``PLUGINS_CONFIG`` at runtime, so wiring
the merge_validator requires an operator action: add an entry under
``PLUGINS_CONFIG['netbox_branching']['merge_validators']``. This
command prints the exact line to copy, so operators don't have to
guess the dotted path.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand


VALIDATOR_DOTTED_PATH = "netbox_proxbox.intent.merge_validator.validate_proxmox_intent"


SNIPPET = """\
# Add to NetBox configuration.py to enable the proxbox merge validator
# (only effective when both `netbox_branching` and `netbox_proxbox` are
# installed and the master flag `netbox_to_proxmox_enabled` is True):

PLUGINS_CONFIG = {{
    # ... your existing entries ...
    "netbox_branching": {{
        # ... your existing branching config ...
        "merge_validators": [
            "{validator}",
        ],
    }},
}}
"""


class Command(BaseCommand):
    help = (
        "Print the NetBox configuration.py snippet that registers "
        "the proxbox merge_validator with netbox_branching."
    )

    def handle(self, *args, **options) -> None:
        self.stdout.write(SNIPPET.format(validator=VALIDATOR_DOTTED_PATH))
