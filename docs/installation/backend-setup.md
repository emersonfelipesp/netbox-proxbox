# Proxbox Backend Setup

The Proxbox backend is required for the plugin to function. This guide covers the installation and configuration of the backend service.

## Option 1: Using Docker (Recommended)

The simplest way to install the backend is using Docker:

```
docker pull emersonfelipesp/proxbox-api:latest
docker run -d -p 8800:8800 --name proxbox-api emersonfelipesp/proxbox-api:latest
```

## Option 2: Manual Installation

If Docker is not an option, you can install the backend manually. For detailed instructions, please refer to the [Proxbox API documentation](https://github.com/netdevopsbr/netbox-proxbox/blob/develop/proxbox_api/README.md).

## SSL Configuration

If you're using SSL certificates, you may need to set the appropriate permissions for the Proxbox backend to access them:

```
sudo chmod +rx -R /etc/ssl/private/
sudo chmod +rx -R /etc/ssl/certs/
```

## Systemd Service Setup

To run the backend as a systemd service:

1. Copy the service file to the systemd directory:
```
sudo cp -v /opt/netbox/netbox/netbox-proxbox/contrib/*.service /etc/systemd/system/
```

2. Reload systemd and enable the service:
```
sudo systemctl daemon-reload
sudo systemctl enable --now proxbox
```

3. Start and verify the service:
```
sudo systemctl start proxbox
sudo systemctl status proxbox
```

## Development Setup

For development purposes, you can run the backend directly:

```
/opt/netbox/venv/bin/uvicorn netbox-proxbox.proxbox_api.main:app --host 0.0.0.0 --port 8800 --app-dir /opt/netbox/netbox --ssl-keyfile=/etc/ssl/private/netbox.key --ssl-certfile=/etc/ssl/certs/netbox.crt --reload
```

### Creating Self-Signed Certificates (Development Only)

If you need to test the plugin without reusing Netbox certificates, you can create your own self-signed certificates:

```
sudo openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
-keyout /etc/ssl/proxbox.key \
-out /etc/ssl/proxbox.crt
```

> **Note:** The certificate files are created in `/etc/ssl` by default. You'll need to update the systemd service file to use these certificates. Consider using an HTTP proxy like NGINX to serve the FastAPI application.

## Next Steps

After setting up the backend, you can proceed to configure the plugin through the Netbox web interface. The plugin configuration is managed entirely through the Netbox GUI or its API. 