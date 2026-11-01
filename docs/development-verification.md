# Development verification

GitHub Actions runs automatically on pushes to `main`, pull requests and manual
dispatch. It uses fresh dependencies and synthetic local data; no production
database, browser profile, provider login or app secrets enter the test jobs.

Run `npm --prefix browser-tests ci`, `npm --prefix browser-tests run browsers:install`,
then `npm --prefix browser-tests run test:e2e` locally. Browser dependencies are
isolated below `browser-tests/` so Railway continues to detect the Python app.
The tests start their own loopback servers and never target production. StuffApp
also needs `python scripts/install-test-dependencies.py` in a Python virtualenv.
Failure traces, screenshots and HTML reports are retained for seven days in the
workflow's artifacts; they contain only synthetic test data. Generated output is
ignored by Git. The fixtures never add an authentication bypass to app code.

The final main-push job polls the existing production health/version endpoints
and requires the exact tested commit SHA. A healthy older deployment cannot pass.
It is read-only, does not deploy twice, and never resubmits writes. Existing Vercel
and Railway Git auto-deploys remain in charge; the workflow reports verification
after the push and is not a deployment gate or a new manual approval step.

## Sentry

The SDK captures server and client exceptions. Configure a separate Sentry project
for each app: Next.js uses `NEXT_PUBLIC_SENTRY_DSN`; Flask and the native Today
host use `SENTRY_DSN`. Keep Gerri separate from Mark's project. Connect Vercel's
resource to the owning project and Production; its integration supplies `SENTRY_ORG`,
`SENTRY_PROJECT`, and the server-only `SENTRY_AUTH_TOKEN` for source-map uploads.
No tokens, DSNs or production environments belong in Git or test fixtures.
Source-map upload is disabled when the build token is absent. Missing DSNs leave
monitoring disabled without blocking the app. Do not call delivery verified until
a synthetic error is visible in the owning Sentry project.

Events contain only error classes, stack locations and release metadata.
Arbitrary error messages, request headers/bodies/URLs, user identity, breadcrumbs,
contexts, attachments and locals are removed. Session Replay, logs and traces are
not enabled. This deliberately limits context until an explicit privacy review.

`.mcp.json` and `.codex/config.toml` register the official hosted Sentry MCP URL.
The coding client still needs its normal Sentry OAuth sign-in; tokens are stored
by the client, not these files. A running session does not acquire tools merely
because the files were added. Restart/reload the trusted project and complete
the client sign-in before claiming the connector is available.

The native Today host can read its own DSN from the existing protected Application
Support directory's `sentry.json` (`{"dsn":"<Today project DSN>"}`, mode 0600),
or its process environment. It never uses a web app's project or credentials.
Run `npm ci` on that host after dependency updates; an unavailable SDK does not
interrupt native service. No extra worker or local data permissions are created.

