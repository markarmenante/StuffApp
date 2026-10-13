"""Exact authenticated order-unit evidence, separate from listing asking prices."""
from datetime import datetime, timezone
from decimal import Decimal
import re
import time

# '$' preserves an observed display symbol without asserting USD.
SYMBOLS = {'$': '$', 'USD': '$', 'EUR': '€', 'GBP': '£'}


def save(db, capture, items, requested_at):
    if capture is None:
        return
    if not isinstance(capture, dict) or len(items) != 1 or items[0]['quantity'] != 1 or items[0].get('identity_ambiguous'):
        raise ValueError('A receipt amount requires one unambiguous purchased item')
    item = items[0]
    url = 'https://order.ebay.com/ord/show?orderId=' + item['order_id']
    if (capture.get('order_id') != item['order_id'] or capture.get('item_id') != item['item_id']
            or capture.get('quantity') != 1 or capture.get('url') != url):
        raise ValueError('Receipt identity does not match the requested purchase')
    currency, amount, evidence = (capture.get(k) for k in ('currency', 'unit_amount', 'evidence'))
    if currency not in SYMBOLS or not isinstance(amount, str) or not re.fullmatch(r'\d{1,7}\.\d{2}', amount):
        raise ValueError('Receipt unit amount or currency is invalid')
    cents = int(Decimal(amount) * 100)
    if cents <= 0 or cents > 100000000:
        raise ValueError('Receipt unit amount is outside the supported range')
    if not isinstance(evidence, str) or not 30 <= len(evidence) <= 2500:
        raise ValueError('Receipt unit amount lacks bounded source evidence')
    try:
        observed = datetime.fromisoformat(str(capture.get('observed_at') or '').replace('Z', '+00:00'))
        if observed.tzinfo is None:
            raise ValueError()
        stamp = observed.timestamp()
    except (ValueError, TypeError):
        raise ValueError('Receipt observation time is invalid') from None
    if not requested_at - 5 <= stamp <= time.time() + 60:
        raise ValueError('Receipt evidence is not from this purchase check')
    stored = db.execute('SELECT * FROM ebay_order_items WHERE order_id=? AND item_id=? AND ignored=0',
                        (item['order_id'], item['item_id'])).fetchall()
    if len(stored) != 1 or stored[0]['quantity'] != 1 or stored[0]['attention']:
        raise ValueError('Receipt purchase requires review')
    currency_tokens = {'$': r'\$', 'USD': r'US\s*\$|USD', 'EUR': r'EUR|€', 'GBP': r'GBP|£'}
    if not re.search(r'(?:Unit price\s+(?:' + currency_tokens[currency] + r')|Currency:\s*' + re.escape(currency) + r'(?:\s|$))', evidence, re.I):
        raise ValueError('Receipt currency lacks explicit source evidence')
    # Reuse the exact-item receipt parser. It excludes totals, other orders,
    # sibling items, coupons/refunds, missing currency and ambiguous amounts.
    from banknote_check_sources import ebay_receipt_unit_price
    price = ebay_receipt_unit_price(evidence, stored[0])
    expected = SYMBOLS[currency] + format(Decimal(amount), ',.2f')
    if expected.endswith('.00'):
        expected = expected[:-3]
    if price != expected:
        raise ValueError('Receipt unit amount disagrees with its source evidence')
    db.execute('INSERT INTO ebay_purchase_prices(line_key,currency,unit_amount_minor,source_url,observed_at,evidence) '
               'VALUES(?,?,?,?,?,?) ON CONFLICT(line_key) DO UPDATE SET currency=excluded.currency,'
               'unit_amount_minor=excluded.unit_amount_minor,source_url=excluded.source_url,'
               'observed_at=excluded.observed_at,evidence=excluded.evidence',
               (stored[0]['line_key'], currency, cents, url, observed.astimezone(timezone.utc).isoformat(), evidence))


def for_item(db, item):
    if not item or item['quantity'] != 1 or item['attention']:
        return None
    row = db.execute('SELECT * FROM ebay_purchase_prices WHERE line_key=?', (item['line_key'],)).fetchone()
    if not row:
        return None
    amount = format(Decimal(row['unit_amount_minor']) / 100, ',.2f')
    price = SYMBOLS[row['currency']] + (amount[:-3] if amount.endswith('.00') else amount)
    return dict(row, price=price)
