#!/bin/bash
set -euo pipefail

# Stop web server
systemctl stop netbox.service

# Stop RQ worker (required: code changes are only picked up after worker restart)
if systemctl list-unit-files netbox-rq.service &>/dev/null; then
    systemctl stop netbox-rq.service
else
    echo "WARNING: netbox-rq.service not found. If you run rqworker manually, stop it now."
fi

pip3 uninstall netbox-proxbox -y

pip3 install -e .

# Start web server
systemctl start netbox.service

# Start RQ worker
if systemctl list-unit-files netbox-rq.service &>/dev/null; then
    systemctl start netbox-rq.service
else
    echo "WARNING: netbox-rq.service not found. Start the RQ worker manually to pick up code changes."
fi
