# Machine Setup

Use this when starting on a new Mac or when Codex needs to recover the app
workspace from scratch.

## Clone Apps

```bash
mkdir -p "$HOME/GitHub" "$HOME/Developer"

test -d "$HOME/GitHub/StuffApp/.git" || \
  git clone https://github.com/markarmenante/StuffApp.git "$HOME/GitHub/StuffApp"

test -d "$HOME/GitHub/n552ym/.git" || \
  git clone https://github.com/markarmenante/n552ym.git "$HOME/GitHub/n552ym"

test -d "$HOME/GitHub/boardroom/.git" || \
  git clone https://github.com/markarmenante/boardroom.git "$HOME/GitHub/boardroom"

test -d "$HOME/GitHub/family-office/.git" || \
  git clone https://github.com/markarmenante/family-office.git "$HOME/GitHub/family-office"

ln -sfn "$HOME/GitHub/StuffApp" "$HOME/Developer/stuffapp"
ln -sfn "$HOME/GitHub/n552ym" "$HOME/Developer/n552ym"
```

Canonical quick-switch paths:

```text
Museum:        /Users/markarmenante/GitHub/boardroom/apps/museum
StuffApp:      /Users/markarmenante/GitHub/StuffApp
N552YM:        /Users/markarmenante/GitHub/n552ym
Family Office: /Users/markarmenante/GitHub/family-office
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
cd /Users/markarmenante/GitHub/boardroom
git pull --ff-only
npm install
npm run db:setup -w apps/museum
npm run dev -w apps/museum
```

For Apple Messages and Google Drive ingest on the Mac:

```bash
npm run source:webhook
```

Museum deploys from `markarmenante/boardroom` on Vercel (Root
Directory `apps/museum`); the standalone museum-of-time repo was
deleted 2026-08-17.

## Start Family Office Locally

```bash
cd /Users/markarmenante/GitHub/family-office
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
