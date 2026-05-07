# `netbox-proxmox-automation` — Detailed Reference

> Reference dossier for the upstream NetBox Labs project
> [`netboxlabs/netbox-proxmox-automation`](https://github.com/netboxlabs/netbox-proxmox-automation),
> mirrored locally at `/root/nms/netbox-proxmox-automation`.
>
> This document exists inside the `netbox-proxbox` repository so that
> contributors here can consult an authoritative summary of the sibling
> project's code, conventions, and design decisions when deciding what to
> borrow and what to diverge from.
>
> Source revision basis: project version `2025.11.01` (CalVer).

---

## Table of Contents

1. [Overview](#1-overview)
2. [System Requirements & Compatibility](#2-system-requirements--compatibility)
3. [High-Level Architecture](#3-high-level-architecture)
4. [Repository Layout](#4-repository-layout)
5. [Configuration Model](#5-configuration-model)
6. [NetBox Customization Layer](#6-netbox-customization-layer)
7. [Setup / Provisioning Scripts](#7-setup--provisioning-scripts)
8. [Helper Modules (`setup/helpers/`)](#8-helper-modules-setuphelpers)
9. [Event Rules Catalog](#9-event-rules-catalog)
10. [Ansible Playbooks](#10-ansible-playbooks)
11. [AWX / Tower / AAP Integration](#11-awx--tower--aap-integration)
12. [Flask Webhook Application](#12-flask-webhook-application)
13. [Discovery Workflows](#13-discovery-workflows)
14. [Migration Workflow](#14-migration-workflow)
15. [NetBox Branching Plugin Integration](#15-netbox-branching-plugin-integration)
16. [Documentation Site](#16-documentation-site)
17. [Dependencies](#17-dependencies)
18. [Operational Notes](#18-operational-notes)
19. [Known Issues & Roadmap](#19-known-issues--roadmap)
20. [Comparison Notes for `netbox-proxbox`](#20-comparison-notes-for-netbox-proxbox)

---

## 1. Overview

`netbox-proxmox-automation` is an event-driven integration between
[NetBox](https://github.com/netbox-community/netbox) and
[Proxmox VE](https://www.proxmox.com/en/proxmox-virtual-environment).
NetBox holds the **desired state** of every Proxmox VM and LXC container
(name, vCPUs, memory, disks, primary IP, SSH keys, target node). When a
NetBox object is created, updated, or deleted, NetBox fires a **webhook**
through an associated **event rule**, and the integration translates that
intent into the matching Proxmox API operation: clone a template, resize a
disk, start/stop/delete the workload, set cloud-init config, migrate
between nodes, etc.

The project ships **two interchangeable execution paths** for the same
event-rule fabric:

- **AWX / Tower / AAP** — a set of Ansible playbooks executed by job
  templates that AWX invokes per webhook.
- **Flask application** — a small Flask + Flask-RESTX HTTP service that
  receives webhooks directly and calls the Proxmox API in-process.

Both paths share the **same NetBox-side configuration** (custom fields,
choice sets, event rules) — only the webhook target differs.

| Attribute | Value |
|---|---|
| Maintainer | Nate Patwardhan <`npatwardhan@netboxlabs.com`> |
| License | Apache 2.0 |
| Versioning | CalVer (`YYYY.MM.PATCH`); current `2025.11.01` |
| Upstream | `https://github.com/netboxlabs/netbox-proxmox-automation` |

### What it IS

- A **desired-state translator** from NetBox into Proxmox.
- An opinionated set of **custom fields and event rules** layered onto a
  vanilla NetBox installation.
- A **reference architecture** for "use NetBox as the source of truth and
  let webhooks drive your hypervisor."

### What it IS NOT

- Not a NetBox plugin (no Django app, no migrations, no models).
- Not [`ProxBox`](https://github.com/netdevopsbr/netbox-proxbox) — it does
  **not** sync Proxmox state into NetBox continuously; the only
  Proxmox→NetBox flow is the one-shot **discovery scripts**.
- Not a full application/OS deployment system. Cloud-init brings the VM
  online; further configuration is the operator's responsibility.

---

## 2. System Requirements & Compatibility

| Requirement | Constraint |
|---|---|
| NetBox | ≥ 4.3.7 (README states ≥ 4.2; `usage.md` tightens to 4.3.7 because of MAC address modeling changes) |
| Proxmox VE | 8.x (8.4 explicitly tested). 9.x **untested / unsupported** |
| Python | ≥ 3.12 |
| Webhook receiver | One of: AWX / Tower / AAP **or** the bundled Flask app |
| OS images | Officially only Debian/Ubuntu cloud images (jammy / focal / noble) for VMs; LXC uses standard Proxmox `vztmpl` images |
| Optional | NetBox Branching plugin (setup-time only) |

Authentication is **token-only** on both sides — NetBox API token and
Proxmox API token (with privilege separation **disabled** so the token
inherits the user's role). Passwords are never stored.

---

## 3. High-Level Architecture

The data-flow is unidirectional from NetBox to Proxmox at runtime, with a
one-shot reverse path used only during initial discovery.

```
                     ┌──────────────────────────────────────┐
                     │              NetBox 4.3+             │
                     │  ┌──────────────────────────────┐    │
                     │  │ Custom Fields + Choice Sets  │    │
                     │  │ proxmox_node, proxmox_vmid,  │    │
                     │  │ proxmox_vm_type, ...         │    │
                     │  └──────────────────────────────┘    │
                     │  ┌──────────────────────────────┐    │
                     │  │ Event Rules (17)             │    │
                     │  │ → Webhooks                   │    │
                     │  └──────────────┬───────────────┘    │
                     └────────────────┬┴─────────────────────┘
                                      │ HTTP POST (event payload)
                ┌─────────────────────┴─────────────────────┐
                │                                           │
        automation_type:                            automation_type:
        flask_application                           ansible_automation
                │                                           │
                ▼                                           ▼
   ┌─────────────────────────┐                 ┌─────────────────────────┐
   │  Flask + Flask-RESTX    │                 │  AWX / Tower / AAP      │
   │  app.py + helpers/      │                 │  Job Templates          │
   │  Synchronous, no queue  │                 │  Execution Environment  │
   └────────────┬────────────┘                 └────────────┬────────────┘
                │ proxmoxer (HTTPS, token)                  │ community.proxmox
                ▼                                           ▼
                       ┌──────────────────────────┐
                       │      Proxmox VE 8.x      │
                       │  qemu / lxc / cluster    │
                       └──────────────────────────┘
                                      ▲
                                      │ one-shot:
                                      │ paramiko + dmidecode/ethtool
                                      │ + Proxmox API
                       ┌──────────────┴───────────────┐
                       │ Discovery scripts (setup/)   │
                       │ → write back into NetBox     │
                       └──────────────────────────────┘
```

**Key invariants:**

- The webhook payload is the **only trigger**. There is no scheduler,
  queue, or reconciliation loop.
- Either one Flask host **or** AWX (not both at once for the same NetBox
  instance — webhook URLs would collide).
- All long-running Proxmox tasks (clone, start, stop, delete, migrate,
  resize) are awaited synchronously by polling the `tasks/<upid>/status`
  endpoint until `status == 'stopped'`.

---

## 4. Repository Layout

```
netbox-proxmox-automation/
├── README.md                          Quick-start, version history, requirements
├── SECURITY.md                        Vuln reporting → security@netboxlabs.com
├── LICENSE.md                         Apache 2.0
├── requirements.txt                   Pinned deps (also covers MkDocs site)
├── mkdocs.yml                         Material-theme docs site config
├── .gitignore                         Python + project-specific ignores
│
├── conf.d/
│   └── netbox_setup_objects.yml-sample   Master config consumed by all setup scripts
│
├── docs/                              MkDocs source
│   ├── index.md / usage.md
│   ├── netbox-*.md / proxmox-*.md / configure-*.md
│   ├── stylesheets/extra.css
│   └── images/                        50+ UI screenshots
│
├── netbox-event-driven-automation-flask-app/
│   ├── app.py                         Flask + Flask-RESTX entrypoint
│   ├── app_config.yml-sample          Simplified runtime config
│   ├── requirements.txt               Flask deps
│   └── helpers/netbox_proxmox.py      All business logic
│
├── playbooks/
│   ├── awx-proxmox-*.yml              16 Proxmox playbooks (VM + LXC ops)
│   ├── awx-update-dns.yml             Roadmap: BIND9 zone regeneration
│   ├── ansible-tasks/                 Shared include files
│   └── mkdocs.yml                     (Older alternate docs config)
│
├── setup/
│   ├── netbox_setup_objects_and_custom_fields.py
│   ├── netbox_setup_webhook_and_event_rules.py
│   ├── configure_ansible_automation.py
│   ├── netbox-discover-proxmox-cluster-and-nodes.py
│   ├── netbox-discover-proxmox-vms.py
│   ├── requirements.txt               Setup deps (adds awxkit)
│   └── helpers/
│       ├── proxmox_api_common.py
│       ├── netbox_proxmox_api.py
│       ├── netbox_proxmox_cluster.py
│       ├── netbox_objects.py
│       ├── netbox_branches.py
│       ├── ansible_automation_awx.py
│       └── ansible_automation_awx_manager.py
│
└── templates/
    └── bind9/zone-template.j2         Jinja2 BIND9 zone (DNS roadmap feature)
```

---

## 5. Configuration Model

### 5.1. Master config — `conf.d/netbox_setup_objects.yml-sample`

This single YAML file is consumed by **every setup script** and also by
the discovery scripts. It is split into seven top-level sections.

```yaml
proxmox_api_config:
  node: pve
  api_host: <proxmox host or IP>
  api_port: 8006
  api_user: proxmox_api_user
  api_token_id: <token name>
  api_token_secret: <token secret>
  verify_ssl: false

netbox_api_config:
  api_proto: http            # http | https
  api_host: <netbox host or IP>
  api_port: 8000
  api_token: <netbox secret>
  verify_ssl: false

proxmox:
  ssh_known_hosts_file: /path/known_hosts
  create_vms_templates: true     # opt-in: populate proxmox-vm-templates choice set
  create_lxc_templates: true     # opt-in: populate proxmox-lxc-templates choice set
  cluster_name: <cluster name>
  node_commands:
    dmidecode_command: /usr/sbin/dmidecode
    lshw_command:      /usr/bin/lshw
    ethtool_command:   /usr/sbin/ethtool
    ipaddr_command:    /usr/sbin/ip -br a

netbox:
  branch:         <branch name>      # optional — NetBox Branching plugin
  branch_timeout: 120                # optional — seconds
  site:          "Home Lab"          # optional
  cluster_role:  "Proxmox"
  device_role:   "Proxmox node"
  vm_role:       "Proxmox VM"
  lxc_role:      "Proxmox LXC"

automation_type: ansible_automation   # or flask_application

ansible_automation:
  host: <awx host>
  http_proto: http | https
  http_port: 80
  ssl_verify: false
  username: awx_user
  password: awx_password
  settings:
    project:
      name: netbox-proxmox-ee-test1
      scm_type: git
      scm_url: https://github.com/netboxlabs/netbox-proxmox-automation.git
      scm_branch: main
    inventory:
      name: Demo Inventory
    hosts:
      name: localhost

flask_application:
  host: <flask host>
  http_proto: http | https
  http_port: 9000
  ssl_verify: false
  netbox_webhook_name: "netbox-proxmox-webhook"
```

The boolean keys at `proxmox.create_vms_templates` and
`proxmox.create_lxc_templates` toggle **whether the corresponding choice
sets are populated** at setup time. If a deployment never uses LXC, set
`create_lxc_templates: false` to skip the LXC template choice set
entirely.

### 5.2. Flask runtime config — `app_config.yml-sample`

The Flask app does **not** read the master config above. It loads a
trimmed `app_config.yml` from its current working directory:

```yaml
netbox_webhook_name: "netbox-proxmox-webhook"

proxmox_api_config:
  api_host: ...
  api_port: 8006
  api_user: ...
  api_token_id: ...
  api_token_secret: ...
  verify_ssl: false

netbox_api_config:
  api_proto: http
  api_host: ...
  api_port: 8000
  api_token: ...
  verify_ssl: false
```

> **No environment variables anywhere.** The entire codebase reads
> configuration exclusively from YAML files passed via `--config /path` or
> from the hardcoded `app_config.yml`. There is **no** `os.environ` usage
> in the Flask app or helpers.

---

## 6. NetBox Customization Layer

The setup script `netbox_setup_objects_and_custom_fields.py` introduces a
fixed schema of choice sets, custom fields, and tags into NetBox. None of
these are NetBox plugins; they are pure NetBox configuration objects
created via the REST API.

### 6.1. Custom Field Choice Sets

| Choice set | Populated from | Used by |
|---|---|---|
| `proxmox-vm-templates`   | All Proxmox VM templates (`is_template == 1`, `type == qemu`) | `proxmox_vm_templates` field |
| `proxmox-vm-storage`     | Proxmox storage volumes minus `dir`-content stores | `proxmox_vm_storage`, `proxmox_disk_storage_volume` |
| `proxmox-lxc-templates`  | `local:vztmpl/*.tzst` images on each node | `proxmox_lxc_templates` |
| `proxmox-cluster-nodes`  | All cluster member node names | `proxmox_node` |
| `proxmox-vm-type`        | Static: `vm`, `lxc` | `proxmox_vm_type` |

### 6.2. Custom Fields

All fields are attached to `virtualization.virtualmachine` (some are also
attached to `virtualization.virtualdisk`).

| Custom field | Type | Group | Purpose |
|---|---|---|---|
| `proxmox_node`              | choice (`proxmox-cluster-nodes`) | Proxmox (common) | Target node where the VM lives. Migration trigger. |
| `proxmox_vm_type`           | choice (`proxmox-vm-type`)       | Proxmox (common) | Discriminator: `vm` vs `lxc`. Drives Flask dispatch. |
| `proxmox_vmid`              | text                              | Proxmox (common) | Numeric Proxmox VMID (set by clone/create handler). |
| `proxmox_vm_storage`        | choice (`proxmox-vm-storage`)    | Proxmox (common) | Default storage volume for primary disk. |
| `proxmox_public_ssh_key`    | text                              | Proxmox (common) | Cloud-init SSH key for Ubuntu user. |
| `proxmox_vm_templates`      | choice (`proxmox-vm-templates`)  | Proxmox VM       | Template VMID to clone from (VM type). |
| `proxmox_disk_storage_volume` | choice (`proxmox-vm-storage`)  | Proxmox VM       | Storage for non-primary disks (per VirtualDisk). |
| `proxmox_lxc_templates`     | choice (`proxmox-lxc-templates`) | Proxmox LXC      | LXC OS template path (e.g. `local:vztmpl/foo.tzst`). |

### 6.3. Tags

Created on first run of the discovery scripts:

| Tag | Color | Applied to |
|---|---|---|
| `proxmox-vm-discovered`  | red   | VMs created by `netbox-discover-proxmox-vms.py vm` |
| `proxmox-lxc-discovered` | (default) | LXCs created by `netbox-discover-proxmox-vms.py lxc` |

---

## 7. Setup / Provisioning Scripts

Every script accepts `--config /path/to/yml` and `--debug`. They are meant
to be run once per environment (or once per change, idempotent) from a
dedicated `venv` populated by `setup/requirements.txt`.

### 7.1. `netbox_setup_objects_and_custom_fields.py`

Bootstraps NetBox with everything the integration assumes will exist.

- Reads master config.
- Connects to Proxmox via `NetBoxProxmoxAPIHelper` to enumerate templates,
  storage volumes, and cluster nodes.
- Creates: cluster type (`Proxmox`), cluster (named after
  `proxmox.cluster_name`), the five choice sets (Section 6.1), all eight
  custom fields (Section 6.2), and the tags.
- Branch-aware: if `netbox.branch` is set, the entire run executes inside
  a NetBox branch via `helpers.netbox_branches.NetBoxBranches`.
- Idempotent: every call funnels through `NetBox.createOrUpdate()`, which
  diffs each declared field against the live object and only writes on
  drift.

### 7.2. `netbox_setup_webhook_and_event_rules.py`

Creates the webhook(s) and the 17 event rules.

- Branches on `automation_type`:
  - `flask_application` → creates **one** webhook pointing at
    `http://<flask host>:<port>/<netbox_webhook_name>/`, then registers
    every event rule with that single webhook.
  - `ansible_automation` → instantiates `AnsibleAutomationAWXManager`,
    queries AWX for job templates (one per playbook), creates **one
    webhook per template** (each posts to its own
    `/api/v2/job_templates/<id>/launch/` endpoint with a Jinja2 body
    template that hands the NetBox event payload to AWX as `extra_vars`).
- The full event-rule dictionary is the single source of truth — see
  [Section 9](#9-event-rules-catalog).

### 7.3. `configure_ansible_automation.py`

Orchestrates AWX: `create` and `destroy` subcommands.

`create` flow:

1. Login via `awxkit` using config credentials.
2. `create_organization`, `create_inventory`, `create_host`
   (`localhost` with `ansible_connection: local`).
3. `create_execution_environment` pointing at a container image (default
   `localhost:5000/awx/ee/exec-env-test1:1.1.0`).
4. `create_project` against the upstream Git repo
   (`https://github.com/netboxlabs/netbox-proxmox-automation.git`,
   branch `main`); polls until project sync `status == successful`.
5. `create_credential_type` with the NetBox+Proxmox schema (see
   Section 11.1).
6. `create_credential` populated from the master config.
7. For each playbook in `playbooks/awx-*.yml`, `create_job_template` with
   `ask_variables_on_launch=True` and `ask_credential_on_launch=True`,
   then `add_credential` to attach the shared credential.

`destroy` undoes the inverse: deletes all job templates, the project, the
credential, and (only if not the AWX defaults) the host and inventory.

### 7.4. `netbox-discover-proxmox-cluster-and-nodes.py`

One-shot Proxmox→NetBox sync of the **physical/virtual host
infrastructure** (not the workloads). Added in 2025.11.X.

- Interactively prompts for SSH credentials per Proxmox node (password
  vs key, sudo y/n).
- Per node, runs over SSH:
  - `dmidecode -t system` → manufacturer, product name, serial number.
    (Special-case: Protectli hardware uses the `eth0` MAC as the serial.)
  - `cat /sys/class/net/<iface>/address` → MAC address.
  - `ethtool <iface>` → speed → mapped to NetBox interface type
    (`1gbase-t`, `2.5gbase-t`, `10gbase-t`, `bridge`, `other`).
- Per node, queries Proxmox API for the network configuration
  (`nodes/<node>/network`) to find bridges and physical interfaces.
- Writes back into NetBox: Site, Cluster Type, Cluster Group, Cluster,
  Manufacturer, Platform (Proxmox version string), Device Role, Device
  Type, Device, physical interfaces, bridge interfaces, IPv4/IPv6
  addresses, MAC address objects (`dcim.mac_addresses` with
  `primary_mac_address` linkage on each interface).
- Has a `--simulate` mode that reads precomputed JSON from
  `.simulate/proxmox_nodes/<node>/{system,networking}.json` instead of
  hitting real hardware. Used internally for dev/testing.

### 7.5. `netbox-discover-proxmox-vms.py`

One-shot Proxmox→NetBox sync of the **workloads**. Subcommands `vm` and
`lxc`.

- Builds a set of existing NetBox VM names so it never duplicates.
- Queries Proxmox cluster resources for all qemu VMs / lxc containers and
  their full configs (vcpus, memory, disks, network interfaces, SSH
  keys).
- For each new entry: creates the `virtual_machine`, attaches all
  interfaces (with MACs assigned via separate `dcim.mac_addresses`
  objects), assigns IPv4 addresses (skipping IPv6 link-local and
  stripping zone IDs), sets `primary_ip4` on whichever interface presents
  itself as `eth0`/`net0`, then creates `virtualization.virtual_disks`
  for every disk found.
- Tags every newly inserted VM with `proxmox-vm-discovered` (or
  `-lxc-discovered`) so a follow-up curator pass can spot them.

---

## 8. Helper Modules (`setup/helpers/`)

The seven helpers under `setup/helpers/` are where most of the durable
patterns live. They are also reused by the Flask app's `helpers/`
package via copy-and-adapt rather than direct import — the Flask app is
a self-contained subtree.

### 8.1. `proxmox_api_common.ProxmoxAPICommon`

Base class shared by `NetBoxProxmoxAPIHelper` and
`NetBoxProxmoxCluster`. On construction it builds a `proxmoxer.ProxmoxAPI`
session (token auth) and immediately collects:

- `self.proxmox_cluster_name` — from `cluster.status.get()`.
- `self.proxmox_nodes` — `{name: {ip, online, version}}` for every node.
- A `--simulate` shortcut reads the same shape from JSON files on disk
  for tests.

### 8.2. `netbox_proxmox_api.NetBoxProxmoxAPIHelper`

Extends `ProxmoxAPICommon` with workload-level state:

- `proxmox_vm_templates`, `proxmox_lxc_templates` — keyed by name; LXC
  templates are scanned per node.
- `proxmox_vms`, `proxmox_lxc` — non-template workloads; duplicate names
  across nodes are disambiguated as `name--vmid`.
- `proxmox_storage_volumes` (vm storage = non-`dir` content),
  `proxmox_lxc_storage_volumes` (`dir` content with `vztmpl`).
- `proxmox_get_vms_configurations()` — for each VM: parses every `scsiN`
  key with regex, normalizes disk size to MB, strips `qemu-guest-agent`
  network info to just non-loopback / non-docker interfaces,
  URL-decodes the SSH public key.

### 8.3. `netbox_objects` — typed NetBox accessors

Every NetBox object type used by the integration has a thin subclass of a
generic `NetBox` base. The base class implements:

- `findBy(...)` / `findByMulti(...)` — single- or multi-field lookup.
- `createOrUpdate()` — drift-detect: walk every declared field and only
  PATCH on a real diff; otherwise PUT-create + re-fetch by ID.
- Debug payload sanitization that masks `password`, `token`, `secret`,
  `mac_address`, `mac`, and IP-address fields before logging.
- `__netbox_make_slug(s)` — `re.sub(r'\W+', '-', s).lower()`.

The 20+ subclasses cover Sites, Manufacturers, Platforms, Device Types
(plus interface templates), Device Roles, Devices, Device Interfaces
(physical + bridge), MAC-address mapping, Tags, Custom Fields, Custom
Field Choice Sets, Cluster Types/Groups/Clusters, Virtual Machines,
Virtual Machine Interfaces (with MAC linkage), IP Addresses, Webhooks,
and Event Rules. The pattern in every subclass is:

```python
def __init__(self, nb_obj, payload, ...):
    super().__init__(nb_obj)
    self.object_type = "dcim.devices"
    self.required_fields = ["name", "device_type", "site", "role"]
    self.payload = payload
    if self.findBy("name", payload["name"]):
        self.createOrUpdate()
    elif self.hasRequired():
        self.createOrUpdate()
```

### 8.4. `netbox_branches.NetBoxBranches`

Wraps the optional NetBox Branching plugin:

- Lists existing branches via `nb.plugins.branching.branches.all()`.
- `create_branch()` — creates the branch, polls every second up to
  `branch_timeout` seconds (default 120) until `status == ready`, then
  installs `X-NetBox-Branch: <name>` on the pynetbox HTTP session so all
  subsequent calls execute against the branch.
- `activate_branch()` — convenience wrapper; raises if the branch has
  already been merged.
- `delete_branch()`, `branch_changes()`, `show_branches()`.

The Branching plugin is **only** wired into the setup scripts; the Flask
runtime path does not (and does not need to) use it.

### 8.5. `netbox_proxmox_cluster.NetBoxProxmoxCluster`

The discovery-time SSH layer. Extends `ProxmoxAPICommon` with:

- `generate_proxmox_node_creds_configuration()` — interactive prompts.
- `__get_proxmox_node_info_cmd(node, cmd)` — paramiko `exec_command`,
  PTY-based sudo passthrough.
- `get_proxmox_nodes_system_information()` — runs `dmidecode`.
- `get_proxmox_nodes_network_interfaces()` — combines Proxmox API
  network info with `ethtool` and `/sys/class/net/<iface>/address`.

### 8.6. `ansible_automation_awx.AnsibleAutomationAWX`

Thin wrapper over `awxkit`. `awxkit.config` is patched with the host /
proto / port from config, and the class exposes generic helpers:

```
get_object_by_name(method, name)
get_object_by_id(method, id)
get_object_id(method, name) -> int
get_objects_by_kwargs(method, **kwargs)
create_object(method, name, payload)
delete_object_by_name(method, name)
```

### 8.7. `ansible_automation_awx_manager.AnsibleAutomationAWXManager`

Builds the AWX object graph on top of the base helper:

`create_organization → create_inventory → create_host →
create_execution_environment → create_project → create_credential_type →
create_credential → create_job_template (per playbook) →
create_job_template_credential`.

Each step caches the created object's ID on `self` (`self.org_id`,
`self.inventory_id`, etc.) for later reuse and teardown.

---

## 9. Event Rules Catalog

The 17 event rules registered by `netbox_setup_webhook_and_event_rules.py`.
Action filters are NetBox-native (`type_create`, `type_update`,
`type_delete`).

| # | Event rule name | Model | Triggers | Conditions | Maps to playbook / Flask handler |
|---|---|---|---|---|---|
| 1 | `proxmox-clone-vm-and-set-resources` | virtualmachine | created | status=staged, type=vm | `awx-proxmox-clone-vm-and-set-resources.yml` / `proxmox_clone_vm` |
| 2 | `proxmox-vm-set-resources` | virtualmachine | updated | status=staged, type=vm | (resources update) / `proxmox_update_vm_vcpus_and_memory` |
| 3 | `proxmox-set-ipconfig0` | virtualmachine | created+updated | status=staged, type=vm, primary_ip4≠null | `awx-proxmox-set-ipconfig0.yml` / `proxmox_set_ipconfig0` (+ optional ssh key) |
| 4 | `proxmox-remove-vm` | virtualmachine | deleted | type=vm | `awx-proxmox-remove-vm.yml` / `proxmox_delete_vm` |
| 5 | `proxmox-stop-vm` | virtualmachine | updated | status=offline, type=vm | `awx-proxmox-stop-vm.yml` / `proxmox_stop_vm` |
| 6 | `proxmox-start-vm` | virtualmachine | updated | status=active, type=vm | `awx-proxmox-start-vm.yml` / `proxmox_start_vm` |
| 7 | `proxmox-migrate-vm` | virtualmachine | updated | status∈{active,offline}, type=vm, proxmox_node changed | `awx-proxmox-migrate-vm.yml` / `NetBoxProxmoxHelperMigrate.migrate_vm` |
| 8 | `proxmox-add-vm-disk` | virtualdisk | created | name≠scsi0, name≠rootfs | `awx-proxmox-add-vm-disk.yml` / `proxmox_add_disk` |
| 9 | `proxmox-resize-vm-disk` | virtualdisk | updated | name≠rootfs | `awx-proxmox-resize-vm-disk.yml` / `proxmox_resize_disk` |
| 10 | `proxmox-remove-vm-disk` | virtualdisk | deleted | name≠scsi0 | `awx-proxmox-remove-vm-disk.yml` / `proxmox_delete_disk` |
| 11 | `proxmox-clone-lxc-and-set-resources` | virtualmachine | created | status=staged, type=lxc | `awx-proxmox-clone-lxc-and-set-resources.yml` / `proxmox_create_lxc` |
| 12 | `proxmox-lxc-set-resources` | virtualmachine | updated | status=staged, type=lxc | (resources update) / `proxmox_update_lxc_vpus_and_memory` |
| 13 | `proxmox-set-netif` | virtualmachine | created+updated | status=staged, type=lxc, primary_ip4≠null | `awx-proxmox-set-netif.yml` / `proxmox_lxc_set_net0` |
| 14 | `proxmox-remove-lxc` | virtualmachine | deleted | type=lxc | `awx-proxmox-remove-lxc.yml` / `proxmox_delete_lxc` |
| 15 | `proxmox-stop-lxc` | virtualmachine | updated | status=offline, type=lxc | `awx-proxmox-stop-lxc.yml` / `proxmox_stop_lxc` |
| 16 | `proxmox-start-lxc` | virtualmachine | updated | status=active, type=lxc | `awx-proxmox-start-lxc.yml` / `proxmox_start_lxc` |
| 17 | `proxmox-resize-lxc-disk` | virtualdisk | updated | name=rootfs | `awx-proxmox-resize-lxc-disk.yml` / `proxmox_lxc_resize_disk` |

The rules use a single shared status taxonomy:

- `staged` — desired-state authoring; initial creation and resource
  changes happen here.
- `active` — operator wants the workload running.
- `offline` — operator wants the workload stopped.

Status transitions are how the integration models lifecycle.

---

## 10. Ansible Playbooks

All playbooks share a uniform shape:

```yaml
- hosts: all
  connection: local
  gather_facts: false
  vars:
    proxmox_env_info: "{{ proxmox_env_info | default({}) }}"   # from credential
    netbox_env_info:  "{{ netbox_env_info  | default({}) }}"   # from credential
    vm_config:        "{{ vm_config        | default({}) }}"   # from webhook body
  tasks:
    - include_tasks: ansible-tasks/collect-proxmox-vm.yml      # or lxc
    - <action via community.proxmox or community.general>
    - <write back to NetBox via netbox.netbox>
```

Credential injection is performed by AWX's credential type
(see [Section 11](#11-awx--tower--aap-integration)); per-event variables
arrive as `extra_vars` populated by the webhook body template.

### 10.1. Shared task includes — `ansible-tasks/`

| File | Purpose |
|---|---|
| `collect-proxmox-vm.yml`  | Runs `community.proxmox.proxmox_cluster_join_info` then `proxmox_vm_info` (qemu) per node; produces `collected_proxmox_vm` (`name → vmid`) and `proxmox_node_info` (`name → ip`). |
| `collect-proxmox-lxc.yml` | Same shape for LXC: produces `collected_proxmox_lxc`. |

### 10.2. VM playbooks

| Playbook | Purpose |
|---|---|
| `awx-proxmox-clone-vm-and-set-resources.yml` | Full clone of a template, sets cores/vcpus/memory, discovers the new VM, writes vmid + scsi0 disk back to NetBox. |
| `awx-proxmox-remove-vm.yml`                  | Force-stops then deletes a VM by vmid. |
| `awx-proxmox-start-vm.yml`                   | Starts a VM and re-discovers state. |
| `awx-proxmox-stop-vm.yml`                    | Force-stops a VM. |
| `awx-proxmox-set-ipconfig0.yml`              | Sets `ipconfig0=ip=…,gw=…` and SSH key via cloud-init. Gateway is derived as `last_octet=1`. |
| `awx-proxmox-add-vm-disk.yml`                | `community.proxmox.proxmox_disk` `state: present`, size MB→GB. |
| `awx-proxmox-resize-vm-disk.yml`             | `state: resized`. |
| `awx-proxmox-remove-vm-disk.yml`             | `state: absent`. |
| `awx-proxmox-migrate-vm.yml`                 | `migrate: true, timeout: 600s`; no-ops if source == target. |

### 10.3. LXC playbooks

| Playbook | Purpose |
|---|---|
| `awx-proxmox-clone-lxc-and-set-resources.yml` | Creates LXC from OS template (full clone), sets cores/cpus/memory/pubkey/storage, writes vmid + rootfs disk to NetBox. |
| `awx-proxmox-remove-lxc.yml`     | Force-stop + delete. |
| `awx-proxmox-start-lxc.yml`      | Start. |
| `awx-proxmox-stop-lxc.yml`       | Stop (force). |
| `awx-proxmox-resize-lxc-disk.yml`| Grow `rootfs`. |
| `awx-proxmox-set-netif.yml`      | Set `net0=name=net0,bridge=vmbr0,ip=…,gw=…,firewall=1`. |

### 10.4. DNS playbook (roadmap, currently observational)

`awx-update-dns.yml` reads NetBox DNS plugin objects (zones, SOA, NS, MX,
all A/CNAME/PTR records) and renders
`templates/bind9/zone-template.j2`. As of 2025.11.01 it only **prints**
the rendered zone — there is no write-out task, no `nsupdate`, no
gss-tsig. The roadmap calls out gss-tsig as the planned next step.

`templates/bind9/zone-template.j2` consumes:

- `dns_zone_origin`, `dns_zone_ttl`
- `collected_soa` (mname, rname, serial, refresh, retry, expire, minimum)
- `collected_ns` (list)
- `collected_mx` (list)
- `collected_rr` (list of `{name, ttl, type, value}`, sorted; PTR records
  formatted differently)

### 10.5. Unit conversion divergence

> Disk sizes in NetBox are stored as **MB**. Proxmox uses **GB** at the
> API surface for `qm` operations and `community.proxmox.proxmox_disk`.
>
> - Ansible playbooks divide MB by **1024** to produce GB.
> - Flask helpers divide MB by **1000** to produce GB.
>
> Both work for typical disk sizes, but they are not strictly equivalent.
> A disk authored as `10240 MB` becomes `10 GiB` via Ansible and
> `10.24 GB` via the Flask app.

---

## 11. AWX / Tower / AAP Integration

### 11.1. Credential Type — `NetBox Proxmox Credential Type`

Created by `AnsibleAutomationAWXManager.create_credential_type` with two
linked schemas:

**Inputs** (fields the user fills in once per credential):

```yaml
fields:
  - id: proxmox_api_host
  - id: proxmox_api_port
  - id: proxmox_api_user
  - id: proxmox_api_token_id
  - id: proxmox_api_token_secret   # secret
  - id: proxmox_node
  - id: proxmox_verify_ssl
  - id: netbox_api_proto
  - id: netbox_api_host
  - id: netbox_api_port
  - id: netbox_api_token           # secret
  - id: netbox_verify_ssl
required: [<all of the above>]
```

**Injectors** (how those values become Ansible `extra_vars`):

```yaml
extra_vars:
  proxmox_env_info:
    api_host:         '{{ proxmox_api_host }}'
    api_port:         '{{ proxmox_api_port }}'
    api_user:         '{{ proxmox_api_user }}'
    api_token_id:     '{{ proxmox_api_token_id }}'
    api_token_secret: '{{ proxmox_api_token_secret }}'
    node:             '{{ proxmox_node }}'
    verify_ssl:       '{{ proxmox_verify_ssl }}'
  netbox_env_info:
    api_proto:  '{{ netbox_api_proto }}'
    api_host:   '{{ netbox_api_host }}'
    api_port:   '{{ netbox_api_port }}'
    api_token:  '{{ netbox_api_token }}'
    verify_ssl: '{{ netbox_verify_ssl }}'
```

This is why every playbook reads `proxmox_env_info.*` and
`netbox_env_info.*` rather than top-level vars — the credential type
namespaces them.

### 11.2. Project source

- SCM type: `git`
- Default URL: `https://github.com/netboxlabs/netbox-proxmox-automation.git`
- Default branch: `main`
- Project name: `netbox-proxmox-ee-test1`

### 11.3. Execution Environment

- Default name: `netbox-proxmox-exec-env`
- Default image: `localhost:5000/awx/ee/exec-env-test1:1.1.0`
- Required collections: `awx.awx`, `community.general`,
  `community.proxmox`, `netbox.netbox`
- Required Python deps: `proxmoxer`, `pynetbox`, `requests`, `lxml`

The image must be built and published separately by the operator (the
`docs/configure-awx-aap.md` page sketches the Containerfile recipe).

### 11.4. Job Template generation

For each `playbooks/awx-*.yml`:

- Template name = playbook filename minus `playbooks/awx-` prefix and
  minus `.yml` (e.g. `proxmox-clone-vm-and-set-resources`).
- Inventory = the configured demo inventory.
- Credentials = the shared `NetBox Proxmox Credential Type` credential.
- `ask_variables_on_launch = True` — required so the webhook can deliver
  `vm_config` as `extra_vars`.
- `ask_credential_on_launch = True`.

### 11.5. Webhook body template (per template)

The setup script generates one Jinja2 body template per job template
that maps the NetBox event payload onto `vm_config`. Example for
`proxmox-clone-vm-and-set-resources`:

```jinja
{% raw %}
{
  "extra_vars": {
    "vm_config": {
      "name":     "{{ data['name'] }}",
      "vmid":     "{{ data['custom_fields']['proxmox_vmid'] }}",
      "template": "{{ data['custom_fields']['proxmox_vm_templates'] }}",
      "node":     "{{ data['custom_fields']['proxmox_node'] }}",
      "storage":  "{{ data['custom_fields']['proxmox_vm_storage'] }}",
      "vcpus":    {{ data['vcpus'] }},
      "memory":   {{ data['memory'] }}
    }
  }
}
{% endraw %}
```

---

## 12. Flask Webhook Application

Located at
`netbox-event-driven-automation-flask-app/`, the Flask app is the
"battery-included" alternative to AWX. It is the simpler path — one
process, no Ansible, no external orchestrator.

### 12.1. Startup (`app.py`)

- `VERSION = '2025.11.01'`.
- Loads `app_config.yml` from the working directory at import time. Hard
  failure if missing or if `netbox_webhook_name` is absent.
- Module-level logger writes to
  `netbox-proxmox-webhook-listener.log` at INFO level.
- `app = Flask(__name__)`, `api = flask_restx.Api(app, version=VERSION,
  title="NetBox-Proxmox Webhook Listener")`.
- `ns = api.namespace(app_config['netbox_webhook_name'])` — every route is
  mounted under `/<webhook_name>/...`. With the sample config, that
  becomes `/netbox-proxmox-webhook/`.
- A `session` dict tracks `request_count` and `last_called` for the
  status route.

### 12.2. Routes

| Route | Method | Purpose |
|---|---|---|
| `/<webhook_name>/status/` | GET  | Returns version, server start time, request count, last call time. Sanitizes any logged headers (strips `\r\n`). |
| `/<webhook_name>/`        | POST | Main webhook ingress. |

### 12.3. Dispatch table

The POST handler validates that the body is JSON and that `model` and
`event` are present, then dispatches:

**`model == 'virtualmachine'`** — reads `proxmox_node` from
`custom_fields` (errors out if missing). Branches on
`custom_fields.proxmox_vm_type`:

| `proxmox_vm_type` | event       | status   | Action |
|---|---|---|---|
| `vm`  | created  | staged  | `NetBoxProxmoxHelperVM.proxmox_clone_vm` |
| `vm`  | updated  | staged  | `proxmox_update_vm_vcpus_and_memory` (+ optional `proxmox_set_ipconfig0`, `proxmox_set_ssh_public_key`) |
| `vm`  | deleted  | staged  | `proxmox_delete_vm` |
| `vm`  | updated  | offline | If node unchanged → `proxmox_stop_vm`. Else → `NetBoxProxmoxHelperMigrate.migrate_vm`. |
| `vm`  | updated  | active  | If node unchanged → `proxmox_start_vm`. Else → `migrate_vm`. |
| `vm`  | deleted  | (any)   | `proxmox_delete_vm` |
| `lxc` | created  | staged  | `NetBoxProxmoxHelperLXC.proxmox_create_lxc` |
| `lxc` | updated  | staged  | `proxmox_lxc_set_net0` (+ optional resource update) |
| `lxc` | deleted  | staged  | `proxmox_delete_lxc` |
| `lxc` | updated  | offline | `proxmox_stop_lxc` |
| `lxc` | updated  | active  | `proxmox_start_lxc` |
| `lxc` | deleted  | (any)   | `proxmox_delete_lxc` |

**`model == 'virtualdisk'`** — discriminates LXC vs VM by `data['name']
== 'rootfs'`, then resolves the parent VM's `proxmox_node` via
`NetBoxProxmoxHelper.netbox_get_proxmox_node_from_vm_id()`.

| Disk class | event   | Action |
|---|---|---|
| LXC (`name==rootfs`) | updated | `proxmox_lxc_resize_disk` (only if size changed) |
| LXC                  | deleted | no-op (200) — rootfs is removed with the LXC itself |
| VM                   | created | `proxmox_add_disk` |
| VM                   | updated | `proxmox_resize_disk` |
| VM                   | deleted | `proxmox_delete_disk` (refuses to delete `scsi0`) |

All handlers return `(status_code, {"result": "<message>"})`.

### 12.4. Helper class hierarchy (`helpers/netbox_proxmox.py`)

```
NetBoxProxmoxHelper
 ├── NetBoxProxmoxHelperVM        — qemu/cloud-init operations
 ├── NetBoxProxmoxHelperLXC       — lxc operations
 └── NetBoxProxmoxHelperMigrate   — cluster-level migrate operations
```

#### `NetBoxProxmoxHelper` (base)

| Method | Purpose |
|---|---|
| `__init__(cfg, proxmox_node, debug)` | Builds `proxmoxer.ProxmoxAPI` (token auth) and `pynetbox.api`. |
| `json_data_check_proxmox_vmid_exists(payload)` | Raises if `custom_fields.proxmox_vmid` missing. |
| `netbox_get_proxmox_vmid(vm_obj_id)` | Returns the `proxmox_vmid` custom field for a NetBox VM. |
| `netbox_get_proxmox_node_from_vm_id(vm_id)` | Returns the `proxmox_node` custom field. |
| `proxmox_job_get_status(upid)` | Polls `nodes/<n>/tasks/<upid>/status` until `status == 'stopped'`. |
| `generate_gateway_from_ip_address(addr, last_quad=1)` | Computes `x.y.z.1` from `x.y.z.W/prefix`. |
| `proxmox_get_vms()` | All non-template VMs as `{name: vmid}`. |
| `create_vm_root_disk_in_netbox(vm_id, name, info)` | Parses `storage:vm-NNN-disk-N,size=XG` and creates `virtualization.virtual_disks` in NetBox. |

#### `NetBoxProxmoxHelperVM`

| Method | Proxmox API call |
|---|---|
| `proxmox_clone_vm(json)` | `POST nodes/<n>/qemu/<srcvmid>/clone` (full=1, newid, name); polls; sets vcpus/memory. |
| `proxmox_update_vm_vcpus_and_memory(json)` | `POST nodes/<n>/qemu/<vmid>/config` (cores, memory). |
| `proxmox_start_vm(json)` | `POST nodes/<n>/qemu/<vmid>/status/start`. |
| `proxmox_stop_vm(json)`  | `POST .../status/stop`. |
| `proxmox_delete_vm(json)` | `stop → DELETE nodes/<n>/qemu/<vmid>`. |
| `proxmox_set_ipconfig0(json)` | `POST .../config` with `ipconfig0=ip=<addr>,gw=<gw>`. |
| `proxmox_set_ssh_public_key(json)` | URL-encodes key, `POST .../config` with `sshkeys=…`. |
| `proxmox_add_disk(json)` | If name is `scsi0`: delegate to resize; else `POST .../config` with `scsiN=<storage>:<sizeGB>,backup=0,ssd=0`. |
| `proxmox_resize_disk(json)` | `PUT nodes/<n>/qemu/<vmid>/resize` (`disk`, `size`). |
| `proxmox_delete_disk(json)` | `PUT nodes/<n>/qemu/<vmid>/unlink` (`idlist`, `force=1`). Refuses `scsi0`. |

#### `NetBoxProxmoxHelperLXC`

| Method | Proxmox API call |
|---|---|
| `proxmox_create_lxc(json)` | `POST nodes/<n>/lxc` with vmid/hostname/ostemplate/cores/memory/storage/password=`netbox-proxmox-automation`/onboot=1/unprivileged=1/swap=0/ssh-public-keys (optional). |
| `proxmox_update_lxc_vpus_and_memory(json)` | `PUT nodes/<n>/lxc/<vmid>/config` (cores, memory). NB: job polling is commented out in source. |
| `proxmox_lxc_set_net0(json)` | `PUT .../config` with `net0=name=net0,bridge=vmbr0,ip=…,gw=…,firewall=1`. |
| `proxmox_lxc_resize_disk(json)` | `PUT .../resize` (`disk=rootfs`, `size`). |
| `proxmox_start_lxc(json)` | `POST .../status/start`. |
| `proxmox_stop_lxc(json)`  | `POST .../status/stop`. |
| `proxmox_delete_lxc(json)` | `stop → DELETE nodes/<n>/lxc/<vmid>`. |

#### `NetBoxProxmoxHelperMigrate`

| Method | Notes |
|---|---|
| `__init__(cfg, proxmox_node, debug)` | super(); then loads cluster nodes + VM/LXC name→{vmid,node} maps. |
| `__wait_for_migration_task(node, upid)` | 10-minute timeout, returns 200 on `exitstatus == OK`. |
| `migrate_vm(vmid, source, target)` | `POST nodes/<source>/qemu/<vmid>/migrate` with `target` and `online=1`. |
| `migrate_lxc(vmid, source, target)` | Defined for symmetry, **not invoked** from `app.py` (LXC migration is a known limitation). |

### 12.5. Execution model & caveats

- **Synchronous, single-threaded inside each request.** No queue, no
  worker pool, no Celery/RQ/Redis. Long-running clone or migration
  operations block the gunicorn worker for their full duration; sizing
  workers (`-w 4` in the docs) is the only knob.
- **No retry, no idempotency token.** A duplicate webhook delivery
  causes a duplicate Proxmox operation (or fails benignly if the target
  state already matches).
- **`verify_ssl=False` is hardcoded for Proxmox** in
  `helpers/netbox_proxmox.py`'s constructor regardless of what
  `proxmox_api_config.verify_ssl` says. The NetBox client honors the
  config value. (This is a known divergence not documented upstream.)
- **No environment variables.** Only file-based config.
- **Request lifecycle logging** is included; debug mode masks
  credentials in logged payloads.

### 12.6. Production deployment

The docs prescribe:

```bash
gunicorn -w 4 -b 0.0.0.0:9000 'app:app'
```

NGINX in front (TLS termination, optional auth) is left as an exercise.
No systemd unit, no init script, no Dockerfile is provided.

---

## 13. Discovery Workflows

There are two entirely separate one-shot discovery scripts. They are
**not** invoked by webhooks and they do **not** run on a schedule.

### 13.1. Cluster + node discovery

Script: `setup/netbox-discover-proxmox-cluster-and-nodes.py`

| Source | What is collected |
|---|---|
| Proxmox API (`cluster.status`) | Cluster name, node names, IPs, online flag, version per node |
| SSH `dmidecode -t system`     | Manufacturer, product name, serial number |
| SSH `cat /sys/class/net/<ifc>/address` | MAC per interface |
| SSH `ethtool <ifc>`           | Link speed → mapped to NetBox interface type |
| Proxmox API (`nodes/<n>/network`) | Bridge / physical interface topology |

Output (in NetBox): Sites, Cluster Types, Cluster Groups, Clusters,
Manufacturers, Platforms, Device Roles, Device Types, Devices, Device
Interfaces (physical and bridge), MAC Address objects, IP Addresses
(IPv4 + IPv6).

### 13.2. VM + LXC discovery

Script: `setup/netbox-discover-proxmox-vms.py {vm,lxc}`

For each Proxmox workload not already represented in NetBox:

- Creates `virtualization.virtual_machines` with vcpus, memory, status.
- Creates `virtualization.interfaces` per Proxmox NIC and assigns the
  MAC via a separate `dcim.mac_addresses` object linked through
  `primary_mac_address`.
- Assigns IPv4 addresses (link-local IPv6 skipped, zone IDs stripped).
- Sets `primary_ip4` on `eth0` / `net0`.
- Creates `virtualization.virtual_disks` per Proxmox disk.
- Tags the VM with `proxmox-vm-discovered` (or `-lxc-discovered`).

The discovery scripts are **branch-aware** when `netbox.branch` is set in
config — they perform the entire write inside a NetBox branch via
`NetBoxBranches`.

---

## 14. Migration Workflow

Migration is the single feature where a NetBox **update** event is
interpreted as a node-change rather than a state-change.

Trigger: event rule `proxmox-migrate-vm` fires on
`virtualmachine.updated` when `status ∈ {active, offline}`, `type == vm`,
**and** `proxmox_node` differs between `prechange` and `postchange`
snapshots.

Flask path:

```
app.py
  └─ NetBoxProxmoxHelperMigrate(app_config, proxmox_node=postchange.node)
       └─ migrate_vm(vmid, source=prechange.node, target=postchange.node)
            └─ POST nodes/<source>/qemu/<vmid>/migrate  online=1
            └─ poll task up to 10 minutes
```

AWX path: `awx-proxmox-migrate-vm.yml` calls `community.proxmox.proxmox`
with `migrate: true, timeout: 600`, no-ops if `source == target`.

**LXC migration is not supported.** This is a Proxmox limitation that
the project does not work around — the corresponding
`NetBoxProxmoxHelperMigrate.migrate_lxc()` is defined but not wired
into `app.py`.

---

## 15. NetBox Branching Plugin Integration

The optional [NetBox Branching plugin](https://netboxlabs.com/docs/extensions/branching/)
is supported **at setup and discovery time only**. The flow:

1. `netbox.branch` and `netbox.branch_timeout` are present in the master
   config.
2. The setup/discovery script calls
   `NetBoxBranches.activate_branch(name)`.
3. `activate_branch` creates the branch (if missing), polls every second
   for up to `branch_timeout` seconds for `status == ready`, then sets
   `X-NetBox-Branch: <name>` on the pynetbox session.
4. All subsequent NetBox API calls execute inside that branch.
5. The operator merges the branch in NetBox manually after review.

The runtime Flask app deliberately does not engage with branches — it
operates on whatever `main` reflects when the webhook fires.

---

## 16. Documentation Site

- **Theme:** MkDocs Material with a custom NetBox Labs palette
  (`nbl-light`, `nbl-dark`, defined in `docs/stylesheets/extra.css`).
- **Logo / favicon:** `docs/images/netbox-favicon.png`,
  `docs/images/netbox-light-favicon.png`.
- **Analytics:** Google Analytics property `G-Q107GMDTJM`.
- **Markdown extensions:** `pymdownx.tabbed`, `pymdownx.snippets`,
  `pymdownx.superfences` (with Mermaid), `admonition`,
  `pymdownx.details`, `attr_list`, `md_in_html`, `toc` depth 3.
- **Plugins:** `search`.

### Page index

| Page | Subject |
|---|---|
| `index.md` | Project overview, what is/is not, list of event-driven behaviors |
| `usage.md` | Two automation paths, prerequisites, scope |
| `netbox-key-and-permissions.md` | Creating an API user/group/permissions/token |
| `proxmox-api-user-and-key.md`   | `pveum` and UI flow for `api_user@pve` and a non-expiring token |
| `proxmox-vm-templates.md`       | Building cloud-init Ubuntu templates with `virt-customize` and `qm template` |
| `proxmox-lxc-templates.md`      | Pointing at upstream LXC docs |
| `netbox-ipam.md`                | Mandatory IPAM (RIRs, Aggregates, Prefixes) |
| `netbox-customization.md`       | Custom fields and choice sets created by the setup script |
| `proxmox-discover-clusters-and-nodes.md` | Cluster/node discovery |
| `proxmox-discover-vm-and-lxc.md`         | Workload discovery |
| `configure-flask-application.md`         | Flask runtime install and run |
| `configure-awx-aap.md`                   | AWX/Tower/AAP install and run, EE recipe |
| `netbox-event-rules-and-webhooks-flask.md` | Event rule list (Flask flavor) |
| `netbox-event-rules-and-webhooks-awx-aap.md` | Event rule list (AWX flavor) |
| `proxmox-and-node-migration.md`           | Experimental VM migration |

A second `mkdocs.yml` lives inside `playbooks/` — it is an older nav
config kept for compatibility with documentation generation pipelines
that build only the AWX path. The root `mkdocs.yml` is the canonical
one.

---

## 17. Dependencies

### 17.1. Root `requirements.txt`

Used by the docs site **and** as the implicit runtime baseline for
helpers. Notable pins (full list in repo):

| Package | Version |
|---|---|
| `mkdocs` | 1.6.1 |
| `mkdocs-material` | 9.6.22 |
| `pymdown-extensions` | 10.16.1 |
| `proxmoxer` | 2.2.0 |
| `pynetbox` | 7.5.0 |
| `paramiko` | 4.0.0 |
| `Jinja2` | 3.1.6 |
| `PyYAML` | 6.0.3 |
| `requests` | 2.33.0 |
| `cryptography` | 46.0.7 |
| `bcrypt` | 4.3.0 |
| `PyNaCl` | ≥ 1.6.2 |
| `certifi` | 2025.10.5 |
| `watchdog` | 6.0.0 |
| `invoke` | 2.2.0 |

### 17.2. `setup/requirements.txt` delta

Adds:

| Package | Version |
|---|---|
| `awxkit` | 24.6.1 |
| `setuptools` | 80.9.0 |

### 17.3. `netbox-event-driven-automation-flask-app/requirements.txt`

Notable runtime additions over the baseline:

| Package | Version | Role |
|---|---|---|
| `Flask` | 3.1.3 | Web framework |
| `flask-restx` | 1.3.0 | REST API + Swagger UI |
| `gunicorn` | 23.0.0 | WSGI prod server |
| `proxmoxer` | 2.2.0 | Proxmox client |
| `pynetbox` | 7.4.1 | NetBox client (slightly older than root) |
| `Werkzeug` | ≥ 3.1.5 | WSGI utilities |
| `jsonschema` | 4.23.0 | JSON validation |
| `python-daemon` | 3.1.0 | Daemonization (unused by default) |
| `pexpect` | 4.9.0 | Process interaction |
| `aniso8601` | 9.0.1 | ISO 8601 (Flask-RESTX dep) |
| `ansible-runner` | 2.4.0 | Listed but **not** used directly in the Flask path |

---

## 18. Operational Notes

- **No systemd unit.** The Flask app is run with `gunicorn` by the
  operator's own process manager. There is no provided `.service` file.
- **No cron jobs.** Discovery scripts are interactive and one-shot.
- **No background workers.** No queue. No retry. The webhook handler
  must finish each Proxmox operation before returning a response.
- **Reverse proxy.** TLS termination + auth are explicitly listed as
  out-of-scope and "exercises for the reader."
- **Logging.** A single rolling-but-not-rotated file
  (`netbox-proxmox-webhook-listener.log`) in the working directory.
  Rotation is delegated to `logrotate` or equivalent.
- **NetBox token scope.** The NetBox API token must be **write-enabled**
  on Devices, Interfaces, Virtual Machines, and Virtual Disks. Read-only
  tokens will silently fail the discovery + clone-disk write-back paths.
- **Proxmox token scope.** The Proxmox token user must have the
  `Administrator` role and the token must have privilege separation
  **disabled** so it inherits the user's permissions.

---

## 19. Known Issues & Roadmap

Per `README.md`:

**Known issues:**

- Proxmox 9.x untested (project tests on 8.x).
- Not all NIC types/speeds map onto NetBox interface types — unmappable
  speeds default to `other`.
- Only SCSI disk types are supported on the VM path.
- LXC migration is unsupported (Proxmox limitation, not worked around).
- Proxmox tags are not synchronized.

**Roadmap:**

- NetBox Custom Objects support for NetBox > 4.4.
- DNS update via gss-tsig — depends on the `netbox-dns` plugin and
  completes the half-built `awx-update-dns.yml` /
  `bind9/zone-template.j2` path.
- NetBox Discovery / Assurance integration.

---

## 20. Comparison Notes for `netbox-proxbox`

Why this reference lives in the `netbox-proxbox` repo: although both
projects target NetBox↔Proxmox integration, they are architecturally
different and the differences are useful to keep in front of mind.

| Axis | `netbox-proxmox-automation` | `netbox-proxbox` (this repo) |
|---|---|---|
| Distribution | Standalone repo, **no NetBox plugin** | Real NetBox plugin (Django app, models, migrations, UI) |
| Source of truth | NetBox (desired-state authoring) | NetBox stores **observed** state synced from Proxmox; users still author bits in NetBox |
| Direction | NetBox → Proxmox (webhook driven) | Mostly Proxmox → NetBox (sync), plus operational hooks back |
| Trigger | NetBox event rules + webhooks | Sibling FastAPI service (`proxbox-api`) with REST/SSE/WebSocket; RQ background jobs |
| Proxmox client | `proxmoxer` directly in Flask, or `community.proxmox` in Ansible | `proxmox-sdk` (schema-driven, dual mock/real) via `proxbox-api` |
| Storage of credentials | YAML files on disk, no env vars | NetBox-stored encrypted endpoint records (`ProxmoxEndpoint`, etc.); Fernet at rest |
| Concurrency | Synchronous per webhook, no queue | RQ jobs, configurable concurrency, SSE progress streaming |
| UI | None — operator works in NetBox UI directly | Plugin views, rich Django templates, `pxb` CLI |
| Discovery | One-shot scripts (`setup/netbox-discover-*`) | Continuous reconciliation through `proxbox-api` services |
| Migration | First-class NetBox-driven (`proxmox_node` field flip) | Not the focus; Proxmox migrations are observed not authored |
| Branching | Setup-time branch awareness | Not applicable in the same shape |
| Auth | NetBox API token + Proxmox API token (both in YAML) | bcrypt API key on `proxbox-api` + Fernet-encrypted creds |

**Patterns worth borrowing:**

- The drift-detect `createOrUpdate` pattern in `helpers/netbox_objects.py`
  is a clean template for any "ensure-this-NetBox-object-matches-spec"
  routine.
- The credential-type Injectors approach (Section 11.1) is a tidy
  abstraction for namespacing two unrelated credential bags
  (`proxmox_env_info` + `netbox_env_info`) without polluting the global
  variable scope.
- The branching-aware pynetbox session header
  (`X-NetBox-Branch`) is a reusable trick for any NetBox-writing tool.

**Patterns to deliberately reject in `netbox-proxbox`:**

- No-queue synchronous webhook execution does not scale to
  large-cluster operations; `proxbox-api` is right to use RQ.
- File-based YAML config with hardcoded `app_config.yml` is too rigid
  for a multi-tenant plugin; NetBox-stored encrypted endpoints are the
  better model.
- `verify_ssl=False` hardcode in the Flask helper is a bug — never
  silently ignore the operator's TLS choice.
- MB→GB conversion divergence between Flask (÷1000) and Ansible (÷1024)
  is exactly the kind of unit drift `netbox-proxbox` should avoid by
  centralizing conversions in one place.

---

*End of reference.*
