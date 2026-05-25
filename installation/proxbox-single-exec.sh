#!/usr/bin/env bash
# Entrypoint for docker-compose-single-exec.yml.
#
# Installs netbox-proxbox into the container, registers it in PLUGINS,
# and runs `manage.py proxbox_sync --wait`. Exits with the job's status.
#
# Environment:
#   NETBOX_PROXBOX_PIP_SPEC   PEP 508 spec for `uv pip install`. Default: netbox-proxbox.
#   PROXBOX_SYNC_TIMEOUT      Seconds. Forwarded to --timeout. Default: 7200.
#   PROXBOX_SYNC_USER         Optional. Forwarded to --user when set.

set -euo pipefail

PIP_SPEC="${NETBOX_PROXBOX_PIP_SPEC:-netbox-proxbox}"
TIMEOUT="${PROXBOX_SYNC_TIMEOUT:-7200}"
USER_ARG="${PROXBOX_SYNC_USER:-}"

i=0
until uv pip install --upgrade "$PIP_SPEC"; do
  i=$((i + 1))
  [ "$i" -ge 30 ] && exit 1
  sleep 5
done

mkdir -p /etc/netbox/config
if ! grep -q '"netbox_proxbox"' /etc/netbox/config/plugins.py 2>/dev/null; then
  printf 'PLUGINS = ["netbox_proxbox"]\n' > /etc/netbox/config/plugins.py
fi

cmd=(/opt/netbox/venv/bin/python /opt/netbox/netbox/manage.py proxbox_sync --wait --timeout "$TIMEOUT")
[ -n "$USER_ARG" ] && cmd+=(--user "$USER_ARG")

exec "${cmd[@]}"
