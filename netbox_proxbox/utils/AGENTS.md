# Utility Modules

- `__init__.py` is the canonical `netbox_proxbox.utils` import target and owns
  the backend URL, host, and VM-list filtering helpers. Do not add a peer
  `netbox_proxbox/utils.py`; the package shadows that module name.
- `metrics.py` contains the shared bounded duration and timezone-qualified
  timestamp validators used by the NetBox Proxmox metrics forms and API
  serializers. Keep its grammar aligned with the independent proxbox-api
  InfluxDB request schema without adding a runtime dependency on that service.
- `__init__.py` never mutates process-wide state while building backend URLs.
  It must not set `REQUESTS_CA_BUNDLE` or shell out to `mkcert`; TLS trust is
  the operator's system trust store or the per-endpoint `verify_ssl` flag.
- `encryption.py` owns the Fernet helpers. `_coerce_fernet_key()` keeps
  decrypting already stored legacy raw 32-byte keys, but every **write** of a
  new key (settings model save, settings form and serializer, verified
  rotation) goes through `require_canonical_fernet_key()`, which accepts only a
  44-character url-safe base64 Fernet key. Do not add key derivation: the key
  is shared byte-for-byte with proxbox-api, so a derived key would make every
  existing ciphertext undecryptable there.
