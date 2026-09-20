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

“Checked” does not always mean “verified live”: existing venue evidence rules
remain in force. Unreadable eBay listings still need explicit live evidence;
other unreadable sites retain the existing unverified state.

Coin archive enrichment runs after candidates are visible, for at most another
60 seconds within the overall scan budget. It uses cached archive queries and
metadata-only provenance results; it does not download full lot descriptions
or photographs for the market list.

## Identity and decisions

Canonical URLs remove known tracking parameters and fragments, preserve
identity parameters such as CNG `CoinID`, and recognize eBay item IDs across
regional domains. Different listings with the same title remain distinct.

Candidates reuse an existing ID when rediscovered. Transactions check the
latest scan generation before writing. Updates cannot resurrect dismissed or
ordered candidates, overwrite their record IDs, or let an old scan replace a
newer scan. Existing undecided candidates remain visible during discovery.
Only a successful, nonempty scan with no source errors supersedes old
undecided candidates. Partial, failed, or empty scans retain them.

The existing 60-day prune of dismissed/superseded candidates still applies.
An expired dismissed record can therefore appear again in a later scan.
Ordered records are not pruned by the scan.

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
