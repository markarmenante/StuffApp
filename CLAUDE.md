# CLAUDE.md — StuffApp

## Standing instructions from Mark

- **Commit and push directly to `main`.** No draft-PR round-trips — `main` is
  the deploy branch; Railway auto-deploys it.
- **Proactively install/connect whatever tools, MCP connectors, or
  dependencies streamline development**, and tell Mark when something needs a
  one-time authorization on his side.

## What this is

Flask + SQLite collection app at https://stuff.armenante.com (Railway, behind
Cloudflare). One main module — `app.py` — plus `templates/`,
`static/css/style.css`, and `schema.sql`. See README.md for local paths and
the Railway start command.

## Dev setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/flask --app app run --port 5001
```

Claude Code web sessions: `.claude/hooks/session-start.sh` does the venv +
install automatically once registered as a SessionStart hook in
`.claude/settings.json`.

Tests: `.venv/bin/python tests/run_all.py`

## Open security decisions (need Mark)

Two items were left for you because fixing them unattended risks a
lockout or a failed deploy:

- **Auth rests on a trusted header with an owner fallback.**
  `_resolve_user_email` (app.py) falls back to `OWNER_EMAIL` when no
  `Cf-Access-Authenticated-User-Email` header is present, so anything
  hitting the app without that header is owner. The Railway origin
  `web-production-fca7e.up.railway.app` is public (Cloudflare proxies to
  it), so that origin is a direct, unauthenticated bypass of Cloudflare
  Access. Fix is a Cloudflare-side control (Authenticated Origin Pulls,
  a Tunnel, or an IP allowlist) — NOT deleting the railway domain (CF
  pulls from it). Only after the origin is locked down should the
  `or OWNER_EMAIL` fallback be dropped and the CF Access JWT validated;
  removing the fallback first would fail the `/` healthcheck and lock
  everyone out.
- **Admin secret was an in-source constant.** Now reads
  `STUFFAPP_ADMIN_SECRET` from the env with the old value as fallback.
  Set a fresh value on Railway to rotate; it's still rendered into
  admin.html, so treat the old one as burned.

## Deferred refactors (surveyed, not yet done — all behavior-preserving)

Left for a supervised pass because each touches security- or
data-write-sensitive paths: person/property slot machinery (~200 lines,
health data), the 9-copy Anthropic lookup scaffold (~155), the 48-copy
import-secret guard → decorator (~48-92, security gate), and the
one-shot bulk-UPDATE admin routes → table-driven registry (~100).

## Gotchas

- Banknote list ordering lives in `CATEGORY_ORDER_BY['banknotes']`, built on
  custom SQL functions (`NATION_NAME`, `US_NOTE_GROUP`, `SERIES_YEAR`,
  `DENOM_*`) registered in `_configure_db_connection`. Any ordering change
  must bump the `banknote_display_number_vN` migration key so Display
  Numbers (B1, B2, …) reseed to match.
- Country history panels come from the built-in `COUNTRY_KEYS` /
  `COUNTRY_ERAS` tables in `app.py`; uncovered countries fall back to
  Claude-generated histories (the `country_eras` table), which need
  `ANTHROPIC_API_KEY` at boot. As of Aug 2026 that fallback appears inactive
  in production — prefer adding built-in entries (see djibouti and
  guinea-bissau for the pattern; historical territories map to their modern
  nation).
- The SQLite DB lives at `$DATA_DIR/stuffapp.db` (defaults to the repo root;
  gitignored).
