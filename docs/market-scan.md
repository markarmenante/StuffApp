# Progressive market scans

Coins and banknotes use one execution pipeline. `market_scan.py` contains the
scan scheduler, source adapters, per-scan context, fetch/cache service, and
transactional market repository. `app.py` supplies `CoinMarketPolicy` and
`BanknoteMarketPolicy` (currently private classes), the collection rules,
venue parsers, model prompts, and Flask routes. Both categories use the same UI.

## Visible behavior

Each source's completed candidates are normalized, checked against their
listing pages, and saved immediately. The market page polls every five seconds
and replaces only its results area when the persisted revision changes. It
keeps the location picker and active Buy/Bought/dismiss requests intact. Progress
shows completed sources and candidate count, using the server's start time.

eBay buy candidates require a live verdict from a readable exact listing page.
A fresh exact-item observation from the authenticated signed-in browser may resolve
a server-side challenge, but never override an ended or invalid listing. Search
snippets, model-written live evidence and future closing dates cannot establish
availability. Older unverified eBay candidates
move to Earlier candidates; Buy and View listing recheck current availability.
Bought can still file a purchase already made. Other unreadable venues retain
the existing unverified state.

Coin archive enrichment runs after candidates are visible, for at most another
60 seconds within the overall scan budget. It uses cached archive queries and
metadata-only provenance results; it does not download full lot descriptions
or photographs for the market list.

## Market grouping

Both Market Scan pages gather similar listings into visible sections. Banknotes
use the country spelling aliases and complete series label, with the existing US
note-type rules separating same-year classes such as Silver Certificates and
Federal Reserve Notes. Series suffixes remain distinct. Coins use the existing
catalogue-region normalization, including the separate island headings.

Groups follow the first appearance in the existing ranked results; listings
retain their rank order within each group. This is display-only metadata on
copies: persisted ranks, catalogue references, eligibility, ownership warnings,
dismissals and per-listing actions remain unchanged. Current and Earlier market
views use the same grouping. Collection lists are unchanged.

Watched/sponsored cards are grouped independently in their existing observed
section. They reuse the country already identified for collection checks and
only explicitly named series in card titles. A bare year is not treated as a
series. Missing data reads “Series not specified”, “Other banknote listings” or
“Region not specified”; it does not trigger enrichment or a new scan. Grouping
never upgrades an observed card into a verified recommendation.

## Identity and decisions

Canonical URLs remove known tracking parameters and fragments, preserve
identity parameters such as CNG `CoinID`, and recognize eBay item IDs across
regional domains. Different listings with the same title remain distinct.

Dealer inventory and product-category URLs, including HTML/PHP inventory pages, cannot serve as exact offers. The same guard hides older invalid cards and blocks their View/Buy actions.

Candidates reuse an existing ID when rediscovered. Transactions check the
latest scan generation before writing. Updates cannot resurrect dismissed or
ordered candidates, overwrite their record IDs, or let an old scan replace a
newer scan. Existing undecided candidates remain visible during discovery.
Only a successful, nonempty scan with no source errors supersedes old
undecided candidates. Partial, failed, or empty scans retain them.

Banknote current candidates and observed watched/sponsored cards have **Delete**.
It permanently suppresses that exact listing from all recommendation sources,
without changing the eBay watchlist, collection or Ordered records. Another
listing with the same catalogue reference remains eligible. The decision lives
in `market_dismissals`, keyed by category and canonical listing URL, on the hosted
collection database, so it survives browsers/devices, restarts and all source
refreshes. Current views, personal-source model input and final transactional
publication consult it; a batch already running cannot resurrect a deleted item.
The deletion transaction marks all matching non-ordered candidate rows dismissed
and advances scan revisions. UI refreshes started before deletion cannot put the
card back; errors leave it visible and retryable.

The existing 60-day prune of dismissed/superseded candidate history still applies,
and personal evidence expires after 24 hours. Neither removes the suppression
record. Startup and pre-prune migration preserve existing retained banknote
dismissals, including legacy payload-only rows; dismissals already pruned before
this upgrade cannot be recovered. Earlier candidates remain explicitly labelled
Dismissed with historical View and Bought recovery, without recommendation Buy
or Delete controls. Filing a purchase through Bought does not erase suppression.
Ordered records are not pruned. Coin dismissal behavior is unchanged.

`POST /banknotes/market/<candidate_id>/dismiss` saves the candidate's listing
identity. `POST /banknotes/market/ebay-feed/<ebay_item_id>/dismiss` resolves an
account-bound observed card instead of accepting an arbitrary URL; a known prior
deletion remains idempotent after its snapshot expires. Both require the existing
app-owner authorization and cross-site write guard, and return the canonical URL
for removal of duplicate visible occurrences. These are app actions, not
bridge-token endpoints. The personal-card action is available only on web.

## Budgets and concurrency

Defaults and supported controls:

| Setting | Default | Meaning |
| --- | --- | --- |
| `MARKET_SCAN_SECONDS` | 1200 | Overall scan processing deadline; maximum configurable 1500 |
| `MARKET_SCAN_DISCOVERY_SECONDS` | 900 | Stop waiting for and issuing discovery work; maximum 1400 and always within overall deadline |
| `MARKET_SCAN_WORKERS` | 2 | Theme workers, capped at two by the scheduler |
| `MARKET_SCAN_SEARCHES` | 10 | Search-tool allowance for a theme call, subject to the total reservation budget |
| `MARKET_SCAN_TOTAL_SEARCHES` | 10 × theme count | Reserved server search-tool uses across calls/continuations/retries; maximum 160 |
| `MARKET_SCAN_MODEL_REQUESTS` | 2 × theme count + 6 | Model-call attempts including repairs; maximum 48 |
| `MARKET_SCAN_OUTPUT_TOKENS` | 100000 | Sum of requested maximum output tokens across all model calls; maximum 160000 |
| `MARKET_SCAN_PAGE_REQUESTS` | 320 | Page and uncached FX requests; maximum 500 |

There are at most two active scan model requests across categories in one
server process. While direct-catalogue discovery runs, only one broad theme is
started, leaving an opportunity for the catalogue's shaping request. The second
theme worker resumes after the catalogue source completes. This intentionally
does not increase concurrency.

The limiter is process-local. Mark's and Gerri's Railway services have separate
processes and quotas must be allocated accordingly if they share a provider
account. Their collection contexts, candidates, decisions, and caches are never
shared. No new credential, cross-owner cache, or external coordination service
is introduced. Continue using the existing single Gunicorn worker: process-local
scan ownership is not compatible with adding workers/replicas without a job
ownership redesign.

Model calls disable SDK retries, cap each request at 240 seconds or the remaining
discovery time, and permit at most one `pause_turn` continuation. Rate-limit
retries are rescheduled (up to three attempts) rather than sleeping in a worker.
All attempts reserve their request, search and output-token budgets before
transmission. Token exhaustion never triggers a larger-budget search restart.
Malformed JSON is salvaged locally first, then gets at most one tool-free repair;
a repair failure cannot restart discovery. Repaired listing URLs must already
occur in the original output.

The token ceiling is an **output-token reservation ceiling**, not a dollar or
combined input/output ceiling. Application prompts are also limited to 150 KB,
and reported input/output usage is recorded. Provider-generated web-search
input and the provider's interpretation of tool-use limits remain external.

At a deadline, queued work is cancelled and late discoveries cannot publish.
Python cannot forcibly interrupt an HTTP request already inside a library;
it returns under its request timeout, and cooperative checks prevent follow-on
requests. Optional archive work and processing share the remaining overall
budget. Normal database lock acquisition can take the existing busy timeout.

## Fetching and database work

Page results carry status, final URL, HTML, and challenge state explicitly.
A per-scan single-flight cache allows price, grade, description, image/seller
extraction and liveness checks to reuse a page. Default TTLs are 90 seconds for
listings, one hour for archives, and three seconds for failures/challenges.
A host challenge creates a three-second cooldown. Cached bodies use a 24 MB
LRU limit; caches die with the scan. Existing VCoins/archive pacing is retained,
with shared 150 ms minimum host request-start spacing within a scan.

Cheap eligibility rejection and canonical deduplication precede price retrieval.
Banknote holdings are loaded once and grouped by folded country, using the
existing matching rules. FX misses use a separate short cache-write transaction,
with per-scan caching of unsuccessful lookups too. Model selection is also resolved once per scan, rather than once per theme. Source/processing workers own
and close their database connections. No scan writer is held over listing or
archive requests.

## Measurements and validation

`market_scans.progress` persists source progress and final metrics. Structured
`market scan metrics` logs include attempts, discovery/model/HTTP seconds,
requested budgets, reported input/output tokens, page requests, cache hits,
time to first candidate, raw/retained/published counts, duplicates, liveness rejections and drop reasons. Successful
catalogue sources include their source summary. `revision` drives UI updates.

Historical production baselines were 12m30s for the latest coin scan and 17m51s
for banknotes. The coin catalogue had finished after 1m50s and supplied all 12
surviving candidates, but the old pipeline waited for all themes. This motivates
progressive delivery; it is not a measured production speedup of this revision.

`test_market_runtime.py` exercises early delivery, delayed retries, deadlines,
request budgets, single-flight caching, cache expiry and URL identity.
`test_market_progressive.py` exercises live persistence, preserved decisions,
stale generations, partial scans, FX concurrency, preloaded holdings, cheap
rejection, tool-free repair and metadata-only archives. Both, plus the formerly
omitted interrupted-scan suite, are in `tests/run_all.py`.

Use controlled sources for regression and browser tests. Do not trigger a full
paid production scan merely to validate code. After an authorized deployment,
use naturally requested scans to compare first-candidate time, final duration,
source yield, retries, and candidate quality before changing budgets further.


## Personal eBay sources and collection warnings (2026-10-11)

Every Banknotes Market Scan requests a fresh read of the existing signed-in eBay
browser through Today's separate discovery reader. It includes Watched cards and
only Sponsored cards actually observed in “Similar to what you've watched.” This
is separate from the Purchases shipment bridge: no watchlist, account, order,
purchase or collection ownership changes are performed by the discovery reader.

The request uses the existing `STUFFAPP_TODAY_TOKEN` configuration on **web only**.
`POST /banknotes/market/ebay-feed/request` uses the same bridge token to request a fresh read-only snapshot without a paid scan; it reuses any pending request.
`GET /banknotes/market/ebay-feed` claims a queued request; `POST` to the same route
accepts its bounded snapshot. Gerri cannot expose the endpoint or request this
source. Requests expire after three minutes; the scan waits at most 110 seconds.
Snapshots must match the linked buyer and contain fresh, exact eBay item IDs.
Cards are deduplicated by item ID across eBay regions and tracking URLs, retaining
both source labels when the same item is watched and sponsored. Partial pages,
missing sign-in, unavailable recommendation modules and blocked exact listings
are reported separately instead of claimed as complete coverage.

The observed cards appear in **Your eBay watched and sponsored items**, including
cards whose exact listing is unreadable. This section shows observed prices and
source labels, an explicit availability state, and an **Open eBay to check** link.
It has no Buy/Bought controls. A card becomes a normal banknote buy candidate
only after the existing grade, collection scope and exact-listing liveness checks.
Sponsored placement never adds score or establishes quality, rarity or value.
Observed cards already present as checked candidates are not repeated.

Exact browser liveness observations expire after ten minutes; the displayed
source snapshot expires after 24 hours. Old source rows are pruned on the next
scan request. Raw pages, cookies, credentials, addresses and payment details are
not transferred. Bounded main-item listing text may accompany an exact read.
The existing scan model shapes only observed URLs; unknown fields remain unknown.

Issued-for-circulation notes only: specimens, proofs, remainders, essais, trials,
replicas, fantasies and other non-issued/non-circulating notes are excluded, as
are **NET grading designations**. This common rule applies before model shaping,
to observed watched/sponsored cards, to ordinary candidates, to old saved rows,
and at View/Buy/Bought actions. Explicit denials such as “not a specimen” do not
trigger it. An issued note graded UNC is eligible; “net price” and `.net` web
addresses are not NET grading designations. Coin rules are unchanged.

All banknote candidate sources, including existing saved scans, check Own/Ordered
holdings and show matching collection links. **A matching Pick or other catalogue
reference determines “Already in your collection.”** Serial numbers, grading
certificates and grade differences do not affect this decision (Mark, 2026-10-11).
The matcher normalizes case, spacing and catalogue aliases (Pick/P, Friedberg/Fr,
TBB/B), preserves variety suffixes and catalogue namespaces, and scopes references
by country. It reads both `pick_number` and `other_catalog`. A same eBay purchase
listing is separately labelled as a linked listing. Sold/gifted/lost holdings do
not count. Missing country or catalogue reference produces an incomplete-check
notice; denomination/year similarity alone is not a duplicate verdict, and absence
of a match is not a guarantee of novelty.

`tests/test_market_ebay_feed.py` covers authentication, Gerri isolation, request
claims/expiry, account mismatch, strict listing identity, duplicate source labels,
source availability, fresh browser proof, observed-card visibility without
purchase controls, invented model URLs, and reference-based collection warnings.

`tests/test_market_dismissal.py` verifies permanent decisions across regional URLs,
watched/sponsored/ordinary sources, concurrent publication, source and candidate
pruning, database reopen, migration, owner/tenant/CSRF guards, no unnecessary model
work, and preserved collection/Ordered/Bought history.


## eBay session recovery

Banknotes Scan/Rescan first checks the already linked eBay buyer through Today's
existing Mac bridge. A working session is reused. If sign-in or an eBay security
check is required, Today opens the fixed Watchlist URL once in the Mac's default
browser and the page waits up to ten minutes. The current adapter reads Chrome,
which is the designated Mac's default; unsupported browser sessions, wrong
accounts and unavailable Automation access remain explicit failures.

No model scan runs during this preflight. After the bound account and fresh
snapshot are confirmed, the requested scan resumes once with that same snapshot.
Refreshing the page preserves an active wait. Cancel prevents late readiness
from starting the scan; Retry creates a new terminal-request replacement;
Continue without eBay starts the scan with personalized sources explicitly
skipped. Chrome's normal saved session may sign in directly. Password, 2FA and
CAPTCHA prompts require completion in the opened tab; no credentials are read
or challenge bypass is attempted. This is a host browser connection, so the Mac
must be awake and Today online even when the scan starts on another device.

`ebay_market_sessions` is a one-to-one extension of the existing feed request,
with bounded retry/claim timestamps and an atomic consumed scan ID. Bridge token
and web-only tenant gates are unchanged. Coins use public sources rather than
this Banknotes personal feed. Regression coverage is in
`tests/test_market_ebay_session.py`; browser fixtures never execute paid models.
