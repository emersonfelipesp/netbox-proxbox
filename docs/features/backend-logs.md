# Backend Logs

Proxbox provides a Backend Logs page for viewing real-time log output from the proxbox-api backend. This feature enables operators to monitor backend activity, debug sync issues, and track operation progress.

## Overview

The proxbox-api backend generates detailed logs during sync operations, API requests, and internal processes. The Backend Logs page provides a unified interface to browse, filter, and search these logs without directly accessing the backend server.

## Accessing Backend Logs

Navigate to **Proxbox > Backend Logs** to access the logs page. The page requires:

- A configured FastAPIEndpoint in NetBox
- The user must have view permission on the FastAPIEndpoint model

## Features

### Log Display

- **Timestamp**: When the log entry was generated
- **Level**: Log severity (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- **Module**: Which backend module generated the log
- **Message**: The log message content
- **Operation**: Associated operation ID for correlated requests

### Filtering

- **Level Filter**: Filter logs by severity level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- **Operation ID Filter**: Filter logs by operation ID to track specific sync operations
- **Clear Filters**: Reset all filters to show all logs

### Auto-Refresh

- **Auto-refresh enabled by default**: Logs automatically reload every few seconds
- **Toggle off**: Disable auto-refresh to pause updates
- **Manual Refresh**: Click the refresh button to manually reload logs

### Pagination

- **Log Count**: Shows current number of displayed logs
- **Load More**: Button to load additional log entries when scrolling
- **Total Count**: Shows total available logs (when filtered)

## Use Cases

### Monitoring Sync Operations

1. Start a sync (manual or scheduled)
2. Navigate to Backend Logs
3. Filter by operation ID from the sync job
4. Watch real-time progress of the sync

### Debugging Issues

1. When a sync fails or behaves unexpectedly
2. Check the logs for ERROR or CRITICAL level entries
3. Use operation ID to correlate with specific sync jobs
4. Identify the root cause from module and message

### Tracking Backend Health

- Monitor INFO level logs for routine operations
- Watch for WARNING entries that may indicate potential issues
- ERROR and CRITICAL entries require immediate attention

## API Integration

The Backend Logs page fetches logs from the proxbox-api backend via:

```
GET /logs
GET /logs?level=<level>
GET /logs?operation_id=<operation_id>
GET /logs?limit=<limit>&offset=<offset>
```

The plugin proxies these requests through the configured FastAPIEndpoint.

## Requirements

- A working proxbox-api backend (version with logs endpoint)
- A configured FastAPIEndpoint in NetBox
- Network connectivity from NetBox to the backend
- Proper authentication if the backend requires it

## Troubleshooting

### No Logs Displayed

- Verify the FastAPIEndpoint is configured and reachable
- Check network connectivity between NetBox and the backend
- Ensure the backend service is running

### Logs Not Updating

- Enable auto-refresh or click refresh button
- Check if the backend service is still running
- Verify no browser-side network issues

### Filtered Results Empty

- Clear filters to see all available logs
- Verify the operation ID or level filter is correct
- Check if logs exist for the selected criteria