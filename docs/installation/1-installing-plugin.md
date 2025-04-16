# Installing the Plugin using pip

## TL'DR (For Experienced Users)

### Enable plugin in configuration.py (usually on /opt/netbox/netbox/netbox)

```
PLUGINS = ['netbox_proxbox']
```

### Run the commands

```bash
# Activate virtual environment
source /opt/netbox/venv/bin/activate

# Install plugin
pip install netbox-proxbox==0.0.6b2

# Enable plugin in configuration.py (usually on /opt/netbox/netbox/netbox)
PLUGINS = ['netbox_proxbox']

# Run migrations
cd /opt/netbox/netbox/
python3 manage.py migrate netbox_proxbox
python3 manage.py collectstatic --no-input

# Restart service
sudo systemctl restart netbox
```

> **Note:** You'll still need to set up the backend. See [Backend Setup Guide](../installation/backend-setup.md) for details.

---

Follow the steps below to install the Proxbox plugin using pip.

## Step 1: Enter Netbox's virtual environment

First, you need to activate the virtual environment for Netbox. Run the following command:

```
source /opt/netbox/venv/bin/activate
```

## Step 2: Install the plugin package

Install the latest beta version of the Proxbox plugin:

```
pip install netbox-proxbox==0.0.6b2
```

## Step 3: Enable the plugin

Add the plugin to your Netbox configuration. Edit `/opt/netbox/netbox/netbox/configuration.py` and add the following line:

```python
PLUGINS = ['netbox_proxbox']
```

## Step 4: Run database migrations

Run the following commands to apply the necessary database migrations:

```
cd /opt/netbox/netbox/
python3 manage.py migrate netbox_proxbox
python3 manage.py collectstatic --no-input
```

## Step 5: Restart the Netbox service

Finally, restart the Netbox service to load the new plugin:

```
sudo systemctl restart netbox
```

## Next Steps

After completing the plugin installation, you'll need to set up the Proxbox backend. Please refer to the [Backend Setup Guide](../installation/backend-setup.md) for detailed instructions.

For more information about using the plugin, please refer to the [Usage Guide](../usage.md).