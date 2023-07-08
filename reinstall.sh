#!/bin/bash

systemctl stop netbox.service

pip3 uninstall netbox-proxbox -y

python3 setup.py develop

systemctl start netbox.service
