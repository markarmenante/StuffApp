# StuffApp code review — 2026-11-23

Mark's request: "do a review of StuffApp. especially the banknote functionality.
look across types (watches, coins, banknotes, art) and centralize common
services: pdf scans, check functionality that adds data from external sources.
improve performance and look to minimize paid calls to ai."

Scope: `app.py` (≈44k lines) and the side modules that scan documents, enrich
records from external sources, or call Anthropic/Perplexity. Items marked
**[verified]** were traced by hand to the line and, where stated, reproduced
with a measurement or a test. Line numbers refer to the code as committed with
this review. No production data was read and no paid call was made: all
measurements use a synthetic database with every provider stubbed.

## Top findings

1. **[verified, fixed] The banknote list view did O(countries × notes) work on
   every load.** `list_view` (app.py:15997) calls `ensure_country_history` per
   distinct country, and `series_panels` (app.py:5921) calls
   `_country_history_state` per panel-less row; each re-read and re-classified
   the whole `banknotes` table through `_country_history_years`. Synthetic
   1,200 notes / 120 countries: **63 s per view, 1,134 full-table scans,
   1.38 million `_country_key` calls** (cProfile: 287 of 296 s). Now one
   cached index per database version: **~2 s warm, ~10 s first view**,
   `_country_history_request` ×120 from 6.5 s to 0.007 s.
2. **[verified, fixed] State-name generation had no failure backoff and was
   billed on every list view, note save and boot.** `ensure_state_names`
   (app.py:5551) rides on `ensure_country_history`; a failure in
   `_run_state_names_job` (app.py:5520) only printed. A country whose answer
   fails validation (e.g. "unusable response: 14 eras") paid a web-search call
   per view, per save, and per boot of *each* Railway instance. Synthetic
   test: **300 paid attempts in 3 views → 100 (first view only)**.
3. **[verified, fixed] Era-map drawings were re-commissioned by every detail
   view after a failure.** `GET /api/era-supplements` (app.py:26818) →
   `ensure_era_supplement` (app.py:26763); `_run_era_supplement_job`
   (app.py:26732) only printed on failure. Each attempt is a heavy call
   (12k output tokens, escalating to 32k on overrun, plus 3 web searches).
   Now: one attempt, then a backoff.
4. **[verified, fixed] Slow explicit lookups were paid twice.** Watch specs and
   value (Perplexity sonar-pro, 240 s timeout ×3 attempts), coin specs and art
   (240 s), recording notes (SDK default 600 s) run synchronously in the
   request, but Cloudflare cuts requests at 100 s. The browser shows an error,
   the server finishes and discards the suggestions (they are only in the
   response), and the natural re-click pays again. Now identical concurrent
   requests share one call, and an identical successful request within 10
   minutes is replayed. Test: **two identical clicks → one provider call**.
5. **[verified, fixed] Photo-side classification was repeated for identical
   photographs.** `_classify_banknote_listing_photos` (app.py:17581) sends up to
   24 images per call and runs from record Check, draft Check, market Buy and
   restart recovery. Now cached by content hash for 30 days, **conclusive
   decisions only**, so "run Check again" still re-asks for uncertain sides.
6. **[verified, fixed in the follow-up pass] Retries that could re-bill a
   request the provider had already processed** (see "Retries" below).
   Mark approved changing the deferred "Anthropic retry loop" item; one shared
   policy now never repeats a timeout.

## Findings in detail

### Performance

| # | Where | Scenario | Fix | Status |
|---|---|---|---|---|
| P1 | `_country_history_years` (app.py:5284), callers `list_view` (15997), `series_panels` (5921) | Each call re-read all banknotes and ran `collection_country` + `_country_key` (loops every spelling) per row; called once per country plus once per panel-less row. | `_country_history_year_index` (app.py:5250): one pass, cached until `PRAGMA data_version` (any committed write), the DB file identity, the year, or the country tables change. Per-render memo of `_country_history_state` in `series_panels`. | **[verified] fixed**: 63 s → ~2 s warm on 1,200/120 synthetic. Test `test_year_index_matches_the_full_scan_and_tracks_commits` compares with the old brute-force scan. |
| P2 | `_configure_db_connection` SQL functions `COLLECTION_FAMILY_RANK/SECTION` | `collection_family_issue` evaluated ~23×/row by the list query (27,600 calls for 1,200 rows). | `_collection_family_scalars` (app.py:6232), `lru_cache(typed=True)` over the pure function; Python callers still get fresh dicts. | **[verified] fixed** (small: warm view ~2.0 → ~1.7 s). |
| P3 | `resolve_anthropic_lookup_model` (app.py:15456) | Every lookup, Check, scan theme and generation asked the Models API first (up to 5 s; Market Scan even reserves a page request for it). | Successful resolutions cached 6 h per key/family; fallbacks never cached. | **[verified] fixed**; test `test_model_alias_is_resolved_once`. |
| P4 | `_fit_vision_image` (app.py:14687) | Images passed through at full camera resolution unless their base64 exceeded 4.5 MB; banknote Check sends up to 8 images and re-sends them on each `pause_turn` continuation. | `enrichment.fit_vision_image`: bound every image to 1568 px on the long edge (the size the API itself scales to), in its own format; images already within bounds pass byte-for-byte. `ANTHROPIC_VISION_MAX_EDGE` overrides. | **[verified] fixed**: a 12 MP photo uploads 15% of the pixels. Token cost is unchanged by design (the API resized anyway); latency and payload drop. |
| P5 | `file_thumb` (app.py:24117) | PDF thumbnails rendered page 1 at 2× (letter → 1224×1584) to show 320 px. | `document_scan.render_first_page` renders at ~1.5× the target. | fixed. |
| P6 | `listing_checks.purchase_sources`, banknote Check sources | The same saved receipt PDF is re-parsed for every Check and original-listing comparison. | `document_scan.pdf_text` memoises by sha256 (64 docs). | fixed. |
| P7 | indexes | Hot keyed lookups (`trimmed_image_sources`, `market_scan_items`, `original_listing_image_sources`, `country_history_jobs`) already have PK/indexes; list views are whole-collection scans ordered by Python SQL functions, so column indexes would not help. | none needed | checked. |

### AI cost (paid calls)

| # | Where | Scenario | Fix | Status |
|---|---|---|---|---|
| C1 | `ensure_state_names` / `_run_state_names_job` / `_backfill_country_histories` (app.py:5551 / 5520 / 5363) | No failure record: every list view, banknote save, and boot of both instances re-billed a failing generation. | Durable backoff in `ai_generation_failures`: 1 h, 6 h, 24 h, then weekly; cleared on success; the explicit country-history Retry (`force=True`) bypasses it. | **[verified] fixed**; test `test_failed_state_names_wait_out_a_backoff_instead_of_billing_every_view`. |
| C2 | `ensure_era_supplement` / `_run_era_supplement_job` (app.py:26763 / 26732) | Detail-page map view re-commissioned a failed drawing each time. | Same backoff; a pin in backoff reports `pending: false` so the map stops waiting. | **[verified] fixed**; test `test_failed_era_drawing_is_not_recommissioned_by_every_map_view`. |
| C3 | Explicit lookups: `fetch_watch_specs` (14503), `fetch_watch_valuation_*` (14122), `fetch_coin_specs` (27415), `fetch_coin_history` (15336), `fetch_coin_context(_perplexity)`, `fetch_art_lookup` (24581), `fetch_recording_notes` (15563) | Cloudflare's 100 s cap discards slow results; re-clicks, double-clicks and duplicate tabs paid again. | `enrichment.replay` keyed by the exact request (model, tools, messages, budget; not the timeout): concurrent duplicates share one call; identical successful requests replay for 10 min (`ENRICHMENT_REPLAY_SECONDS`, 0 disables). Failures and unfinished turns are never stored. A changed record is a new request. Auction-first brand revaluations are excluded (their restore/re-run wants fresh research). | **[verified] fixed**; tests `test_repeated_identical_watch_lookup_makes_one_paid_call`, `test_changed_watch_or_failed_lookup_asks_again`, `test_repeated_identical_art_lookup_uses_one_anthropic_call`. |
| C4 | `_classify_banknote_listing_photos` (17581) | Same photographs classified again by record Check, draft Check, Buy, restart recovery. Up to 24 images + 5k output per call. | `enrichment.remember` (durable `ai_result_cache`) keyed by model, prompt, photo ids, sha256s and gallery roles; stores only `banknote_photo_sides.conclusive` decisions (every photo high-confidence, verified distinct front/back gallery pair, clean gallery). 30-day TTL. | **[verified] fixed**; test `test_conclusive_photo_sides_are_classified_once_uncertain_ones_again`. |
| C5 | `fetch_banknote_specs` first turn (28694) | Two concurrent Checks of the same note (double submit, two tabs) paid twice. | `enrichment.single_flight` on the first identification turn. **No replay**: "normal Check retry" is a contract, so a later Check always asks again. | fixed. |
| C6 | Page-view / startup triggers | Country histories: list view, saves, startup sweep. Bounded already (`banknote_history.claim`: 3 attempts per request, 60 s apart). State names and era maps were not bounded (C1, C2). Startup import recovery only re-dispatches idle/queued/interrupted checks; the label worker is cached and leased. | C1, C2. | checked. |
| C7 | Prompt caching | Evaluated, **not applied**. The prompts put per-record content first (images, dealer text) and static rules after it, so there is no reusable prefix. Static blocks: photo sides 1.9k chars, slab labels 2.5k, country eras 2.4k, era map 1.8k (all below the cacheable minimum), banknote Check ~14.5k chars + ~5.6k per-note addendum (~4–5k tokens). Market Scan themes share context but run in parallel, so cache writes would race. A cache write costs more than plain input, so blanket caching would *raise* cost on one-off calls. | Follow-up: banknote Check's fixed instructions can go out as a `cache_control` system block cut from the same prompt, with each note's photos and text after it (`BANKNOTE_CHECK_PROMPT_CACHE=1`). Estimated saving ~5–10% of a batched Check's input. | **implemented, default off**: model-level equivalence could not be shown (no key in the sandbox); see Follow-up. |
| C8 | Model choice | Photo sides, trim verdict/geometry (`ANTHROPIC_NOTE_QUAD_MODEL`), Check translation and serial scan use `auto-sonnet`; the coin image audit already uses Haiku. Watch specs and value use Perplexity sonar-pro with `search_context_size=high` (the most expensive context tier). | Follow-up: separate `ANTHROPIC_TRIM_MODEL` and `ANTHROPIC_PHOTO_SIDES_MODEL` settings (both fall back to `ANTHROPIC_NOTE_QUAD_MODEL`), plus `scripts/ab-cheaper-models.py`, a bounded A/B (≤40 calls, sample inputs only) that reports match/differ per item. | **not switched**: no Anthropic or Perplexity key in the sandbox, so there is no evidence yet; see Follow-up. |
| C9 | `_anthropic_create_uncached` (13989) | A turn stopped at `max_tokens` is re-run from scratch at 4× the budget, up to 32k (era map: 12k → 32k), re-billing the whole input and its searches. | Recommendation: allow one escalation only, or stream long generations. | left: not a retry of a failed request (the first answer completed), so outside the follow-up's retry policy; needs Mark. |

### Retries that could re-bill **[verified, fixed in the follow-up pass]**

Anthropic Python SDK 2.13 (installed and read for this review) retries
`APITimeoutError` by default (`DEFAULT_MAX_RETRIES = 2`). A timed-out web-search
request may already have been processed, so each retry can be billed again.
Before the follow-up:

* Clients created **without `max_retries`** (default 2 retries, timeouts
  included): country history and state names (SDK default 600 s timeout),
  era map (1500 s), coin specs (240 s), art lookup (240 s), recording notes,
  coin history/context, collection analysis (600 s), watch value (Anthropic
  path). With the app-level `for attempt in range(3)` loops this was up to
  9 attempts for one click.
* `_pedigree_model_call`: `max_retries=1` plus two app-level attempts on
  transient errors (timeouts included) with a 480 s timeout, so up to
  4 × 480 s.
* Perplexity: three attempts on any `URLError`. Correction to the first
  version of this review: a timeout while *waiting for the response* reaches
  the caller as a bare `TimeoutError` and was already not retried. A timeout
  while connecting or sending (`URLError(timeout)`) was retried.
* Already correct: banknote Check (`max_retries=0`, one transport retry inside
  the 75 s budget, never on invalid responses) and Market Scan / estimates
  (`market_scan.model_call`, explicit budgets, no hidden retries).

After the follow-up there is one policy, in `enrichment`:

* **What is retried** (`retryable`): a connection failure with no response
  (never a timeout), 429, 529, 500/502/503. Nothing else is: no timeout, no
  408/409/504, no other status, no invalid or completed response. A provider
  `x-should-retry: false` vetoes the retry.
* **How it waits** (`call_with_retries`): bounded backoff of base × attempt,
  raised to a readable Retry-After and capped (30 s by default, 15 s for
  coin research, serial scan and pedigree).
* **SDK retries are off:** `anthropic_client` passes `max_retries=0` unless
  a caller says otherwise.
* **The nine app loops are gone.** They are now `_lookup_with_retries` calls:
  watch value, coin context, coin history, recording notes, art, coin specs,
  serial scan and pedigree, plus `_banknote_provider_create`. Each keeps its
  attempt count and exhaustion message ("Rate limited after retries: …",
  "Lookup failed after retries: …", or the friendly "… timed out" text);
  errors a site never caught are re-raised unchanged.
* **Paths that leaned on the SDK default** (country history, state names, era
  map, collection analysis, coin image audit) use
  `anthropic_client(..., retries=2)` under the same policy.
* **Banknote Check** keeps one transport retry within its deadline, with
  strict Retry-After and a 5 s reserve. 408 and 409 are no longer retried;
  `tests/test_banknote_provider_recovery.py` was updated for exactly that.
* **Perplexity** keeps three attempts and its two messages, and never
  retries a timeout.
* Coin research's configured attempts (default 1) are honoured, so it no
  longer gets the SDK's two hidden retries.

Tests per error class: `tests/test_enrichment.py` (`RetryPolicyTests`,
Perplexity timeouts/overload/504) and `tests/test_retry_policy.py`. The latter
covers art, coin specs, watch value, serial scan, pedigree and a background
generation through the real call sites, including "a timeout makes exactly
one paid call".

### Duplication across watches, coins, banknotes and art

* **Client and transport plumbing:** 23 separate `anthropic.Anthropic(...)`
  constructions, 24 inline `import anthropic`, 17 `_require_anthropic_key()`
  calls, 12 model env names, one Perplexity transport inside app.py.
  **Centralized:** every client now comes from `enrichment.anthropic_client(kind, …)`
  (metered, kwargs unchanged), and Perplexity goes through
  `enrichment.perplexity_chat`.
* **Retry loops:** 9 `for attempt in range(…)` loops with three different
  exhaustion semantics. **Left** (deferred refactor; see Retries).
* **JSON extraction:** 12 `re.search(r'\{…\}', text)` variants alongside
  `parse_model_json_object`. Left; they differ in their error text, which the
  routes return to the UI.
* **Image loading:** coins, banknotes, pedigree and serial scan already share
  `_load_vision_images` / `_banknote_check_vision_images`; the size rule now
  lives in `enrichment.fit_vision_image`.
* **PDF handling:** text extraction (banknote Check sources, original-listing
  comparisons for every category), PDF sniffing (check sources, source
  archives) and thumbnails. **Centralized** in `document_scan`.
* Each type keeps its own prompts, schemas, field mappings, blank-only and
  guarded-apply rules. None of those moved.

### Other observations

* **Paid lookups and viewer roles.** The global `before_request` hook enforces
  sign-in, owner-only `/admin`, per-category access and same-origin writes.
  But the explicit lookup POST routes (watch lookup/value/revalue, coin
  lookup/history/context, art lookup, recording notes, banknote serial scan,
  pedigree research) do not call `require_owner()`, so a non-owner *viewer*
  with access to that category could trigger paid calls. Banknote Check, Market
  Scan, analysis and the admin tools were owner-gated. **Fixed in the
  follow-up:** those routes now start with the same `require_owner()` (the
  same 403 for viewers), and the watch "Search Value" and pedigree "🔎
  Research" buttons render disabled for viewers. The ✓ Check and Scan
  buttons were already owner-only. `_resolve_user_email` and the open
  security items are unchanged. Test: `tests/test_owner_paid_lookups.py`.
* **No AI on PDFs.** No flow sends PDFs to a model; purchase evidence is the
  literal text layer, and image-only receipts are kept and reported
  unverified. This review keeps it that way.
* **Market Scan, estimates and slab labels** are the best-bounded paid paths
  (budgets, leases, caches, no hidden retries). They are the model for the
  rest and were not changed beyond metering.
* `banknote_catalog_audit.py` (an offline script) builds its own client and is
  not metered.

## Paid AI call inventory

Model defaults: `auto-sonnet` resolves to the newest Sonnet through the Models
API (fallback `claude-sonnet-4-6`). "Explicit" means a user click. Cost drivers
are given in the units billed (input/output tokens, web searches, images),
because current list prices could not be re-checked during this review.

| Kind (`/admin/ai-usage`) | Types | Trigger | Model (env) | Tools / budget | Before | After |
|---|---|---|---|---|---|---|
| banknote-check | banknotes | explicit Check; draft Check worker | `ANTHROPIC_COIN_LOOKUP_MODEL` (auto-sonnet) | ≤8 images, web_search ≤4, 8192 out, 75 s shared budget; + web_fetch ≤4 (12k tokens each) and translation in the same budget; + optional Perplexity Search (5 results) | no cache; full-res images; 1 transport retry | single-flight first turn; images ≤1568 px; retry unchanged; no replay (retry contract) |
| banknote-photo-sides | banknotes | Check, draft Check, Buy | `ANTHROPIC_NOTE_QUAD_MODEL` | ≤24 images @1100 px, 5000 out, 35 s | none | durable content cache, conclusive only (30 d) |
| banknote-serial-scan | banknotes | explicit Scan | `ANTHROPIC_COIN_LOOKUP_MODEL` | 2 images, 1024 out, 120 s, SDK retries | none | images ≤1568 px; metered |
| banknote-trim-geometry / -verdict | banknotes | photo upload, crop, Buy | `ANTHROPIC_NOTE_QUAD_MODEL` | 1–2 images ≤1600 px, 4096 out, 30 s | none | metered (not cached: "Crop photos" retry must re-ask) |
| country-history | banknotes | list view, note save, startup sweep | `ANTHROPIC_COUNTRY_ERAS_MODEL` | web_search 3, 5000 out (×4 escalation to 32k) | durable claim, 3 attempts / 60 s | unchanged (already bounded); metered |
| state-names | banknotes | list view, note save, startup sweep | `ANTHROPIC_COUNTRY_ERAS_MODEL` | web_search 2, 2000 out (escalation) | **none: every view/boot on failure** | durable backoff 1 h/6 h/24 h/7 d |
| era-supplement | coins, banknotes | detail map view | `ANTHROPIC_ERA_MAP_MODEL` | web_search 3, 12000 out (→32k), 1500 s | **none: every view on failure** | durable backoff |
| coin-specs | coins | explicit lookup; pedigree fill | `ANTHROPIC_COIN_LOOKUP_MODEL` or Perplexity | web_search 4, 2048 out, 240 s, ≤3 attempts (was ×3 loop + SDK retries; now shared policy, no timeout retry) | none | replay 10 min + single-flight; images ≤1568 px |
| coin-history | coins | explicit lookup | `ANTHROPIC_COIN_RESEARCH_MODEL` | web_search 4, 900 out | none | replay + single-flight |
| coin-context | coins | explicit lookup (job) | `ANTHROPIC_COIN_RESEARCH_MODEL` or Perplexity | web_search n, images | none | replay + single-flight |
| coin-image-audit | coins | admin audit | Haiku 4.5 (fixed) | 2 images, 300 out | none | metered |
| watch-specs | watches | explicit lookup; admin bulk | Perplexity sonar-pro, context high | 2048 out, 240 s ×3 | none | replay + single-flight |
| watch-value | watches | explicit value; brand revaluation job | Perplexity sonar-pro high, or Anthropic web_search 5/10 | 1536–2048 out | none | replay for single value (not auction-first) |
| art-lookup | art | explicit lookup | `ANTHROPIC_ART_LOOKUP_MODEL` | web_search 3, 1024 out, 240 s ×3 | none | replay + single-flight |
| recording-notes | recordings | explicit lookup | `ANTHROPIC_RECORDING_MODEL` | web_search 4, 2000 out, ×3 | none | replay + single-flight |
| pedigree | coins, banknotes | explicit research job | `ANTHROPIC_PEDIGREE_MODEL` | images, web_search budget, 4000 out, 480 s, ≤2 attempts (was up to 4 incl. timeouts) | none | images ≤1568 px; metered |
| original-listing-compare | all | original-listing worker | `ANTHROPIC_COIN_LOOKUP_MODEL` | text only (listing + receipts ≤90k chars), 4096 out, 60 s | worker-level | metered; receipt PDFs parsed once (memo) |
| collection-analysis | all | explicit analysis | `ANTHROPIC_ANALYSIS_MODEL` | 9000 out, 600 s | none | metered |
| market-scan | coins, banknotes | explicit Market Scan | `ANTHROPIC_MARKET_SCAN_MODEL` | per-scan request/search/output budgets | budgets | metered; alias resolution cached |
| market-estimate | banknotes | explicit Estimate prices | `ANTHROPIC_MARKET_SCAN_MODEL` | ≤12/job, 3500 out, `MAX_SEARCHES` | cached results | metered |
| market-slab-label | banknotes | accepted watched feed | `ANTHROPIC_COIN_LOOKUP_MODEL` | 1 image ≤1568 px, 6000 out | photo/item/version caches | metered |
| perplexity search (catalogue) | banknotes | inside Check | Perplexity Search API | 2 queries, 5 results, ≤15 s, no retries | none | unchanged |

## What changed

New shared modules, used by every type:

* **`enrichment.py`** is the external-enrichment ("Check") service layer and
  the only Anthropic/Perplexity plumbing:
  * metered client factory and per-kind usage;
  * request fingerprints;
  * `single_flight`, `replay` (10 min, explicit lookups) and `remember`
    (durable content-hash cache, `ai_result_cache`);
  * generation backoff (`ai_generation_failures`);
  * model-alias cache;
  * vision image fitting;
  * the Perplexity transport (retry semantics unchanged);
  * the `KINDS` inventory.
* **`document_scan.py`** is the document/PDF scan service: `pdf_text` (same
  limits and messages, memoised by sha256), `is_pdf`, `render_first_page`.
  `banknote_check_sources.pdf_text` remains the lookup point that Check,
  original-listing comparisons and tests use. The downloaded-receipt branch
  now parses bytes directly (no temp file), and `source_documents` uses the
  shared sniff.

Wiring in `app.py`:

* All 23 Anthropic client constructions go through
  `enrichment.anthropic_client(kind, …)` with unchanged kwargs.
* `_anthropic_create(…, replay_kind=…)` and
  `perplexity_chat_completion(…, replay_kind=…)` are used by the explicit
  lookups listed in C3.
* Photo-side content cache, banknote Check single-flight, state-name and
  era-map backoff, country-history year index and `series_panels` memo, model
  alias cache, bounded vision images, the SQL family memo, and the
  `file_thumb` renderer.
* New owner-only, read-only `GET /admin/ai-usage`: per-kind requests, replays,
  shared joins, cache hits, tokens, web searches and errors since boot; the
  kind inventory; and generations waiting out a backoff. Use it to see the
  reductions in production.

New tables, both cache/reporting tables (allowed by the 3NF rule's surgical
exception; the collection tables stay the source of truth):

* `ai_result_cache(cache_key PK, kind, created_at, expires_at CHECK ≥ created_at, result)`
  with an index on `expires_at`; expired rows are pruned at boot.
* `ai_generation_failures(job_key PK, kind, failures CHECK > 0, last_failed_at, retry_after, last_error)`.

Nothing changes what is written to collection records. Contracts kept:
guarded apply, catalogue Check (`tests/test_banknote_catalog_*`), vision
source originals, Market Scan rules, single/multi-note import.

## Tests

* New: `tests/test_enrichment.py` (22), `tests/test_document_scan.py` (5),
  `tests/test_paid_call_savings.py` (11). These include the required proof
  that **a repeated identical request does not make a second paid call**
  (unit level, through the watch lookup route, and through `fetch_art_lookup`).
  All three are added to `tests/run_all.py` and to CI's
  `scripts/test-regressions.py`.
* Run with the model keys unset (`run_all.py` does not strip them, unlike
  CI); `anthropic`, `sentry-sdk`, `pillow-heif` and `gunicorn` were installed
  for this; `rembg` absent as in CI.
* **Pre-existing failures on untouched main:**
  * `tests/test_market_wantlist.py`: `AssertionError: {'british-alderney'}` at
    line 92, identical before and after this change.
  * `tests/test_banknote_crop_jobs.py` (in neither `run_all.py` nor CI) cannot
    import `banknote_crop_jobs` when run directly (it adds no repo path).
* After this change: all other `run_all.py` suites and all CI regression
  suites pass, as on main.
* Follow-up pass adds `tests/test_retry_policy.py`,
  `tests/test_owner_paid_lookups.py` and
  `tests/test_banknote_check_prompt_cache.py`, extends
  `tests/test_enrichment.py`, and updates
  `tests/test_banknote_provider_recovery.py`. That last update is for the
  intended policy change only: 408/409 moved from "retried" to "one call",
  plus a timeout/504 case.

## Follow-up pass (2026-11-23): the four items left for Mark

Mark reconnected Railway and asked for all four items.

1. **Retries.** Implemented as described in "Retries" above.
2. **Cheaper models and the Perplexity watch setting.** *Not switched.* This
   cloud sandbox carries neither `ANTHROPIC_API_KEY` nor `PERPLEXITY_API_KEY`
   (contrary to CLAUDE.md's 2026-08-17 note about the Default environment),
   so the bounded A/B could not run, and switching without evidence was
   ruled out. No Railway variable was changed.
   * New settings: `ANTHROPIC_TRIM_MODEL` (crop geometry/verdict) and
     `ANTHROPIC_PHOTO_SIDES_MODEL` (front/back sorting), each falling back to
     `ANTHROPIC_NOTE_QUAD_MODEL`, so each can switch alone.
     `PERPLEXITY_WATCH_LOOKUP_SEARCH_CONTEXT` already existed.
   * To decide, run `scripts/ab-cheaper-models.py` from a session with both
     keys, on sample photos and 3–4 watch references (never production data;
     the script copies inputs into a temporary data folder and stops at 40
     paid calls). Switch only the areas it reports as matching on every item,
     on both web and gerri.
3. **Owner-only paid lookups.** Implemented (see Other observations).
4. **Prompt caching for multi-note Check.** Implemented behind
   `BANKNOTE_CHECK_PROMPT_CACHE=1`, default off. Equivalence of model output
   could not be shown without a key.
   * **How it works:** the system block is the exact instruction text of the
     default prompt, with only "above/below" pointed at the user message. It
     is cut from the default prompt at run time; any mismatch falls back to
     the default layout.
   * **What is proven without a key:** the default request is unchanged; the
     cached block is identical for every note; per-note facts never enter
     it; both layouts give identical Check results for the same model reply;
     `cache_read_input_tokens` is metered (`/admin/ai-usage`).
   * **Before turning it on:** run 2–3 fixture Checks with and without the
     flag from a keyed sandbox.
   * Test: `tests/test_banknote_check_prompt_cache.py`.

### Keyed run (2026-11-23, later the same day)

Mark copied the production keys into the Mac checkout's `.env` with
`railway variables --kv`. The sandbox read only the two key lines from it. The
sandbox can reach Anthropic but not Perplexity, so only the Anthropic items
ran. Inputs were four sample photos in PMG holders: Mauritius 5 rupees
front and back, Spain 25 pesetas 1928, and Peru 10 soles 1945. Everything ran
in temporary data folders. In all, 28 paid calls; the cap was 40. **No setting
was changed.**

| Item | Current → candidate | Result | Decision |
|---|---|---|---|
| Trim geometry | claude-sonnet-5-5 → claude-haiku-5-5 | Holder and label flags were equal on 4/4 in two runs, and corners were within 8/1000. But Haiku returned axis-aligned rectangles where Sonnet reported the ~0.3° tilt of each holder. | **Not switched.** The precision loss is systematic, the sample was all near-straight photos, and the saving is a fraction of a cent per uploaded photo. |
| Photo sides | claude-sonnet-5-5 → claude-haiku-5-5 | Run 1 differed. In run 2 the front/back picks, sides and confidence matched; Haiku's pairing note was weaker (no back serial). | **Not switched.** It was not consistent across runs. |
| Watch lookup context | Perplexity high → medium | Not run: api.perplexity.ai is not reachable from the sandbox. | Unchanged. |
| Check prompt cache | flag off → on, 2 notes each | Identity fields were identical: country, denomination, date, Pick (P-22, P-74b), grade and serial. Only free-text issuer and printer wording varied. The second note read the cached block (15.9k tokens). Each cached call also wrote a further ~13k tokens, so cost was +21% on the first note and −17% on the second, about even over two notes. | **Left off.** It costs more for a lone Check, which is the common case since single-note orders open directly. Revisit only if the extra cache writes are understood. |

## Left deliberately, with reasons

* **`max_tokens` escalation** (C9): a completed answer re-run at 4× budget;
  not a failed-request retry, so outside the approved policy.
* **Switching to cheaper models or a cheaper Perplexity context** (C8): the
  keyed run above found no safe switch. Perplexity is still untested because
  the sandbox can't reach it.
* **Turning on Check prompt caching** (C7): the model output was equivalent,
  but the cost was about even over two notes and higher for a single Check
  (see the keyed run above). The flag stays off.
* **Trim verdict/geometry caching:** deterministic inputs, but the explicit
  "Crop photos" retry must be able to get a fresh answer.
* **Banknote Check replay:** excluded by the "normal Check retry" contract;
  only concurrent duplicates are shared.
* **Deferred refactors and open security decisions:** untouched.
* **The 10-minute replay window** is a judgement call: it covers Cloudflare's
  100 s cap plus a re-click. `ENRICHMENT_REPLAY_SECONDS=0` turns replay off
  with an environment change only (Railway restarts the service; no code change).
