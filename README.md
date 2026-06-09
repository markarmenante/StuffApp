# StuffApp

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
N552YM: /Users/markarmenante/Developer/n552ym
```

Do not use `/Users/markarmenante/Documents/GitHub/stuff-app` for production
StuffApp work. That dashed repo is the stale Next/Vercel rebuild.
