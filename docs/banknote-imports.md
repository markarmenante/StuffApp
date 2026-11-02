# Banknote order review

The **++** button beside **+** in the Banknotes collection opens an eBay order-number
window. Enter the order and press Enter or **Process order** to start the same exact-order
import below. The window shows progress, prevents duplicate submissions and retains the
entered number if the request fails. Cancel or Escape closes it before processing.

Entering an exact eBay order on **Order review**, or pressing Check on an otherwise
blank banknote form with an order number, reads the complete checkout first.
When it contains exactly one verified banknote, Check runs and the ordinary
collection detail editor opens directly. There is no separate review or Release
step for that single note. Missing catalogue fields, an unavailable paid amount,
or uncertain photo sides remain blank with current warnings in that editor;
provider failures remain retryable through its normal Check control.

Multiple-item orders keep the saved draft review and explicit Release workflow.
Unknown item types, possible bundles, ambiguous quantities, account/membership
failures, changed source facts and conflicting existing records also stay saved
for review. One pending item from a multi-item checkout is still a multi-item
order. The order-only form stays local and prevents new edits/autosave while
processing; an existing failed form is preserved.

Single-note completion is enabled by an explicit import/resume POST, including
clicking a saved order or re-entering its number. Existing checked single drafts
can finish without repeating Check. Historical drafts default to review and are
never published by a GET or an unrelated startup sweep. A previously authorized
single import can resume completion after restart. Publication uses the same
atomic source/account/revision/duplicate guards and exact purchase/photo copying
as Release; concurrent finishers create or complete one record once. Normal detail
opens with Ordered status, never automatically Owned. Successful Check timestamps
and resolved same-source failure cleanup carry through; unresolved enrichment
warnings remain visible until a newer successful normal Check.

An order with no imported items says that no items have been saved for review yet.
Retrieval, sign-in, verification and failure messages remain visible, with Retry
order after failure. A zero pending count means review is complete only when the
batch actually contains items and every item has been released.

A fresh authenticated read is required. An eBay checkout can contain several seller
orders: the reader verifies each seller order's details link has the same observed
`purchaseOrderId`, and the returned item membership must match those verified links
exactly. Every draft retains its own actual seller order, exact item ID, seller,
paid unit amount and original listing. Shipping, tax, order totals and listing
asking prices cannot supply an item price. A missing receipt leaves the price blank.
A receipt with valid exact-item evidence can supply its amount despite eBay's
**Multiple items; shipment or delivery not confirmed** group-status warning.
Each receipt is matched to its exact item, including distinct items sharing one
seller order; cents are preserved and no group total is divided between items.
Every other status review warning still withholds the amount. The complete
checkout is saved for review without accepting delivery or ownership. Wrong
receipt identity, quantity, currency, freshness or unit-price evidence still
rejects the response atomically. Ambiguous or previously excluded purchases remain
protected. Saved receipt lookup rechecks the current purchase and refuses an
older amount after a refund, exclusion, changed source identity or ambiguous
purchase, even when given an earlier source snapshot. Existing draft values
remain retained for review.
A partial or old-reader response without checkout membership is rejected atomically.

eBay's **Multiple items; shipment or delivery not confirmed** group-status warning
does not prevent inspecting an exact single-item purchase. With fresh
exact listing evidence, verified account/membership and no quantity, bundle,
duplicate or collection-link conflict, **Check** may read the full original photos
and fill blank note-identification, grading and supported catalogue fields. It may
also prepare classified front/back display images, reusing an accepted preview
crop when the original hash and current capture agree. Check retains the purchase
warning and does not release the item. Model output cannot supply image paths or
modify purchase/status/owner fields. Other purchase warnings, known non-note
objects, explicit conflicting catalogue/denomination identities and bundles
retain their existing restrictions.

An exact single-note item held only by that group-status warning remains editable
in review. **Save draft**, retained-photo selection and **Adjust crop** work even
after the listing capture expires; a new **Check** still needs fresh evidence.
Review also recognizes a title with one unambiguous P/PK catalogue reference and
one positive written currency denomination, such as a Peso face value, even when
the seller omitted “banknote”, “PMG” or the full word “Pick”. An unrecognized
currency word or incomplete title does not disable **Check**. Such items remain
locked for editing and release until Check verifies two distinct, complete,
high-confidence opposite sides of the same banknote from the current listing.
Another complete unrelated or uncertain note view invalidates this proof;
holder-only label photos do not. Missing, mixed or uncertain photos retain their
originals and a retryable explanation without publishing fields or selected
images. Known non-note objects, malformed/ranged or repeated references,
nonpositive face values, multiple known denominations and bundle blockers remain
excluded from inspection. Neither this inspection path nor the title fallback
changes automatic single-note completion rules.

Photo identity is server-owned evidence stored separately from editable fields.
It binds the exact source digest, listing content and every inspected original's
URL, filename and hash, including the verified front/back pair. Editing and
release require that evidence still match the source, capture and saved assets;
publication and release additionally verify the original file bytes. Listing
age alone, or a timestamp-only refresh, does not revoke accepted identity. A
changed capture or source does, and a new Check still requires fresh evidence.
Price, seller, purchase date and status stay source-controlled while the warning
persists. Refreshing the complete order fills a blank draft price from the newly
authenticated exact-item receipt while preserving occupied draft or recovery
values, saved metadata and photos. Metadata-only Check cannot invent a price.
**Release to Collection** is an explicit owner action and creates an
**Ordered** record, never an automatic ownership confirmation. It preserves the
source warning in the review history and uses only the existing exact paid-amount
authority, leaving an unavailable price blank. These items never complete through
the automatic single-note path. Every manual write repeats the account, complete
checkout membership, exact source, quantity, exclusion, bundle, duplicate and
collection-link checks under the normal revision guard. Other blocked items
remain read-only.

Eligible detail checks queue durably on explicit import/resume, or start through
the item's Check control. Reading a saved order never schedules work. Every write
rechecks the draft revision/token, exact source, full listing-capture fingerprint
and original-photo hashes. Check also binds the exact receipt evidence, so a
corrected amount during provider work cannot publish an older result. A changed
purchase date or newly ambiguous source identity requires a fresh order review;
release rechecks retained original hashes, including originals behind accepted
crops. If side identification is uncertain, unassigned full
listing photos still supply metadata evidence but do not become selected image
slots. Accepted crops continue resolving to their full originals on later Check.
Selecting clear front/back display photos does not discard other useful holder
evidence. Check also receives bounded, hash-verified original gallery photos that
the existing classifier positively identifies as complete views of the same note.
Only photos in the current exact listing capture qualify; unrelated, uncertain,
partial, conflicting or malformed classifications supply no extra references.
These references can expose certification details missing from bare-note views
without replacing the selected display photos or existing metadata.

Both ordinary and purchase-warning drafts persist `queued` before waiting for a
provider slot. The coordinator rescans that queue after each pass: a refresh
that invalidates an in-flight result cannot strand earlier siblings. Its final
queue check and coordinator handoff share the resume lock. Queued/running work
is shown as waiting/checking and blocks edits or release; an untouched idle item
is labelled **Not checked**. Failed or partial results remain visible even when
a purchase warning also exists. Explicit order retry expires abandoned reader
sessions using their existing lease rules, without replacing a live session.

All source drafts are committed before automatic Check begins. Single-note drafts
are the durable processing record; successful or partially enriched known notes
finish automatically under the rules above. Multiple-item drafts remain isolated
until explicit Release. At most two checks run
concurrently; each batch contains at most 25 items. Identification has a five-minute
publication lease. Check uses the existing photo-side classifier and catalogue
validator, fills blank draft fields only, and saves accepted catalogue proof.
Verified metadata and selected originals are checkpointed before optional display
cropping. The checkpoint advances the draft revision and renews the active crop
lease; crop publication repeats the source, token, revision and hash checks. A
slow, failed or stale crop leaves completed identification and originals saved
with a partial-result message. Geometry/validator provider calls have explicit
30-second timeouts without SDK retries. Missing core identification is reported
as partial rather than successful empty enrichment.
The optional crop stage has a 60-second deadline per photograph and is displayed
as "Cropping photos" after details are saved. At most two crop computations can
remain outstanding; timed-out computations keep their capacity until they exit
and cannot publish late results. A timeout leaves the originals available for
manual cropping or an explicit retry.
Small notes in oversized holders can use a candidate measured directly from
the original photograph's paper quad. Candidates occupying 5–15% of the frame
still require the catalog ratio, all hard crop metrics, and an affirmative
vision verdict comparing the candidate with the original paper edges, including
naturally narrow margins. Cleanup-derived crops retain the normal 15% minimum; missing
validation cannot approve a small candidate.
Original source photographs are retained before the slower catalogue call, with
owner/account-bound access. They are protected from orphan cleanup. Source text is
untrusted evidence. A title without the usual banknote discovery words is retained;
ambiguous quantities and bundles stay visible but blocked from release as one note.

Before original photographs have been retained, review cards and Purchased photos
can show previews from the fresh, verified exact-listing capture. This includes
items blocked by a purchase-status warning. Eligible single-note detail checks
prepare their normal display photographs. For other blocked items, import/resume
and explicit refresh prepare cropped previews of the first two listing photos,
using the normal arrival crop pipeline. The **Crop photos** button on Order review
retries these previews and automatic crops on editable siblings from their
retained originals without rereading the eBay order. Manual crops, manual photo
choices and occupied collection photos stay unchanged. The retry request is
durable; ordinary Check continues preserving previously accepted automatic crops.
Blocked previews retain their full originals separately; opening a preview shows
that original and its grading label. Preview files remain inspection-only, never
selected front/back photos, and cannot supply a purchase price. The separate
exact-item eligibility rule above determines whether Check, editing and explicit
Release are available.
Viewing previews never fetches images
on the server, runs Check, accepts a price or changes a draft. Expired captures,
changed source identity, account or membership, excluded purchases and ambiguous
item identities cannot supply previews. Retained and preserved photos take priority.
Preview jobs share the two provider slots with Check, retain originals before model
work, and verify the source, capture and draft revision again before publishing a
crop. Failed or uncertain attempts retain originals and require an explicit retry;
GETs never queue work. Preview files are served only by their owner/account-bound
route, kept out of editable assets, and protected from orphan cleanup.

After Check reads the original holder photographs, newly selected front/back
images pass through the same crop pipeline used for uploads. An explicit Check
also retries a draft side still using an untouched original after an inconclusive
arrival crop. Accepted crops, manually selected photos and collection photographs
are preserved. Accepted display crops retain their original, corner transform and
file hash in the draft; release copies the display crop and preserves the source
for future Check and Adjust crop. Detection runs outside the draft
write lock, and a changed revision discards its output without replacing edits.
An engraving-only cleanup after a measured paper crop cannot remove a large
side or substantially change that sheet's proportions, even without catalogue
dimensions. Pale or low-contrast printing must remain inside the displayed note.

The review list opens each saved draft in the existing banknote detail page,
including its identification, side-by-side images, grading, purchase and reference
fields. Save draft, Check, Release to Collection and Order review use draft routes;
collection-only actions are available after release. Saved original photos can be
selected in Purchased photos. Changes use a draft revision: a stale save or late Check cannot overwrite newer edits. Check
failures persist with a retry message. Read-only status GETs never start provider
work. At startup the single Gunicorn worker requeues interrupted active checks
and preview crops, replacing their old tokens before dispatch. Saved details,
originals, and manual selections are preserved; invalid or changed sources fail
clearly. Completed, partial, and failed jobs are not automatically retried.
Outside worker replacement, an expired check is shown as retryable. Review cards
use selected photos when present, without filling an absent side with an
unselected gallery image.
When automatic side identification is uncertain, **Use as front** and **Use as back**
select from that draft's saved originals. The choice is revision guarded, cannot
use another draft's asset or the same image for both sides, and cannot replace an
occupied photo in an existing collection record. Both explicit selections clear
only resolved side-identification warnings; purchase and provider warnings remain.

Each selected front and back photo has **Adjust crop** on the review detail page.
It uses the same four-corner editor as the collection. **Save crop** saves a new
draft image, retains the original photograph and records the crop transform.
Further adjustments start from that original, and Check can still read its holder
label. Cancel leaves the image unchanged. Draft revisions and image identity
protect against stale editors; cropping is unavailable during Check or after
release. Released items open directly in the ordinary collection detail page,
including its photo editor and all other normal controls. Back returns to the
order review list, including after a full-form save. Older bookmarked review
links resolve to the same collection record; they do not reopen a locked copy.
Released cards display that record's current fields and photo previews when you
return to review. The saved import snapshot and verified purchase source remain
retained separately.

An explicit crop of a preserved unfinished-record photo remains in the draft
until Release to Collection. Release applies only that reviewed photo change,
while retaining other occupied collection fields and the original image. A
concurrent collection change still requires review before release.

**Refresh eBay order** explicitly rereads the complete source, keeps saved fields
and photos, updates verified membership, and queues fresh checks. An item absent
from that fresh snapshot cannot be released.

Release is an atomic transaction. It revalidates the current connected account,
exact item membership, source identity, draft revision and existing item links.
It creates the collection record and exact purchase link once, preserves originals,
copies display photographs, and retains catalogue evidence. Repeated release is
idempotent. A remaining draft returns to its order review; pending drafts in another
batch return to saved orders; otherwise release returns to the collection.

A unique unfinished existing banknote with the exact seller order and exact original
listing may be completed instead of duplicated. This narrow recovery requires
blank country, denomination, Pick and other catalogue fields and no purchase link.
Its occupied fields, original photos and crops seed the draft. Release compares the
saved record snapshot and fills its remaining blanks, with a narrow exception for
an explicitly saved draft crop of that record's photo; concurrent changes stop
the release. The detail page shows which existing fields or photographs changed,
with before/current previews. **Update draft from collection** explicitly accepts
that reviewed snapshot into the draft, keeps draft-only edits and adopts the
current occupied collection values and photos. It does not run Check or release.
A second collection change requires another review. The user then explicitly
clicks Release to Collection. Other release validation failures display their
reason without locking the draft as an unrelated revision conflict. A populated
or ambiguous existing match stays blocked for review.

Storage is separate from `banknotes`: `banknote_import_batches`,
`banknote_import_items`, `banknote_import_assets`, `banknote_import_image_edits`,
`banknote_import_evidence`, `banknote_import_preview_jobs`, and
`banknote_import_photo_previews`.
Batch/account/order and account/item-line uniqueness prevent duplicate drafts.
Collection lists, reports, totals and Market Scan coverage see no staged drafts.
No existing collection record or photo is removed by this workflow.

## Routes and runtime

- `GET /banknotes/imports/new`: new/resume order review.
- `POST /banknotes/imports`: `{order_number, refresh?:true}`; resume by default and
  authorize direct completion only if the complete checkout proves one banknote.
  Responses expose `processing_single` and `completion_url`; ordinary status GETs
  only read progress. The entry page waits for a single note and opens its normal
  detail URL; multiple items open the saved review.
- `GET /banknotes/imports/<batch>` and `/status`: review HTML and read-only state.
  Item capabilities expose `can_check`, `can_edit`, `can_release` and
  `locked_fields`; a purchase warning alone does not imply a disabled editor.
- `POST /banknotes/imports/<batch>/crop-photos`: retry pending photo crops across
  the order, retaining all purchase and release restrictions.
- `GET /banknotes/imports/<batch>/items/<item>/preview/<position>`: guarded saved
  listing preview; `?original=1` shows its retained full original.
- `GET /banknotes/imports/<batch>/items/<item>`: saved draft detail.
  Once released, GET redirects to the real banknote detail page with a return
  link to this order review; draft writes remain rejected after release.
- `POST` or `PATCH` the item URL: `{revision, updates}`.
- `POST` the item URL plus `/check`: `{revision}`, asynchronous status 202.
- `POST` the item URL plus `/photos`: `{revision, field, filename}` selects
  `image_1` (front) or `image_2` (back) from a retained same-draft original.
- `POST` the item URL plus `/refresh-existing`: `{revision, existing_record_version}`
  accepts the reviewed current record into an unfinished-record draft.
- `GET` the item URL plus `/trim-quad/<field>` opens crop data for a selected
  front or back; `/trim-source/<field>` serves its original under draft access rules.
- `POST` the item URL plus `/trim-quad/<field>`: `{revision, trimmed, quad}` saves
  the adjusted crop to that draft only.
- `POST /banknotes/imports/<batch>/release`: `{items:[{id,revision}]}`.

All draft routes require the collection owner. The existing authenticated Today
purchase bridge carries only active import claims with `import_checkout:true`;
regular collection Check retains its exact-order behavior. The designated Today
Mac must be awake with the correct signed-in eBay account. Existing provider keys
and source readers are reused. `BANKNOTE_IMPORT_WORKER=0` disables automatic draft
checks for isolated tests; it does not change read-only status behavior.

Validation uses synthetic three-seller-order checkouts, exact cents against unrelated
totals, membership and account failures, repeated import/release, revision conflicts,
provider failure/retry, saved photos, blank-only partial-record recovery and accepted
catalogue evidence. No real purchase or collection release is performed by tests.
