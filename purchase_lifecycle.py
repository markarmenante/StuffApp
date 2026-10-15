"""Collection purchase phases; delivery evidence never establishes ownership."""
SUPPORTED_CATEGORIES = frozenset(('coins', 'banknotes', 'cameras', 'lenses', 'pens',
    'art', 'items', 'vehicles', 'recordings', 'audio', 'rifles'))
PENDING = ('Ordered', 'Shipped', 'Delivered')
VALUES = (*PENDING, 'Own')
NEXT = dict(zip(VALUES, (*VALUES[1:], None)))


def canonical(value):
    text = str(value or '').strip()
    if not text or text.casefold() in ('own', 'owned'):
        return 'Own'
    return {v.casefold(): v for v in (*PENDING, 'Sold', 'Loaned', 'Gifted', 'Consigned', 'Lost')}.get(text.casefold(), text)


def held(value):
    return canonical(value) in VALUES


def options(existing):
    """Add purchase phases without changing a category's other dispositions."""
    return list(dict.fromkeys([''] + list(VALUES) + [canonical(v) for v in existing if v]))


def resolve(category, row, delivery=None):
    if category not in SUPPORTED_CATEGORIES:
        return None
    row = dict(row or {})
    status = canonical(row.get('status'))
    source = 'collection'
    delivery = delivery or {}
    review = delivery.get('review') or {}
    reason = review.get('reason') or ''
    attention = bool(delivery.get('attention'))
    observed = delivery.get('status')
    if observed and observed not in PENDING:
        reason = reason or ('Purchase status: ' + str(observed) + '. Review the order before progressing.')
        attention = attention or not review.get('dismissed', False)
    if status in PENDING:
        if observed in PENDING:
            status = observed
            source = 'manual' if delivery.get('manual') else 'eBay'
    return dict(status=status, label='Owned' if status == 'Own' else status,
                value=status, next=NEXT.get(status), inspection_required=status in PENDING,
                source=source, attention=attention, review_reason=reason)


def for_record(db, category, row):
    delivery = None
    if category == 'banknotes':
        from ebay_orders import banknote_deliveries
        delivery = banknote_deliveries(db, row['id']).get(row['id'])
    return resolve(category, row, delivery)


def set_manual_delivery(db, category, row, target, previous):
    """Caller owns the write transaction. Keep evidence and owner override distinct."""
    if category != 'banknotes' or target not in PENDING or target == previous:
        return
    from ebay_orders import event
    link = db.execute('SELECT 1 FROM banknote_ebay_links WHERE banknote_id=?', (row['id'],)).fetchone()
    if link:
        db.execute('UPDATE banknote_ebay_links SET manual_status=? WHERE banknote_id=?',
                   (target, row['id']))
        event(db, row['id'], previous, target, 'Owner purchase status')


def status_sql(category, column='status'):
    """Same phase rules as resolve(), for list/search/report filtering only.

    The shipping tables remain authoritative and separate. This expression does
    not persist their projection or invent an Own transition.
    """
    raw = f"LOWER(TRIM(COALESCE({column}, '')))"
    base = f"CASE WHEN {raw} IN ('', 'own', 'owned') THEN 'own' ELSE {raw} END"
    if category != 'banknotes':
        return '(' + base + ')'
    delivery = """SELECT CASE
        WHEN l.manual_status IS NOT NULL THEN lower(l.manual_status)
        WHEN i.attention LIKE 'Multiple purchase rows%'
          OR EXISTS (SELECT 1 FROM ebay_mail_receipts m WHERE m.line_key=i.line_key
                     AND NOT EXISTS (SELECT 1 FROM ebay_purchase_observations p WHERE p.line_key=i.line_key)) THEN NULL
        WHEN i.delivery_status!='Delivered' AND lower(trim(COALESCE(o.status_text,'')))
             IN ('refunded','canceled','cancelled','order canceled','order cancelled') THEN NULL
        ELSE lower(i.delivery_status) END
        FROM banknote_ebay_links l JOIN ebay_order_items i ON i.line_key=l.line_key
        LEFT JOIN ebay_purchase_observations o ON o.line_key=i.line_key
        WHERE l.banknote_id=banknotes.id"""
    return f"(CASE WHEN {raw} IN ('ordered','shipped','delivered') THEN COALESCE(({delivery}),{raw}) ELSE {base} END)"
