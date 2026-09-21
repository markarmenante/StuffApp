# Banknote order updates directly from eBay

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
  auto-match. Comparison links, historical references, similarity of title,
  denomination or grade cannot. One unambiguous note and one quantity-one
  order item are required; repeat listing purchases need manual review.
- Other likely banknote purchases appear in **Needs matching**. The owner
  can confirm a match or exclude it. Multi-quantity orders remain review-only.
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
