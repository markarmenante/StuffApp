# StuffApp development

Read `CLAUDE.md` first for standing instructions and production boundaries.
Read `CONNECTORS.md` before adding or changing an integration. Commit and push
completed changes directly to main as Mark has authorized.

## Development tools (2026-11-01)

- GitHub Actions: the tracked workflow runs unit/type/build checks and browser tests
  on pushes and pull requests, then verifies the exact production commit after
  a main push. It preserves existing Git auto-deploys and adds no approval step.
- Playwright: `npm --prefix browser-tests run test:e2e` starts isolated loopback servers; install Chromium
  with `npm --prefix browser-tests run browsers:install`. Tests use synthetic data and no native
  profiles, provider accounts or production database. Failure traces/reports
  are workflow artifacts, retained for seven days. See
  `docs/development-verification.md` for the scope and commands.
- Sentry SDK and project MCP configuration are present. Set a separate SENTRY_DSN
  on web and Gerri; MCP OAuth is client-managed. Monitoring is disabled without
  its own DSN. Never claim delivery/access until verified. Request/user data,
  breadcrumbs, arbitrary error messages and locals are removed from events.
