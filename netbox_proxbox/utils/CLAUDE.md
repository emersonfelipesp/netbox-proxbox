# Utility Modules

- `metrics.py` contains the shared bounded duration and timezone-qualified
  timestamp validators used by the NetBox Proxmox metrics forms and API
  serializers. Keep its grammar aligned with the independent proxbox-api
  InfluxDB request schema without adding a runtime dependency on that service.
