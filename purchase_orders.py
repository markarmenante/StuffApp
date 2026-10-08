"""Source-neutral order references from explicitly linked purchase evidence."""
import re
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

import source_documents


def valid_number(value):
    return value is None or (isinstance(value, str) and (not value.strip() or bool(
        re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9 ._/#-]{0,79}', value.strip()))))


def order_reference(db, category, record):
    """Prefer the entered number; never manufacture a marketplace's internal ID."""
    record = dict(record or {})
    saved = record.get('order_number')
    marketplace = record.get('marketplace') or ''
    if not marketplace and category == 'banknotes' and re.fullmatch(r'\d{2}-\d{5}-\d{5}', saved or ''):
        marketplace = 'eBay'
    linked = purchase_orders(db, category, record.get('id'))
    def same_provider(order):
        if marketplace == 'Direct':
            return order['provider'] not in ('VCoins', 'CNG', 'eBay')
        return not marketplace or order['provider'] == marketplace
    if saved is None:
        choices = [o for o in linked if same_provider(o)]
        return choices[0] if len(choices) == 1 else dict(number='', url=None, provider=marketplace, kind='order')
    number = saved.strip()
    result = dict(number=number, url=None, provider=marketplace, kind='order')
    if not number:
        return result
    matches = [o for o in linked if o['number'].casefold() == number.casefold()
               and same_provider(o)]
    if len(matches) == 1:
        return matches[0]
    if marketplace == 'eBay' and re.fullmatch(r'\d{2}-\d{5}-\d{5}', number):
        return dict(result, url='https://order.ebay.com/ord/show?orderId=' + number)
    if marketplace in ('VCoins', 'CNG'):
        for row in db.execute("SELECT url,title,kind FROM purchase_source_archives WHERE kind IN ('order','invoice')"):
            order = archive_order(row['url'], row['title'], row['kind'])
            if order and order['provider'] == marketplace and order['number'].casefold() == number.casefold():
                matches.append(order)
        remote = {o['url']: o for o in matches if not o['url'].startswith('/uploads/')}
        if len(remote) == 1:
            return next(iter(remote.values()))
        local = {o['url']: o for o in matches}
        if len(local) == 1:
            return next(iter(local.values()))
    return result


def ebay_item_for_order(db, category, record):
    """An order narrows the search, but item identity and uniqueness still apply."""
    record = dict(record)
    number = (record.get('order_number') or '').strip()
    if category != 'banknotes' or record.get('marketplace') not in (None, '', 'eBay') or not number:
        return None
    from ebay_matching import comparison, profile
    from ebay_orders import unverified_email_keys
    excluded = unverified_email_keys(db)
    items = [dict(r) for r in db.execute('SELECT * FROM ebay_order_items WHERE order_id=? AND ignored=0', (number,))
             if r['line_key'] not in excluded]
    links = [dict(r) for r in db.execute('SELECT * FROM banknote_ebay_links')]
    occupied = {link['line_key'] for link in links if link['banknote_id'] != record['id']}
    bundle = re.compile(r'\b(?:lot|set|bundle|pair)\s*(?:of\s*)?[2-9]\d*\b|\bpair of\b'
                        r'|\b[2-9]\d*\s+(?:consecutive\s+)?(?:serial\s+)?(?:notes|banknotes)\b', re.I)
    candidates = [item for item in items if item['line_key'] not in occupied
                  and item['quantity'] == 1 and not item['attention']
                  and not bundle.search(item['title'])
                  and comparison(record, item, profile(item['title']), set(),
                                 allow_missing_identity=True)]
    # A blank record cannot select one of several purchases just because a sibling is linked.
    if len(candidates) == 1 and (len(items) == 1 or (record.get('country') and record.get('denomination'))):
        return candidates[0]
    return None


def ebay_listing_for_order(db, category, record):
    item = ebay_item_for_order(db, category, record)
    return 'https://www.ebay.com/itm/' + item['item_id'] if item else None


def source_priority(provider, category='coins'):
    preferred = ('VCoins', 'CNG', 'eBay') if category == 'coins' else ('eBay', 'VCoins', 'CNG')
    return preferred.index(provider) if provider in preferred else len(preferred)


def archive_order(url, title, kind):
    """A source's printed number is not its listing, lot or internal page ID."""
    if kind not in ('order', 'invoice') or not isinstance(url, str):
        return None
    local = bool(re.fullmatch(r'/uploads/[A-Za-z0-9_-]+\.pdf', url, re.I))
    if not local and not source_documents.safe_remote(url):
        return None
    match = re.fullmatch(
        r'\s*(?P<provider>[\w][\w .&\'()-]{0,79}?)\s+'
        r'(?P<kind>order(?: receipt)?|invoice|receipt)\s*(?:number|no\.?)?\s*[:#]?\s*'
        r'(?P<number>[A-Za-z0-9][A-Za-z0-9._/-]{0,63})\s*(?:\.pdf)?\s*',
        title or '', re.I)
    if not match or not re.search(r'\d', match['number']):
        return None
    provider = match['provider'].strip()
    if re.search(r'\b(?:possible|uncertain|unverified|candidate|comparison)\b', provider, re.I):
        return None
    provider = {'vcoins': 'VCoins', 'cng': 'CNG', 'ebay': 'eBay', 'ma-shops': 'MA-Shops'}.get(
        provider.lower(), provider)
    number = re.sub(r'\.pdf$', '', match['number'], flags=re.I)
    if provider == 'VCoins' and not re.fullmatch(r'\d+-\d+', number):
        return None
    if provider == 'eBay' and not re.fullmatch(r'\d{2}-\d{5}-\d{5}', number):
        return None
    if not local:
        parts = urlsplit(url)
        host = parts.hostname.removeprefix('www.')
        if host != {'VCoins': 'vcoins.com', 'CNG': 'cngcoins.com',
                    'eBay': 'order.ebay.com', 'MA-Shops': 'ma-shops.com'}.get(provider):
            return None
        if provider == 'VCoins':
            if not re.fullmatch(r'/[a-z]{2}/MyAccount/(?:ShowOrder|Invoice)\.aspx', parts.path, re.I):
                return None
            ids = parse_qs(parts.query).get('IdOrder', [])
            if len(ids) != 1 or not re.fullmatch(r'\d+', ids[0]):
                return None
        elif provider == 'eBay':
            if parts.path != '/ord/show' or parse_qs(parts.query).get('orderId') != [number]:
                return None
        elif provider == 'CNG':
            # Public CoinID / LOT_ID pages describe lots, not the owner's order.
            if not parts.path.lower().endswith('.pdf'):
                return None
        elif not parts.path.lower().endswith('.pdf'):
            return None
    reference_kind = 'invoice' if match['kind'].lower() == 'invoice' else 'order'
    if provider == 'VCoins' and not local:
        # Invoice and order pages share the verified internal order identifier.
        language = parts.path.split('/')[1]
        url = urlunsplit(('https', 'www.vcoins.com', f'/{language}/MyAccount/ShowOrder.aspx',
                         urlencode({'IdOrder': ids[0]}), ''))
        reference_kind = 'order'
    return dict(provider=provider, number=number, url=url, kind=reference_kind)


def purchase_orders(db, category, record_id):
    from original_listings import ebay_purchase_orders
    if category not in source_documents.TABLES or not record_id:
        return []
    orders = [dict(order, provider='eBay', kind='order')
              for order in ebay_purchase_orders(db, category, record_id)]
    table, key = source_documents.TABLES[category]
    for row in db.execute(f'SELECT a.url,a.title,a.kind FROM {table} l '
                          f'JOIN purchase_source_archives a ON a.url=l.url WHERE l.{key}=?', (record_id,)):
        order = archive_order(row['url'], row['title'], row['kind'])
        if order:
            orders.append(order)
    for row in db.execute("SELECT title,filename FROM record_documents WHERE category=? AND record_id=? "
                          "AND doc_set='main'", (category, record_id)):
        if row['filename']:
            order = archive_order('/uploads/' + row['filename'], row['title'], 'invoice')
            if order:
                orders.append(order)
    # Prefer a live exact order/invoice link over its archived PDF, with one
    # entry per marketplace and printed number. Never promote review candidates.
    orders.sort(key=lambda o: (source_priority(o['provider'], category), o['provider'], o['number'],
                               o['url'].startswith('/uploads/'), o['kind'] != 'order', o['url']))
    unique = {}
    for order in orders:
        unique.setdefault((order['provider'], order['number']), order)
    return list(unique.values())
