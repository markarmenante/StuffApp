"""A read-only handoff to the exact eBay purchase after manual inspection.

Opening this page never leaves feedback, changes a rating, or writes ownership.
The transition controller decides when to open it; it is safe to reopen later.
"""
import re
from urllib.parse import quote, urlsplit, parse_qs, urlencode

from flask import abort, make_response, render_template, request

import purchase_orders

COMMENT = 'Banknote as described. Very smooth transaction.'
ORDER_ID = re.compile(r'\d{2}-\d{5}-\d{5}')
ITEM_ID = re.compile(r'\d{9,15}')


def _unavailable(message):
    return dict(state='unavailable', message=message, url=None, order_url=None,
                comment=COMMENT, rating='Positive', stars=5)


def handoff(db, category, record):
    """Return reusable handoff data from one verified saved purchase association.

    A local ``purchases:order:item`` key is never an eBay transaction ID. The
    order page lets eBay identify its feedback action without inventing one.
    """
    if category != 'banknotes':
        return None
    record = dict(record or {})
    record_id = record.get('id')
    if not isinstance(record_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', record_id):
        return _unavailable('The banknote record could not be identified.')
    if str(record.get('status') or '').strip().lower() not in ('own', 'owned'):
        return _unavailable('Inspect this banknote and mark it Owned before starting seller feedback.')
    if (record.get('marketplace') or '').strip().lower() not in ('', 'ebay'):
        return _unavailable('This banknote is not linked to an eBay purchase.')

    rows = db.execute(
        'SELECT i.line_key,i.order_id,i.item_id,i.title,i.seller,i.quantity,i.ignored '
        'FROM banknote_ebay_links l JOIN ebay_order_items i ON i.line_key=l.line_key '
        'WHERE l.banknote_id=?', (record_id,)).fetchall()
    if len(rows) != 1:
        return _unavailable('An exact eBay purchase must be linked before seller feedback can start.')
    item = dict(rows[0])
    if item['ignored'] or item['quantity'] != 1:
        return _unavailable('This purchase needs an individual banknote match before seller feedback can start.')
    order_id, item_id = item['order_id'], item['item_id']
    if (not isinstance(order_id, str) or not ORDER_ID.fullmatch(order_id)
            or not isinstance(item_id, str) or not ITEM_ID.fullmatch(item_id)):
        return _unavailable('The saved eBay purchase has no supported exact order link.')
    duplicates = db.execute(
        'SELECT COUNT(*) FROM ebay_order_items WHERE order_id=? AND item_id=? AND ignored=0',
        (order_id, item_id)).fetchone()[0]
    linked = db.execute('SELECT COUNT(*) FROM banknote_ebay_links WHERE line_key=?',
                        (item['line_key'],)).fetchone()[0]
    if duplicates != 1 or linked != 1:
        return _unavailable('More than one saved purchase matches this banknote. Review the match first.')
    saved_number = record.get('order_number')
    if saved_number is not None and saved_number.strip() != order_id:
        return _unavailable('The banknote order number and its linked eBay purchase do not match.')

    # The exact link supplies a missing printed number without altering the record.
    # An unrelated repeat purchase of the same listing must not replace this order.
    reference_record = dict(record, order_number=order_id, marketplace='eBay')
    reference = purchase_orders.order_reference(db, category, reference_record)
    order_url = reference.get('url') if reference else None
    try:
        parsed = urlsplit(order_url or '')
        exact = (reference.get('provider') == 'eBay' and reference.get('number') == order_id
                 and parsed.scheme == 'https' and parsed.netloc == 'order.ebay.com'
                 and parsed.path == '/ord/show' and not parsed.fragment
                 and parse_qs(parsed.query, keep_blank_values=True) == {'orderId': [order_id]})
    except (ValueError, TypeError, AttributeError):
        exact = False
    if not exact:
        return _unavailable('An exact eBay order link is not available. Review the purchase match first.')
    return dict(state='ready',
                url='/banknotes/' + quote(record_id, safe='') + '/feedback?'
                    + urlencode({'order': order_id, 'item': item_id}),
                order_url=order_url, order_id=order_id, item_id=item_id,
                item_title=str(item['title'] or '')[:500], seller=str(item['seller'] or '')[:150],
                comment=COMMENT, rating='Positive', stars=5,
                message='Open this purchase on eBay and choose Leave feedback. Submit the feedback there.')


def register(app, get_db, require_owner, can_see_row):
    @app.get('/banknotes/<record_id>/feedback', endpoint='banknote_feedback_handoff')
    def page(record_id):
        require_owner()
        db = get_db()
        row = db.execute('SELECT * FROM banknotes WHERE id=?', (record_id,)).fetchone()
        if row is None or not can_see_row('banknotes', row):
            abort(404)
        result = handoff(db, 'banknotes', row)
        # A reopened handoff remains bound to the purchase that triggered it.
        if 'order' in request.args or 'item' in request.args:
            if (result['state'] != 'ready'
                    or request.args.getlist('order') != [result.get('order_id')]
                    or request.args.getlist('item') != [result.get('item_id')]):
                result = _unavailable('The linked purchase has changed. Return to the banknote and review its purchase match.')
        response = make_response(render_template(
            'feedback_handoff.html', feedback=result,
            record_url='/banknotes/' + quote(record_id, safe='')))
        response.headers['Cache-Control'] = 'private, no-store'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['X-Robots-Tag'] = 'noindex, nofollow'
        return response
