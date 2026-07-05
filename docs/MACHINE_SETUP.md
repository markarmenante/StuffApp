# Machine Setup

Use this when starting on a new Mac or when Codex needs to recover the app
workspace from scratch.

## Clone Apps

```bash
mkdir -p "$HOME/Documents/GitHub" "$HOME/Developer"

test -d "$HOME/Documents/GitHub/stuffapp/.git" || \
  git clone https://github.com/markarmenante/StuffApp.git "$HOME/Documents/GitHub/stuffapp"

test -d "$HOME/Documents/GitHub/n552ym/.git" || \
  git clone https://github.com/markarmenante/n552ym.git "$HOME/Documents/GitHub/n552ym"

test -d "$HOME/Documents/GitHub/museum-of-time/.git" || \
  git clone https://github.com/markarmenante/museum-of-time.git "$HOME/Documents/GitHub/museum-of-time"

test -d "$HOME/Documents/GitHub/Family Office/.git" || \
  git clone https://github.com/markarmenante/family-office.git "$HOME/Documents/GitHub/Family Office"

ln -sfn "$HOME/Documents/GitHub/stuffapp" "$HOME/Developer/stuffapp"
ln -sfn "$HOME/Documents/GitHub/n552ym" "$HOME/Developer/n552ym"
```

Canonical quick-switch paths:

```text
Museum:        /Users/markarmenante/Documents/GitHub/museum-of-time
StuffApp:      /Users/markarmenante/Documents/GitHub/stuffapp
N552YM:        /Users/markarmenante/Documents/GitHub/n552ym
Family Office: /Users/markarmenante/Documents/GitHub/Family Office
```

## Production Targets

```text
Museum:        https://museum-of-time-peach.vercel.app on Vercel
StuffApp:      https://stuff.armenante.com on Railway
N552YM:        https://n552ym.vercel.app/trips on Vercel
Family Office: https://ym-familyoffice-production.up.railway.app on Railway
```

StuffApp source is `markarmenante/StuffApp`, without a dash. The stale
`markarmenante/stuff-app` Next/Vercel rebuild was retired and deleted in
June 2026.

## Start StuffApp Locally

```bash
cd /Users/markarmenante/Developer/stuffapp
git pull --ff-only
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
flask --app app run --port 5001
```

Railway runs:

```bash
gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 300
```

## Start N552YM Locally

```bash
cd /Users/markarmenante/Developer/n552ym
git pull --ff-only
npm install
npm run dev
```

N552YM deploys from `markarmenante/n552ym` on Vercel.

## Start Museum Locally

```bash
cd /Users/markarmenante/Documents/GitHub/museum-of-time
git pull --ff-only
npm install
npm run db:setup
npm run dev
```

For Apple Messages and Google Drive ingest on the Mac:

```bash
npm run source:webhook
```

Museum deploys from `markarmenante/museum-of-time` on Vercel.

## Start Family Office Locally

```bash
cd /Users/markarmenante/Documents/GitHub/Family\ Office
git pull --ff-only
npm install
npm run dev
```

Family Office deploys from `markarmenante/family-office` on Railway.

## Working Rule

Before editing either app:

```bash
git status --short
git pull --ff-only
```

After finishing code or repo-doc changes:

```bash
git status --short
git add <changed files>
git commit -m "<short message>"
git push
```

Shared breadcrumbs, if iCloud is available:

```text
/Users/markarmenante/Library/Mobile Documents/com~apple~CloudDocs/Stuff Codex/APP_BREADCRUMBS.md
```
