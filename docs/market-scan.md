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

Opening Market Scan from a collection keeps that list's Status selection, coin
Home/Era selections, search and other collection query settings. Collection
returns to the same selection after Earlier candidates, Current scan, refresh
or Rescan. This return context travels in that page's URL, so separate tabs and
categories keep their own selections. A directly opened Market Scan without
collection context returns to the ordinary collection default. No shared browser
storage or saved collection data is changed.

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

Banknote discovery covers colonial and dependent administrations worldwide,
including Japanese issues, protectorates, mandates, trust territories,
condominiums, leased territories, client states and military occupations.
British and continental examples are illustrative. Dedicated Japanese and
worldwide themes seek unlisted administrations; the historical 35-entry want-list
is a priority aid, not a coverage boundary. Broad searches still seek missing
issuers when want-list themes are present. All supported administrations have
equal ranking priority; coins retain their ancient-Greek scope.

New territories and occupation issues need issue-specific administration evidence
under [market-validation.md](market-validation.md). Labels distinguish the actual
relationship. The two additional themes use the existing global time, token,
tool and concurrency caps; a scan is bounded discovery, not a guarantee to inspect
every territory or listing. Collection and Ordered records are unchanged.

Both Market Scan pages gather similar listings into visible sections. Banknotes
group first by explicit issuer and canonical country, then by complete series,
US note type and catalogue reference. Different issuer names, series suffixes
and reference varieties stay distinct. Grades and serials do not split the same
reference. Explicit US Treasury spelling aliases share one issuer; the legacy
“United States (Legal Tender Note)” label does so only for an identified United
States Note. National banks and Federal Reserve banks stay separate, and a
country name alone never supplies an issuer. Within an issuer, notes follow
series year and numeric denomination;
issuer blocks retain first appearance in the ranked results. Coins retain their
existing region grouping and ranking.

Scanned, watched and sponsored banknotes now share those issuer sections. Source
labels, availability warnings, duplicate checks and exact Buy/Bought/Delete
targets remain with each listing. Observed cards use only explicitly named
series and references; an issuer is never guessed from a title. Missing issuer
information appears as “Unknown issuer”. Current and Earlier views use the same
grouping, and deleting a card updates both section counts. Display grouping
does not rewrite stored payloads, ranks or the ordinary collection list.

Banknotes show `Price: …` and `Est. value: …`, or exactly `No estimate`. The
asking/current price remains separate from a researched market-value range.
New research can provide structured `valuation` data with currency, range,
research date, grade comparison and dated sold/price-guide evidence. Sources
are available by expanding the terse estimate. The rendering path makes no
network calls and never converts legacy free-text `fair` into a numeric value.
Old cards without supported data simply show `No estimate`; their saved text
is preserved. A watched-card shaping call has no research capability and cannot
create an estimate. Invalid, unsupported or stale estimates are omitted by
`market_valuation.py`. Tests: `test_market_grouping.py`,
`test_market_valuation.py` and the browser interaction checks.

For an explicit fixed asking price in the estimate's currency, the small marker
compares that price with the midpoint of the supported range: green at or below
the midpoint, yellow above it through exactly 30% above, and red beyond 30%.
For an $80–$120 range, the benchmark is $100: $100 is green, $130 is yellow,
and $130.01 is red. This comparison uses exact amounts before display rounding.
The marker's accessible label and expanded explanation identify the midpoint
benchmark. Opening it expands the evidence without opening the seller listing.
An unknown price, unknown sale type, auction/bid amount, currency mismatch or
missing estimate has no marker; no exchange rate or fixed-price status is
inferred for this comparison.

Comparable research starts with the exact catalogue variety and offered grade,
including references and grades clearly stated in the listing title when
structured fields are blank or the live page is blocked. It then tries adjacent
grades of the same variety before closely related date/variety evidence.
Verified proxies require a short adjustment explanation and are always marked
low confidence in expanded evidence. Actual realized/guide amounts, source
dates and currency checks remain required; active asking prices are not sales.
The routine availability label is hidden on observed cards; ended-listing
warnings and purchase-time availability checks remain active.

`Estimate prices` researches the current banknote candidates and observed
watched/sponsored listings that lack supported estimates. It starts or joins one
owner-authorized background job through `POST /banknotes/market/estimates`;
`GET /banknotes/market/estimates/status` only reads progress. Estimate rendering
and status reads never schedule research. Each job covers at most 12 uncached exact listings, with two
workers, a 300-second deadline and up to six searches per listing. If more
listings remain, the button becomes `Estimate remaining`. A requested banknote
scan can also enqueue bounded enrichment after its results are saved.

Research is cached within that service's collection database and overlaid for
display without rewriting source cards, prices, ranks or collection records.
Changed note identity invalidates reuse; deleted or no-longer-eligible targets
cannot publish late. Unsupported research stays `No estimate` and receives a
retry cooldown. The UI polls status and replaces only results, preserving open
evidence and deferring replacement while a location choice or purchase/delete
request is active. Failed starts remain retryable. Controlled tests intercept
research and purchase actions rather than running a paid scan.

Fresh signed-in exact-listing reads can supply price-comparison context for an
already saved estimate without another model call. Today puts visible, enabled
purchase controls on the dedicated second line of its bounded evidence;
descriptions and recommendation cards cannot supply that proof. A bid control
takes precedence over a fixed-price control. The authenticated feed POST may
retain this context in an existing positive estimate cache entry, keyed to the
same listing and note identity and bound to the observed price. Its own observed
timestamp expires after 24 hours; refreshing it does not extend the valuation's
expiry or rewrite the source card. Display GETs only read this context.

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

Coin and banknote current candidates and observed watched/sponsored cards have **Delete**.
It permanently suppresses that exact listing from all recommendation sources,
preserving collection and Ordered records. New explicit Delete actions also
request removal of that exact eBay item from the linked account's watchlist.
The browser checks actual watch state even for researched or sponsored cards;
it never assumes those cards are watched. Non-eBay deletion only suppresses the
listing in StuffApp. Another
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
record. Startup and pre-prune migration preserve existing retained market
dismissals, including legacy payload-only rows; dismissals already pruned before
this upgrade cannot be recovered. Earlier candidates remain explicitly labelled
Dismissed with historical View and Bought recovery, without recommendation Buy
or Delete controls. Filing a purchase through Bought does not erase suppression.
Ordered records are not pruned. Coin dismissal now uses the same permanent
category-and-listing suppression as banknotes, so a later scan cannot restore it.

`POST /<category>/market/<candidate_id>/dismiss` saves the candidate's listing
identity. `POST /banknotes/market/ebay-feed/<ebay_item_id>/dismiss` resolves an
account-bound observed card instead of accepting an arbitrary URL; a known prior
deletion remains idempotent after its snapshot expires. Both require the existing
app-owner authorization and cross-site write guard, and return the canonical URL
for removal of duplicate visible occurrences. These are app actions, not
bridge-token endpoints. The personal-card action is available only on web.

Suppression and the new intent are committed atomically. `ebay_unwatch_commands`
deduplicates by linked account and exact item ID; initialization, existing
dismissals, ordinary reads and scans never create commands. Commands expire in
ten minutes. Today's existing web-only token claims one through
`GET /banknotes/market/ebay-unwatch` and posts a bounded result to the same route.
The command carries account, exact item, expiry and an opaque claim token. A
120-second abandoned claim can only be reclaimed in `verify_only` mode, so a
restart or lost acknowledgment never repeats an uncertain click. Success requires
fresh exact-item/account evidence of `not_watching`; queueing, sign-in challenges,
expired requests and ambiguous results never count as confirmed removal.

The owner-only `GET /banknotes/market/ebay-unwatch/status` is read-only and shared
by both Market Scan categories. The page
shows pending, verified or needs-attention text after removing the recommendation,
and restores recent status on reload. A terminal failure leaves the listing
suppressed and directs the owner to check eBay; it does not launch a retry or undo
suppression. No purchase, bid, feedback or other eBay action is authorized by this
queue. Verification uses synthetic writes and intercepted browser requests.
Duplicate Delete requests return the same command/result, including terminal
failures; they do not restart a completed or uncertain command. A failed removal
therefore currently needs an exact-listing check on eBay, rather than an implicit
new watchlist action from a stale page or network retry.

External removal additionally requires a cryptographically verified Cloudflare
Access application JWT from `Cf-Access-Jwt-Assertion`. The web deployment pins
`STUFFAPP_CF_ACCESS_TEAM_DOMAIN` to its existing HTTPS Cloudflare team issuer and
`STUFFAPP_CF_ACCESS_AUD` to this application's audience. PyJWT checks the RS256
signature against that team's fixed `/cdn-cgi/access/certs` endpoint, issuer,
audience, time claims, application type, subject, and signed email against both
the configured owner and resolved app identity. Keys have a five-minute cache;
retrieval has a three-second timeout, bounded body and no redirects. Missing
configuration/proof or failed verification suppresses locally but creates no
unwatch command. Raw email headers, dev-user settings, owner fallback and bridge
tokens cannot substitute for signed owner proof. No JWT or decoded identity is
logged or returned. Status exposes only `unwatch_authorized` for read-only checks.
The Gerri instance remains disabled and does not need these variables.
New removal intents also require an exact same-origin HTTPS `Origin` with no
conflicting Fetch Metadata, or `Sec-Fetch-Site: same-origin` when Origin is absent.
Missing proof, `Origin: null`, malformed origins and cross-site metadata cannot
queue an external write, even with an authenticated owner session. Read-only
capability checks validate the signed identity without requiring POST metadata.

Before dispatch, Today may focus its own sign-in/security-check tab once and
wait read-only within the current 120-second claim and ten-minute request expiry.
It resumes the same intent only after verifying the exact linked account. If
that wait ends, the UI reports unconfirmed removal and offers the exact listing
for manual checking. Expired/uncertain actions are never clicked again.

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
source labels, an explicit availability state, and the same **View listing**, **Buy**,
**Bought** and **Delete** actions as scan candidates. View listing opens the exact
observed item. Buy rechecks availability and collects Location before filing an
Ordered record and opening the seller's ordering page. Bought files a purchase
already made without opening the seller. Owner-selected cards do not need a paid
scan; missing catalogue or grade details remain blank, and issued-note/NET
exclusions still apply. A card becomes a normal ranked scan candidate only after
the existing grade, collection scope and exact-listing liveness checks.
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
by country. It reads both `pick_number` and `other_catalog`. Criswell state-note
references also require one consistent issuing state: for example, `SCCR7`,
`Fr. SCCR7`, `Cr-SC-7`, and `Cr.7` with explicit South Carolina context identify
the same state issue, independently of federal `Fr.7` or another state's `Cr.7`.
Observed listing titles can supply this explicit reference and state at display
time, including already cached cards and scan candidates. Missing or conflicting
state/variety evidence remains incomplete; no collection record or feed snapshot
is rewritten. An explicit non-US country is never overridden by US state text. A same eBay purchase
listing is separately labelled as a linked listing. Sold/gifted/lost holdings do
not count. Missing country or catalogue reference produces an incomplete-check
notice; denomination/year similarity alone is not a duplicate verdict, and absence
of a match is not a guarantee of novelty.

`tests/test_market_ebay_feed.py` covers authentication, Gerri isolation, request
claims/expiry, account mismatch, strict listing identity, duplicate source labels,
source availability, fresh browser proof, observed-card visibility and
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


## Buying personal cards and capturing the order number

Personal-card actions resolve a recent observation for the currently linked buyer,
using `/banknotes/market/ebay-feed/<item_id>/buy`. They accept the same Location and
Bought flag as ordinary candidates. The shared purchase transaction deduplicates
by exact canonical listing, including concurrent clicks and a card that also
appears in scan results. Photo and network reads precede the short write lock.
A completed account-bound purchase remains retryable after its source snapshot
expires. Bought does not erase a prior Delete decision.

For an exact, currently live US eBay listing with a Buy It Now control, Buy opens
eBay's verified `/bin/ctb` ordering page. Auction-only listings and other sellers
retain their exact listing/ordering page; contact-only dealers do not acquire a
checkout capability. The handoff never submits payment. StuffApp's Ordered status
records the initiated purchase and does not mean payment or physical ownership
has been confirmed.

An explicit banknote Buy/Bought also queues a check for the exact eBay item through
Today's existing authenticated Purchases connection. The Mac searches the source
title and verifies the exact item ID across the complete search result; title
similarity alone cannot match a purchase. This avoids unrelated unreadable older
orders blocking the new purchase. The existing buyer binding, browser queue and
web-only tenant apply. No new credential or payment permissions are introduced.

The explicit Buy/Bought action also authorizes the existing session-recovery flow.
If Chrome is inactive or eBay needs sign-in or verification, the first capture
attempt may open the fixed eBay Purchases page once on the designated Mac. Later
attempts reuse that session and preserve its sign-in tab instead of opening more
tabs. Passwords, verification codes, CAPTCHA and provider consent remain the
owner's actions; the reader never enters credentials or submits payment. Capture
resumes automatically when the existing session is ready, within the original
24-hour expiry. An offline or powered-off Mac still has to come online.

Only a unique, quantity-one, paid purchase supplies the order number. Ambiguous
orders, repeat purchases, unreadable results, account changes and conflicting
record edits are held for review. Existing entered order numbers, including an
intentional clear, are preserved. The detail page displays capture status and
fills an untouched blank order field after confirmation without refreshing the
page. Pending checks retry at most once per minute for up to 24 hours; Today and
the designated Mac must be online with the linked eBay session available.

Tests: `test_market_ebay_buy.py`, `test_market_checkout.py`,
`test_market_purchase_capture.py`, `test_market_personal_buy_browser.cjs`, and
`test_market_purchase_capture_browser.cjs`. Browser tests use isolated fixtures
and never submit a purchase.
