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

Click **Files** to see the remembered destination, then **Choose folder…** to
select an existing `StuffFiles` folder (normally in iCloud Drive on a Mac).
Selecting its parent uses or creates a `StuffFiles` child. Folder selection is
saved independently of downloading; close the dialog to finish setting it
without starting an export. The browser stores this choice per site/profile,
not on the Railway server. The app cannot silently choose an absolute Mac path.

Changing the destination resets both the incremental-download checkpoint and
Sweep's local upload fingerprints in the same transaction as the folder handle.
The next download to a different folder is complete; reselecting the same folder
keeps its existing checkpoint. Existing files in the former folder are untouched.
Failed file writes no longer advance the successful-download checkpoint.

Browsers without the directory API still download a zip using their own download
settings; the Files dialog explains that fallback. Test directory/checkpoint
behavior with `node tests/test_files_directory.js` in addition to the Python suite.
