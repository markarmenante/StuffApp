"""External-enrichment ("Check") service layer shared by every collection type.

Watches, coins, banknotes, art and recordings each keep their own prompts,
schemas and field mappings. What they share lives here: the paid-call
plumbing for Anthropic and Perplexity.

* ``anthropic_client(kind, ...)`` builds the SDK client through one factory and
  meters every ``messages.create`` (tokens, web searches, provider) by kind.
* ``single_flight`` lets concurrent identical requests share one provider call.
* ``replay`` returns the stored result of an identical, successful explicit
  lookup for a short window. Slow lookups outlive Cloudflare's 100-second
  request cap; the browser then shows an error while the server finishes and
  discards the paid result, and the natural re-click used to pay again.
* ``remember`` is a durable content-hash cache for deterministic sub-steps
  whose inputs are fully content-addressed (photo-side classification).
* ``cooldown_*`` record failed background generations (page-view and startup
  triggered), so a generation that keeps failing validation is retried on a
  backoff instead of being billed again on every view and every boot.
* ``cached_model_alias`` keeps the resolved ``auto-*`` model id instead of
  asking the Models API before every call.
* ``fit_vision_image`` bounds every image to the documented vision size.
* ``perplexity_chat`` is the one Perplexity chat-completions transport.

Nothing here decides which fields are written; callers keep their own
validation, guards and blank-only rules.
"""
from collections import OrderedDict
import base64
import hashlib
import io
import json
import logging
import os
import threading
import time

log = logging.getLogger(__name__)

# ── Kinds: one row per paid call path, for metering and the inventory ──────
# replay_ttl applies only where a caller opts in with replay(); 0 = never.
REPLAY_TTL = 600
KINDS = {
    # banknotes
    'banknote-check': dict(types='banknotes', provider='anthropic', trigger='explicit Check; draft Check worker'),
    'banknote-catalogue-fetch': dict(types='banknotes', provider='anthropic', trigger='inside Check (bounded follow-up)'),
    'banknote-translation': dict(types='banknotes', provider='anthropic', trigger='inside Check'),
    'banknote-photo-sides': dict(types='banknotes', provider='anthropic', trigger='Check, draft Check, market Buy'),
    'banknote-serial-scan': dict(types='banknotes', provider='anthropic', trigger='explicit Scan'),
    'banknote-trim-geometry': dict(types='banknotes', provider='anthropic', trigger='photo upload/crop'),
    'banknote-trim-verdict': dict(types='banknotes', provider='anthropic', trigger='photo upload/crop'),
    'country-history': dict(types='banknotes', provider='anthropic', trigger='list view, note save, startup sweep'),
    'state-names': dict(types='banknotes', provider='anthropic', trigger='list view, note save, startup sweep'),
    'era-supplement': dict(types='coins, banknotes', provider='anthropic', trigger='detail map view'),
    # coins
    'coin-specs': dict(types='coins', provider='anthropic|perplexity', trigger='explicit lookup'),
    'coin-history': dict(types='coins', provider='anthropic', trigger='explicit lookup'),
    'coin-context': dict(types='coins', provider='anthropic|perplexity', trigger='explicit lookup (job)'),
    'coin-image-audit': dict(types='coins', provider='anthropic', trigger='admin audit'),
    # watches
    'watch-specs': dict(types='watches', provider='perplexity', trigger='explicit lookup; admin bulk lookup'),
    'watch-value': dict(types='watches', provider='perplexity|anthropic', trigger='explicit value; brand revaluation job'),
    # art / recordings
    'art-lookup': dict(types='art', provider='anthropic', trigger='explicit lookup'),
    'recording-notes': dict(types='recordings', provider='anthropic', trigger='explicit lookup'),
    # shared research / market
    'pedigree': dict(types='coins, banknotes', provider='anthropic', trigger='explicit research job'),
    'original-listing-compare': dict(types='all', provider='anthropic', trigger='original-listing worker'),
    'collection-analysis': dict(types='all', provider='anthropic', trigger='explicit analysis job'),
    'market-scan': dict(types='coins, banknotes', provider='anthropic', trigger='explicit Market Scan'),
    'market-estimate': dict(types='banknotes', provider='anthropic', trigger='explicit Estimate prices'),
    'market-slab-label': dict(types='banknotes', provider='anthropic', trigger='accepted watched feed (cached)'),
    'catalogue-audit': dict(types='banknotes', provider='anthropic', trigger='offline audit script'),
}


def kind_info(kind):
    return KINDS.get(kind, dict(types='?', provider='?', trigger='?'))


# ── Metering ───────────────────────────────────────────────────────────────
_USAGE_LOCK = threading.Lock()
_USAGE = {}
_USAGE_FIELDS = ('calls', 'replayed', 'joined', 'cache_hits', 'input_tokens', 'output_tokens',
                 'cache_read_tokens', 'cache_write_tokens', 'web_searches', 'errors')


def _int(value):
    return value if type(value) is int else 0


def _bump(kind, **amounts):
    with _USAGE_LOCK:
        row = _USAGE.setdefault(kind, dict.fromkeys(_USAGE_FIELDS, 0))
        for key, amount in amounts.items():
            row[key] += amount


def record_call(kind, provider, model, response=None, error=None):
    """Count one billed request. Never raises."""
    try:
        usage = getattr(response, 'usage', None) if response is not None else None
        tool_use = getattr(usage, 'server_tool_use', None)
        values = dict(calls=1, errors=1 if error is not None else 0,
                      input_tokens=_int(getattr(usage, 'input_tokens', None)),
                      output_tokens=_int(getattr(usage, 'output_tokens', None)),
                      cache_read_tokens=_int(getattr(usage, 'cache_read_input_tokens', None)),
                      cache_write_tokens=_int(getattr(usage, 'cache_creation_input_tokens', None)),
                      web_searches=_int(getattr(tool_use, 'web_search_requests', None)))
        if isinstance(response, dict):   # Perplexity JSON
            usage = response.get('usage') or {}
            values.update(input_tokens=_int(usage.get('prompt_tokens')),
                          output_tokens=_int(usage.get('completion_tokens')))
        _bump(kind, **values)
        log.info('paid call: kind=%s provider=%s model=%s in=%d out=%d cache_read=%d '
                 'cache_write=%d searches=%d error=%s', kind, provider, model if isinstance(model, str) else '?',
                 values['input_tokens'], values['output_tokens'], values['cache_read_tokens'],
                 values['cache_write_tokens'], values['web_searches'],
                 type(error).__name__ if error is not None else '-')
    except Exception:   # metering must never break a lookup
        pass


def usage_snapshot():
    with _USAGE_LOCK:
        return {kind: dict(row) for kind, row in _USAGE.items()}


class _MeteredMessages:
    def __init__(self, client, kind):
        self._client = client
        self._kind = kind

    def create(self, **kwargs):
        try:
            response = self._client.messages.create(**kwargs)
        except Exception as error:
            record_call(self._kind, 'anthropic', kwargs.get('model'), error=error)
            raise
        record_call(self._kind, 'anthropic', kwargs.get('model'), response)
        return response

    def __getattr__(self, name):
        return getattr(self._client.messages, name)


class _RetryingMessages(_MeteredMessages):
    def __init__(self, client, kind, retries):
        super().__init__(client, kind)
        self._retries = retries

    def create(self, **kwargs):
        send = super().create
        return call_with_retries(lambda: send(**kwargs), attempts=1 + self._retries)


class MeteredClient:
    """The SDK client with ``messages.create`` metered; everything else passes through.

    ``retries`` (default 0) applies the shared retry policy to every create
    call, for call paths without their own app-level retry. The SDK's own
    retries are off (max_retries=0) so a timeout is never repeated."""

    def __init__(self, client, kind, retries=0):
        self._client = client
        self.kind = kind
        self.messages = _RetryingMessages(client, kind, retries) if retries else _MeteredMessages(client, kind)

    def __getattr__(self, name):
        return getattr(self._client, name)


def anthropic_client(kind, retries=0, **kwargs):
    """The one Anthropic client factory. kwargs go to ``anthropic.Anthropic``
    (callers keep their timeout). The SDK's automatic retries default to 0:
    the SDK retries timeouts, and a timed-out request may already be billed.
    ``retries`` adds app-level retries under the shared policy instead."""
    import anthropic
    kwargs.setdefault('max_retries', 0)
    return MeteredClient(anthropic.Anthropic(**kwargs), kind, retries)


# ── Retry policy ───────────────────────────────────────────────────────────
# Retry only failures that were not billed or are safe to repeat: a
# connection failure with no response (never a timeout), 429 rate limits,
# 529 overloaded, and 500/502/503. A timeout or a completed response is
# never repeated. One retry policy for every Anthropic and Perplexity call.
RETRY_STATUSES = frozenset({429, 500, 502, 503, 529})


def _status_of(error):
    status = getattr(error, 'status_code', None)
    if type(status) is not int:
        status = getattr(error, 'code', None)   # urllib.error.HTTPError
    return status if type(status) is int else None


def _headers_of(error):
    response = getattr(error, 'response', None)
    headers = getattr(response, 'headers', None)
    if headers is None:
        headers = getattr(error, 'headers', None)   # urllib.error.HTTPError
    return headers or {}


def _is_timeout(error):
    import socket
    if isinstance(error, (TimeoutError, socket.timeout)):
        return True
    try:
        import anthropic
        if isinstance(error, anthropic.APITimeoutError):
            return True
    except ImportError:
        pass
    reason = getattr(error, 'reason', None)
    return isinstance(reason, (TimeoutError, socket.timeout)) or 'timed out' in str(reason or '').lower()


def retryable(error):
    """True when repeating the request cannot double-bill: see RETRY_STATUSES."""
    if error is None or _is_timeout(error):
        return False
    if str(_headers_of(error).get('x-should-retry', '')).lower() == 'false':
        return False
    status = _status_of(error)
    if status is not None:
        return status in RETRY_STATUSES
    try:
        import anthropic
        if isinstance(error, anthropic.APIConnectionError):
            return True    # no response arrived (timeouts excluded above)
    except ImportError:
        pass
    import urllib.error
    return isinstance(error, urllib.error.URLError)   # e.g. refused/DNS before a response


def retry_after(error):
    """Seconds the provider asked us to wait; None when absent; inf when unreadable."""
    import math
    headers = _headers_of(error)
    try:
        if headers.get('retry-after-ms') is not None:
            value = float(headers.get('retry-after-ms')) / 1000
        elif headers.get('retry-after') is not None:
            value = float(headers.get('retry-after'))
        else:
            return None
    except (TypeError, ValueError):
        return float('inf')
    return value if math.isfinite(value) and value >= 0 else float('inf')


def backoff(error, attempt, base, cap, strict=False):
    """Bounded wait before attempt ``attempt + 1``; None means do not retry.

    Default: ``base * (attempt + 1)``, raised to a readable Retry-After, capped.
    strict (banknote Check): the provider's Retry-After or ``base``; an
    unreadable Retry-After vetoes the retry."""
    requested = retry_after(error)
    if strict:
        if requested is not None and requested == float('inf'):
            return None
        wait = base if requested is None else requested
    else:
        wait = base * (attempt + 1)
        if requested is not None and requested != float('inf'):
            wait = max(wait, requested)
    return min(wait, cap)


def call_with_retries(send, *, attempts=2, give_up=None, base=10.0, cap=30.0, deadline=None,
                      reserve=0.0, strict_retry_after=False, on_error=None, sleep=None, clock=None):
    """Call ``send()`` up to ``attempts`` times under the shared policy.

    A failure is retried only when ``retryable`` and attempts remain and the
    bounded wait still leaves ``reserve`` seconds before ``deadline``.
    Otherwise ``give_up(error)`` decides what the caller sees: an exception
    to raise in its place (each call site keeps its historical message), or
    None to re-raise the original error unchanged."""
    sleep = sleep or time.sleep
    clock = clock or time.monotonic
    for attempt in range(max(1, attempts)):
        try:
            return send()
        except Exception as error:
            wait = None
            if attempt < attempts - 1 and retryable(error):
                wait = backoff(error, attempt, base, cap, strict_retry_after)
                if wait is not None and deadline is not None and deadline - clock() - wait < reserve:
                    wait = None
            if on_error is not None:
                on_error(error, wait is not None)
            if wait is None:
                replacement = give_up(error) if give_up is not None else None
                if replacement is None:
                    raise
                raise replacement from error
            sleep(wait)


# ── Request fingerprints ───────────────────────────────────────────────────
def _json_default(value):
    if hasattr(value, 'model_dump'):
        return value.model_dump()
    if isinstance(value, (bytes, bytearray)):
        return 'sha256:' + hashlib.sha256(value).hexdigest()
    if isinstance(value, (set, frozenset)):
        return sorted(value, key=repr)
    return repr(value)


def fingerprint(kind, payload):
    """sha256 of the kind and the canonical JSON of the exact request."""
    body = json.dumps([kind, payload], sort_keys=True, ensure_ascii=False, default=_json_default)
    return hashlib.sha256(body.encode('utf-8')).hexdigest()


# ── Single-flight ──────────────────────────────────────────────────────────
class _Flight:
    __slots__ = ('event', 'value', 'error')

    def __init__(self):
        self.event = threading.Event()
        self.value = None
        self.error = None


_FLIGHTS = {}
_FLIGHTS_LOCK = threading.Lock()


def single_flight(key, compute, kind=None):
    """Run compute once for concurrent callers with the same key."""
    with _FLIGHTS_LOCK:
        flight = _FLIGHTS.get(key)
        leader = flight is None
        if leader:
            flight = _FLIGHTS[key] = _Flight()
    if not leader:
        flight.event.wait()
        if kind:
            _bump(kind, joined=1)
        if flight.error is not None:
            raise flight.error
        return flight.value
    try:
        flight.value = compute()
        return flight.value
    except BaseException as error:
        flight.error = error
        raise
    finally:
        with _FLIGHTS_LOCK:
            _FLIGHTS.pop(key, None)
        flight.event.set()


# ── Replay window (explicit lookups) ───────────────────────────────────────
_MISS = object()
_REPLAY = OrderedDict()
_REPLAY_LOCK = threading.Lock()
_REPLAY_MAX = 256


def replay_ttl():
    try:
        return max(0, int(os.environ.get('ENRICHMENT_REPLAY_SECONDS', REPLAY_TTL)))
    except ValueError:
        return REPLAY_TTL


def _replay_get(key):
    now = time.time()
    with _REPLAY_LOCK:
        entry = _REPLAY.get(key)
        if entry is None:
            return _MISS
        expires, value = entry
        if expires <= now:
            _REPLAY.pop(key, None)
            return _MISS
        _REPLAY.move_to_end(key)
        return value


def _replay_put(key, value, ttl):
    with _REPLAY_LOCK:
        _REPLAY[key] = (time.time() + ttl, value)
        _REPLAY.move_to_end(key)
        while len(_REPLAY) > _REPLAY_MAX:
            _REPLAY.popitem(last=False)


def replay(kind, payload, compute, accept=None, ttl=None):
    """Explicit lookups: identical concurrent requests share one call, and an
    identical successful request inside the window returns the stored result.
    Failures and results rejected by ``accept`` are never stored."""
    ttl = replay_ttl() if ttl is None else ttl
    key = fingerprint(kind, payload)
    if ttl > 0:
        hit = _replay_get(key)
        if hit is not _MISS:
            _bump(kind, replayed=1)
            log.info('paid call avoided: kind=%s replay', kind)
            return hit

    def run():
        value = compute()
        if ttl > 0 and (accept is None or accept(value)):
            _replay_put(key, value, ttl)
        return value
    return single_flight(key, run, kind)


# ── Durable content-hash cache and generation cooldowns ────────────────────
_CONNECT = None
_MEMORY_STORE = {}
_MEMORY_LOCK = threading.Lock()

SCHEMA = (
    '''CREATE TABLE IF NOT EXISTS ai_result_cache (
        cache_key TEXT PRIMARY KEY,
        kind TEXT NOT NULL,
        created_at REAL NOT NULL,
        expires_at REAL NOT NULL CHECK (expires_at >= created_at),
        result TEXT NOT NULL)''',
    'CREATE INDEX IF NOT EXISTS idx_ai_result_cache_expires ON ai_result_cache(expires_at)',
    '''CREATE TABLE IF NOT EXISTS ai_generation_failures (
        job_key TEXT PRIMARY KEY,
        kind TEXT NOT NULL,
        failures INTEGER NOT NULL CHECK (failures > 0),
        last_failed_at REAL NOT NULL,
        retry_after REAL NOT NULL,
        last_error TEXT)''',
)


def init_schema(db):
    for statement in SCHEMA:
        db.execute(statement)
    db.execute('DELETE FROM ai_result_cache WHERE expires_at < ?', (time.time(),))


def configure(connect):
    """Register the app's connection factory (sqlite3 connections, Row factory)."""
    global _CONNECT
    _CONNECT = connect


def reset():
    """Forget in-process state (tests)."""
    with _REPLAY_LOCK:
        _REPLAY.clear()
    with _MEMORY_LOCK:
        _MEMORY_STORE.clear()
    with _USAGE_LOCK:
        _USAGE.clear()
    with _ALIAS_LOCK:
        _ALIASES.clear()


def _with_db(work):
    if _CONNECT is None:
        return _MISS
    try:
        db = _CONNECT()
    except Exception:
        return _MISS
    try:
        return work(db)
    except Exception as error:   # the cache is an optimisation, never a failure path
        log.info('enrichment store unavailable: %s', type(error).__name__)
        try:
            db.rollback()
        except Exception:
            pass
        return _MISS
    finally:
        db.close()


def _store_get(key):
    def read(db):
        row = db.execute('SELECT result, expires_at FROM ai_result_cache WHERE cache_key=?', (key,)).fetchone()
        if row is None or row[1] <= time.time():
            return _MISS
        return json.loads(row[0])
    found = _with_db(read)
    if found is not _MISS:
        return found
    with _MEMORY_LOCK:
        entry = _MEMORY_STORE.get(key)
    if entry and entry[0] > time.time():
        return json.loads(entry[1])
    return _MISS


def _store_put(key, kind, value, ttl):
    try:
        text = json.dumps(value, sort_keys=True, ensure_ascii=False)
    except (TypeError, ValueError):
        return
    now = time.time()

    def write(db):
        db.execute('INSERT OR REPLACE INTO ai_result_cache (cache_key, kind, created_at, expires_at, result) '
                   'VALUES (?, ?, ?, ?, ?)', (key, kind, now, now + ttl, text))
        db.commit()
        return True
    if _with_db(write) is _MISS:
        with _MEMORY_LOCK:
            _MEMORY_STORE[key] = (now + ttl, text)


def remember(kind, payload, compute, accept, ttl):
    """Durable cache keyed by the content hash of the exact request. Only
    results ``accept`` approves are stored; JSON-serialisable results only."""
    key = fingerprint(kind, payload)
    found = _store_get(key)
    if found is not _MISS:
        _bump(kind, cache_hits=1)
        log.info('paid call avoided: kind=%s content cache', kind)
        return found

    def run():
        value = compute()
        try:
            ok = bool(accept(value))
        except Exception:
            ok = False
        if ok:
            _store_put(key, kind, value, ttl)
        return value
    return single_flight(key, run, kind)


COOLDOWN_STEPS = (3600, 6 * 3600, 24 * 3600, 7 * 86400)


def cooldown_active(job_key):
    """True while a failed background generation waits for its next attempt."""
    def read(db):
        row = db.execute('SELECT retry_after FROM ai_generation_failures WHERE job_key=?', (job_key,)).fetchone()
        return bool(row) and row[0] > time.time()
    found = _with_db(read)
    return False if found is _MISS else found


def record_failure(job_key, kind, error):
    def write(db):
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT failures FROM ai_generation_failures WHERE job_key=?', (job_key,)).fetchone()
        failures = (row[0] if row else 0) + 1
        delay = COOLDOWN_STEPS[min(failures, len(COOLDOWN_STEPS)) - 1]
        now = time.time()
        db.execute('INSERT OR REPLACE INTO ai_generation_failures '
                   '(job_key, kind, failures, last_failed_at, retry_after, last_error) VALUES (?, ?, ?, ?, ?, ?)',
                   (job_key, kind, failures, now, now + delay, str(error)[:300]))
        db.commit()
        return failures
    _with_db(write)


def clear_failure(job_key):
    def write(db):
        db.execute('DELETE FROM ai_generation_failures WHERE job_key=?', (job_key,))
        db.commit()
        return True
    _with_db(write)


def failures_snapshot():
    def read(db):
        return [dict(job_key=r[0], kind=r[1], failures=r[2], retry_after=r[3], last_error=r[4])
                for r in db.execute('SELECT job_key, kind, failures, retry_after, last_error '
                                    'FROM ai_generation_failures ORDER BY last_failed_at DESC LIMIT 100')]
    found = _with_db(read)
    return [] if found is _MISS else found


# ── Model alias resolution cache ───────────────────────────────────────────
ALIAS_TTL = 6 * 3600
_ALIASES = {}
_ALIAS_LOCK = threading.Lock()


def _alias_key(family, api_key):
    return family, hashlib.sha256((api_key or '').encode('utf-8')).hexdigest()[:16]


def cached_model_alias(family, api_key):
    with _ALIAS_LOCK:
        entry = _ALIASES.get(_alias_key(family, api_key))
    if entry and entry[0] > time.time():
        return entry[1]
    return None


def remember_model_alias(family, api_key, model_id):
    with _ALIAS_LOCK:
        _ALIASES[_alias_key(family, api_key)] = (time.time() + ALIAS_TTL, model_id)


# ── Vision images ──────────────────────────────────────────────────────────
VISION_B64_CAP = 4_500_000
VISION_MAX_EDGE = 1568
_FORMATS = {'image/jpeg': 'JPEG', 'image/png': 'PNG', 'image/webp': 'WEBP'}


def vision_max_edge():
    try:
        return max(512, int(os.environ.get('ANTHROPIC_VISION_MAX_EDGE', VISION_MAX_EDGE)))
    except ValueError:
        return VISION_MAX_EDGE


def fit_vision_image(raw, media_type, max_edge=None, b64_cap=VISION_B64_CAP):
    """Return ``(base64_data, media_type)`` for a vision request.

    Images within the long-edge bound and the base64 cap pass through
    byte-for-byte. Larger ones are resized to the bound (the size the API
    itself scales oversized images to, so the model sees no less detail) in
    their own format where possible, then compressed as JPEG only if they
    still exceed the cap. Unreadable images are returned unchanged."""
    max_edge = max_edge or vision_max_edge()
    encoded = base64.b64encode(raw).decode('ascii')
    try:
        from PIL import Image, ImageOps
        with Image.open(io.BytesIO(raw)) as probe:
            size = probe.size
    except Exception:
        return encoded, media_type
    if max(size) <= max_edge and len(encoded) <= b64_cap:
        return encoded, media_type
    try:
        with Image.open(io.BytesIO(raw)) as source:
            image = ImageOps.exif_transpose(source)
            image.load()
        if max(image.size) > max_edge:
            scale = max_edge / float(max(image.size))
            image = image.resize((max(1, round(image.width * scale)), max(1, round(image.height * scale))),
                                 Image.LANCZOS)
        fmt = _FORMATS.get(media_type)
        if fmt:
            out = io.BytesIO()
            keep = image if fmt != 'JPEG' or image.mode in ('RGB', 'L') else image.convert('RGB')
            if fmt == 'PNG':
                keep.save(out, format='PNG', optimize=True)
            else:
                keep.save(out, format=fmt, quality=90)
            candidate = base64.b64encode(out.getvalue()).decode('ascii')
            if len(candidate) <= b64_cap:
                return candidate, media_type
        image = image if image.mode in ('RGB', 'L') else image.convert('RGB')
        last = encoded
        for quality in (85, 75, 65, 55, 45):
            out = io.BytesIO()
            image.save(out, format='JPEG', quality=quality, optimize=True)
            last = base64.b64encode(out.getvalue()).decode('ascii')
            if len(last) <= b64_cap:
                return last, 'image/jpeg'
        return last, 'image/jpeg'
    except Exception:
        return encoded, media_type


# ── Perplexity chat-completions transport ──────────────────────────────────
PERPLEXITY_CHAT_COMPLETIONS_URL = 'https://api.perplexity.ai/chat/completions'


def perplexity_chat(api_key, body_data, kind, sleep=None):
    """POST one chat-completions body; returns ``(api_data, text)``.

    Up to three attempts under the shared retry policy: 429, 529 and
    500/502/503 (honouring Retry-After, bounded) and connection failures
    before a response are retried; a timeout, any other status, or a
    completed response is not. Failure messages are unchanged:
    ``Perplexity HTTP <code>: <detail>`` for a rejected request, otherwise
    ``Lookup failed after retries: <error>``. Every attempt is metered."""
    import urllib.error
    import urllib.request
    body = json.dumps(body_data).encode('utf-8')

    def send():
        req = urllib.request.Request(
            PERPLEXITY_CHAT_COMPLETIONS_URL, data=body,
            headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json',
                     'Accept': 'application/json'},
            method='POST')
        try:
            with urllib.request.urlopen(req, timeout=240) as resp:
                return json.loads(resp.read().decode('utf-8'))
        except (urllib.error.URLError, OSError) as error:
            record_call(kind, 'perplexity', body_data.get('model'), error=error)
            raise

    def give_up(error):
        if isinstance(error, urllib.error.HTTPError) and error.code not in RETRY_STATUSES:
            try:
                detail = error.read().decode('utf-8', 'ignore')[:200]
            except Exception:
                detail = ''
            return RuntimeError(f'Perplexity HTTP {error.code}: {detail}')
        if isinstance(error, urllib.error.URLError):
            return RuntimeError(f'Lookup failed after retries: {error}')
        return None   # a raw socket timeout surfaces as before

    api_data = call_with_retries(send, attempts=3, give_up=give_up, base=10.0, cap=30.0, sleep=sleep)
    record_call(kind, 'perplexity', body_data.get('model'), api_data)
    try:
        text = api_data['choices'][0]['message']['content'] or ''
    except (KeyError, IndexError, TypeError):
        raise RuntimeError(f'Unexpected Perplexity response: {str(api_data)[:200]}')
    return api_data, text.strip()


def anthropic_completed(response):
    """Accept predicate for replay: a finished Anthropic turn with text."""
    if getattr(response, 'stop_reason', None) not in ('end_turn', 'stop_sequence'):
        return False
    return any(getattr(block, 'type', None) == 'text' and str(getattr(block, 'text', '') or '').strip()
               for block in (getattr(response, 'content', None) or ()))


def perplexity_completed(result):
    """Accept predicate for replay: a Perplexity answer with text."""
    return isinstance(result, tuple) and len(result) == 2 and bool(str(result[1] or '').strip())
