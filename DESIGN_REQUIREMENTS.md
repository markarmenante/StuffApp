# Design Requirements

## Distributed macOS and Time-Zone Operation

This app must be developed and run from different macOS machines in different time zones. Treat the local machine, filesystem paths, browser storage, system clock, and system time zone as variable unless explicitly configured.

Requirements:

- Store durable dates and times with UTC plus an explicit IANA time zone, or with the source time zone preserved alongside the normalized value.
- Present user-facing dates and times with clear time-zone labels when timing affects meetings, reminders, travel, deadlines, scans, or financial reporting.
- Do not rely on the host machine's local time zone for business rules. If New York time is the product rule, configure it explicitly as `America/New_York`.
- Avoid hard-coded machine-specific absolute paths. Use documented environment variables or per-machine local config for folders, source scans, credentials, and external tools.
- Keep local development reproducible on a fresh macOS machine by documenting runtime versions, package-manager commands, required services, environment variables, and connector/auth setup.
- Make scheduled jobs, file scans, calendar polling, notifications, and ingestion idempotent so two active Macs do not double-process the same work.
- Prefer database or server-side state as the cross-machine source of truth. Browser `localStorage` and local files may be used only as cache, temporary workspace, or documented fallback.
- When adding or changing features that touch time, reminders, files, notifications, local scans, or external sync, explicitly check the behavior for multiple macOS machines and non-local time zones.
