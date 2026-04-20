# UI Screenshots

Screenshots are captured automatically from a live NetBox instance with the plugin
installed against a Proxmox mock backend. No real infrastructure data is shown.

The capture pipeline spins up a full Docker stack (NetBox + proxbox-api + proxmox-mock),
seeds it with mock data via the sync pipeline, and takes Playwright browser screenshots.
Screenshots are refreshed on every new release and can be triggered manually.

---

## Plugin Home

The plugin home page shows endpoint status cards, quick-sync actions, and navigation
to all Proxmox resources managed by the plugin.

![Plugin Home](../assets/screenshots/home.png)

---

## Dashboard

The operational dashboard displays cluster and node summaries sourced live from
the proxbox-api backend.

![Dashboard](../assets/screenshots/dashboard.png)

---

## Endpoints

=== "Proxmox Endpoints"
    List of configured Proxmox API endpoints the plugin connects to.

    ![Proxmox Endpoints](../assets/screenshots/proxmox-endpoints.png)

=== "FastAPI (Proxbox) Endpoints"
    The companion proxbox-api backend endpoint configuration.

    ![FastAPI Endpoints](../assets/screenshots/fastapi-endpoints.png)

=== "NetBox Endpoints"
    The NetBox self-referential endpoint used by proxbox-api to write back.

    ![NetBox Endpoints](../assets/screenshots/netbox-endpoints.png)

---

## Infrastructure

=== "Clusters"
    Proxmox clusters discovered and synchronized into NetBox.

    ![Clusters](../assets/screenshots/clusters.png)

=== "Nodes"
    Proxmox nodes (devices) associated with each cluster.

    ![Nodes](../assets/screenshots/nodes.png)

=== "Storage"
    Proxmox storage pools tracked per cluster.

    ![Storage](../assets/screenshots/storage.png)

---

## Virtual Machines & Containers

=== "Virtual Machines"
    All Proxmox VMs synchronized into NetBox virtualization.

    ![Virtual Machines](../assets/screenshots/virtual-machines.png)

=== "LXC Containers"
    Linux containers managed by Proxmox and tracked in NetBox.

    ![LXC Containers](../assets/screenshots/lxc-containers.png)

---

## Backup & Recovery

=== "Backups"
    VM backup jobs discovered from Proxmox storage.

    ![Backups](../assets/screenshots/backups.png)

=== "Snapshots"
    VM and container snapshots tracked per virtual machine.

    ![Snapshots](../assets/screenshots/snapshots.png)
