# StuffApp

> **New computer?** Start with [NEW_MACHINE_SETUP.md](NEW_MACHINE_SETUP.md) — accounts, CLIs, local dev, and deploy for all five repos.

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
/Users/markarmenante/Documents/GitHub/stuffapp
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
Museum of Time: /Users/markarmenante/Documents/GitHub/museum-of-time
N552YM:         /Users/markarmenante/Documents/GitHub/n552ym
Family Office: /Users/markarmenante/Documents/GitHub/Family Office
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
