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
