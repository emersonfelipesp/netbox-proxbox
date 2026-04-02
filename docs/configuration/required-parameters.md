# Required Parameters

These are the fields you need to provide for a working end-to-end Proxbox setup.

## Proxmox API

- Hostname or IP address
- Port, usually `8006`
- Username and password, or API token
- TLS verification preference

## NetBox API

- Hostname or IP address of the target NetBox instance
- Port, usually `443`
- A NetBox token
- Token version details if you use a v2 key/secret pair
- TLS verification preference

## ProxBox API (FastAPI)

- Hostname or IP address of the `proxbox-api` service
- Port, usually `8800` for a direct host install or mapped Docker port
- TLS verification preference
- Optional backend token if your deployment requires one

## Operational Requirement

Scheduled sync also requires a standard NetBox RQ worker because Proxbox sync runs through NetBox Jobs on the default queue.
