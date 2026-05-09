/* StuffApp service worker — read-only offline support.
 *
 * Strategy:
 *   /static/* + /uploads/* + /file-thumb/*  → cache-first, immutable.
 *   App pages (/<category>, /<category>/<id>, /, /report/options …)
 *                                            → network-first, cache fallback.
 *   POST / mutating verbs                    → never cached, always network.
 *
 * Cache buckets: shell (CSS/JS) and data (HTML, images, JSON). Bumping
 * the version string here invalidates both on the next visit.
 *
 * Auth note: Cloudflare Access wraps every request. When CF redirects
 * to its login page, response.redirected === true — we skip those so
 * a stale CF cookie doesn't poison the cache with login HTML.
 */

const VERSION = 'v1';
const SHELL_CACHE = `stuffapp-shell-${VERSION}`;
const DATA_CACHE  = `stuffapp-data-${VERSION}`;

// Files we want available the very first time the app loads cold while
// offline. Everything else is filled lazily as the user (or the manual
// pre-warm) hits each URL.
const SHELL_URLS = [
  '/static/css/style.css',
  '/static/js/app.js',
  '/static/js/sync.js',
  '/static/manifest.webmanifest',
  '/static/img/apple-touch-icon.png',
  '/static/img/icon-192.png',
];

self.addEventListener('install', (event) => {
  event.waitUntil((async () => {
    const cache = await caches.open(SHELL_CACHE);
    // Use individual put()s instead of addAll(): a single 404 from
    // a renamed asset would otherwise abort the entire install.
    await Promise.all(SHELL_URLS.map(async (url) => {
      try {
        const r = await fetch(url, { credentials: 'same-origin' });
        if (r && r.ok && !r.redirected) await cache.put(url, r.clone());
      } catch (_) { /* offline at install? skip; next online visit fills */ }
    }));
    await self.skipWaiting();
  })());
});

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    const keep = new Set([SHELL_CACHE, DATA_CACHE]);
    const keys = await caches.keys();
    await Promise.all(keys.filter(k => !keep.has(k)).map(k => caches.delete(k)));
    await self.clients.claim();
  })());
});

// Pages that must NEVER be served from cache — they mutate state on
// the server, or the cached body would be misleading on a re-open.
const NO_CACHE_PATHS = [
  '/admin', '/sweep', '/files-status', '/admin/export',
  '/sw.js',
];

function shouldNotCache(url) {
  return NO_CACHE_PATHS.some(p => url.pathname === p ||
                                   url.pathname.startsWith(p + '/'));
}

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  if (shouldNotCache(url)) return;  // pass-through to network

  // Cache-first for genuinely immutable content. Filenames in
  // /uploads/ are uuid-stamped, so the same URL always means the
  // same bytes — safe to cache forever.
  if (url.pathname.startsWith('/static/') ||
      url.pathname.startsWith('/uploads/') ||
      url.pathname.startsWith('/file-thumb/')) {
    event.respondWith(cacheFirst(req, DATA_CACHE));
    return;
  }

  event.respondWith(networkFirst(req, DATA_CACHE));
});

async function cacheFirst(req, cacheName) {
  const cache = await caches.open(cacheName);
  const hit = await cache.match(req);
  if (hit) return hit;
  try {
    const resp = await fetch(req);
    if (resp && resp.ok && !resp.redirected) {
      cache.put(req, resp.clone()).catch(() => {});
    }
    return resp;
  } catch (err) {
    // No cache + offline: opaque error — surface a 504 the browser
    // will treat the same as a network failure (broken-image icon
    // for <img>, error for fetch()).
    return new Response('', { status: 504, statusText: 'Offline (uncached)' });
  }
}

async function networkFirst(req, cacheName) {
  const cache = await caches.open(cacheName);
  try {
    const resp = await fetch(req);
    if (resp && resp.ok && !resp.redirected) {
      cache.put(req, resp.clone()).catch(() => {});
    }
    return resp;
  } catch (err) {
    const cached = await cache.match(req);
    if (cached) return cached;
    // Final fallback when totally offline and never visited: return
    // the home page from cache so the user lands somewhere usable
    // instead of Safari's "no internet" page.
    const home = await cache.match('/');
    if (home) return home;
    return new Response(
      '<!doctype html><meta charset=utf-8><title>Offline</title>' +
      '<body style="font:14px -apple-system;padding:24px;color:#333">' +
      '<h2>Offline</h2><p>This page hasn\'t been cached for offline use yet. ' +
      'Reconnect, then tap <b>Offline</b> to download a copy.</p></body>',
      { status: 200, headers: { 'Content-Type': 'text/html' } }
    );
  }
}

// Message protocol for the pre-warm flow. The page posts
// {type:'WARM', urls:[…]} and we fetch each URL in batches, replying
// with progress so the toast can show "X / Y cached".
self.addEventListener('message', (event) => {
  if (!event.data || event.data.type !== 'WARM') return;
  const urls = event.data.urls || [];
  const port = event.ports && event.ports[0];
  warmCache(urls, port);
});

async function warmCache(urls, port) {
  const cache = await caches.open(DATA_CACHE);
  const total = urls.length;
  let done = 0, ok = 0, failed = 0;
  // Modest concurrency: iOS Safari throttles aggressively past 6
  // in-flight requests on the same origin, so 6 keeps the pipe full
  // without queueing internally.
  const CONCURRENCY = 6;
  let cursor = 0;
  async function worker() {
    while (cursor < urls.length) {
      const i = cursor++;
      const u = urls[i];
      try {
        const r = await fetch(u, { credentials: 'same-origin' });
        if (r && r.ok && !r.redirected) {
          await cache.put(u, r.clone());
          ok++;
        } else {
          failed++;
        }
      } catch (_) {
        failed++;
      }
      done++;
      if (port && (done === total || done % 5 === 0)) {
        port.postMessage({ done, total, ok, failed });
      }
    }
  }
  await Promise.all(Array.from({length: CONCURRENCY}, worker));
  if (port) port.postMessage({ done, total, ok, failed, finished: true });
}
