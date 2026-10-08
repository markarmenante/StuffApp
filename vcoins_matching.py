"""Match captured VCoins order lines without changing collection records."""
from collections import Counter
from datetime import datetime
from difflib import SequenceMatcher
import re
import unicodedata


def normalized(value):
    text = unicodedata.normalize('NFKD', str(value or ''))
    return re.sub(r'[^a-z0-9]+', ' ', text.encode('ascii', 'ignore').decode().lower()).strip()


def dealer(value):
    return re.sub(r'\b(coins?|numismatics?|nusmatics|auction|inc|llc|ltd|gmbh|co|kg)\b',
                  '', normalized(value)).strip()


def price(value):
    text = '' if value is None else str(value)
    currency = next((code for pattern, code in (
        (r'\u20ac|\bEUR\b', 'EUR'), (r'\u00a3|\bGBP\b', 'GBP'),
        (r'\bAUD\b', 'AUD'), (r'\bCAD\b', 'CAD'), (r'\bCHF\b', 'CHF'))
        if re.search(pattern, text)), 'USD')
    amount = re.search(r'(\d[\d,]*(?:\.\d+)?)', text)
    return (currency, float(amount[1].replace(',', ''))) if amount else None


def evidence(coin, order, item, listing, sku):
    name = dealer(coin.get('vendor'))
    if not name or SequenceMatcher(None, name, dealer(order['columns'][2])).ratio() < .80:
        return None
    try:
        date = datetime.strptime(order['columns'][0], '%m/%d/%Y').date()
        stored = datetime.strptime(coin.get('purchase_date'), '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return None
    gap = abs((date - stored).days)
    if gap > 7:
        return None

    text = ' '.join(str(coin.get(key) or '') for key in ('description', 'coin_references'))
    source = ' '.join(filter(None, (item['title'], listing.get('description'), listing.get('text'))))
    source_normalized = normalized(source)
    title, description = normalized(item['title']), normalized(coin.get('description'))
    sku_match = bool(len(sku) >= 5 and re.search('[A-Za-z]', sku) and re.search(r'\d', sku)
                     and re.search(r'(?<![A-Za-z0-9])' + re.escape(sku) + r'(?![A-Za-z0-9])', text, re.I))
    certificate = bool(coin.get('slab_number') and normalized(coin['slab_number']) in source_normalized)
    exact_description = len(description) >= 100 and description in source_normalized
    full_title = len(title) >= 25 and title in description
    pedigree = re.search(r'Pedigree:\s*(.+?)(?:\n|References:|$)', coin.get('coin_references') or '', re.I)
    exact_pedigree = bool(pedigree and len(normalized(pedigree[1])) >= 35
                          and normalized(pedigree[1]) in source_normalized)
    weight = re.search(r'(\d+(?:\.\d+)?)\s*(?:g|gm|grams?)\b', source, re.I)
    diameter = re.search(r'(\d+(?:\.\d+)?)\s*mm\b', source, re.I)
    weight_gap = abs(float(weight[1]) - float(coin['weight'])) if weight and coin.get('weight') else None
    size_gap = abs(float(diameter[1]) - float(coin['size'])) if diameter and coin.get('size') else None
    same_weight = weight_gap is not None and weight_gap < .011
    same_size = size_gap is not None and size_gap <= .1
    same_price = price(coin.get('price')) is not None and price(coin.get('price')) == price(item['price'])
    mint = bool(coin.get('mint') and normalized(coin['mint']) in title)
    denomination = bool(coin.get('denomination') and normalized(coin['denomination']) in title)
    metrics = [label for label, matches in (
        ('dealer SKU', sku_match), ('certificate', certificate),
        ('description', exact_description or full_title), ('pedigree', exact_pedigree),
        ('price', same_price), ('weight', same_weight), ('diameter', same_size),
        ('mint', mint), ('denomination', denomination)) if matches]

    # One distinctive fact is enough; less distinctive facts need a pair.
    distinctive = sku_match or certificate or exact_description or full_title or exact_pedigree or same_price or same_weight
    if not distinctive and sum((same_size, mint, denomination)) < 2:
        return None
    strong_identity = sku_match or certificate or exact_pedigree or exact_description
    if not strong_identity and ((weight_gap is not None and weight_gap > .03)
                                or (size_gap is not None and size_gap > 1)):
        return None
    return dict(coin=coin, reason='Vendor, date within seven days and ' + ', '.join(metrics),
                metrics=metrics, sku=sku, date_gap=gap, same_weight=same_weight,
                same_size=same_size, source_description=source)


def match_orders(coins, orders, invoices=(), listings=()):
    """Return unique matches and unresolved lines; leave writes to an audited importer."""
    invoices = {invoice['number']: invoice for invoice in invoices}
    listings = {listing['url']: listing for listing in listings}
    proposals = []
    for order in orders:
        invoice = invoices.get(order['columns'][1], {})
        for index, item in enumerate(order['items']):
            if item['quantity'] != 1:
                continue
            rows = [row for row in invoice.get('items', [])
                    if normalized(row['desc']) == normalized(item['title'])]
            sku = rows[0]['sku'] if len(rows) == 1 else ''
            listing = listings.get(item['listing'], {})
            if listing.get('sku'):
                if sku and normalized(sku) != normalized(listing['sku']):
                    proposals.append(dict(order=order, item=item, index=index, candidates=[],
                                          conflict='Invoice and listing SKUs differ'))
                    continue
                sku = listing['sku']
            candidates = [candidate for coin in coins
                          if (candidate := evidence(coin, order, item, listing, sku))]
            proposals.append(dict(order=order, item=item, index=index, candidates=candidates))
    single = [proposal for proposal in proposals if len(proposal['candidates']) == 1]
    counts = Counter(proposal['candidates'][0]['coin']['id'] for proposal in single)
    matches, unresolved = [], []
    for proposal in proposals:
        candidates = proposal['candidates']
        if (len(candidates) == 1 and counts[candidates[0]['coin']['id']] == 1
                and candidates[0]['coin'].get('marketplace') in (None, '', 'VCoins')):
            matches.append(proposal)
        else:
            unresolved.append(proposal)
    return dict(matches=matches, unresolved=unresolved, orders=len(orders))


if __name__ == '__main__':
    import argparse
    import json
    from pathlib import Path

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--coins', type=Path, required=True, help='Saved coin snapshot JSON')
    parser.add_argument('--orders', type=Path, required=True, help='Captured VCoins orders JSON')
    parser.add_argument('--invoices', type=Path, help='Captured invoices JSON')
    parser.add_argument('--listings', type=Path, help='Captured exact listings JSON')
    parser.add_argument('--output', type=Path, required=True, help='Match plan JSON; no database writes')
    args = parser.parse_args()
    result = match_orders(
        json.loads(args.coins.read_text()), json.loads(args.orders.read_text())['orders'],
        json.loads(args.invoices.read_text())['invoices'] if args.invoices else (),
        json.loads(args.listings.read_text())['listings'] if args.listings else ())
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps({key: len(value) if isinstance(value, list) else value
                      for key, value in result.items()}))
