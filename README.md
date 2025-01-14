> Although **Proxbox is under constant development**, I do it with **best effort** and **spare time**. I have no financial gain with this and hope you guys understand, as I know it is pretty useful to some people. If you want to **speed up its development**, solve the problem or create new features with your own code and create a **[Pull Request](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/proposing-changes-to-your-work-with-pull-requests/about-pull-requests)** so that I can **review** it. **I also would like to appreciate the people who already contributed with code or/and bug reports.** Without this help, surely Proxbox would be much less useful as it is already today to several environments!

<div align="center">
	<a href="http://proxbox.netbox.dev.br/">
		<img width="532" src="https://github.com/N-Multifibra/proxbox/blob/main/etc/img/proxbox-full-logo.png" alt="Proxbox logo">
	</a>
	<br>

<div>

### [New Documentation available!](https://proxbox.netbox.dev.br/introduction/)
</div>
<br>
</div>




## Netbox Plugin which integrates [Proxmox](https://www.proxmox.com/) and [Netbox](https://netbox.readthedocs.io/)!

> **NOTE:** Although the Proxbox plugin is in development, it only use **GET requests** and there is **no risk to harm your Proxmox environment** by changing things incorrectly.

<br>

Proxbox is currently able to get the following information from Proxmox:

- **Cluster name**
- **Nodes:**
  - Status (online / offline)
  - Name
- **Virtual Machines and Containers:**
  - Status (online / offline)
  - Name
  - ID
  - CPU
  - Disk
  - Memory
  - Node (Server)

---

<div align="center">

### Proxbox current environment and future plan.

![proxbox services image](/etc/img/proxbox-services.png)

### Versions


The following table shows the Netbox and Proxmox versions compatible (tested) with Proxbox plugin.

| netbox version | proxmox version | proxbox version |
| ------------- |-------------|-------------|
| >= v3.4.0 | >= v6.2.0  | =v0.0.5 |
| >= v3.2.0 | >= v6.2.0 | =v0.0.4 |
| >= v3.0.0 < v3.2 | >= v6.2.0 | =v0.0.3 |


</div>

---

### Summary
[1. Installation](#1-installation)
- [1.1. Install package](#11-install-package)
  - [1.1.1. Using pip (production use)](#111-using-pip-production-use---not-working-yet) - NOT WORKING
  - [1.1.2. Using git (development use)](#112-using-git-development-use) - CURRENTLY WORKING
- [1.2. Enable the Plugin](#12-enable-the-plugin)
- [1.3. Configure Plugin](#13-configure-plugin)
  - [1.3.1. Change Netbox 'configuration.py' to add PLUGIN parameters](#131-change-netbox-configurationpy-to-add-plugin-parameters)
  - [1.3.2. Change Netbox 'settings.py' to include Proxbox Template directory](#132-change-netbox-settingspy-to-include-proxbox-template-directory)
- [1.4. Run Database Migrations](#14-run-database-migrations)
- [1.5. systemd Setup](#15-systemd-setup-proxbox-backend)
- [1.6 Restart WSGI Service](#15-restart-wsgi-service)

[2. Configuration Parameters](#2-configuration-parameters)

[3. Usage](#3-usage)

[4. Enable Logs](#4-enable-logs)

[5. Contributing](#5-contributing)

[6. Roadmap](#6-roadmap)

[7. Get Help from Community!](#7-get-help-from-community)

---

## 1. Installation

The instructions below detail the process for installing and enabling Proxbox plugin.
The plugin is available as a Python package in pypi and can be installed with pip.

### 1.1. Install package

#### 1.1.1. Using pip (production use)

> NOT WORKING

Enter Netbox's virtual environment.
```
source /opt/netbox/venv/bin/activate
```

Install the plugin package.
```
(venv) $ pip install netbox-proxbox
```

#### 1.1.2. Using git (development use)

> CURRENTLY WORKING

**OBS:** This method is recommend for testing and development purposes and is not for production use.

Move to netbox main folder
```
cd /opt/netbox/netbox
```

Clone netbox-proxbox repository
```
git clone https://github.com/netdevopsbr/netbox-proxbox.git
```

Install required packages

```
cd /opt/netbox
source venv/bin/activate
cd netbox/netbox-proxbox

pip3 install -r requirements.txt
```

Run netbox-proxbox on develop mode

```
python3 setup.py develop
```

---

### 1.2. Enable the Plugin

Enable the plugin in **/opt/netbox/netbox/netbox/configuration.py**:
```python
PLUGINS = ['netbox_proxbox']
```

---

### 1.3. Configure Plugin

#### 1.3.1. Change Netbox '**[configuration.py](https://github.com/netbox-community/netbox/blob/develop/netbox/netbox/configuration.example.py)**' to add PLUGIN parameters
The plugin's configuration is also located in **/opt/netbox/netbox/netbox/configuration.py**:

Replace the values with your own following the [Configuration Parameters](#2-configuration-parameters) section.

**OBS:** You do not need to configure all the parameters, only the one's different from the default values. It means that if you have some value equal to the one below, you can skip its configuration. For netbox you should ensure the domain/port either targets gunicorn or a true http port that is not redirected to https.

```python
PLUGINS_CONFIG = {
    'netbox_proxbox': {
        'proxmox': [
            {
                'domain': 'proxbox.example.com',    # May also be IP address
                'http_port': 8006,
                'user': 'root@pam',   # always required
                'password': 'Strong@P4ssword', # only required, if you don't want to use token based authentication
                'token': {
                    'name': 'tokenID',	# Only type the token name and not the 'user@pam:tokenID' format
                    'value': '039az154-23b2-4be0-8d20-b66abc8c4686'
                },
                'ssl': False
            },
            # The following json is optional and applies only for multi-cluster use
            {
                'domain': 'proxbox2.example.com',    # May also be IP address
                'http_port': 8006,
                'user': 'root@pam',   # always required
                'password': 'Strong@P4ssword', # only required, if you don't want to use token based authentication
                'token': {
                    'name': 'tokenID',	# Only type the token name and not the 'user@pam:tokenID' format
                    'value': '039az154-23b2-4be0-8d20-b66abc8c4686'
                },
                'ssl': False
            }
        ],
        'netbox': {
            'domain': 'localhost',     # Ensure localhost is added to ALLOWED_HOSTS
            'http_port': 8001,     # Gunicorn port.
            'token': '0dd7cddfaee3b38bbffbd2937d44c4a03f9c9d38',
            'settings': {
                'virtualmachine_role_id' : 0,
                'node_role_id' : 0,
                'site_id': 0
            }
        },
        'fastapi': {
            # Uvicorn Host is (most of the time) the same as Netbox (as both servers run on the same machine)
            'uvicorn_host': 'localhost',
            'uvicorn_port': 8800,    # Default Proxbox FastAPI port
            # Although it seems weird, the sudo-user is necessary so that Proxbox automatically starts Proxbox Backend.
            # It makes it more "plug-in", without the need to user input manual commands.
            'sudo': {
                'user': "sudo_enabled_user",
                'password': 'Strong@P4ssword',
            }
        }
    }
}
```


#### 1.3.2. Change Netbox '**[settings.py](https://github.com/netbox-community/netbox/blob/develop/netbox/netbox/settings.py)**' to include Proxbox Template directory

> Probably on the next release of Netbox, it will not be necessary to make the configuration below! As the [Pull Request #8733](https://github.com/netbox-community/netbox/pull/8734) got merged to develop branch

**It is no longer necessary to modify the templates section in `settings.py` and you may revert any changes.**

---

### 1.4. Run Database Migrations

```
(venv) $ cd /opt/netbox/netbox/
(venv) $ python3 manage.py migrate
(venv) $ python3 manage.py collectstatic --no-input
```

---

### 1.5. systemd Setup (Proxbox Backend)

**OBS:** It is possible to change Proxbox Backend Port (`8800`), you need to edit `proxbox.service` file and `configuration.py`

Enables **read/exec permission** for **Uvicorn** use **Netbox certificates**. This is a generic way of doing it and probably **not** the **safe** option.
```
sudo chmod +rx -R /etc/ssl/private/
sudo chmod +rx -R /etc/ssl/certs/
```

Copies `proxbox.service` from repository to **systemd folder** and enables it.
```
sudo cp -v /opt/netbox/netbox/netbox-proxbox/contrib/*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now proxbox

sudo systemctl start proxbox
sudo systemctl status proxbox
```

The commands above creates the service file, enables it to run at boot time and starts it immediately.

#### Optional way for developing use:

The certificates used are from Netbox, considering both applications are on the same machine.
If you plan to put Proxbox Backend in another host, I recommend creating another pair of certificates and enabling NGINX in front ot it.

```
/opt/netbox/venv/bin/uvicorn netbox-proxbox.netbox_proxbox.main:app --host 0.0.0.0 --port 8800 --app-dir /opt/netbox/netbox --ssl-keyfile=/etc/ssl/private/netbox.key --ssl-certfile=/etc/ssl/certs/netbox.crt --reload
```

#### (Developer Use Only) Creating self-signed certificates so Proxbox Backend (FastAPI) runs both HTTP and WS (Websocket) via TLS.

If you need to test the plugin without reusing Netbox certificates, you can create your own self-signed certificates and change systemd file.

```
sudo openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
-keyout /etc/ssl/proxbox.key \
-out /etc/ssl/proxbox.crt
```

> The certificate files created are by default located at `/etc/ssl`.
> Proxbox SystemD file needs to be changed to link to this path to find `proxbox.key` and `proxbox.crt` files.
> Consider use some HTTP Proxy like NGINX to serve FastAPI.

---

### 1.6. Restart WSGI Service

Restart the WSGI service to load the new plugin:
```
# sudo systemctl restart netbox
```

---

## 2. Configuration Parameters

The following options are available:

* `proxmox`: (List) Proxmox related configuration to use proxmoxer.
* `proxmox.domain`: (String) Domain or IP address of Proxmox.
* `proxmox.http_port`: (Integer) Proxmox HTTP port (default: 8006).
* `proxmox.user`: (String) Proxmox Username.
* `proxmox.password`: (String) Proxmox Password.
* `proxmox.token`: (Dict) Contains Proxmox TokenID (name) and Token Value (value).
* `proxmox.token.name`: (String) Proxmox TokenID.
* `proxmox.token.value`: (String) Proxmox Token Value.
* `proxmox.ssl`: (Bool) Defines the use of SSL (default: False).

* `netbox`: (Dict) Netbox related configuration to use pynetbox.
* `netbox.domain`: (String) Domain or IP address of Netbox. Ensure name or ip is added to `ALLOWED_HOSTS`
* `netbox.http_port`: (Integer) Netbox HTTP PORT (default: 8001).  If you are not targeting gunicorn directly make sure the HTTP port is not redirected to HTTPS by your HTTP server.
* `netbox.token`: (String) Netbox Token Value.
* `netbox.settings`: (Dict) Default items of Netbox to be used by Proxbox.
  - If not configured, Proxbox will automatically create a basic configuration to make it work.
  - The ID of each item can be easily found on the URL of the item you want to use.
* `netbox.settings.virtualmachine_role_id`: (Integer) Role ID to be used by Proxbox when creating Virtual Machines
* `netbox.settings.node_role_id`: (Integer) Role ID to be used by Proxbox when creating Nodes (Devices)
* `netbox.settings.site_id` (Integer) Site ID to be used by Proxbox when creating Nodes (Devices)

## 3. Usage

If everything is working correctly, you should see in Netbox's navigation the **Proxmox VM/CT** button in **Plugins** dropdown list.

On **Proxmox VM/CT** page, click button ![full update button](etc/img/proxbox_full_update_button.png?raw=true "preview")

It will redirect you to a new page and you just have to wait until the plugin runs through all Proxmox Cluster and create the VMs and CTs in Netbox.

**OBS:** Due the time it takes to full update the information, your web brouse might show a timeout page (like HTTP Code 504) even though it actually worked.

---

## 4. Enable Logs

So that Proxbox plugin logs what is happening to the terminal, copy the following code and paste to `configuration.py` Netbox configuration file:

```python
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
}
```

You can customize this using the following link: [Django Docs - Logging](https://docs.djangoproject.com/en/4.1/topics/logging/).
Although the above standard configuration should do the trick to things work.

---

## 5. Contributing
Developing tools for this project based on [ntc-netbox-plugin-onboarding](https://github.com/networktocode/ntc-netbox-plugin-onboarding) repo.

Issues and pull requests are welcomed.

---

## 6. Roadmap
- Start using custom models to optimize the use of the Plugin and stop using 'Custom Fields'
- Automatically remove Nodes on Netbox when removed on Promox (as it already happens with Virtual Machines and Containers)
- Add individual update of VM/CT's and Nodes (currently is only possible to update all at once)
- Add periodic update of the whole environment so that the user does not need to manually click the update button.
- Create virtual machines and containers directly on Netbox, having no need to access Proxmox.
- Add 'Console' button to enable console access to virtual machines

---

## 7. Get Help from Community!
If you are struggling to get Proxbox working, feel free to contact someone from community (including me) to help you.
Below some of the communities available:
- **[Official - Slack Community (english)](https://netdev.chat/)**
- **[Community Discord Channel - 🇧🇷 (pt-br)](https://discord.gg/X6FudvXW)**
- **[Community Telegram Chat - 🇧🇷 (pt-br)](https://t.me/netboxbr)**

---

## Installing and using Proxbox Plugin (pt-br video)
[![Watch the video](https://img.youtube.com/vi/Op-4MQjDf6A/maxresdefault.jpg)](https://www.youtube.com/watch?v=Op-4MQjDf6A)

## Stars History 📈

[![Star History Chart](https://api.star-history.com/svg?repos=netdevopsbr/netbox-proxbox&type=Timeline)](https://star-history.com/#netdevopsbr/netbox-proxbox&Timeline)
