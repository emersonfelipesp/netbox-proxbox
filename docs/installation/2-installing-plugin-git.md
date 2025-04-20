# Installing the Plugin using Git

## TL'DR (For Experienced Users)

### Enable plugin in configuration.py (usually on /opt/netbox/netbox/netbox)

```
PLUGINS = ['netbox_proxbox']
```

### Run the commands

```bash
# Clone the repository
cd /opt/netbox/netbox/netbox

git clone https://github.com/your-repo/netbox-proxbox.git

# Enter the plugin directory
cd netbox-proxbox

# Activate virtual environment
source /opt/netbox/venv/bin/activate

# Install plugin
pip install .

# Run migrations
cd /opt/netbox/netbox/
python3 manage.py migrate netbox_proxbox
python3 manage.py collectstatic --no-input

# Restart service
sudo systemctl restart netbox
```

> **Note:** You'll still need to set up the backend. See [Backend Setup Guide](../installation/backend-setup.md) for details.

---

Follow the steps below to install the Proxbox plugin using Git.

## Step 1: Clone the Repository

Navigate to the Netbox directory and clone the Proxbox plugin repository:

```
cd /opt/netbox/netbox/netbox
git clone https://github.com/your-repo/netbox-proxbox.git
```

## Step 2: Enter the Plugin Directory

Change into the plugin directory:

```
cd netbox-proxbox
```

## Step 3: Enter Netbox's Virtual Environment

Activate the virtual environment for Netbox:

```
source /opt/netbox/venv/bin/activate
```

## Step 4: Install the Plugin

Install the plugin using the cloned repository:

```
pip install .
```

## Step 5: Enable the Plugin

Add the plugin to your Netbox configuration. Edit `/opt/netbox/netbox/netbox/configuration.py` and add the following line:

```python
PLUGINS = ['netbox_proxbox']
```

## Step 6: Run Database Migrations

Run the following commands to apply the necessary database migrations:

```
cd /opt/netbox/netbox/
python3 manage.py migrate netbox_proxbox
python3 manage.py collectstatic --no-input
```

## Step 7: Restart the Netbox Service

Finally, restart the Netbox service to load the new plugin:

```
sudo systemctl restart netbox
```

## Next Steps

After completing the plugin installation, you'll need to set up the Proxbox backend. Please refer to the [Backend Setup Guide](../installation/backend-setup.md) for detailed instructions.

For more information about using the plugin, please refer to the [Usage Guide](../usage.md).
