# Proxmox OCI Testing Appliance

The `emersonfelipesp/netbox-proxbox:oci` image is a testing appliance for the
Proxmox VE OCI-to-LXC workflow. It combines NetBox, the latest stable
`netbox-proxbox` release from PyPI, `proxbox-api`, PostgreSQL, Redis, and a NetBox
RQ worker in one image. Do not use this all-in-one layout as a production NetBox
deployment.

The image exposes NetBox on TCP port `8080`. proxbox-api listens separately on
TCP port `8800`, but binds to `127.0.0.1` by default because the plugin consumes
it inside the same LXC. The plugin is enabled automatically and points to the
embedded backend at `http://127.0.0.1:8800`.

## Pull the image into Proxmox VE

In the storage content view, select **Pull from OCI Registry** and use:

```text
docker.io/emersonfelipesp/netbox-proxbox:oci
```

The moving `oci` tag is convenient for testing the newest published appliance.
For reproducible testing of the NetBox Proxbox 0.0.27 release, use the validated
immutable reference:

```text
docker.io/emersonfelipesp/netbox-proxbox:netbox-4.7.0-proxbox-0.0.27-api-0.0.23.post2-e5e8500524f71ffd2ec3a2577ae6380defd40313
```

That reference and the `oci` tag resolve to OCI index digest
`sha256:b381a746264ecb0cb4ff8e94e55f8a776c887b08bdeb63fef6e3187efb5141da`.
The index publishes `linux/amd64` and `linux/arm64` images. The immutable image
was successfully validated with the Proxmox VE **Pull from OCI Registry**
workflow and stored as an LXC template artifact. This validation proves the
registry-to-Proxmox transfer path; it does not change the appliance's
testing-only support boundary.

Create an LXC from the downloaded artifact. The image provides `/sbin/init`, so
the default OCI entrypoint selected by Proxmox starts the complete appliance.
Map or allow TCP `8080` for NetBox. If direct backend access is required, set
the OCI environment variable `PROXBOX_BIND_HOST=<LXC-IP>` and restrict TCP
`8800` with the LXC or network firewall. Do not use a wildcard bind address.
The backend administration endpoints
must not be exposed to an untrusted network.

Allocate at least 4 GiB RAM and two CPU cores for the initial migration. First
boot can take several minutes because NetBox and plugin migrations run before the
web service starts.

## Persistent data

Keep these image volumes on persistent LXC storage:

| Path | Contents |
|---|---|
| `/var/lib/postgresql` | NetBox PostgreSQL database |
| `/var/lib/redis` | Redis state |
| `/var/lib/proxbox-api` | proxbox-api SQLite database, generated route cache, and logs |
| `/var/lib/proxbox-stack` | generated NetBox, database, and encryption secrets |

Back up all four paths together. Restoring the databases without
`/var/lib/proxbox-stack` loses the keys needed to read the stored configuration.

## Create the first administrator

Open the LXC console and run the normal NetBox command directly:

```bash
/opt/netbox/netbox/manage.py createsuperuser
```

No Docker command or environment setup is required. The appliance configuration
reads its generated database password and NetBox secret key from persistent
files.

For non-interactive test automation:

```bash
DJANGO_SUPERUSER_USERNAME=admin \
DJANGO_SUPERUSER_EMAIL=admin@example.invalid \
DJANGO_SUPERUSER_PASSWORD='replace-this-test-password' \
/opt/netbox/netbox/manage.py createsuperuser --no-input
```

## Configure Proxmox access

After signing in, open **Plugins > Proxbox** and create the Proxmox endpoint for
the test cluster. The embedded backend is already configured; supply only the
target Proxmox endpoint and its test credentials. Use a scoped API token instead
of a root password.

The backend-to-NetBox integration still needs a NetBox API token because NetBox
cannot safely manufacture a durable administrator credential before the first
administrator exists. Create that token in NetBox, then add the NetBox endpoint
through the Proxbox UI with `127.0.0.1`, port `8080`, and HTTP.

## Runtime checks

Run these commands in the LXC:

```bash
/usr/local/sbin/proxbox-stack-healthcheck
/opt/netbox/netbox/manage.py check
/opt/netbox/netbox/manage.py showmigrations netbox_proxbox
supervisorctl status
```

All plugin migrations should show `[X]`, and all supervised programs should be
`RUNNING`.

Redis may warn when the LXC host has `vm.overcommit_memory=0`. Configure
`vm.overcommit_memory=1` on the Proxmox host when background Redis persistence
is required; an unprivileged LXC cannot safely change that host-level setting.

## Image tags and updates

`oci` tracks the latest successfully tested stable PyPI releases. For a
GitHub Release, the image installs exactly the plugin version named by the
release tag. The build waits for that version to appear on PyPI and fails if it
does not, and it verifies the installed plugin version before publishing. For
manual and pull-request runs, the image uses the newest stable PyPI release.
After the versioned image is published, the `oci` tag moves only when the released plugin version is the newest stable
published stable release (yanked or Python-incompatible newer releases still
count), so rebuilding an older release never downgrades it. Prerelease tags are
not published as images.
Versioned tags encode all application versions plus the source commit:

```text
netbox-4.7.0-proxbox-<plugin-version>-api-<backend-version>-<source-sha>
```

Use the registry-reported OCI digest when exact byte-for-byte reproduction is
required. Publication occurs only from an approved GitHub Release; manual and
pull-request validation does not publish images. Pulling a new image does not replace or
migrate an existing LXC automatically; create a new test LXC and attach a
copied data set when testing upgrades.
