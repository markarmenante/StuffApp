"""Read-only, account-bound eBay discovery from Today's signed-in browser.

This feed never imports purchases, changes watchlists, or writes orders. Only
the existing authenticated Mac bridge can supply an observed snapshot.
"""
from datetime import datetime, timezone
from urllib.parse import urlsplit
import json
import os
import re
import time
import uuid

from flask import abort, jsonify, request
import ebay_mail

REQUEST_SECONDS = 180
SESSION_SECONDS = 600
FRESH_SECONDS = 600
KINDS = ('watched', 'sponsored')


def enabled():
    return ebay_mail.configured() and os.environ.get('RAILWAY_SERVICE_NAME', 'web') == 'web'


def init_schema(db):
    db.executescript('''
        CREATE TABLE IF NOT EXISTS ebay_market_requests (
            id TEXT PRIMARY KEY, requested_at REAL NOT NULL, expires_at REAL NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('queued','reading','done','expired')),
            expected_account TEXT, observed_at REAL, source_status TEXT NOT NULL DEFAULT '{}'
        );
        CREATE TABLE IF NOT EXISTS ebay_market_sessions (
            request_id TEXT PRIMARY KEY REFERENCES ebay_market_requests(id) ON DELETE CASCADE,
            state TEXT NOT NULL DEFAULT 'checking' CHECK(state IN ('checking','sign_in_required','challenge_required','ready','unavailable')),
            message TEXT NOT NULL DEFAULT '', retry_after REAL NOT NULL DEFAULT 0,
            open_reserved INTEGER NOT NULL DEFAULT 0 CHECK(open_reserved IN (0,1)),
            claimed_at REAL, scan_id TEXT UNIQUE REFERENCES market_scans(id) ON DELETE SET NULL
        );
        CREATE TABLE IF NOT EXISTS ebay_market_cards (
            request_id TEXT NOT NULL REFERENCES ebay_market_requests(id) ON DELETE CASCADE,
            item_id TEXT NOT NULL, title TEXT NOT NULL, listing_url TEXT NOT NULL,
            price TEXT NOT NULL, image_url TEXT NOT NULL, source_label TEXT NOT NULL,
            listing_text TEXT NOT NULL, live_state TEXT NOT NULL,
            listing_checked_at REAL, PRIMARY KEY(request_id,item_id)
        );
        CREATE TABLE IF NOT EXISTS ebay_market_card_sources (
            request_id TEXT NOT NULL, item_id TEXT NOT NULL,
            source TEXT NOT NULL CHECK(source IN ('watched','sponsored')),
            PRIMARY KEY(request_id,item_id,source),
            FOREIGN KEY(request_id,item_id) REFERENCES ebay_market_cards(request_id,item_id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_ebay_market_requests_status ON ebay_market_requests(status,requested_at);
        CREATE INDEX IF NOT EXISTS idx_ebay_market_cards_item ON ebay_market_cards(item_id,request_id);
    ''')
    db.commit()


def item_id(url):
    try:
        p = urlsplit(str(url or ''))
        host = (p.hostname or '').lower()
        if p.scheme != 'https' or p.username or p.password or p.port not in (None, 443):
            return None
        if not re.fullmatch(r'(?:www\.)?ebay\.(?:com|co\.uk|de|fr|it|es|ca|com\.au|at|ch|ie|nl|be)', host):
            return None
        m = re.fullmatch(r'/itm/(?:[^/]+/)?(\d{9,15})/?', p.path)
        return m.group(1) if m else None
    except ValueError:
        return None


def timestamp(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        if parsed.tzinfo is None:
            return None
        return parsed.timestamp()
    except (TypeError, ValueError):
        return None


def utc(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat()


def expected_account(db):
    accounts = [r[0].lower() for table in ('ebay_purchase_account', 'ebay_connection')
                for r in db.execute('SELECT account_name FROM ' + table + ' WHERE id=1').fetchall()
                if r[0]]
    if len(set(accounts)) > 1:
        raise ValueError('The linked eBay accounts disagree; personalized sources were not read.')
    return accounts[0] if accounts else None


def queue(db, recover_session=False):
    if not enabled():
        return None
    now = time.time()
    db.execute("DELETE FROM ebay_market_card_sources WHERE request_id IN (SELECT id FROM ebay_market_requests WHERE requested_at<?)", (now - 86400,))
    db.execute("DELETE FROM ebay_market_cards WHERE request_id IN (SELECT id FROM ebay_market_requests WHERE requested_at<?)", (now - 86400,))
    db.execute('DELETE FROM ebay_market_sessions WHERE request_id IN (SELECT id FROM ebay_market_requests WHERE requested_at<?)', (now - 86400,))
    db.execute('DELETE FROM ebay_market_requests WHERE requested_at<?', (now - 86400,))
    ident = uuid.uuid4().hex
    db.execute('INSERT INTO ebay_market_requests(id,requested_at,expires_at,status,expected_account) VALUES(?,?,?,?,?)',
               (ident, now, now + (SESSION_SECONDS if recover_session else REQUEST_SECONDS), 'queued', expected_account(db)))
    if recover_session:
        db.execute('INSERT INTO ebay_market_sessions(request_id) VALUES(?)', (ident,))
    db.commit()
    return ident



def prepare_session(db):
    """Coalesce explicit owner requests; no browser or model action runs here."""
    account = expected_account(db)
    db.execute("UPDATE ebay_market_requests SET status='expired' WHERE status IN ('queued','reading') AND expected_account IS NOT ? AND id IN (SELECT request_id FROM ebay_market_sessions)", (account,))
    row = db.execute("SELECT r.id FROM ebay_market_requests r JOIN ebay_market_sessions s ON s.request_id=r.id "
                     "WHERE r.status IN ('queued','reading') AND r.expires_at>? ORDER BY r.requested_at DESC LIMIT 1", (time.time(),)).fetchone()
    return row['id'] if row else queue(db, recover_session=True)


def session_status(db, ident=None):
    if not enabled():
        return None
    where, params = ('WHERE r.id=?', (ident,)) if ident else ('ORDER BY r.requested_at DESC LIMIT 1', ())
    row = db.execute('SELECT r.*,s.state,s.message,s.scan_id FROM ebay_market_requests r '
                     'JOIN ebay_market_sessions s ON s.request_id=r.id ' + where, params).fetchone()
    if not row:
        return None
    state, message = row['state'], row['message']
    active = row['status'] in ('queued', 'reading') and row['expires_at'] > time.time()
    if (row['status'] == 'expired' and state != 'unavailable') or (row['expires_at'] <= time.time() and not row['scan_id']):
        state, message = 'unavailable', 'The eBay session check expired. Retry when the Mac is online and eBay is signed in.'
    try:
        if row['expected_account'] != expected_account(db):
            state, message, active = 'unavailable', 'The linked eBay account changed. Start a new session check.', False
    except ValueError:
        state, message, active = 'unavailable', 'The linked eBay accounts disagree. Personalized sources remain unavailable.', False
    return dict(request_id=row['id'], state=state, message=message or 'Checking eBay on your Mac…',
                active=active, expires_at=utc(row['expires_at']), scan_id=row['scan_id'])


def finish_session_attempt(db, payload):
    """A waiting attempt never becomes a successful or empty feed."""
    ident = payload.get('request_id') if isinstance(payload, dict) else None
    if not isinstance(ident, str):
        return False
    row = db.execute('SELECT r.*,s.request_id FROM ebay_market_requests r JOIN ebay_market_sessions s ON s.request_id=r.id WHERE r.id=?', (ident,)).fetchone()
    if not row:
        return False
    if row['expected_account'] != expected_account(db):
        raise ValueError('The linked eBay account changed during the session check.')
    if row['status'] != 'reading' or row['expires_at'] <= time.time():
        raise ValueError('The eBay session request is no longer active.')
    session = payload.get('session')
    if not isinstance(session, dict) or session.get('state') not in ('ready', 'sign_in_required', 'challenge_required', 'unavailable'):
        raise ValueError('The browser did not report a supported session check.')
    state = session['state']
    if state == 'ready':
        if not payload.get('account') or payload.get('account', '').lower() != row['expected_account']:
            raise ValueError('The browser account does not match the linked account.')
        return False  # Complete validates and stores the observed snapshot first.
    if payload.get('items') or payload.get('account'):
        raise ValueError('An unavailable session cannot supply personalized cards.')
    messages = {
        'sign_in_required': 'eBay is open in the default browser on your Mac. Complete sign-in there; this scan will continue automatically.',
        'challenge_required': 'eBay needs a security check in the default browser on your Mac. Complete it there; this scan will continue automatically.',
        'unavailable': 'The Mac could not verify eBay. Keep Today online with Chrome as the default browser and its existing Automation access enabled, then retry.'}
    message = messages[state]
    if state == 'unavailable':
        message = {
            'wrong_account': 'The browser is signed in to a different eBay account. Switch to the account already linked to Purchases, then retry.',
            'unsupported_browser': 'This Mac’s existing eBay reader supports Chrome. Set Chrome as the Mac’s default browser, then retry; other browser sessions cannot be read by this connection.',
            'unbound_account': 'Connect the existing eBay Purchases account before using personalized market sources.',
        }.get(session.get('reason'), message)
    waiting = state in ('sign_in_required', 'challenge_required')
    db.execute('UPDATE ebay_market_sessions SET state=?,message=?,retry_after=?,claimed_at=NULL WHERE request_id=?',
               (state, message, time.time() + 8, ident))
    db.execute('UPDATE ebay_market_requests SET status=? WHERE id=?', ('queued' if waiting else 'expired', ident))
    return True


def cards(db, ident):
    result = []
    for row in db.execute('SELECT * FROM ebay_market_cards WHERE request_id=? ORDER BY rowid', (ident,)):
        card = dict(row)
        card['sources'] = [r[0] for r in db.execute('SELECT source FROM ebay_market_card_sources WHERE request_id=? AND item_id=? ORDER BY source', (ident, row['item_id']))]
        result.append(card)
    return result


def get_result(db, ident):
    row = db.execute('SELECT * FROM ebay_market_requests WHERE id=?', (ident,)).fetchone()
    if not row or row['status'] != 'done':
        return None
    return cards(db, ident), json.loads(row['source_status'])


def recent_card(db, url, max_age=FRESH_SECONDS):
    ident = item_id(url)
    if not ident:
        return None
    row = db.execute('SELECT c.*,r.observed_at,r.expected_account FROM ebay_market_cards c '
                     'JOIN ebay_market_requests r ON r.id=c.request_id '
                     "WHERE c.item_id=? AND r.status='done' AND r.observed_at>=? ORDER BY r.observed_at DESC LIMIT 1",
                     (ident, time.time() - max_age)).fetchone()
    if not row:
        return None
    try:
        account = expected_account(db)
    except ValueError:
        return None
    if account and row['expected_account'] != account:
        return None
    out = dict(row)
    out['sources'] = [r[0] for r in db.execute('SELECT source FROM ebay_market_card_sources WHERE request_id=? AND item_id=? ORDER BY source', (row['request_id'], ident))]
    return out


def live_probe(db, url):
    row = recent_card(db, url)
    if not row or not row['listing_checked_at'] or row['listing_checked_at'] < time.time() - FRESH_SECONDS:
        return None
    if row['live_state'] not in ('live', 'ended') or not row['listing_text']:
        return None
    return dict(state=row['live_state'], status=200, challenged=False,
                length=len(row['listing_text']), final=row['listing_url'],
                checked_at=row['listing_checked_at'], price=row['price'],
                title=row['listing_text'].splitlines()[0], identity_text=row['listing_text'], images=[row['image_url']] if row['image_url'] else [],
                why='Exact listing read in the signed-in eBay browser', browser_observed=True)


def _bounded(raw, key, limit, required=False):
    value = raw.get(key, '')
    if not isinstance(value, str) or len(value) > limit or (required and not value.strip()):
        raise ValueError('Invalid ' + key)
    return value.strip()


def complete(db, payload):
    if not isinstance(payload, dict):
        raise ValueError('Invalid eBay discovery snapshot')
    ident = _bounded(payload, 'request_id', 32, True)
    row = db.execute('SELECT * FROM ebay_market_requests WHERE id=?', (ident,)).fetchone()
    now = time.time()
    if not row or row['status'] != 'reading' or row['expires_at'] < now:
        raise ValueError('The eBay discovery request expired or was already completed')
    observed = timestamp(payload.get('observed_at'))
    if observed is None or not row['requested_at'] - 5 <= observed <= now + 60:
        raise ValueError('The eBay discovery observation is not fresh')
    sources = payload.get('sources')
    if not isinstance(sources, dict) or set(sources) != set(KINDS):
        raise ValueError('Both eBay source states are required')
    clean_sources = {}
    for key in KINDS:
        value = sources[key]
        if not isinstance(value, dict) or value.get('status') not in ('ok', 'partial', 'unavailable'):
            raise ValueError('Invalid eBay source state')
        clean_sources[key] = dict(status=value['status'], message=_bounded(value, 'message', 300))
    raw = payload.get('items')
    if not isinstance(raw, list) or len(raw) > 100:
        raise ValueError('The eBay discovery snapshot exceeds its card limit')
    account = _bounded(payload, 'account', 100).lower()
    needs_account = bool(raw) or any(s['status'] != 'unavailable' for s in clean_sources.values())
    if needs_account and not re.fullmatch(r'[\w.%-]+', account):
        raise ValueError('A signed-in eBay account is required')
    linked = expected_account(db)
    if needs_account and any(a and a != account for a in (linked, row['expected_account'])):
        raise ValueError('The eBay account does not match this collection')
    clean = {}
    for raw_card in raw:
        if not isinstance(raw_card, dict):
            raise ValueError('Invalid eBay card')
        url = _bounded(raw_card, 'listing_url', 2000, True)
        number = item_id(url)
        if number is None or raw_card.get('item_id') != number:
            raise ValueError('An eBay card does not identify an exact listing')
        kinds = raw_card.get('sources')
        if not isinstance(kinds, list) or not kinds or any(k not in KINDS or clean_sources[k]['status'] == 'unavailable' for k in kinds):
            raise ValueError('An eBay card has an unobserved source')
        image = _bounded(raw_card, 'image_url', 2000)
        if image and not re.match(r'^https://i\.ebayimg\.com/', image):
            image = ''
        checked = timestamp(raw_card.get('listing_checked_at'))
        live = raw_card.get('live_state', 'unknown')
        text = _bounded(raw_card, 'listing_text', 8000)
        if live not in ('live', 'ended', 'unknown'):
            raise ValueError('Invalid eBay listing state')
        if live != 'unknown' and (not text or checked is None or not row['requested_at'] - 5 <= checked <= now + 60):
            raise ValueError('Live evidence must come from a fresh exact listing read')
        card = dict(item_id=number, title=_bounded(raw_card, 'title', 500, True),
                    listing_url='https://www.ebay.com/itm/' + number,
                    price=_bounded(raw_card, 'price', 120), image_url=image,
                    source_label=_bounded(raw_card, 'source_label', 150),
                    listing_text=text, live_state=live, listing_checked_at=checked,
                    sources=set(kinds))
        if number in clean:
            saved_image = card['image_url'] or clean[number]['image_url']
            card['sources'].update(clean[number]['sources'])
            if card['live_state'] == 'unknown' and clean[number]['live_state'] != 'unknown':
                saved_sources = card['sources']
                card = dict(clean[number], sources=saved_sources)
            # Keep a validated same-item thumbnail independently of live evidence.
            card['image_url'] = card['image_url'] or saved_image
        clean[number] = card
    for card in clean.values():
        fields = ('item_id','title','listing_url','price','image_url','source_label','listing_text','live_state','listing_checked_at')
        db.execute('INSERT INTO ebay_market_cards(request_id,' + ','.join(fields) + ') VALUES(' + ','.join('?' for _ in range(10)) + ')',
                   [ident] + [card[k] for k in fields])
        db.executemany('INSERT INTO ebay_market_card_sources VALUES(?,?,?)', [(ident, card['item_id'], k) for k in card['sources']])
    db.execute("UPDATE ebay_market_requests SET status='done',observed_at=?,expected_account=?,source_status=? WHERE id=?",
               (observed, account or row['expected_account'], json.dumps(clean_sources), ident))
    db.execute("UPDATE market_scans SET revision=revision+1 WHERE category='banknotes' AND status='running'")
    return len(clean)


def register(app, get_db, on_complete=None, after_complete=None):
    @app.route('/banknotes/market/ebay-feed/request', methods=['POST'])
    def ebay_market_feed_request():
        """Refresh observed cards without launching a model-backed scan."""
        if not enabled():
            abort(404)
        ebay_mail.authenticate()
        db = get_db()
        db.execute('BEGIN IMMEDIATE')
        try:
            row = db.execute("SELECT id FROM ebay_market_requests WHERE status IN ('queued','reading') "
                             "AND expires_at>? ORDER BY requested_at DESC LIMIT 1", (time.time(),)).fetchone()
            ident = row['id'] if row else queue(db)
            db.commit()
            return jsonify(ok=True, request_id=ident), 202
        except ValueError as exc:
            db.rollback()
            return jsonify(error=str(exc)), 409
        except Exception:
            db.rollback()
            raise

    @app.route('/banknotes/market/ebay-feed', methods=['GET', 'POST'])
    def ebay_market_feed():
        if not enabled():
            abort(404)
        ebay_mail.authenticate()
        db = get_db()
        db.execute('BEGIN IMMEDIATE')
        try:
            db.execute("UPDATE ebay_market_requests SET status='expired' WHERE status IN ('queued','reading') AND expires_at<?", (time.time(),))
            if request.method == 'GET':
                db.execute("UPDATE ebay_market_requests SET status='queued' WHERE status='reading' AND expires_at>? AND id IN "
                           "(SELECT request_id FROM ebay_market_sessions WHERE claimed_at<?)", (time.time(), time.time()-120))
                row = db.execute("SELECT r.* FROM ebay_market_requests r LEFT JOIN ebay_market_sessions s ON s.request_id=r.id "
                                 "WHERE r.status='queued' AND (s.request_id IS NULL OR s.retry_after<=?) ORDER BY r.requested_at LIMIT 1", (time.time(),)).fetchone()
                data = None
                if row:
                    db.execute("UPDATE ebay_market_requests SET status='reading' WHERE id=?", (row['id'],))
                    data = dict(id=row['id'], requested_at=utc(row['requested_at']), expires_at=utc(row['expires_at']))
                    session = db.execute('SELECT * FROM ebay_market_sessions WHERE request_id=?', (row['id'],)).fetchone()
                    if session:
                        data['session_recovery'] = dict(open_browser=not bool(session['open_reserved']))
                        db.execute('UPDATE ebay_market_sessions SET open_reserved=1,claimed_at=? WHERE request_id=?', (time.time(),row['id']))
                account = row['expected_account'] if row else expected_account(db)
                db.commit()
                return jsonify(request=data, expected_account=account)
            if request.content_length is None or request.content_length > 1024 * 1024:
                abort(413)
            payload = request.get_json(silent=True)
            if finish_session_attempt(db, payload):
                db.commit()
                return jsonify(ok=True, pending=True, items_accepted=0)
            count = complete(db, payload)
            if on_complete:
                on_complete(db)
            db.execute("UPDATE ebay_market_sessions SET state='ready',message='eBay is signed in. Continuing the requested scan.' WHERE request_id=?", (payload['request_id'],))
            db.commit()
            if after_complete:
                try:
                    after_complete()
                except Exception:
                    app.logger.warning('Accepted eBay feed; photo-label worker will resume after restart')
            return jsonify(ok=True, items_accepted=count)
        except ValueError as exc:
            db.rollback()
            return jsonify(error=str(exc)), 409
        except Exception:
            db.rollback()
            raise
