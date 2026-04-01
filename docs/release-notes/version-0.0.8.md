# Version 0.0.8

`0.0.8` was the major release that moved Proxbox onto the current NetBox Jobs and streaming sync model.

## Highlights

- Switched sync execution from the old custom process model to NetBox Jobs.
- Aligned job execution with the default NetBox RQ queue so a standard `manage.py rqworker` can process Proxbox jobs.
- Added scheduled and recurring sync through NetBox's built-in job system.
- Added VM snapshot synchronization and virtual disk sync support.
- Hardened SSE-based sync execution and job timeout handling.
- Updated the plugin for NetBox `4.5` compatibility and tightened custom-view permission handling.

## Upgrade Notes

- Keep a standard NetBox RQ worker running after upgrade.
- Review job behavior and queue assumptions if you previously relied on `netbox_proxbox.sync`.
