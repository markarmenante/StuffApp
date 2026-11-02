# Order processing review — 2026-11-02

Independent backend and frontend reviews used GPT-6 Astra and GPT-6.1 Terra,
with separate integration and regression reviews. The scope was exact-order
entry, single-note completion, multiple seller orders, item identity, paid
prices, listing captures, original photos and crops, Check, autosave, refresh,
retry, duplicate prevention, and collection release.

## Confirmed defects and corrections

| Defect | Correction and regression coverage |
| --- | --- |
| A warning-only purchase titled `Colombia One Peso Oro 1-1-1954 P380g Uncirculated Grade 66` stayed blocked because it lacked a discovery keyword. | Review recognizes one valid Pick shorthand and one positive currency denomination. Original-photo Check, metadata, crops, editing, exact price, and explicit release are covered. Automatic single-note eligibility is unchanged. |
| The first correction still depended on a finite currency vocabulary and left `Brazil 100 Cruzeiros ND(1964) P170b Uncirculated Grade 68 Top Pop (1)` blocked. | Explicit Check can inspect exact quantity-one purchases independently of the currency vocabulary. Unknown titles require a verified complete front/back pair from the current original gallery before editing or release. Server-owned identity evidence is bound to purchase, capture and original hashes. Brazil and several historical currencies have focused regressions; the full browser flow also covers Brazil's initially locked draft, Check, photos, exact price and explicit release. |
| Stalled HTTP requests could leave controls disabled indefinitely. | Requests have a 30-second deadline. An uncertain write requires reading saved status before retrying; local edits remain available and writes are never replayed automatically. |
| Editing during Check could invalidate its result without explaining the interruption. | Editing pauses while Check runs, with an explicit message; revision checks still protect concurrent clients. |
| Normal Check did not bind its result to the listing capture or receipt it read. | Publication rechecks the capture, receipt, purchase date, draft revision and work token. Changed evidence rejects the result without publishing a collection record. |
| Changed original files could remain behind displayed or accepted crops. | Original hashes are verified before and after Check and again at release, including the originals behind accepted crops. |
| Re-cropping a collection photo could make the draft's previous-photo comparison return 404, and orphan cleanup could discard that retained photo. | Recovery drafts retain their bound snapshot photos for comparison. Access remains restricted to the owner, connected purchase account, and banknote category; regression tests cover retention and access denial. |
| A second purchase row for the same order/item could evade a line-key-only check. | Check and release require exactly one current purchase identity, not merely a matching line key. |
| An older or conflicting same-second exact-order response could be skipped by purchase storage, then materialize stale quantity or identity as if the response had been accepted. | Exact-order completion checks freshness and conflicts before applying any evidence. Single- and multi-note refresh regressions verify rollback of purchases, receipts, captures and drafts. Identical same-second retries remain valid. |
| A previously stored purchase could bypass a subsequently excluded seller. | Exact-order completion rechecks seller exclusion before accepting the response. |
| Explicit `3 x ... Banknotes` listing quantities were not recognized as bundles. | Multiplicative quantities are blocked while unit-labelled image/note dimensions remain valid. Single- and multi-note tests retain bundle protection without blocking legitimate siblings. |
| The complete order-review browser suite existed but was absent from CI. | CI now runs it, along with both order JavaScript suites and the new backend consistency suite. Synthetic desktop/mobile flows cover the integrated behavior. |

## Retained behavior

- A verified checkout with exactly one known note can finish Check and open the
  normal collection editor automatically.
- Multi-note checkouts retain individual drafts and explicit collection release.
- Group delivery warnings do not prevent reviewing a clearly identified note;
  unresolved quantities, bundles, identity conflicts and duplicates remain guarded.
- Paid item amounts retain their receipt authority and currency. Shipping, tax
  and checkout totals are not substituted for a missing item price.
- Original photos remain evidence; display crops do not replace them as Check
  inputs. Manual edits and selected photos survive refresh where identity agrees.
- GET/status requests do not start processing or release notes. Release remains
  atomic and retry-safe.

## Verification

### Spain checkout follow-up: coordination and recovery

The Spain checkout exposed a failure that successful individual-note tests did
not cover: an explicit order refresh overlapped two active Checks while a third
item waited for a slot. Provider logs confirmed successful identification. The
refresh invalidated the first two work tokens, but the batch coordinator had
already visited those rows and never returned to them. Their completed fields
and crops were discarded, leaving raw gallery thumbnails and blank drafts.
The third item started after the refresh and completed normally. Running the
actual first original through the crop pipeline produced a correct full-paper
crop; changing its detector would not have fixed the lost publication.

| Failure point | Repair and regression |
| --- | --- |
| Refresh invalidates work after a coordinator has passed that item. | Rescan durable queued work and synchronize the final handoff with explicit resume. Deterministic three-item regression refreshes while the third job waits and confirms all refreshed siblings complete. |
| Waiting ordinary drafts appear saved and allow conflicting writes. | Persist queued intent before acquiring a provider slot; show waiting/checking status and reject queued edits, photo changes and release. |
| Optional crop latency discards completed identification. | Checkpoint metadata, catalogue evidence and selected originals before cropping; late/failed crops become partial results without losing those fields. Stale crops still cannot overwrite newer source facts or edits. |
| A cached automatic crop cannot be retried. | Explicit Crop photos retries automatic outputs from original files while preserving manual choices/crops and collection photographs. |
| Restart leaves preview work queued but without a worker. | Reattach durable queued preview tokens and claim queued-to-checking atomically, preventing duplicate provider work. |
| An expired local-reader session blocks a new explicit order retry. | Apply existing expiry rules before deciding whether the old reader is still active. Live sessions and successor request identity remain protected. |
| Removed gallery photos remain candidates after a listing refresh. | Classify/select only the current captured gallery; retain old originals for inspection and intentional saved-reference use. |
| Empty identification or rejected crop looks successful. | Report missing core fields and unconfirmed paper boundaries as partial results with an actionable retry message. |

The focused coordinator, lifecycle, crop-timeout and crop-retry suites exercise
these failure sequences with isolated databases and controlled provider results.
The real Spain checkout is also verified through normal review controls after
deployment. This is a set of specific recovery guarantees, not a claim that
external providers can never fail.

Run `python3 scripts/test-regressions.py`,
`node tests/test_banknote_import_review.js`, and
`node tests/test_banknote_single_order.js`, and
`node tests/test_banknote_order_uncertain.js`. CI additionally runs the full
order-review and crop-control browser suites plus the Playwright suite.
All fixtures use temporary databases and synthetic provider responses; no test
releases a real purchase into the collection.

Production verification checks the deployed commit and the reported Colombia
draft through its normal Check action. That draft remains available for the
owner's explicit release. External eBay authentication, changed page markup,
provider outages and missing source facts remain runtime dependencies; the
review does not claim exhaustive coverage of all possible provider responses.

The Brazil follow-up also identified a pre-existing recovery limitation: if a
retained original file is missing or corrupt, Check and release reject it, but
Check currently skips downloading a URL already present in the asset table.
Repeated Check cannot repair that file. This does not explain the reported
Brazil draft, whose originals load correctly, and is not resolved by the
currency-independent review correction.
