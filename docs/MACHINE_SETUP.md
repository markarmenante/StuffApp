# Machine Setup

Use this when starting on a new Mac or when Codex needs to recover the two-app
workspace from scratch.

## Clone Both Apps

```bash
mkdir -p "$HOME/Documents/GitHub" "$HOME/Developer"

test -d "$HOME/Documents/GitHub/stuffapp/.git" || \
  git clone https://github.com/markarmenante/stuffapp.git "$HOME/Documents/GitHub/stuffapp"

test -d "$HOME/Documents/GitHub/n552ym/.git" || \
  git clone https://github.com/markarmenante/n552ym.git "$HOME/Documents/GitHub/n552ym"

ln -sfn "$HOME/Documents/GitHub/stuffapp" "$HOME/Developer/stuffapp"
ln -sfn "$HOME/Documents/GitHub/n552ym" "$HOME/Developer/n552ym"
```

Canonical quick-switch paths:

```text
StuffApp: /Users/markarmenante/Developer/stuffapp
N552YM:   /Users/markarmenante/Developer/n552ym
```

## Production Targets

```text
StuffApp: https://stuff.armenante.com on Railway
N552YM:   https://n552ym.vercel.app/trips on Vercel
```

StuffApp source is `markarmenante/stuffapp`, without a dash. Do not use
`markarmenante/stuff-app` or `/Users/markarmenante/Documents/GitHub/stuff-app`
for production StuffApp work; that is the stale Next/Vercel rebuild.

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
