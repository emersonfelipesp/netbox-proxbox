# Proxmox Metrics Architecture

This feature is owned by `netbox-proxbox` and `proxbox-api`. It is independent
of `netbox-monitoring`, `netbox-nms`, and `nms-backend`; those systems may build
their own observability integration without becoming a runtime dependency of
the Proxmox metrics path.

## Responsibilities

`netbox-proxbox` owns the `ProxmoxMetricsInfluxDB` mapping, the encrypted query
token, permissions, and the operator UI. The Fernet key
is `ProxboxPluginSettings.encryption_key`; ciphertext is never returned by a
serializer, stored in an ObjectChange snapshot, or sent to a browser.

`proxbox-api` owns the typed InfluxDB v2 query contract. It validates the
credential-free URL, organization, bucket, TLS mode, bounded time range,
measurement/field/tag/node/VM filters, aggregation, and row limit. It generates the
Flux query from structured fields and normalizes the Influx CSV/JSON response
into stable columns and rows. Arbitrary caller-supplied Flux is not accepted.

The plugin calls the backend through its configured `FastAPIEndpoint`. The
browser calls only NetBox. InfluxDB is reachable only from `proxbox-api`:

```text
NetBox UI or plugin API
        │  mapping id + bounded filters
        ▼
netbox-proxbox ── encrypted token decrypted server-side ──► proxbox-api
                                                               │
                                                               │ typed query
                                                               ▼
                                                            InfluxDB
```

## Failure and security boundaries

- Disabled mappings, missing encryption keys, undecryptable ciphertext, and
  absent backend endpoints fail closed.
- The plugin sends the decrypted token only in the authenticated backend
  request body. It never logs the body and never returns the token.
- Backend errors are typed and secret-safe; raw Influx responses are not
  forwarded to callers.
- Legacy external token references are not resolved during migration. They are
  cleared, affected mappings are disabled, audit snapshots are masked, and
  operators must re-enter plugin-owned credentials.
- The backend accepts HTTPS targets only, validates DNS-resolved destinations
  against the shared SSRF policy, disables redirects, and keeps TLS verification
  enabled unless the operator-controlled `PROXBOX_ALLOW_INSECURE_INFLUX_TLS`
  override is explicitly enabled.

## API and UI surfaces

Metadata CRUD remains at `/api/plugins/proxbox/metrics-influxdb/`. Live data is
retrieved with `GET /api/plugins/proxbox/metrics-influxdb/{id}/data/` and
bounded query parameters. The NetBox detail page links to the same operation
through a server-rendered query page. Neither surface accepts a Flux string or
direct InfluxDB connection parameters from the browser.

## Verification evidence

Focused tests cover encrypted credential persistence and masking, route
registration, local query validation, migration/recovery contracts, structured
query validation, Flux generation, CSV/JSON normalization, bounded rows,
secret-safe failures, and the no-NMS dependency boundary. Full NetBox harness
tests are still required to exercise permission-enforced metadata/data routes
and live migration application. Release review must also record the configured
cyclomatic-complexity analyzer and its per-function results for changed code.
