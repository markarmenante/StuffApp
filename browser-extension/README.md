# StuffApp eBay Reader

This Manifest V3 extension lets an explicit StuffApp Check or order import read
eBay in the browser on the current computer. It runs in desktop Chrome or Edge
on Windows, macOS and Linux, using the eBay sign-in in that browser profile.
It does not require Today, a designated Mac, a native helper or a host token.

Install the package from StuffApp's browser setup page. Unzip it into a permanent
folder, enable Developer mode in `chrome://extensions` or `edge://extensions`,
choose **Load unpacked**, and select the folder containing `manifest.json`.
The pinned ID is `fneejjjbhjdbppmedabagldignnjpdek`; keep the public manifest key
when packaging. The key is an identifier, not an authentication credential.
This unpacked build does not update itself. After replacing its files, choose
**Reload** on the browser's extension page. Browsers without desktop Chromium
extension support need Chrome or Edge for this reader.

Only top-level `https://stuff.armenante.com` pages can request a read. A claimed
request carries its exact order, expected buyer, expiration and a temporary
token. The extension binds its results to that token and the originating tab
and document. It cannot read or complete another user's server request; the
authenticated StuffApp page submits evidence through the normal owner routes.

The extension creates its own eBay tab, uses fixed DOM readers in the isolated
world, and closes only its own tab. Installed StuffApp app windows use an
existing regular browser window, or a new one when needed. The only automated
click is the observed purchase-history next-page control. Sign-in and security
challenges are displayed for the user to complete; passwords, codes, consent
and CAPTCHA are never automated.

The evidence parsers derive from Today's `apps/today/ebay-purchases.ts` and
retain exact account/item identity, complete checkout inventory, original
gallery and unit-price checks. They exclude addresses, payment details, totals,
messages, recommendations, cookies and unrelated orders from returned evidence.
The server retains final authority for account binding, membership, seller
suppression, duplicates and import/release rules.

There are no content scripts, network fetches, native messaging or remote code.
Session storage contains only created tab IDs for cleanup after a worker restart.
Evidence and temporary tokens stay in worker memory until their bounded request
expires. A browser/worker restart cancels the read; the user can explicitly retry.
Active reads call browser APIs at most one second apart and return each polling
message immediately, following Chromium's service-worker lifecycle rules.

## Protocol version 1

Use `chrome.runtime.sendMessage(extensionId, message, callback)` from StuffApp.
All successful job responses include `ok`, `id`, `order_id` and `status`.

- `stuffapp.ebay.ping`: availability; returns `ok`, `version: 1` and extension version.
- `stuffapp.ebay.start`: `request: {id, order_id, expected_account, expires_at,
  import_checkout?}` and `token`. `expires_at` is Unix seconds, at most ten minutes
  ahead. Start returns immediately. Only one read runs at a time.
- `stuffapp.ebay.poll`: `id` and `token`; returns `reading`, `sign_in_required`,
  `challenge_required`, `complete`, `failed` or `cancelled`. A sign-in/challenge
  response includes `session: {state}`. Continue polling the same job.
- Terminal `complete`/`failed` includes `payload` in the existing purchase
  completion format: evidence, `{id, error}`, or `{id, session}`. Only the
  authenticated StuffApp page sends this payload to its server.
- `stuffapp.ebay.cancel`: `id` and `token`; clears evidence and closes the owned
  tab. A late read cannot return evidence afterward.

Wrong document/tab/token returns `forbidden`. Lost worker state returns
`reader_restarted`, requiring explicit Retry. A source tab closing or polling
stopping for 90 seconds cancels the read. Do not hold a message callback open
for the entire order read.

## Verification

```sh
node --test browser-extension/tests/reader.test.mjs
node tests/test_ebay_browser_extension.cjs
```

The second command requires the repository's `browser-tests` Playwright install
and Chromium. It runs the actual extension in a new temporary profile with all
HTTP requests intercepted. Fixtures verify complete checkout, price cents,
original galleries, wrong-account/incomplete-checkout rejection, sign-in
recovery, cancellation and a popup source window. No live account is used.

Chromium API references: [script injection](https://developer.chrome.com/docs/extensions/reference/api/scripting),
[service-worker lifetime](https://developer.chrome.com/docs/extensions/develop/concepts/service-workers/lifecycle),
[external messaging](https://developer.chrome.com/docs/extensions/develop/concepts/messaging#external-webpage).
