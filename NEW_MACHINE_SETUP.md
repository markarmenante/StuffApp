# New-machine setup — develop, test, deploy

One-stop note for getting productive on a fresh computer. The same note lives in all four active repos. Last verified 2026-07-14.

The four active repos: **family-office**, **boardroom**, **StuffApp**, **n552ym**. (Archived, do not clone: `museum-of-time` and `oryn-boardroom` were folded into the boardroom monorepo's `/museum` and `/oryn`; `ym-parties` was folded into n552ym's party features.)

## Accounts & dashboards

| Service | Where | Used for |
| --- | --- | --- |
| GitHub | https://github.com/markarmenante | All source |
| Railway | https://railway.app/dashboard (account markarmenante@gmail.com) | Hosts **family-office** (project `ym-familyoffice`: Next.js service + Postgres, uploads volume at `/app/uploads`) and **StuffApp** (`web` service) |
| Vercel | https://vercel.com/dashboard (account `markarmenante`) | Hosts **boardroom** (project `board`, root `apps/board` → board-delta-silk.vercel.app) and **n552ym** |
| Cloudflare | https://dash.cloudflare.com | DNS for `stuff.armenante.com` (fronts StuffApp on Railway) |
| Anthropic Console | https://console.anthropic.com | API keys: family-office document intake, StuffApp vision |
| Perplexity | https://www.perplexity.ai/settings/api | Optional family-office quick-file scan provider |
| Google Drive | "Museum of Time" shared drive (owner nmanousos@gmail.com) | Source folders the family-office document types mirror |

Production URLs: family-office → https://ym-familyoffice-production.up.railway.app · boardroom → https://board-delta-silk.vercel.app · StuffApp → https://stuff.armenante.com

## Install (macOS)

```bash
# Homebrew first: https://brew.sh
brew install git gh node vercel-cli postgresql@17
brew services start postgresql@17
# Railway CLI (not in brew):
bash <(curl -fsSL cli.new)
# Claude Code (CLI + desktop app): https://claude.com/claude-code
npm install -g @anthropic-ai/claude-code
```

Chrome: install the **Claude in Chrome** extension (drives your signed-in browser; needed for boardroom prod-data inspection — see gotchas). In Claude Code, connect the **Railway MCP** server and the Google Drive / Gmail / Calendar connectors as needed.

## Sign in (per machine — these expire / don't roam)

```bash
gh auth login          # GitHub
railway login          # Railway — CLI auth is per-machine; the Railway MCP can hold
                       # stale auth even after CLI relogin, prefer the CLI when they disagree
vercel login           # Vercel
git clone https://github.com/markarmenante/{family-office,boardroom,StuffApp,n552ym}.git
```

## Deploy flow — all repos

**Push to `main` auto-deploys everywhere.** family-office runs `prisma migrate deploy` on start (Railway `start:railway`); Vercel builds boardroom and n552ym per push; StuffApp redeploys on Railway.

## Per-repo local dev

### family-office (this pattern is the most involved)
```bash
cd family-office && npm install
createdb family_office        # postgresql@17 must be running
cat > .env <<ENV
DATABASE_URL="postgresql://$(whoami)@localhost:5432/family_office?schema=public"
SESSION_SECRET="$(openssl rand -hex 24)"
ENV
npx prisma migrate deploy && npm run db:seed   # seeded login: admin@familyoffice.local / FamilyOffice123!
npm run dev                                    # http://localhost:3000
```
AI intake needs `ANTHROPIC_API_KEY` in `.env` (prod value lives in the Railway service env — as of July 2026 the intake model is `claude-sonnet-5`; it rejects `temperature` and thinking tokens count against `max_tokens`). Direct prod-DB scripts: `npm run prod:db -- <cmd>` (needs `railway login`). Optional: LibreOffice for document conversion (`brew install --cask libreoffice`).

### boardroom
Read `HANDOFF.md` + `PICKUP.md` first. Monorepo; the app is `apps/board`. **All Vercel env vars are "sensitive" — `vercel env pull` returns empty strings**, so local dev cannot get `DATABASE_URL`; inspect prod data through the app's API using a signed-in Chrome tab (Claude in Chrome), not the DB. On Vercel the OIDC token arrives per-request via the `x-vercel-oidc-token` header, not the env var.

### StuffApp
Python/Flask (gunicorn). `pip install -r requirements.txt`, needs `ANTHROPIC_API_KEY`. Deployed on Railway behind Cloudflare.

### n552ym
Plain Next.js on Vercel (`npm install && npm run dev`). Covers aviation, trips, parties, lodging, residency, and the Rivet email workflow.

## Secrets

Never committed. They live in the Railway service variables (family-office, StuffApp) and Vercel project envs (boardroom, n552ym). If a value is unreadable there (Vercel sensitive), it can only be replaced, not recovered — keep that in mind before rotating.
