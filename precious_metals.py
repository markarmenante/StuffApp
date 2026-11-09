"""Anonymous public USD spot quotes, cached separately from collection records."""
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import tempfile
import threading
import urllib.request

URL = 'https://api.gold-api.com/price/{}'
SEED = Path(__file__).resolve().parent / 'data' / 'precious-metals.json'
TTL_SECONDS = 600
_lock = threading.Lock()
_active = set()
_attempts = {}


def _time(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else None
    except (TypeError, ValueError):
        return None


def parse_quote(payload, symbol, now=None):
    now = now or datetime.now(timezone.utc)
    price, timestamp = payload.get('price'), _time(payload.get('updatedAt'))
    if (payload.get('symbol') != symbol or payload.get('currency') != 'USD'
            or isinstance(payload.get('exchangeRate'), bool) or payload.get('exchangeRate') != 1
            or isinstance(price, bool) or not isinstance(price, (int, float))
            or not math.isfinite(price) or price <= 0 or not timestamp
            or (timestamp - now).total_seconds() > 300):
        raise ValueError('Invalid public metal quote')
    return dict(price=price, updated_at=timestamp.isoformat())


def snapshot(data_dir):
    result = dict(version=1, quotes={})
    for path in (Path(data_dir) / 'precious-metals.json', SEED):
        try:
            data = json.loads(path.read_text())
            if data.get('version') == 1 and isinstance(data.get('quotes'), dict):
                if not result.get('checked_at') and _time(data.get('checked_at')):
                    result['checked_at'] = data['checked_at']
                for symbol in ('XAU', 'XAG'):
                    quote = data['quotes'].get(symbol)
                    if symbol in result['quotes'] or not isinstance(quote, dict):
                        continue
                    try:
                        result['quotes'][symbol] = parse_quote(dict(symbol=symbol, currency='USD', exchangeRate=1,
                            price=quote.get('price'), updatedAt=quote.get('updated_at')), symbol)
                    except (ValueError, TypeError):
                        pass
        except (OSError, ValueError, TypeError, AttributeError):
            pass
    return result


def _read(symbol):
    request = urllib.request.Request(URL.format(symbol), headers={'User-Agent': 'StuffApp/1.0 (public metal quotes)'})
    with urllib.request.urlopen(request, timeout=8) as response:
        raw = response.read(65537)
        if len(raw) > 65536:
            raise ValueError('Metal quote exceeds size limit')
        return json.loads(raw)


def refresh(data_dir):
    data = snapshot(data_dir)
    for symbol in ('XAU', 'XAG'):
        try:
            quote = parse_quote(_read(symbol), symbol)
            old = _time(data['quotes'].get(symbol, {}).get('updated_at'))
            if not old or _time(quote['updated_at']) >= old:
                data['quotes'][symbol] = quote
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            pass  # Retain this metal's last valid quote, including its original date.
    data['checked_at'] = datetime.now(timezone.utc).isoformat()
    folder = Path(data_dir)
    folder.mkdir(parents=True, exist_ok=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', dir=folder, prefix='.precious-metals-', delete=False) as handle:
            name = handle.name
            json.dump(data, handle, separators=(',', ':'))
        os.replace(name, folder / 'precious-metals.json')
    finally:
        if name and os.path.exists(name):
            os.unlink(name)


def request_refresh(data_dir):
    if os.environ.get('COIN_ECONOMICS_REFRESH') == '0':
        return False
    key = str(Path(data_dir).resolve())
    now = datetime.now(timezone.utc)
    with _lock:
        checked = _time(snapshot(data_dir).get('checked_at'))
        previous = _attempts.get(key) or checked
        if key in _active:
            return True
        if previous and 0 <= (now - previous).total_seconds() < TTL_SECONDS:
            return False
        _active.add(key)
        _attempts[key] = now
    def run():
        try:
            refresh(data_dir)
        except (OSError, ValueError, TypeError):
            pass
        finally:
            with _lock:
                _active.discard(key)
    threading.Thread(target=run, name='coin-public-metal-quotes', daemon=True).start()
    return True
