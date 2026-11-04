# Check eBay orders on this computer

The StuffApp eBay browser connection lets an explicit order import or banknote
Check read the signed-in eBay account on the computer being used. It supports
desktop Chrome and Edge on macOS, Windows and Linux. It does not require the
Today Mac to be awake for those reads.

Open **Use this computer** in Order review, or visit `/ebay/browser/setup` while
signed in to StuffApp as the collection owner. Download and unzip the connection,
then load its `browser-extension` folder from Chrome's or Edge's extensions page
using **Developer mode → Load unpacked**. Keep the folder on that computer.
Refresh StuffApp, check the connection, and sign in to the connected eBay buyer
in the same browser profile. Install once on each computer/profile being used.
This is an unpacked extension; updates require downloading the current folder
and reloading it in the browser's extensions page.

When the connection is available, new explicit imports and Checks select this
browser before the request enters the queue. The existing Today reader continues
to handle requests created without the connection. A request cannot be claimed
by both readers. Retrying a failed order with the connection installed creates
a browser request. Keep the StuffApp page open while the read finishes; after a
lost page or restarted browser, explicitly retry instead of replaying evidence.

The connection opens its own eBay tabs and reads the exact requested order. It
does not make purchases, place bids, alter the watchlist, enter passwords or
complete verification. Required eBay sign-in or verification is completed by
the person in the opened tab. Existing tabs and browser cookies are preserved.

Each browser claim is authenticated by the existing StuffApp owner session and
same-origin JSON request. Its short-lived token is bound to one request, account
and banknote/import; only its hash is stored on the server. The extension accepts
messages only from `https://stuff.armenante.com`, binds jobs to the requesting
tab, and has access only to the required eBay hosts. It contains no Today token,
OAuth token, cookie-export mechanism or native application permissions.

Returned evidence passes the existing server account, exact-order, complete
checkout, quantity, receipt-price and original-gallery validation. Multi-item
orders retain review and explicit Release. Verified single-note imports retain
their existing Check-and-open behavior. No historical drafts are released by
opening a page. Mark's and Gerri's collections remain separate; this extension
is configured only for Mark's StuffApp site.

Market Scan, background purchase updates, native Today data and watchlist actions
retain their existing Today connection. Safari, Firefox and mobile browsers do
not run this desktop Chrome/Edge extension.
