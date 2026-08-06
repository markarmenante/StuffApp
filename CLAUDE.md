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

Tests: `.venv/bin/python tests/test_banknote_sort.py`

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
