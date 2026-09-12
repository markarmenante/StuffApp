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
  family-office and n552ym under `~/GitHub/`; museum lives in
  boardroom at `apps/museum`).
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
    installed there; Mark runs `claude remote-control` in a Terminal
    from a project directory (e.g. `~/GitHub/boardroom`) and leaves
    that window open — there is NO desktop-app switch for this. The
    Mac's sessions then appear in ListAgents, and local work (reading
    `.env`, running boardroom's `ops/find-local-repos.sh`, deleting
    stale checkouts) is delegated to it instead of asked of Mark.
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

## Railway topology (updated 2026-08-20)

Production `stuff.armenante.com` is project **courageous-adventure**,
service `web` (origin `web-production-cf059.up.railway.app`). The same
project also runs service **`gerri`** → `gerri.armenante.com`: a second
instance of this repo with its own `/data` volume and its own
`STUFFAPP_OWNER_*` env (separate owner, separate collection DB). The
account holds exactly two Railway projects, both production and both
permanent: courageous-adventure (this app) and ym-familyoffice
(Family Office). The old duplicate projects observant-success and
poetic-peace were fully deleted 2026-08-17. Every push to `main`
deploys BOTH instances — so batch doc-only commits, and check nobody
is mid-Check on either before pushing.

## Origin maps and era borders (coins, banknotes)

Both detail pages carry an Origin map (Leaflet; `static/js/coin-geo.js`
holds the shared geography). Pin rules, per Mark (2026-09-06): coins
before 1500 pin at the mint, or the region's principal city when the
mint is uncertain; coins from 1500 on and all banknotes pin at the seat
of the issuing state as of the year (`_coin_capital`, `_banknote_pin`,
era-aware). The banknote map also names the issuing state as of the
year in its own language and English (`BANKNOTE_STATE_NAMES`;
`country_state_names` for generated ones).

The borders of the record's own year come from the historical-basemaps
snapshots (jsDelivr, BC included). Where the nearest snapshot is more
than `ERA_SUPPLEMENT_GAP_YEARS` stale and nothing covers the pin, a
supplement is drawn once and served over the snapshot from then on:
hand-drawn ones live in `static/geo/` and are listed in
`ERA_STATIC_SUPPLEMENTS`; the rest Claude draws on demand into the
`era_supplements` table, keyed `<snapshot>:<polity slug>`, commissioned
by the first `/api/era-supplements` call for that pin (i.e. the first
view of a new record). Generated maps are labelled "AI-drawn
approximation" in the caption. Generation needs `ANTHROPIC_API_KEY`
(production has it; the sandbox usually does not).

## Market Scan (coins, banknotes)

The Market Scan pill (left of "+" on the Coins and Banknotes lists)
swaps the list for live buy candidates and reads "Collection" while
showing them. A scan runs in a background thread (`_run_market_scan`;
Cloudflare caps a request at 100 s) as several parallel web-search
Claude calls, one per theme in `_MARKET_THEMES`: banknotes lead with
colonial issues before independence (British, French, Italian,
Portuguese, German), then denomination gaps in series held, the pattern
of recent purchases, and a "new sources" theme that hunts venues Mark
does not use yet; coins are ancient Greek only. Every call sees the
fair-price profile, the holdings summary, denomination coverage and
recent purchases, and its venue rule REPLACES the profile's
"major auction houses only" rule (Mark, 2026-09-09: eBay, Stack's,
Numista, dealers are buy candidates here). Results are filtered to live
lots with a URL and a grade that clears the bar (notes 64+ with EPQ/PPQ
preferred, 50+ only for stated rarity; coins XF40+), de-duplicated,
checked against the collection (`_similar_banknotes`) and ranked.
Tables: `market_scans`, `market_scan_items` (payload JSON). Buy cannot
check out on a seller's site: it opens the listing (pay there) and files
the item as an Ordered record with the price's USD tail and the listing
URL. **Bought** (2026-09-11) files the same way without opening the
listing — for a note paid for after opening the listing from the row,
which is a link; before this, buying that way filed nothing (Mark's
French Indochina 5 piastres, and the next scan deleted the candidate).
A new scan now marks the previous scan's undecided items `superseded`
instead of deleting them (60-day prune of superseded + dismissed), and
`/<cat>/market?earlier=1` ("Earlier candidates") lists superseded and
dismissed items with Bought. Model env: `ANTHROPIC_MARKET_SCAN_MODEL`.
Test: `tests/test_market_bought.py`.
Colonial want-list (2026-09-12): `BANKNOTE_COLONIAL_WANTLIST` in app.py
is the table of banknote-issuing colonies the collection lacked on
that date (35 entries: name, empire group, issuer, period, `held`
country substrings, `before` year). `_banknote_wantlist_open` retires
an entry once an Own/Ordered note's country matches (dated up to
`before` where set — a 1958 Cuba note does not retire Spanish-colonial
Cuba); `_banknote_wantlist_themes` turns the open entries into up to
three TOP-PRIORITY themes (British / French-Portuguese-Dutch / other)
that lead every banknote scan, and the market page's status line shows
"colonial want-list: N of 35 still open". Add or retire entries in the
table; nothing else needs touching. Test: `tests/test_market_wantlist.py`.
Photos (2026-09-12): Buy/Bought store the listing's photos as the
record's image_1/image_2 — the scan's own image URL first (eBay
thumbnails upgraded to s-l1600), then the listing page's photos
(`_market_page_image_urls`: JSON-LD, og:image, eBay gallery) when the
scan had none or the fetch failed; the liveness probe harvests the same
photos for a candidate the model gave no image for, so the list shows a
thumbnail. Banknote photos are trimmed on Buy like an upload. Every
image attempt logs `market buy image: …`. Test: `tests/test_market_images.py`.
eBay liveness (2026-09-12): eBay walls the scan's page fetch with a
redirect to /splashui/captcha and keeps ended item pages up (title,
photos, price, an ENDED badge), so an "unknown" verdict — which never
drops — let months-old ended eBay lots through (ten of thirteen
candidates on 2026-09-11 were eBay; the French Guinea specimen had
ended 2024-12-25). Now the captcha bounce counts as a challenge by URL,
a readable eBay page with no buy/bid control is ended, an unreadable
eBay page gets one retry and then keeps its item only on the model's
own live evidence (`closes` in the future, or `live_evidence` quoting
Buy It Now / bids / time left — the prompt now demands it for eBay),
and every probe logs `market scan verify: <state> status= len=
challenged= why=` so a scan's logs show what each venue served. Test:
`tests/test_market_ebay_liveness.py`. The container's egress proxy
refuses ebay.com, so eBay can only be checked in production's logs.

## What the model sees for a banknote (Check, serial scan)

Uploads of `image_1` / `image_2` are trimmed to the bare note on arrival
(since 2026-09-10), so the stored files no longer show a PMG / PCGS
holder label. Every vision call therefore resolves each image through
`_banknote_vision_source` — the untrimmed original recorded in
`trimmed_image_sources`, when it is still on disk — and reads THAT.
Forgetting this is what "Check no longer picks up the grading data"
looked like (Morocco 5 francs, 2026-09-10): the label with Pick #,
grade, EPQ and cert number had been cropped away before Check ran. The
page keeps showing the trimmed image. Test:
`tests/test_banknote_vision_source.py`.

## Serial-number scan (banknotes)

The Scan button in the Serial # cell of the banknote detail page (Mark,
2026-09-10) posts to `POST /banknotes/<id>/scan-serial`: Claude vision
reads the serial off the note's own front/back photos (`_load_vision_images`,
same as Check; no web search, no dealer text) and the route stores it on
the record — overwriting a different existing value, since the photo is
the note itself — returning `{serial_number, previous, stored, unchanged,
confidence, readings, basis}` for the page to report. A note issued
without a serial, or an unreadable one, returns null and writes nothing.
Needs `ANTHROPIC_API_KEY` (production has it). Test:
`tests/test_banknote_serial_scan.py` (model call stubbed).

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
  `ANTHROPIC_API_KEY`. That fallback IS active in production (2026-09-10:
  Réunion, Cayman Islands, British Caribbean Territories all generated
  within ~2 min of their first note — `ensure_country_history` fires from
  every banknote write path, the list view, and the startup sweep), so a
  new country/colony needs no code. The gap is the wait: until the
  generation lands the list shows a dashed placeholder panel
  (`usp-pending`, state from `_country_history_state`) that polls
  `/banknotes/country-history/status` and reloads when ready, or offers
  `/banknotes/country-history/retry` when a generation failed. Built-in
  entries are still the better home for a country with many notes (see
  djibouti and guinea-bissau for the pattern; historical territories map
  to their modern nation).
- The SQLite DB lives at `$DATA_DIR/stuffapp.db` (defaults to the repo root;
  gitignored).
