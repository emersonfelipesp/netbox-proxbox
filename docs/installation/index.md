# Installation

## NetBox Plugin Installation Model

Proxbox is installed as a standard NetBox plugin. The NetBox-side steps are:

1. Install the Python package into the NetBox environment.
2. Add `netbox_proxbox` to `PLUGINS`.
3. Run plugin migrations.
4. Run `collectstatic`.
5. Restart NetBox and the NetBox RQ worker.

For the general NetBox plugin process, see the official
[NetBox plugin installation guide](https://netboxlabs.com/docs/netbox/plugins/).
Use the Proxbox-specific pages below for exact package names, Docker file
locations, migrations, and backend setup.

Choose the path that matches your NetBox deployment:

- Host or VM NetBox with a Python virtualenv: prefer [Installing the Plugin Using Git](./2-installing-plugin-git.md) for the current repository state.
- Docker-based NetBox (`netbox-community/netbox-docker`): use [Installing the Plugin in Docker-Based NetBox Deployments](./3-installing-plugin-docker.md).

Available guides:

- [Pre-Installation](./pre-installation.md)
- [Installing the Plugin Using PyPI](./1-installing-plugin.md)
- [Installing the Plugin Using Git](./2-installing-plugin-git.md)
- [Installing the Plugin in Docker-Based NetBox Deployments](./3-installing-plugin-docker.md)
- [Proxbox Backend Setup](./backend-setup.md)
- [Upgrading Proxbox](./upgrading.md)
