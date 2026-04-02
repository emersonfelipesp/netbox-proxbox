# Version 0.0.9

`0.0.9` expanded storage coverage, live job UX, and plugin settings while continuing the NetBox `4.5.x` release line.

## Highlights

- Added richer `ProxmoxStorage` relationships for virtual disks, backups, and snapshots.
- Added VM task history synchronization and plugin UI pages for storage, snapshots, and task history.
- Added per-VM sync actions and snapshot participation in full-update sync stages.
- Added endpoint connectivity details, port validation, and secret-handling improvements.
- Added plugin settings for guest-agent interface naming and Proxmox fetch concurrency.
- Improved live SSE job progress, stage progress bars, and log rendering in the UI.

## Notes

- `0.0.9` is followed by several post releases that focus on migration and packaging fixes.
- If you are upgrading from older `0.0.7` or early `0.0.8` installs, use the latest `0.0.9.post4` line instead of stopping at base `0.0.9`.
