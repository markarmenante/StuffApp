"""Shared market-scan execution, HTTP reuse and transactional persistence.

No Flask globals or collection rules live here. A scan owns its context/cache;
only the provider semaphore is process-wide. Never cache owner prompts globally.
"""
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from contextlib import contextmanager
from contextvars import ContextVar, copy_context
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
import json
import os
import sys
import threading
import time
import uuid


class ScanStopped(RuntimeError):
    pass


class RetryLater(RuntimeError):
    def __init__(self, message, delay=75):
        super().__init__(message)
        self.delay = delay


def setting(name, default, minimum=1, maximum=1000000):
    try:
        return max(minimum, min(maximum, int(os.environ.get(name, default))))
    except (TypeError, ValueError):
        return default


def canonical_url(url):
    """Remove tracking, never identity queries (CNG CoinID, dealer IDs)."""
    p = urlsplit(str(url or '').strip())
    host = (p.hostname or '').lower().removeprefix('www.')
    if host.startswith('ebay.') or '.ebay.' in host:
        import re
        m = re.search(r'/itm/(?:[^/]+/)?(\d+)', p.path)
        if m:
            return 'https://ebay.com/itm/' + m.group(1)
    tracking = {'fbclid', 'gclid', 'msclkid', 'mc_cid', 'mc_eid', '_trkparms', '_trksid', 'mkcid', 'mkrid', 'campid', 'toolid', 'customid'}
    query = sorted((k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
                   if not k.lower().startswith('utm_') and k.lower() not in tracking)
    if p.port and p.port not in (80, 443):
        host += ':' + str(p.port)
    return urlunsplit((p.scheme.lower(), host, p.path.rstrip('/') or '/', urlencode(query), ''))


_CURRENT = ContextVar('market_scan_context', default=None)
_SOURCE = ContextVar('market_scan_source', default='processing')
_DISCOVERY = ContextVar('market_scan_discovery', default=False)
_ATTEMPT = ContextVar('market_scan_attempt', default=1)
_PROVIDER = threading.BoundedSemaphore(2)


def current():
    return _CURRENT.get()


@contextmanager
def scope(ctx, source='processing', attempt=1, discovery=False):
    tokens = (_CURRENT.set(ctx), _SOURCE.set(source), _ATTEMPT.set(attempt), _DISCOVERY.set(discovery))
    try:
        yield
    finally:
        _DISCOVERY.reset(tokens[3])
        _ATTEMPT.reset(tokens[2]); _SOURCE.reset(tokens[1]); _CURRENT.reset(tokens[0])


def submit(pool, fn, *args):
    ctx = copy_context()
    return pool.submit(ctx.run, fn, *args)


@dataclass
class ScanContext:
    seconds: float = 1200
    discovery_seconds: float = 900
    max_requests: int = 48
    max_searches: int = 120
    max_output_tokens: int = 100000
    max_page_requests: int = 320
    clock: object = time.monotonic
    stop: object = field(default_factory=threading.Event)
    lock: object = field(default_factory=threading.RLock)
    metrics: dict = field(default_factory=dict)
    totals: dict = field(default_factory=dict)
    fetcher: object = None
    banknote_rows: object = None
    first_candidate_seconds: object = None
    model: object = None
    model_lock: object = field(default_factory=threading.Lock)
    fx: dict = field(default_factory=dict)
    fx_lock: object = field(default_factory=threading.Lock)
    archive_cache: dict = field(default_factory=dict)

    def __post_init__(self):
        self.started = self.clock()
        self.deadline = self.started + self.seconds
        self.discovery_deadline = self.started + min(self.seconds, self.discovery_seconds)

    @classmethod
    def configured(cls, themes):
        return cls(seconds=setting('MARKET_SCAN_SECONDS', 1200, 30, 1500),
                   discovery_seconds=setting('MARKET_SCAN_DISCOVERY_SECONDS', 900, 10, 1400),
                   max_requests=setting('MARKET_SCAN_MODEL_REQUESTS', 2 * themes + 6, 1, 48),
                   max_searches=setting('MARKET_SCAN_TOTAL_SEARCHES', themes * 10, 1, 160),
                   max_output_tokens=setting('MARKET_SCAN_OUTPUT_TOKENS', 100000, 1000, 160000),
                   max_page_requests=setting('MARKET_SCAN_PAGE_REQUESTS', 320, 10, 500))

    def remaining(self, discovery=False):
        return max(0, (min(self.deadline, self.discovery_deadline) if discovery or _DISCOVERY.get() else self.deadline) - self.clock())

    def check(self, discovery=False):
        if self.stop.is_set() or self.remaining(discovery) <= 0:
            raise ScanStopped('scan time budget reached')

    def pause(self, seconds, discovery=False):
        self.check(discovery)
        if seconds >= self.remaining(discovery) or self.stop.wait(seconds):
            raise ScanStopped('scan stopped before retry')
        self.check(discovery)

    def metric(self, key, value=1, source=None):
        with self.lock:
            m = self.metrics.setdefault(source or _SOURCE.get(), {})
            m[key] = m.get(key, 0) + value

    def reserve(self, **amounts):
        self.check()
        limits = {'requests': self.max_requests, 'searches': self.max_searches,
                  'output_tokens_reserved': self.max_output_tokens, 'page_requests': self.max_page_requests}
        with self.lock:
            for key, amount in amounts.items():
                if self.totals.get(key, 0) + amount > limits[key]:
                    raise ScanStopped(key.replace('_', ' ') + ' budget reached')
            for key, amount in amounts.items():
                self.totals[key] = self.totals.get(key, 0) + amount
                self.metric(key, amount)

    def snapshot(self):
        with self.lock:
            return json.loads(json.dumps({'sources': self.metrics, 'totals': self.totals,
                                         'first_candidate_seconds': self.first_candidate_seconds,
                                         'elapsed_seconds': round(self.clock() - self.started, 3)}))


@contextmanager
def provider_slot(ctx):
    if ctx is None:
        yield
        return
    while not _PROVIDER.acquire(timeout=min(.25, ctx.remaining(True))):
        ctx.check(True)
    try:
        ctx.check(True)
        yield
    finally:
        _PROVIDER.release()


def model_call(client, **kwargs):
    """One charged request, without hidden SDK retries or token escalation."""
    ctx = current()
    if ctx is None:
        return client.messages.create(**kwargs)
    ctx.check(True)
    # Reject oversized application prompts before sending. Search-result input
    # tokens are provider-controlled; max_tokens strictly bounds output only.
    if len(str(kwargs.get('messages', '')).encode('utf-8')) > 150000:
        raise ScanStopped('model input size budget reached')
    searches = sum(t.get('max_uses', 0) for t in kwargs.get('tools', []))
    with provider_slot(ctx):
        ctx.reserve(requests=1, searches=searches, output_tokens_reserved=kwargs['max_tokens'])
        started = ctx.clock()
        try:
            response = client.messages.create(timeout=min(240, ctx.remaining(True)), **kwargs)
        finally:
            ctx.metric('model_seconds', ctx.clock() - started)
        usage = getattr(response, 'usage', None)
        for key in ('input_tokens', 'output_tokens'):
            ctx.metric(key, getattr(usage, key, 0) or 0)
        ctx.check(True)
        return response


@dataclass(frozen=True)
class PageResult:
    status: object
    text: str
    final_url: str
    challenged: bool = False


class FetchService:
    """Per-scan single-flight page cache with bounded host request pacing.

    Injected transport does the actual request; parsers share the same HTML.
    Challenges get a short cooldown and are never treated as live evidence.
    """
    def __init__(self, ctx, transport, clock=time.monotonic, ttl=90, archive_ttl=3600, pace=.15, max_cache_bytes=24 * 1024 * 1024):
        self.ctx, self.transport, self.clock = ctx, transport, clock
        self.ttl, self.archive_ttl, self.pace = ttl, archive_ttl, pace
        self.lock = threading.RLock()
        self.cache, self.pending, self.next_host, self.cooldown = OrderedDict(), {}, {}, {}
        self.max_cache_bytes, self.cache_bytes = max_cache_bytes, 0
        self.parsed = {}

    def fetch(self, url, limit=400000):
        key = canonical_url(url)
        host = urlsplit(key).netloc
        while True:
            self.ctx.check()
            with self.lock:
                now = self.clock()
                cached = self.cache.get(key)
                if cached and cached[0] > now and cached[1] >= limit:
                    self.cache.move_to_end(key)
                    self.ctx.metric('cache_hits')
                    return cached[2]
                if self.cooldown.get(host, 0) > now:
                    self.ctx.metric('challenge_cooldown_hits')
                    return PageResult(None, '', url, True)
                event = self.pending.get(key)
                if event is None:
                    event = self.pending[key] = threading.Event()
                    break
            event.wait(min(.1, self.ctx.remaining()))
        try:
            with self.lock:
                delay = max(0, self.next_host.get(host, 0) - self.clock())
                self.next_host[host] = self.clock() + delay + self.pace
            if delay:
                self.ctx.pause(delay)
            self.ctx.reserve(page_requests=1)
            start = self.clock()
            try:
                page = self.transport(url, max(limit, 400000), min(8, self.ctx.remaining()))
            finally:
                self.ctx.metric('http_seconds', self.clock() - start)
            self.ctx.check()
            ttl = 3 if page.challenged or page.status is None else (self.archive_ttl if host.endswith('acsearch.info') else self.ttl)
            with self.lock:
                previous = self.cache.pop(key, None)
                if previous:
                    self.cache_bytes -= sys.getsizeof(previous[2].text)
                self.cache[key] = (self.clock() + ttl, max(limit, 400000), page)
                self.cache_bytes += sys.getsizeof(page.text)
                while self.cache_bytes > self.max_cache_bytes and self.cache:
                    _, removed = self.cache.popitem(last=False)
                    self.cache_bytes -= sys.getsizeof(removed[2].text)
                    self.parsed.clear()
                if page.challenged:
                    self.cooldown[host] = self.clock() + 3
            return page
        finally:
            with self.lock:
                self.pending.pop(key).set()

    def parsed_page(self, url, name, parser):
        page = self.fetch(url)
        key = (canonical_url(url), name, page)
        with self.lock:
            if key in self.parsed:
                return self.parsed[key]
        value = parser(page)
        with self.lock:
            self.parsed[key] = value
        return value


@dataclass
class Source:
    name: str
    run: object
    lane: str = 'search'


class ThemeSource(Source):
    def __init__(self, name, call):
        def run():
            items, error = call()
            return items, error, ''
        super().__init__(name, run, 'search')


class CatalogueSource(Source):
    def __init__(self, name, call):
        super().__init__(name, call, 'catalogue')


class ScanService:
    """Consume completed sources, publish immediately, requeue delayed retries.

    Discovery and normalization pools are distinct, so a slow source cannot
    keep ready candidates waiting. Only the caller writes the repository.
    """
    def __init__(self, ctx, workers=2):
        self.ctx = ctx
        self.workers = max(1, min(2, workers))

    def run(self, sources, process, publish, progress):
        ctx = self.ctx
        pools = {'search': ThreadPoolExecutor(max_workers=self.workers),
                 'catalogue': ThreadPoolExecutor(max_workers=1)}
        processing = ThreadPoolExecutor(max_workers=2)
        waiting = [(ctx.clock(), s, 1) for s in sources]
        running, batches, complete, errors = {}, {}, set(), []
        raw_count = 0

        def invoke(source, attempt):
            with scope(ctx, source.name, attempt, discovery=True):
                ctx.check(True)
                ctx.metric('attempts')
                start = ctx.clock()
                try:
                    return source.run()
                finally:
                    ctx.metric('discovery_seconds', ctx.clock() - start)

        try:
            while waiting or running or batches:
                ctx.check()
                now = ctx.clock()
                if ctx.remaining(True) <= 0:
                    for _, source, _ in waiting:
                        errors.append(source.name + ': discovery deadline reached')
                        complete.add(source.name)
                    waiting.clear()
                    for f, (source, _) in list(running.items()):
                        f.cancel()
                        errors.append(source.name + ': discovery deadline reached')
                        complete.add(source.name)
                        del running[f]
                for entry in list(waiting):
                    ready, source, attempt = entry
                    active = sum(s.lane == source.lane for s, _ in running.values())
                    catalogue_pending = (any(s.lane == 'catalogue' for _, s, _ in waiting)
                                         or any(s.lane == 'catalogue' for s, _ in running.values()))
                    # Reserve a provider slot for the fast direct-catalogue
                    # shaping call; both theme workers resume when it finishes.
                    capacity = (1 if catalogue_pending else self.workers) if source.lane == 'search' else 1
                    if ready <= now and active < capacity:
                        waiting.remove(entry)
                        running[pools[source.lane].submit(invoke, source, attempt)] = (source, attempt)
                all_futures = list(running) + list(batches)
                done = wait(all_futures, timeout=.2, return_when=FIRST_COMPLETED).done if all_futures else set()
                if not all_futures and waiting:
                    ctx.stop.wait(min(.2, max(0, min(x[0] for x in waiting) - ctx.clock())))
                for f in done:
                    if f in running:
                        source, attempt = running.pop(f)
                        try:
                            items, error, note = f.result()
                            if note:
                                with ctx.lock:
                                    ctx.metrics.setdefault(source.name, {})['note'] = note
                            raw_count += len(items)
                            ctx.metric('raw', len(items), source.name)
                            if error:
                                errors.append(error)
                            with scope(ctx, source.name):
                                pf = submit(processing, process, items)
                            batches[pf] = (source, note)
                        except RetryLater as e:
                            if attempt < 3 and ctx.remaining(True) > e.delay:
                                ctx.metric('retries', source=source.name)
                                waiting.append((ctx.clock() + e.delay, source, attempt + 1))
                            else:
                                complete.add(source.name); errors.append(source.name + ': ' + str(e))
                        except Exception as e:
                            complete.add(source.name); errors.append(source.name + ': ' + str(e))
                    else:
                        source, note = batches.pop(f)
                        try:
                            items = f.result()
                            ctx.metric('retained', len(items), source.name)
                            published = publish(items)
                            if published is not None:
                                ctx.metric('published', published, source.name)
                        except Exception as e:
                            errors.append(source.name + ': ' + str(e))
                        complete.add(source.name)
                    progress(len(complete), len(sources), errors, raw_count)
            return errors, raw_count
        finally:
            for f in list(running) + list(batches):
                f.cancel()
            for pool in list(pools.values()) + [processing]:
                pool.shutdown(wait=False, cancel_futures=True)


class MarketRepository:
    """All mutations check the current scan generation inside a short write lock."""
    def __init__(self, connect, category, scan_id):
        self.connect, self.category, self.scan_id = connect, category, scan_id

    @contextmanager
    def transaction(self):
        db = self.connect()
        try:
            db.execute('BEGIN IMMEDIATE')
            latest = db.execute('SELECT id, status FROM market_scans WHERE category = ? ORDER BY started_at DESC, rowid DESC LIMIT 1', [self.category]).fetchone()
            if not latest or latest['id'] != self.scan_id or latest['status'] != 'running':
                raise ScanStopped('scan superseded or stopped')
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def publish(self, items):
        now = datetime.utcnow().isoformat()
        with self.transaction() as db:
            saved = []
            for item in items:
                key = canonical_url(item['listing_url'])
                # Reuse earlier live candidates' IDs so actions in an already
                # open tab remain valid. Never resurrect a dismissed/bought lot.
                row = db.execute("SELECT * FROM market_scan_items WHERE category=? AND canonical_url=? ORDER BY CASE WHEN status IN ('ordered','dismissed') THEN 0 ELSE 1 END, created_at DESC LIMIT 1", [self.category, key]).fetchone()
                if row and row['status'] in ('ordered', 'dismissed'):
                    continue
                ident = row['id'] if row else str(uuid.uuid5(uuid.NAMESPACE_URL, self.category + ':' + key))
                saved.append(item)
                data = [self.scan_id, item.get('score', 0), item['title'], item['listing_url'], item.get('venue', ''), item.get('price', ''), item.get('price_usd'), item.get('grade_numeric'), item.get('designation'), item.get('closes'), item.get('theme'), json.dumps(item), now, key]
                if row:
                    db.execute("UPDATE market_scan_items SET scan_id=?,score=?,title=?,listing_url=?,venue=?,price=?,price_usd=?,grade_numeric=?,designation=?,closes=?,theme=?,payload=?,created_at=?,canonical_url=?,status='new' WHERE id=? AND status IN ('new','superseded')", data + [ident])
                else:
                    db.execute("INSERT INTO market_scan_items(scan_id,score,title,listing_url,venue,price,price_usd,grade_numeric,designation,closes,theme,payload,created_at,canonical_url,id,category,status) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'new')", data + [ident, self.category])
            rows = db.execute("SELECT id FROM market_scan_items WHERE category=? AND status='new' ORDER BY score DESC, grade_numeric DESC, id", [self.category]).fetchall()
            db.executemany('UPDATE market_scan_items SET rank=? WHERE id=?', [(n, r['id']) for n, r in enumerate(rows, 1)])
            db.execute('UPDATE market_scans SET revision=revision+1, item_count=(SELECT count(*) FROM market_scan_items WHERE scan_id=?) WHERE id=?', [self.scan_id, self.scan_id])

        return saved

    def progress(self, data):
        with self.transaction() as db:
            db.execute('UPDATE market_scans SET progress=? WHERE id=?', [json.dumps(data), self.scan_id])

    def finish(self, summary, errors, metrics, failed=False):
        with self.transaction() as db:
            # A partial/empty scan must not sweep away the previous useful list.
            count = db.execute('SELECT count(*) FROM market_scan_items WHERE scan_id=?', [self.scan_id]).fetchone()[0]
            if not errors and count:
                db.execute("UPDATE market_scan_items SET status='superseded' WHERE category=? AND status='new' AND scan_id!=?", [self.category, self.scan_id])
            db.execute("DELETE FROM market_scan_items WHERE category=? AND status IN ('superseded','dismissed') AND created_at<?", [self.category, (datetime.utcnow() - timedelta(days=60)).isoformat()])
            db.execute('UPDATE market_scans SET status=?,finished_at=?,summary=?,error=?,progress=?,revision=revision+1,item_count=? WHERE id=?', ['failed' if failed else 'done', datetime.utcnow().isoformat(), summary, '; '.join(errors)[:1000] or None, json.dumps(metrics), count, self.scan_id])
