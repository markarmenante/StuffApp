# StuffApp

> **New computer?** Start with [NEW_MACHINE_SETUP.md](NEW_MACHINE_SETUP.md) — accounts, CLIs, local dev, and deploy for all four repos.

Production StuffApp runs on Railway behind Cloudflare:

```text
https://stuff.armenante.com
```

Canonical local path:

```text
/Users/markarmenante/Developer/stuffapp
```

Actual GitHub checkout:

```text
/Users/markarmenante/GitHub/StuffApp
```

GitHub repo:

```text
markarmenante/StuffApp
```

Quick local start:

```bash
cd /Users/markarmenante/Developer/stuffapp
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
flask --app app run --port 5001
```

Railway start command:

```bash
gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 300
```

Related app:

```text
Museum of Time: /Users/markarmenante/GitHub/boardroom/apps/museum
N552YM:         /Users/markarmenante/GitHub/n552ym
Family Office: /Users/markarmenante/GitHub/family-office
```

Production switcher:

```text
Museum of Time: https://museum-of-time-peach.vercel.app
StuffApp:      https://stuff.armenante.com
N552YM:         https://n552ym.vercel.app/trips
Family Office: https://ym-familyoffice-production.up.railway.app
```

The old `stuff-app` (dashed) Next/Vercel rebuild was retired and deleted in
June 2026. This Flask app is the only StuffApp.

### Files download destination

Click **Files** to download straight into the previously selected `StuffFiles`
folder. With existing browser permission, no destination dialog is shown.
On first use the browser asks for a folder; choose an existing `StuffFiles`
folder (normally in iCloud Drive on a Mac). Selecting its parent uses or creates
a `StuffFiles` child. If permission has expired, grant access when asked; a denial
keeps the old destination and offers an explicit reconnect instead of downloading.

Use the small arrow beside **Files** (**Change Files folder**) to change the
folder explicitly. Folder selection is saved independently of downloading;
close the settings dialog to finish without starting an export. The browser
stores this choice per site/profile, not on the Railway server. The app cannot
silently choose an absolute Mac path.

Changing the destination resets both the incremental-download checkpoint and
Sweep's local upload fingerprints in the same transaction as the folder handle.
The next download to a different folder is complete; reselecting the same folder
keeps its existing checkpoint. Existing files in the former folder are untouched.
Failed file writes no longer advance the successful-download checkpoint.

Browsers without the directory API still download a zip using their own download
settings without an extra app dialog. Test directory/checkpoint
behavior with `node tests/test_files_directory.js` in addition to the Python suite.
The optional `node tests/test_files_download_browser.cjs` covers the actual Files
controls in isolated Chromium with synthetic handles and mocked exports (set
`PLAYWRIGHT_MODULE` and `BROWSER_CHANNEL` if required by the local runtime).

History toggle scroll restoration is covered by `node tests/test_banknote_history_position.js`.

### Purchase status and banknote feedback

Ordinary collection items share one status control: **Ordered → Shipped →
Delivered → Owned**. Linked eBay shipping evidence supplies a banknote's current
pending phase. **Owned — visually inspected** is an explicit owner action;
shipping updates never mark a record Owned. The watch ordering workflow and
property statuses remain separate. Pending phases remain included in collection
coverage, duplicate checks and reports, and each can be filtered in the list.

After an owner manually moves a pending banknote to Owned, StuffApp opens a
feedback preparation page for its uniquely linked eBay purchase. It provides
Positive/five-star guidance and the exact comment **“Banknote as described. Very
smooth transaction.”** The eBay connection is read-only: the owner copies the
comment, opens the exact order, and submits through eBay's Leave feedback action.
An ambiguous or missing purchase match produces an explanation rather than an
unrelated order link. A blocked popup leaves a link on the saved banknote page.

Run `python tests/run_all.py` for the Python regressions. The optional browser
regression is `node tests/test_purchase_status_browser.cjs`; its header documents
Python, Playwright and browser configuration. It uses isolated fixtures and
intercepts all requests, without changing live records or posting feedback.


### Catalogue audit maintenance

`banknote_catalog_audit.py` is a standalone maintenance worker; it never imports
or initializes the Flask app. `init` creates a consistent private database backup
and immutable per-note baseline. `collect` researches public catalogue types using
only country, catalogue reference, denomination, issuer and issue year. It sends no
collection identifiers, photographs or specimen/purchase data. Missing references
need a locally reviewed public query override. Existing runtime model configuration
is reused; collection concurrency is bounded at four workers.

For an additions-only backfill, initialize a new run with `init --fill-missing-only`.
The saved mode applies to all later commands: only absent or whitespace fields can
be filled, and existing values (including zero and Unknown) stay unchanged. Existing
history in either history field covers both aliases; a single dated issue does not
need a series end date. Matching issue dates and exact variety evidence are still
required. Approved additions append field/source links to Reference Notes in the
same guarded transaction and rollback journal, preserving the earlier text.

Research and writes are separate. Raw responses, actual search/citation evidence,
prompt/source hashes and per-note proposals are journaled privately. Collection
resumes completed work; `revalidate` can salvage a completed response with improved
validation without another provider request. Uncertain fields are held individually,
and unknown values never clear saved information implicitly.

`supplement --research <file>` records independently verified facts that a provider
omitted or left unresolved. It reads only the private run files, validates their hashes
and an explicit per-field source excerpt, then retains both the previous proposal and
the new candidate in an append-only research journal. Provider evidence remains
unchanged; independent evidence is labelled separately. A supplement never changes
the database or approves the physical identity, and requires fresh normal approval
before any candidate can be applied. Explicit date clears must identify `clear_fields`
and include the supported paired date display.

`apply` requires an explicit approval file with exact proposed values and a stated
review basis. An unchanged full saved catalogue identity can support type enrichment;
additional equivalent references require a source crosswalk preserving the full
namespace and variety suffix. Changes to existing identity/reference/date data need
local specimen evidence. Independently retrieved reviewer sources must include their
actual excerpt, retrieval date and explicit review, and remain in the approval audit.
Model-declared new URLs cannot grant themselves this status.

Before each write the worker checks the owner/service tenant and the complete saved
row against its baseline. Only approved catalogue/type fields can change; purchase,
status, grade, serial, certification and image data remain protected. Existing personal
history notes are fill-only. A transactional change journal supports explicit `rollback`,
which refuses to overwrite subsequent user edits. The tool has no scheduled execution
or automatic apply. Run `python banknote_catalog_audit.py --help` for command options;
`python tests/test_banknote_catalog_audit.py` exercises the workflow with isolated
fixtures and mocked provider requests, and is included in `tests/run_all.py`.

### Banknote listing photos

Check examines the exact listing's available gallery (up to 24 original photos)
with one bounded image-only side-classification call. Gallery order does not
imply front/back: two obverse close-ups or holder views cannot fill both slots.
Only a high-confidence, complete view is eligible, and a selected pair must be
confirmed as opposite sides of the same note. Collages, holder-only photos,
other notes and uncertain views are not assigned. A confirmed blank reverse is
valid. No purchase, order, owner or other collection text goes into this call;
it uses the existing note-vision model configuration and no web-search tools.

For supported exact-listing sources, original gallery files remain attached in
Documents. Every occupied image
slot and manual crop is preserved. When only one slot is empty, the saved
original is also examined before filling its partner. An uncertain or duplicate
existing pair produces a warning for manual correction rather than replacing
photos. The final write checks both original filenames and the listing link
again, so an edit made during classification wins. Only newly imported display
copies are cropped; original files and existing crop mappings are retained.

Banknote Buy/Bought uses the same selector and keeps the exact gallery originals.
It reuses the signed-in browser's saved listing capture or archived gallery when
the server cannot read eBay. Search thumbnails and recommendation images alone
are not a verified gallery. Other dealer URL shapes can retain downloaded
originals on disk without a Documents attachment through the current source
registry. Coin photo behavior is unchanged. Missing model
access or inconclusive evidence leaves the affected slot empty; Check can retry.
Tests: `test_banknote_photo_sides.py`, `test_banknote_check_sources.py`, and
`test_market_images.py`.


### Market Scan buying

Watched and sponsored eBay cards share View listing, Buy, Bought and Delete with
Market Scan candidates. Buy asks for Location, saves an Ordered record and opens
eBay's ordering page for a verified Buy It Now listing. Other sellers open their
exact listing, including contact-only dealers. Bought records an existing purchase.
After eBay confirms payment, the existing Today connection checks the exact item
and captures its order number. The record shows progress without a page refresh;
manual edits and ambiguous purchases are preserved for review. Today must be
running on the designated Mac with the linked eBay sign-in available.
See [market-scan.md](docs/market-scan.md) for the verified boundaries and tests.


### Application icon

The approved owl-coin artwork is stored unchanged in
`assets/branding/stuffapp-source.png`. Web/PWA icons, the browser favicon,
Apple touch icon, macOS `assets/branding/stuffapp.icns` and every iOS AppIcon
size are committed with the app, so future deployments and native builds retain
the icon without iCloud access.

Regenerate the derived assets with `python3 generate_app_icons.py`, using the
Pillow version in `requirements.txt`; verify them without writes with
`python3 generate_app_icons.py --check`. Resizing preserves the complete artwork.
Web icons, including the Apple touch icon, and macOS icons retain the original
transparency. Only the existing default native iOS asset catalog uses an opaque
white background to satisfy that platform format. The web manifest uses a source-hash
revision, the page uses normal asset cache-busters, and the service worker's
version is bumped when shipping an icon change. Do not label these images
maskable: platform cropping would cut off the coin.

Deploying updates web assets. Existing installed browser apps pick up icon
changes on the browser's update schedule; existing iOS native apps require a
new build/install from `ios/Stuff.xcodeproj`.
