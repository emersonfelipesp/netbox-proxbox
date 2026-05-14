"""proxbox-scheduler: standalone Proxbox sync scheduler container.

Issue tracker: https://github.com/emersonfelipesp/netbox-proxbox/issues/372

This is a thin loop that wraps the existing ``proxbox_sync`` management
command (or, alternatively, a direct HTTP call to ``proxbox-api``) and
triggers it on a configurable schedule. It owns no NetBox model, no plugin
config, and no shared state — all configuration is environment variables.

Supported modes (set via ``PROXBOX_MODE``):

    off                  scheduler disabled (no-op exit)
    interval=<seconds>   fixed interval between triggers
    continuous           fire next as soon as previous returns
    cron=<expression>    standard 5-field cron expression
"""

__version__ = "0.0.15"
