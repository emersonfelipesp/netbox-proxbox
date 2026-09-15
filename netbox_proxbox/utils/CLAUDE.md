# Utility Modules

- `__init__.py` is the canonical `netbox_proxbox.utils` import target and owns
  the backend URL, host, and VM-list filtering helpers. Do not add a peer
  `netbox_proxbox/utils.py`; the package shadows that module name.
- `metrics.py` contains the shared bounded duration and timezone-qualified
  timestamp validators used by the NetBox Proxmox metrics forms and API
  serializers. Keep its grammar aligned with the independent proxbox-api
  InfluxDB request schema without adding a runtime dependency on that service.
