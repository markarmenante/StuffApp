# CLAUDE.md — StuffApp

## Standing instructions from Mark — read and follow these FIRST

(The SessionStart hook prints this whole section into every web
session's opening context. Keep it the first section of this file, and
fold new standing instructions in here — nowhere else.)

- **Commit and push directly to `main`.** No draft-PR round-trips — `main` is
  the deploy branch; Railway auto-deploys it.
- **Proactively install/connect whatever tools, MCP connectors, or
  dependencies streamline development**, and tell Mark when something needs a
  one-time authorization on his side.
- **Always look for resources in other apps first** (2026-08-09). Before
  minting a credential or asking Mark to copy one: check the boardroom
  repo's CONNECTORS.md registry, the other apps' deployments (Railway,
  Vercel) and their local Mac checkouts (this app: `~/Developer/stuffapp`
  with its `.env`; boardroom `/Users/markarmenante/GitHub/boardroom`;
  Family Office, museum-of-time, n552ym under `~/Documents/GitHub/`).
  Reuse what exists; never re-mint, never make Mark hand-copy what a
  loader can find. Where the keys for THIS app actually are (swept
  2026-08-16; exact env names in CONNECTORS.md):
  - The Anthropic and Perplexity model keys live in Railway project
    `courageous-adventure`, service `web`; the Anthropic key is also in
    the boardroom Vercel envs and the Mac checkout's `.env`.
  - A cloud session cannot READ those values: the Railway and Vercel
    MCP connectors return variable names only, and the Mac is reachable
    only when a local session appears in ListAgents. The claude.ai
    environment's own env config is the reuse recipe for cloud
    sessions — and as of 2026-08-17 the Default environment CARRIES
    `ANTHROPIC_API_KEY` (and `BOARD_DATABASE_URL`), so sessions started
    after that date can run model-dependent code (trim pipeline, Check
    prompts, country histories) directly in the sandbox. If the var is
    missing, check you're in the Default environment before assuming
    it's gone.
  - To reach the Mac from a cloud session: Claude Code is already
    installed there; Mark opens the Claude desktop app with Remote
    Control enabled (or leaves a `claude` session running) and the Mac
    appears in ListAgents — then local work (reading `.env`, running
    boardroom's `ops/find-local-repos.sh`, deleting stale checkouts)
    is delegated to it instead of asked of Mark.
  - So: never treat a missing env var as a dead end, and never skip
    validation because the sandbox lacks a key — production has it.
    Model-dependent behavior can be exercised server-side on
    stuff.armenante.com, e.g. ✓ Check (`POST
    /banknotes/<id>/lookup-specs`) runs the spec lookup and image
    re-trim with production's own key.
- **Database design, all apps** (2026-08-16): normalize to Third Normal
  Form as the default starting point — it resolves most redundancy and
  integrity issues without excess complexity. Junction tables for
  many-to-many relationships, with their foreign keys indexed for join
  performance. Enforce integrity with database constraints (primary,
  foreign, unique) rather than application code alone. Never
  denormalize preemptively: ship the normalized schema first and
  measure real query performance (EXPLAIN ANALYZE) before touching it.
  When denormalization is warranted, do it surgically — a specific
  redundant column, a materialized view, or a cached/reporting table —
  with the normalized tables remaining the source of truth.
- **Remember the apps** (2026-08-16): the registry of all of Mark's
  apps — repos, deploy targets, status — lives in the boardroom repo's
  root `CLAUDE.md`. When you work on an app that isn't listed there,
  add it in the same session.

## What this is

Flask + SQLite collection app at https://stuff.armenante.com (Railway, behind
Cloudflare). One main module — `app.py` — plus `templates/`,
`static/css/style.css`, and `schema.sql`. See README.md for local paths and
the Railway start command.

## Railway topology (updated 2026-08-16)

Production `stuff.armenante.com` is project **courageous-adventure**,
service `web` (origin `web-production-cf059.up.railway.app`). The two
stale duplicate projects that used to triple every deploy —
observant-success (`web-production-fca7e`) and poetic-peace
(`web-production-ac478`) — had their services removed on 2026-08-16
with Mark's approval; only empty project shells remain, which Mark
deletes from the Railway dashboard. Every push to `main` deploys
production exactly once now — so batch doc-only commits, and check
nobody is mid-Check before pushing.

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
  `web-production-cf059.up.railway.app` is public (Cloudflare proxies to
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

## Consolidations done (behavior-preserving, tested)

- Anthropic scaffold: `_message_text(resp)` and `_require_anthropic_key()`
  shared across the 9 `fetch_*` functions.
- Bulk-UPDATE admin routes: the 12 one-shot maintenance endpoints are
  registered from `_BULK_UPDATE_ROUTES` (rule, endpoint, sql, use_now,
  total_table) — each route's exact SQL is verbatim in that table.
- `_table_cols`, `next_cat_id` shim, `_renumber_coin_groups` reuse,
  `_restore_docs_from_slots` (earlier pass).

## Deferred refactors (still open)

- **person_medications → property_slot spec (F2, ~200 lines).** Left for
  a *supervised* pass: it writes health records, and the property-slot
  generics aren't a drop-in (they build the INSERT column list from the
  spec, add a `_format_us_phone` hook, and use different kwargs), so a
  slip maps values to the wrong medical columns silently.
  `tests/test_person_medications.py` pins the current round-trip and is
  the gate for that merge — do it, keep those tests green.
- Anthropic retry loop (~110): three different exhaustion semantics;
  unifying changes behavior.
- coin `_coerce` twins (~53): genuinely divergent (die_axis /
  denomination handling) — a merge is a behavior change, not a refactor.
- import-secret guard → decorator (48 copies): it's the admin-secret
  gate; left untouched per "don't touch security".
- Smaller: `_json_row_or_404` (D2) changes the JSON 404 shape unless
  done with a custom error handler; AI-route error decorator (D3);
  reportlab cell-style / fit-image helpers (D6/D7).

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
