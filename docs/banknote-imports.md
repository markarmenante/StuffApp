# Banknote order review

Entering an exact eBay order on **Order review**, or pressing Check on an otherwise
blank banknote form with an order number, creates a saved review batch. It does not
create collection records. The order-only new form stays local until import; an
existing failed form is preserved.

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
A partial or old-reader response without checkout membership is rejected atomically.

All drafts are committed before automatic Check begins. At most two checks run
concurrently; each batch contains at most 25 items and each Check has a five-minute
publication lease. Check uses the existing photo-side classifier and catalogue
validator, fills blank draft fields only, and saves accepted catalogue proof.
Original source photographs are retained before the slower catalogue call, with
owner/account-bound access. They are protected from orphan cleanup. Source text is
untrusted evidence. A title without the usual banknote discovery words is retained;
ambiguous quantities and bundles stay visible but blocked from release as one note.

The review list opens each saved draft in the existing banknote detail page,
including its identification, side-by-side images, grading, purchase and reference
fields. Save draft, Check, Release to Collection and Order review use draft routes;
collection-only actions are available after release. Saved original photos can be
selected in Purchased photos. Changes use a draft revision: a stale save or late Check cannot overwrite newer edits. Check
failures persist with a retry message. Read-only status GETs never start provider
work. Unstarted checks resume after restart; an interrupted active check is shown
as retryable after its lease expires, without an automatic paid replay.
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
and `banknote_import_evidence`.
Batch/account/order and account/item-line uniqueness prevent duplicate drafts.
Collection lists, reports, totals and Market Scan coverage see no staged drafts.
No existing collection record or photo is removed by this workflow.

## Routes and runtime

- `GET /banknotes/imports/new`: new/resume order review.
- `POST /banknotes/imports`: `{order_number, refresh?:true}`; resume by default.
- `GET /banknotes/imports/<batch>` and `/status`: review HTML and read-only state.
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
