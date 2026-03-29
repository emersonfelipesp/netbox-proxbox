# Background Jobs

Proxbox uses NetBox's built-in RQ-based background job system for asynchronous and scheduled operations.

## Scheduled Sync

The primary background job feature is scheduled recurring sync. See [Scheduled Sync](./scheduled-sync.md) for full documentation covering:

- Starting the RQ worker
- Scheduling a sync from the UI
- Viewing job status, logs, and errors
- How recurring intervals work
- Cancelling jobs

## NetBox Job Infrastructure

All Proxbox background jobs are stored in NetBox's `core.models.Job` table and are visible under **Operations > Background Jobs**. No separate job database or external service is required beyond the Redis instance already needed by NetBox.
