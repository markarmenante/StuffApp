"""Explicit owner Delete commands, bound to one eBay account and listing.

Suppression is immediate; only a fresh browser readback confirms unwatching.
An abandoned claim is observation-only: an uncertain toggle is never repeated.
"""
import re
import time
import uuid
from urllib.parse import urlsplit

from flask import abort, jsonify, request
import ebay_mail
import market_ebay_feed as feed
import market_scan

TTL_SECONDS = 600
LEASE_SECONDS = 120
ACTIVE = ('queued', 'claimed')
RESULTS = ('removed', 'already_unwatched', 'sign_in_required', 'challenge_required', 'uncertain', 'failed')
MESSAGES = {
    'queued': 'Deleted here. eBay watchlist removal pending.',
    'claimed': 'Deleted here. Checking removal from your eBay watchlist…',
    'removed': 'Deleted here and removed from your eBay watchlist.',
    'already_unwatched': 'Deleted here. This item is not on your eBay watchlist.',
    'sign_in_required': 'Deleted here. The eBay sign-in wait ended before removal was confirmed. Sign in and check the exact item on eBay.',
    'challenge_required': 'Deleted here. The eBay security-check wait ended before removal was confirmed. Complete the check and review the exact item on eBay.',
    'uncertain': 'Deleted here. eBay watchlist removal could not be confirmed. Check the exact listing on eBay.',
    'failed': 'Deleted here. eBay watchlist removal could not be completed. Check the exact listing on eBay.',
    'expired': 'Deleted here. The eBay removal request expired before confirmation. Check the exact listing on eBay.',
    'unavailable': 'Deleted here. The linked eBay connection is unavailable; watchlist removal is unconfirmed.',
}


def item_id(url):
    """Validate the original URL before any permissive display canonicalization."""
    try:
        p = urlsplit(str(url or ''))
        host = (p.hostname or '').lower()
        host = re.sub(r'^(?:www|m)\.', '', host)
        if p.scheme != 'https' or p.username or p.password or p.port not in (None, 443):
            return None
        if not re.fullmatch(r'ebay\.(?:com|co\.uk|de|fr|it|es|ca|com\.au|at|ch|ie|nl|be|com\.sg|com\.hk)', host):
            return None
        match = re.fullmatch(r'/itm/(?:[^/]+/)?(\d{9,15})/?', p.path)
        return match.group(1) if match else None
    except ValueError:
        return None


def init_schema(db):
    db.execute('''CREATE TABLE IF NOT EXISTS ebay_unwatch_commands (
        id TEXT PRIMARY KEY, account TEXT NOT NULL, item_id TEXT NOT NULL,
        requested_at REAL NOT NULL, expires_at REAL NOT NULL,
        state TEXT NOT NULL CHECK(state IN ('queued','claimed','removed','already_unwatched',
          'sign_in_required','challenge_required','uncertain','failed','expired')),
        claimed_at REAL, claim_token TEXT, verify_only INTEGER NOT NULL DEFAULT 0 CHECK(verify_only IN (0,1)),
        observed_at REAL, UNIQUE(account,item_id)
    )''')
    db.execute('CREATE INDEX IF NOT EXISTS idx_ebay_unwatch_pending ON ebay_unwatch_commands(state,requested_at)')
    db.commit()


def public(row, now=None):
    row = dict(row)
    state = row['state']
    if state in ACTIVE and row['expires_at'] <= (time.time() if now is None else now):
        state = 'expired'
    return dict(id=row['id'], item_id=row['item_id'], state=state, active=state in ACTIVE,
                message=MESSAGES[state], listing_url='https://www.ebay.com/itm/' + row['item_id'])


def enqueue(db, url, authorized=False):
    """Called only inside a new explicit owner Delete transaction; never on GET/init."""
    number = item_id(url)
    if not number:
        return None
    unavailable = dict(id=None, item_id=number, state='unavailable', active=False,
                       message=MESSAGES['unavailable'], listing_url='https://www.ebay.com/itm/' + number)
    if not authorized:
        unavailable['message'] = 'Deleted here. This session could not authorize eBay watchlist removal. Check your sign-in at StuffApp’s usual address.'
        return unavailable
    if not feed.enabled():
        return unavailable
    try:
        account = feed.expected_account(db)
    except ValueError:
        return unavailable
    if not account:
        return unavailable
    now = time.time()
    db.execute('INSERT OR IGNORE INTO ebay_unwatch_commands(id,account,item_id,requested_at,expires_at,state) '
               "VALUES(?,?,?,?,?,'queued')", (uuid.uuid4().hex, account, number, now, now + TTL_SECONDS))
    return public(db.execute('SELECT * FROM ebay_unwatch_commands WHERE account=? AND item_id=?', (account, number)).fetchone(), now)


def dismiss(db, url, source_url=None, category='banknotes', authorized=False):
    """Publish suppression and the explicit removal intent atomically."""
    result = []
    key = market_scan.dismiss_listing(db, category, url,
             on_dismiss=lambda connection: result.append(enqueue(connection, url if source_url is None else source_url, authorized=authorized)))
    return key, result[0]


def status(db):
    """Read-only owner status, including pending work after a page/process restart."""
    try:
        account = feed.expected_account(db)
    except ValueError:
        account = None
    rows = db.execute('SELECT * FROM ebay_unwatch_commands WHERE requested_at>? ORDER BY requested_at DESC LIMIT 20',
                      (time.time() - 86400,)).fetchall()
    requests = []
    for row in rows:
        if row['account'] != account and row['state'] not in ACTIVE:
            continue  # A previous account's success must not describe this account.
        data = public(row)
        if row['account'] != account and data['active']:
            data.update(state='unavailable', active=False, message=MESSAGES['unavailable'])
        requests.append(data)
    return dict(requests=requests, active=any(row['active'] for row in requests))


def claim(db):
    now = time.time()
    account = feed.expected_account(db)
    db.execute("UPDATE ebay_unwatch_commands SET state='expired' WHERE state IN ('queued','claimed') AND expires_at<=?", (now,))
    db.execute("UPDATE ebay_unwatch_commands SET state='failed' WHERE state IN ('queued','claimed') AND account IS NOT ?", (account,))
    row = db.execute("SELECT * FROM ebay_unwatch_commands WHERE account=? AND expires_at>? AND "
                     "(state='queued' OR (state='claimed' AND claimed_at<?)) ORDER BY requested_at LIMIT 1",
                     (account, now, now - LEASE_SECONDS)).fetchone()
    if not row:
        return dict(request=None, expected_account=account)
    token = uuid.uuid4().hex
    verify_only = row['state'] == 'claimed' or bool(row['verify_only'])
    db.execute("UPDATE ebay_unwatch_commands SET state='claimed',claimed_at=?,claim_token=?,verify_only=? WHERE id=?",
               (now, token, int(verify_only), row['id']))
    return dict(expected_account=account, request=dict(id=row['id'], action='unwatch', item_id=row['item_id'],
                listing_url='https://www.ebay.com/itm/' + row['item_id'], claim_token=token,
                requested_at=feed.utc(row['requested_at']), expires_at=feed.utc(row['expires_at']), verify_only=verify_only))


def complete(db, payload):
    if not isinstance(payload, dict):
        raise ValueError('Invalid eBay removal result')
    ident = payload.get('request_id')
    if not isinstance(ident, str) or not re.fullmatch(r'[a-f0-9]{32}', ident):
        raise ValueError('Invalid eBay removal request')
    row = db.execute('SELECT * FROM ebay_unwatch_commands WHERE id=?', (ident,)).fetchone()
    if not row or row['state'] != 'claimed' or row['expires_at'] <= time.time():
        raise ValueError('The eBay removal request expired or was already completed')
    if payload.get('claim_token') != row['claim_token'] or payload.get('action') != 'unwatch':
        raise ValueError('The eBay removal claim does not match')
    if row['account'] != feed.expected_account(db):
        raise ValueError('The linked eBay account changed')
    if payload.get('item_id') != row['item_id'] or item_id(payload.get('listing_url')) != row['item_id']:
        raise ValueError('The eBay removal result identifies a different listing')
    state = payload.get('state')
    if state not in RESULTS:
        raise ValueError('Invalid eBay removal state')
    observed = feed.timestamp(payload.get('observed_at'))
    if observed is None or not row['claimed_at'] - 5 <= observed <= min(time.time() + 60, row['expires_at']):
        raise ValueError('The eBay removal observation is not fresh')
    account = payload.get('account')
    if account not in ('', None, row['account']):
        raise ValueError('The browser account does not match')
    if state in ('removed', 'already_unwatched'):
        if account != row['account'] or payload.get('watch_state') != 'not_watching':
            raise ValueError('Removal requires verified exact-item watch state')
        if row['verify_only'] and state == 'removed':
            raise ValueError('A reclaimed request may only verify existing watch state')
    db.execute('UPDATE ebay_unwatch_commands SET state=?,observed_at=? WHERE id=?', (state, observed, row['id']))
    return public(dict(row, state=state))


def register(app, get_db, require_owner, owner_authorized):
    @app.route('/banknotes/market/ebay-unwatch/status')
    def ebay_unwatch_status():
        require_owner()
        response = jsonify(dict(status(get_db()), unwatch_authorized=bool(owner_authorized())))
        response.headers['Cache-Control'] = 'no-store'
        return response

    @app.route('/banknotes/market/ebay-unwatch', methods=['GET', 'POST'])
    def ebay_unwatch_bridge():
        if not feed.enabled():
            abort(404)
        ebay_mail.authenticate()
        db = get_db()
        db.execute('BEGIN IMMEDIATE')
        try:
            if request.method == 'GET':
                data = claim(db)
            else:
                if request.content_length is None or request.content_length > 8192:
                    abort(413)
                data = dict(ok=True, unwatch=complete(db, request.get_json(silent=True)))
            db.commit()
            response = jsonify(data)
            response.headers['Cache-Control'] = 'no-store'
            return response
        except ValueError as exc:
            db.rollback()
            return jsonify(error=str(exc)), 409
        except BaseException:
            db.rollback()
            raise
