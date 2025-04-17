# Installing and Starting Proxbox-API

This guide will walk you through the steps to install and start the Proxbox-API using pip.

## Prerequisites

- Python 3.10 or later installed on your system.
- pip, the Python package installer, should be installed.
- Virtual environment (optional but recommended).

## TL;DR

Here is a quick summary of the commands to install and start the Proxbox-API (plugin backend):

```bash
# Create a directory for Proxbox-API
mkdir /opt/proxbox-api
cd /opt/proxbox-api

# Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate

# Install Proxbox-API
pip install proxbox-api==0.0.2.post3

# Get the service file from GitHub repository
wget https://raw.githubusercontent.com/netdevopsbr/netbox-proxbox/refs/heads/develop/contrib/proxbox.service /opt/proxbox-api/

# Copy the service file to systemd directory
sudo cp -v /opt/proxbox-api/proxbox.service /etc/systemd/system/

# Reload systemd and enable the service
sudo systemctl daemon-reload
sudo systemctl enable --now proxbox

# Check the status of the service
systemctl status proxbox

# If needed, start Proxbox-API manually
/opt/proxbox-api/venv/bin/uvicorn proxbox_api.main:app --host 0.0.0.0 --port 8800
```

## Installation Steps

### Create a Virtual Environment:
   
It is recommended to use a virtual environment to manage dependencies. You can create one using the following command:

```bash
mkdir /opt/proxbox-api
cd /opt/proxbox-api
python3 -m venv venv
```
   
Activate the virtual environment:
   
```bash
source venv/bin/activate
```

### Install Proxbox-API:

Use pip to install the Proxbox-API package:

```bash
pip install proxbox-api==0.0.2.post3
```

## Starting Proxbox-API

### systemd Setup

Get the service file from GitHub repository:

```
wget https://raw.githubusercontent.com/netdevopsbr/netbox-proxbox/refs/heads/develop/contrib/proxbox.service /opt/proxbox-api/
```
Then copy `contrib/proxbox.service` to the `/etc/systemd/system/` directory.

```
sudo cp -v /opt/proxbox-api/proxbox.service /etc/systemd/system/
```

Once the configuration file has been saved, reload the service:

```
sudo systemctl daemon-reload
```

Then, start `proxbox` service and enable it to initiate at boot time:

```
sudo systemctl enable --now proxbox
```

You can use the command `systemctl status proxbox` to verify is FastAPI app is running:

```
systemctl status proxbox
```

This will start the Proxbox-API server, and it will be ready to accept requests.

You should now be able to access `http://<YOUR-IP>:8800/docs`, like `http://127.0.0.1:8800/docs` (if localhost).

If any errors with the service, try starting Proxbox-API server manually to check for more information or logs:

```bash
/opt/proxbox-api/venv/bin/uvicorn proxbox_api.main:app --host 0.0.0.0 --port 8800
```

## Troubleshooting

- If you encounter any issues during installation or startup, ensure that all dependencies are correctly installed and that your Python environment is properly configured.
- Check the Proxbox-API logs for any error messages that might provide more insight into the problem.
