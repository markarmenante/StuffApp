// Read-only production verification: no app credentials or database access.
import { setTimeout as delay } from 'node:timers/promises';

const endpoints = ["https://web-production-cf059.up.railway.app/healthz", "https://gerri-production.up.railway.app/healthz"];
const commit = process.env.GITHUB_SHA;
if (!/^[a-f0-9]{40}$/.test(commit || '')) throw new Error('Expected the exact GitHub commit SHA');
const deadline = Date.now() + 8 * 60_000;
for (const endpoint of endpoints) {
  let matched = false;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(endpoint, { redirect: 'error', cache: 'no-store', signal: AbortSignal.timeout(10_000) });
      const observed = response.headers.get('x-app-commit') || (await response.json()).commit;
      if (response.ok && observed === commit) { matched = true; break; }
    } catch { /* A deployment may still be building/restarting. */ }
    await delay(15_000);
  }
  if (!matched) throw new Error(`Production did not confirm the tested commit at ${new URL(endpoint).hostname}`);
  console.log(`Verified ${new URL(endpoint).hostname}: ${commit.slice(0, 7)}`);
}
