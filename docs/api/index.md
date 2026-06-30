# API Reference

Proxbox exposes a REST API under `/api/plugins/proxbox/` for all of its persisted models. The plugin registers **29 `NetBoxModelViewSet` classes** — one per model — via a `NetBoxRouter`, so every model is discoverable at the API root. The API inherits NetBox's standard DRF infrastructure — authentication, permissions, pagination, and filtering work identically to native NetBox endpoints.

!!! note "Read-only endpoints"
    Two endpoints are intentionally **read-only** (GET / HEAD / OPTIONS only) to preserve the four-eyes approval workflow and intent branch safety: `deletion-requests/` and `apply-jobs/`. Attempting a POST, PUT, PATCH, or DELETE to those paths returns HTTP 405. See [Deletion Requests and Apply Jobs](#deletion-requests-and-apply-jobs-read-only) below and the [Deletion Requests operations guide](../operations/deletion-requests.md) for the full safety policy.

## Base URL

```
/api/plugins/proxbox/
```

A GET request to the root returns links to all top-level resources plus the nested `/endpoints/` namespace.

## Authentication

All endpoints require authentication. Three methods are supported:

**Token authentication** (recommended for automation):

```bash
curl -H "Authorization: Token <your-netbox-token>" \
     http://netbox.example.com/api/plugins/proxbox/proxmox-clusters/
```

**Session authentication**: Used automatically by the NetBox web UI. Browser requests that include a valid Django session cookie are accepted.

**Object-level permissions**: All viewsets use `NetBoxModelViewSet`, which enforces NetBox's object permission system via `queryset.restrict(request.user, "view")`. A user must have the corresponding `view`, `add`, `change`, or `delete` model permission to perform each operation.

## Pagination

All list endpoints support NetBox's standard limit/offset pagination.

| Parameter | Default | Description |
|---|---|---|
| `limit` | NetBox `PAGINATE_COUNT` setting | Number of results per page |
| `offset` | `0` | Number of results to skip |

**Response envelope:**

```json
{
  "count": 42,
  "next": "/api/plugins/proxbox/clusters/?limit=50&offset=50",
  "previous": null,
  "results": [...]
}
```

## Search

All list endpoints accept a `?q=` query parameter for free-text search. Each model defines its own set of searchable fields, documented per endpoint.

```bash
curl -H "Authorization: Token <token>" \
     "http://netbox.example.com/api/plugins/proxbox/proxmox-clusters/?q=pve"
```

## Common Response Fields

Every object in every endpoint includes these standard fields:

| Field | Type | Description |
|---|---|---|
| `id` | integer | Unique database ID |
| `url` | string | Canonical API URL for this object |
| `display` | string | Human-readable label for the object |
| `tags` | array | List of NetBox tag objects |
| `custom_fields` | object | Key/value map of custom field values |
| `created` | datetime | ISO 8601 timestamp when the record was created |
| `last_updated` | datetime | ISO 8601 timestamp of the last modification |

## Nested Serializers

Foreign key fields are represented as **nested objects** in GET responses:

```json
{
  "endpoint": {
    "id": 1,
    "url": "/api/plugins/proxbox/endpoints/proxmox/1/",
    "display": "prod-proxmox (10.0.0.1)",
    "name": "prod-proxmox"
  }
}
```

On **write** (POST, PUT, PATCH), these fields accept either the nested object or a plain integer ID:

```json
{ "endpoint": 1 }
```

## Write-Only Fields

Certain credential fields never appear in GET responses. They can only be set on POST, PUT, or PATCH:

| Model | Write-Only Fields |
|---|---|
| `ProxmoxEndpoint` | `password`, `token_value` |
| `NetBoxEndpoint` | `token_secret` |

## Upsert Behavior

Two models perform an **upsert** on POST — if a matching record already exists by natural key, the POST updates it rather than returning a 400 conflict:

| Model | Upsert Key |
|---|---|
| `ProxmoxStorage` | `(cluster, name)` |
| `VMTaskHistory` | `upid` |

## Endpoint Map

| Path | Methods | Documentation |
|---|---|---|
| `/api/plugins/proxbox/` | GET | This page |
| `/api/plugins/proxbox/endpoints/` | GET | [Endpoint Configuration](endpoints.md) |
| `/api/plugins/proxbox/endpoints/proxmox/` | GET POST | [ProxmoxEndpoint](endpoints.md#proxmox-endpoint) |
| `/api/plugins/proxbox/endpoints/proxmox/{id}/` | GET PUT PATCH DELETE | [ProxmoxEndpoint](endpoints.md#proxmox-endpoint) |
| `/api/plugins/proxbox/endpoints/netbox/` | GET POST | [NetBoxEndpoint](endpoints.md#netbox-endpoint) |
| `/api/plugins/proxbox/endpoints/netbox/{id}/` | GET PUT PATCH DELETE | [NetBoxEndpoint](endpoints.md#netbox-endpoint) |
| `/api/plugins/proxbox/endpoints/fastapi/` | GET POST | [FastAPIEndpoint](endpoints.md#fastapi-endpoint) |
| `/api/plugins/proxbox/endpoints/fastapi/{id}/` | GET PUT PATCH DELETE | [FastAPIEndpoint](endpoints.md#fastapi-endpoint) |
| `/api/plugins/proxbox/proxmox-clusters/` | GET POST | [ProxmoxCluster](infrastructure.md#proxmox-cluster) |
| `/api/plugins/proxbox/proxmox-clusters/{id}/` | GET PUT PATCH DELETE | [ProxmoxCluster](infrastructure.md#proxmox-cluster) |
| `/api/plugins/proxbox/proxmox-nodes/` | GET POST | [ProxmoxNode](infrastructure.md#proxmox-node) |
| `/api/plugins/proxbox/proxmox-nodes/{id}/` | GET PUT PATCH DELETE | [ProxmoxNode](infrastructure.md#proxmox-node) |
| `/api/plugins/proxbox/storage/` | GET POST | [ProxmoxStorage](infrastructure.md#proxmox-storage) |
| `/api/plugins/proxbox/storage/{id}/` | GET PUT PATCH DELETE | [ProxmoxStorage](infrastructure.md#proxmox-storage) |
| `/api/plugins/proxbox/backups/` | GET POST | [VMBackup](vm-data.md#vm-backup) |
| `/api/plugins/proxbox/backups/{id}/` | GET PUT PATCH DELETE | [VMBackup](vm-data.md#vm-backup) |
| `/api/plugins/proxbox/snapshots/` | GET POST | [VMSnapshot](vm-data.md#vm-snapshot) |
| `/api/plugins/proxbox/snapshots/{id}/` | GET PUT PATCH DELETE | [VMSnapshot](vm-data.md#vm-snapshot) |
| `/api/plugins/proxbox/task-history/` | GET POST | [VMTaskHistory](vm-data.md#vm-task-history) |
| `/api/plugins/proxbox/task-history/{id}/` | GET PUT PATCH DELETE | [VMTaskHistory](vm-data.md#vm-task-history) |
| `/api/plugins/proxbox/backup-routines/` | GET POST | [BackupRoutine](operations.md#backup-routine) |
| `/api/plugins/proxbox/backup-routines/{id}/` | GET PUT PATCH DELETE | [BackupRoutine](operations.md#backup-routine) |
| `/api/plugins/proxbox/replications/` | GET POST | [Replication](operations.md#replication) |
| `/api/plugins/proxbox/replications/{id}/` | GET PUT PATCH DELETE | [Replication](operations.md#replication) |
| `/api/plugins/proxbox/settings/` | GET | [Plugin Settings](settings.md) |
| `/api/plugins/proxbox/settings/{id}/` | GET PATCH | [Plugin Settings](settings.md) |
| `/api/plugins/proxbox/ha/summary/` | GET | [Cluster HA](ha.md) |
| `/api/plugins/proxbox/ha/vm/{vmid}/` | GET | [Cluster HA](ha.md) |
| `/api/plugins/proxbox/firecracker-host-pools/` | GET POST | FirecrackerHostPool CRUD |
| `/api/plugins/proxbox/firecracker-host-pools/{id}/` | GET PUT PATCH DELETE | FirecrackerHostPool CRUD |
| `/api/plugins/proxbox/firecracker-hosts/` | GET POST | FirecrackerHost CRUD |
| `/api/plugins/proxbox/firecracker-hosts/{id}/` | GET PUT PATCH DELETE | FirecrackerHost CRUD |
| `/api/plugins/proxbox/firecracker-image-templates/` | GET POST | FirecrackerImageTemplate CRUD |
| `/api/plugins/proxbox/firecracker-image-templates/{id}/` | GET PUT PATCH DELETE | FirecrackerImageTemplate CRUD |
| `/api/plugins/proxbox/firecracker-microvms/` | GET POST | FirecrackerMicroVM CRUD |
| `/api/plugins/proxbox/firecracker-microvms/{id}/` | GET PUT PATCH DELETE | FirecrackerMicroVM CRUD |
| `/api/plugins/proxbox/cloud-image-templates/` | GET POST | CloudImageTemplate CRUD |
| `/api/plugins/proxbox/cloud-image-templates/{id}/` | GET PUT PATCH DELETE | CloudImageTemplate CRUD |
| `/api/plugins/proxbox/vm-cloudinit/` | GET POST | ProxmoxVMCloudInit CRUD |
| `/api/plugins/proxbox/vm-cloudinit/{id}/` | GET PUT PATCH DELETE | ProxmoxVMCloudInit CRUD |
| `/api/plugins/proxbox/vm-templates/` | GET POST | ProxmoxVMTemplate CRUD |
| `/api/plugins/proxbox/vm-templates/{id}/` | GET PUT PATCH DELETE | ProxmoxVMTemplate CRUD |
| `/api/plugins/proxbox/ssh-credentials/` | GET POST | NodeSSHCredential CRUD |
| `/api/plugins/proxbox/ssh-credentials/{id}/` | GET PUT PATCH DELETE | NodeSSHCredential CRUD |
| `/api/plugins/proxbox/ssh-credentials/by-node/{node_id}/` | GET | Lookup SSH credential by ProxmoxNode |
| `/api/plugins/proxbox/ssh-credentials/by-node/{node_id}/credentials/` | GET | Retrieve decrypted SSH credential secrets by node |
| `/api/plugins/proxbox/ssh-credentials/by-endpoint/{endpoint_id}/credentials/` | GET | Retrieve decrypted SSH credential secrets by endpoint |
| `/api/plugins/proxbox/firewall/security-groups/` | GET POST | ProxmoxFirewallSecurityGroup CRUD |
| `/api/plugins/proxbox/firewall/security-groups/{id}/` | GET PUT PATCH DELETE | ProxmoxFirewallSecurityGroup CRUD |
| `/api/plugins/proxbox/firewall/rules/` | GET POST | ProxmoxFirewallRule CRUD |
| `/api/plugins/proxbox/firewall/rules/{id}/` | GET PUT PATCH DELETE | ProxmoxFirewallRule CRUD |
| `/api/plugins/proxbox/firewall/ipsets/` | GET POST | ProxmoxFirewallIPSet CRUD |
| `/api/plugins/proxbox/firewall/ipsets/{id}/` | GET PUT PATCH DELETE | ProxmoxFirewallIPSet CRUD |
| `/api/plugins/proxbox/firewall/ipset-entries/` | GET POST | ProxmoxFirewallIPSetEntry CRUD |
| `/api/plugins/proxbox/firewall/ipset-entries/{id}/` | GET PUT PATCH DELETE | ProxmoxFirewallIPSetEntry CRUD |
| `/api/plugins/proxbox/firewall/aliases/` | GET POST | ProxmoxFirewallAlias CRUD |
| `/api/plugins/proxbox/firewall/aliases/{id}/` | GET PUT PATCH DELETE | ProxmoxFirewallAlias CRUD |
| `/api/plugins/proxbox/firewall/options/` | GET POST | ProxmoxFirewallOptions CRUD |
| `/api/plugins/proxbox/firewall/options/{id}/` | GET PUT PATCH DELETE | ProxmoxFirewallOptions CRUD |
| `/api/plugins/proxbox/sdn-fabrics/` | GET POST | ProxmoxSdnFabric CRUD |
| `/api/plugins/proxbox/sdn-fabrics/{id}/` | GET PUT PATCH DELETE | ProxmoxSdnFabric CRUD |
| `/api/plugins/proxbox/sdn-route-maps/` | GET POST | ProxmoxSdnRouteMap CRUD |
| `/api/plugins/proxbox/sdn-route-maps/{id}/` | GET PUT PATCH DELETE | ProxmoxSdnRouteMap CRUD |
| `/api/plugins/proxbox/sdn-prefix-lists/` | GET POST | ProxmoxSdnPrefixList CRUD |
| `/api/plugins/proxbox/sdn-prefix-lists/{id}/` | GET PUT PATCH DELETE | ProxmoxSdnPrefixList CRUD |
| `/api/plugins/proxbox/datacenter-cpu-models/` | GET POST | ProxmoxDatacenterCpuModel CRUD |
| `/api/plugins/proxbox/datacenter-cpu-models/{id}/` | GET PUT PATCH DELETE | ProxmoxDatacenterCpuModel CRUD |
| `/api/plugins/proxbox/resources/firecracker-microvms/` | GET | NMS-compatible Firecracker micro-VM list (non-model view) |
| `/api/plugins/proxbox/resources/interfaces/` | GET | Aggregated VM interface list (non-model view) |
| `/api/plugins/proxbox/resources/ip-addresses/` | GET | Aggregated IP address list (non-model view) |
| `/api/plugins/proxbox/resources/virtual-disks/` | GET | Aggregated virtual disk list (non-model view) |
| `/api/plugins/proxbox/deletion-requests/` | **GET HEAD OPTIONS** | [DeletionRequest (read-only)](../operations/deletion-requests.md) |
| `/api/plugins/proxbox/deletion-requests/{id}/` | **GET HEAD OPTIONS** | [DeletionRequest (read-only)](../operations/deletion-requests.md) |
| `/api/plugins/proxbox/apply-jobs/` | **GET HEAD OPTIONS** | ProxmoxApplyJob (read-only audit) |
| `/api/plugins/proxbox/apply-jobs/{id}/` | **GET HEAD OPTIONS** | ProxmoxApplyJob (read-only audit) |

## Deletion Requests and Apply Jobs (Read-Only)

`DeletionRequest` and `ProxmoxApplyJob` are the two **read-only** viewsets in the plugin. Their `http_method_names` is restricted to `["get", "head", "options"]` — POST, PUT, PATCH, and DELETE return HTTP 405.

### Why they are read-only

Both models form part of a **five-lock deletion safety chain** that prevents autonomous VM destruction. The chain requires separate actors, explicit confirmation phrases, and operator approval — no single API call (and no automated agent) can bypass it. Making the REST surface read-only enforces this at the framework level:

| Lock | Mechanism |
|---|---|
| 1 — Plugin setting | Master `allow_delete` toggle must be enabled in `ProxboxPluginSettings` |
| 2 — Typed phrase | Caller must supply the exact phrase `allow-edit-and-add-actions` in the request |
| 3 — Explicit flag | Request body must include `apply_destroy_confirmed: true` |
| 4 — Requester permission | Initiating user must hold the `delete_deletion_request` permission |
| 5 — Separate authorizer | A **different** user must approve (`self_approve_allowed: false`) |

The `DeletionRequest` REST endpoint exists only for reading the current deletion queue. The actual deletion workflow is initiated through the NetBox UI or the intent API — not the plugin REST API. See the [Deletion Requests guide](../operations/deletion-requests.md) for the complete four-eyes workflow.

### ProxmoxApplyJob

`ProxmoxApplyJob` records the result of intent-branch apply operations (plan → apply cycles). It is written exclusively by the proxbox-api backend; the plugin REST surface is read-only so audit records cannot be tampered with through the API.

**Example — list pending deletion requests:**

```bash
curl -H "Authorization: Token <token>" \
     "http://netbox.example.com/api/plugins/proxbox/deletion-requests/?status=pending"
```

**Example — retrieve an apply job result:**

```bash
curl -H "Authorization: Token <token>" \
     "http://netbox.example.com/api/plugins/proxbox/apply-jobs/42/"
```
