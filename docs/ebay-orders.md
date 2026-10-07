# Banknote order updates from Today

eBay shipment status comes from the signed-in **Purchases** panel in Chrome,
not email. Today opens its own background tab, reads all pages in the default
purchase-history period (maximum 40 pages), and closes only that tab. Chrome
must allow JavaScript from Apple Events and automation from Today/node. Missing
login or incomplete pagination cause no partial update. An unreadable order
is skipped, including its sibling items, without blocking other orders.
Its previous data stays unchanged. Today records skipped order/page references
and reasons in its local sync status; the receiver also reports per-order
validation and stored-identity failures. An all-skipped run is not success.
Duplicate purchase identities are held for review without blocking other orders.
The first authenticated snapshot binds the eBay username;
subsequent snapshots must match it and any configured API buyer account.
When a check skips orders, valid purchases still import and existing linked
shipment statuses update. New automatic collection matches wait for a complete
order set or manual review: a skipped order might hide a repeat purchase.

The authenticated `POST /ebay/today` bridge accepts `source: ebay_purchases`
with account, observation time and structured purchased items. Item/order IDs,
seller, title, quantity, displayed status, displayed delivery text and order date
are retained. Recommendations are never read. Delivery requires an explicit
Delivered status and the purchased item's Delivered-on date. Tracking available
and estimates do not prove shipment. Unknown/exception statuses need review.
Actual shipping dates stay unknown when the panel does not give one.

The retired eBay-email protocol returns HTTP 410. Old email-only statuses are
shown as Unverified until Purchases confirms them. Newer snapshots can correct
old email conclusions; older/replayed snapshots do not overwrite newer ones.
Manual corrections survive. **Collection ownership (`banknotes.status`), photos
and other collection fields never change.**

Today also scans one year of locally available non-eBay purchase messages across
Apple Mail, including Archive and Deleted/Trash. Explicit notices with a single
order identity appear under Other purchase messages as review-only evidence.
eBay references, estimates and ambiguous notices are excluded. Only sender,
subject, order ID, status phrase, receipt time and a message hash leave the Mac;
no raw bodies, addresses, payments or attachments. Missing message bodies retry.
The two sources run independently every 30 minutes while Today is running, so
a closed browser does not block other sellers' notices.

Setup uses `STUFFAPP_TODAY_TOKEN` on Railway **web only**, and the same token in
`~/Library/Application Support/com.boardroom.today/stuffapp-mail.json` (0600):
`{"url":"https://web-production-cf059.up.railway.app/ebay/today","token":"<secret>"}`.
The receiver rejects requests when the token is absent or invalid. It does not
use the legacy owner/header fallback. No eBay developer account or new email
connection is required. Do not put this token on the separate `gerri` service.

`GET http://localhost:5170/api/stuffapp/status` reports progress without secrets;
`POST /api/stuffapp/sync` requests an immediate pass. StuffApp's eBay Orders page
shows the last successful pass and supports pause/resume. Deleting imported data
also pauses reception so the background sender cannot immediately recreate it.

Tests: `python tests/test_ebay_mail.py`, `python tests/test_ebay_orders.py`, and
boardroom's `apps/today/ebay-mail.test.ts`.

## Optional direct eBay API

Banknotes → **eBay Orders** connects one buyer account to this collection.
The worker checks every 30 minutes (minimum supported interval 15 minutes),
using Trading `GetOrders` with `OrderRole=Buyer`, all statuses and all pages
of a fixed 89-day creation window. The only supported Trading calls are
`GetUser` and `GetOrders`; this feature never writes to eBay.

## Production setup

1. Wait for the eBay Developers registration to be approved. Developer
   registration is separate from the normal shopping account.
2. Create/use a **Production** keyset. Save App ID as `EBAY_CLIENT_ID` and
   Cert ID as `EBAY_CLIENT_SECRET` in Railway **web**, not `gerri`. Never
   commit credentials or put them in chat, documentation or client HTML.
3. Configure marketplace account-deletion notifications (do not claim a
   no-data exemption). Set a cryptographically random 32–80 character
   alphanumeric/underscore/hyphen `EBAY_DELETION_VERIFICATION_TOKEN` and
   `EBAY_DELETION_ENDPOINT` to the exact HTTPS endpoint registered on eBay.
   The public endpoint is `/ebay/account-deletion`; a Railway-origin URL
   can be used to avoid Cloudflare Access blocking eBay's server requests.
   GET returns eBay's SHA256 challenge. POST verifies the eBay ECC signature
   against a fixed-host public-key API before any data removal. Key lookup
   uses a client-credentials application token; keys cache for one hour.
   Confirm eBay's test notification succeeds in its developer dashboard.
4. Create an **OAuth-enabled RuName**, use it as `EBAY_RUNAME`. Accepted
   and declined URLs: `https://stuff.armenante.com/banknotes/ebay/callback`.
   A standalone data-use page is available at `/ebay/privacy` (use the
   public origin if required by eBay). Scope is the traditional API base
   scope `https://api.ebay.com/oauth/api_scope`; this scope is broader than
   this code's read-only allowlist, not an eBay-enforced read-only scope.
5. Set `EBAY_SYNC_WORKER=1` on web only and deploy. Optional interval:
   `EBAY_SYNC_INTERVAL_SECONDS=1800`. Without keys and an authorized buyer,
   the worker does nothing and the UI says setup is incomplete.
6. Owner opens **Connect eBay**, signs into the actual purchasing account
   and grants consent on eBay. This stores encrypted access/refresh tokens,
   starts the first check and enables periodic checks. Developer passwords
   and normal eBay passwords are never stored by StuffApp.
7. Verify one live order, its exact listing match, seller, quantity and
   actual shipping evidence. Refresh the dashboard for the first result.
   Check recent sync history; do not claim live validation from fixtures.

OAuth states expire after ten minutes and are bound to the initiating
owner/browser. State-changing owner routes require session CSRF tokens.
Existing application owner/category authorization is retained. The known
public-origin/trusted-header limitation documented in AGENTS.md is not
resolved by this feature; lock down the origin before expanding access.

## Evidence and matching rules

- Exact item IDs from a banknote's purchase-source `Listing:` link, a
  `Market Scan YYYY-MM-DD:` reference, or its filed market candidate can
  auto-match. Comparison links and historical references cannot. One unambiguous note and one quantity-one
  order item are required; repeat listing purchases need manual review.
- Without a purchase link, country + exact Pick/catalog number + denomination
  identify candidates. Explicitly different varieties, grades, graders, issue
  years or serial numbers reject a match. Missing variety letters require
  matching grade plus year, seller or purchase date. Without a catalog number,
  a certificate/serial identity or country, denomination, grade, year, seller
  and purchase date must agree. Purchase dates more than 14 days apart are held.
- Automatic identity matches must be unique in both directions, considering
  Own notes as well as Ordered notes. Existing links, exclusions, overrides,
  multi-quantity orders and repeat purchases remain protected. The matching
  basis is stored on the link and in the shipping audit history. No banknote
  fields are written. The Today import also reconciles previously saved orders;
  **Match recovered orders** runs the same reconciliation immediately.
- Other likely banknote purchases appear in **Needs matching**. The owner
  sees candidate banknotes with the matching fields and can confirm or exclude
  a match. Multi-quantity orders remain review-only.
- `ShippedTime` proves Shipped. `ActualDeliveryTime` for every package
  proves Delivered. Tracking creation and delivery estimates do not.
  Combined-order dates are not applied to unrelated line items.
- Missing/older evidence cannot move a status backwards. Cancellation,
  refund or incomplete payment flags hold advances for review.
- A manual status override persists until Automatic is restored. Every
  status change has evidence/recorded times and its source.
- Shipping is normalized separately from collection ownership status, so
  shipping updates do not remove notes from Own/Ordered collection reports.
  Photos, descriptions, purchase prices, grading and ownership are untouched.
- Orders outside eBay's recent-history window cannot be refreshed by this
  integration; previously observed history stays visible with last-seen time.

All pages must arrive successfully before any order changes are committed.
Network errors retain last-good data. A process/file lock prevents duplicate
workers. Pausing, disconnecting or deleting data invalidates an in-flight
check before it can commit. Token rejection pauses automatic checks until
the owner reconnects. The UI never treats an error as an empty order list.

## Storage and deletion

Only relevant order identifiers, titles, seller identifiers, shipment dates,
tracking and audit history are retained; addresses/payment details/raw API
responses are discarded. Tokens use Fernet encryption, with either
`EBAY_TOKEN_ENCRYPTION_KEY` or an automatically generated 0600 file at
`$DATA_DIR/.ebay-token-key`. Preserve that key with the deployment volume;
restoring an encrypted DB without its key requires reauthorization.

Disconnect deletes tokens, retaining shipping history. **Delete eBay data**
also erases imported order data, matches and history. Both leave owner-entered
banknotes and photos alone. Signed account-deletion notifications erase the
connected buyer's integration data, or only a deleted seller's integration
data. Non-reversible suppression fingerprints prevent re-import. Backup
restoration must replay deletion requests/suppressions before reconnecting;
operators must apply the same deletion requirements to retained backups.

## Verification

`python tests/test_ebay_orders.py` exercises buyer-only API shape, pagination,
partial failure rollback, true delivery evidence, exact matching, duplicate
and quantity ambiguity, overrides, revocation, OAuth browser binding/replay,
CSRF, encrypted tokens and signed notification rejection/deletion.

Official protocol references:

- https://developer.ebay.com/devzone/xml/docs/reference/ebay/GetOrders.html
- https://developer.ebay.com/develop/guides/sell/authorization
- https://developer.ebay.com/develop/guides/sell/marketplace-user-account-deletion
- https://github.com/eBay/event-notification-nodejs-sdk
