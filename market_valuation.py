"""Bounded, attributed Market Scan estimates; presentation never does research.

These are research estimates, not authenticated appraisals. The discovery call
must read its sources; this boundary checks the supplied evidence contract and
keeps an offered price or old free-text `fair` note from becoming an estimate.
"""
import re
import ipaddress
from datetime import date
from decimal import Decimal, InvalidOperation
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


SCHEMA = ('"valuation": {"low": number, "high": number, "currency": str (ISO currency), '
          '"as_of": "YYYY-MM-DD", "confidence": "low"|"medium"|"high", '
          '"grade": str (offered grade and designation), '
          '"adjustments": str (brief grade/variety differences and justified adjustment; required for proxies), '
          '"sources": [{"kind": "sold"|"price_guide", "url": str, "title": str, '
          '"date": "YYYY-MM-DD", "amount": number, "currency": str (same as the estimate), '
          '"grade": str (actual comparable grade and designation), '
          '"match": "exact"|"adjacent_grade"|"related_variety"}]}|null')

PROMPT = """VALUE ESTIMATES: Keep the listing's asking/current price in `price`, separate from `valuation`.
Search in this order: (1) the exact catalogue variety and offered grade/designation; (2) the same variety in adjacent grades; (3) only if those fail, a closely related date/catalogue variety of the same issuer, denomination and design/series. Try common catalogue spelling variants before broadening. A clear listing title can establish catalogue identity and offered grade even when its live page is blocked or structured fields are blank. Distinguish that known offered identity from what the comparable actually sold.
Give a defensible low–high fair market range only from dated sold comparables or an attributed price-guide entry you actually read. Aim for 3–6 recent sales, but a defensible single-sale or guide anchor may support a cautious range. Mark each source match as exact, adjacent_grade, or related_variety. For either nonexact match, use low confidence and a brief valuation.adjustments note naming the actual comparable grade/type, the offered grade/type, and why the range is adjusted or widened. Grade steps and EPQ/PPQ differences are not linear; never invent a percentage premium. Do not substitute a different country, denomination, design, rare signature/prefix, specimen or fancy-serial premium for an ordinary issue. A proxy must be demonstrably comparable; otherwise return valuation:null.
Include each exact source URL, source title, sale/guide date, realized/guide amount, currency and actual comparable grade. Cite the individual lot URL rather than a sale/category/search page. Verify the individual lot's session date from its lot record or auction timetable; never use an arbitrary first or last date of a multi-day auction. If the exact lot date cannot be verified, omit that comparable rather than inventing a date. Sold amounts must state the actual realized price, with buyer-premium treatment in the source title; do not assume a premium is included. Estimate and source amounts must use the same currency; never invent exchange rates.
Use established auction archives (Heritage, Stack's Bowers, Spink, Noonans, Lyn Knight, CNG, Leu, Nomos, Künker, GreatCollections, biddr/sixbid/NumisBids) or exact eBay sold listings; guides may use PMG, PCGS, NGC, Greysheet or NumisMedia. Do not use the candidate's own listing, an active dealer/sponsored ask, a census count, or purchase cost as valuation evidence. Sponsorship and a seller's value claim do not establish market value. If neither direct evidence nor a defensible verified proxy can be read, return valuation:null. Do not invent a number or a source. Older/one-sale/guide-only exact evidence requires low or medium confidence; every proxy requires low confidence. Keep `fair` as a terse evidence note, never a substitute estimate. Observed cards without an external comparable-research step must remain valuation:null unless supplied actual dated sold/guide evidence supports them."""

MAX_ESTIMATE_AGE_DAYS = 366
_CURRENCIES = {'USD', 'EUR', 'GBP', 'CHF', 'CAD', 'AUD', 'NZD', 'JPY', 'CNY',
               'HKD', 'SGD', 'INR', 'SEK', 'NOK', 'DKK', 'ZAR', 'AED', 'BHD',
               'BND', 'BRL', 'CZK', 'HUF', 'IDR', 'KRW', 'MXN', 'MYR', 'PHP',
               'PLN', 'THB', 'TRY', 'TWD'}
_PREFIX = {'USD': '$', 'EUR': '€', 'GBP': '£', 'CHF': 'CHF ', 'CAD': 'C$',
           'AUD': 'A$', 'NZD': 'NZ$', 'JPY': '¥', 'HKD': 'HK$', 'SGD': 'S$'}
_ASKING_SYMBOLS = {'US$': 'USD', 'CA$': 'CAD', 'C$': 'CAD', 'A$': 'AUD',
                   'NZ$': 'NZD', 'HK$': 'HKD', 'S$': 'SGD', 'MX$': 'MXN',
                   'R$': 'BRL', '$': 'USD', '€': 'EUR', '£': 'GBP', '¥': 'JPY',
                   'USD$': 'USD', 'CAD$': 'CAD', 'AUD$': 'AUD', 'AU$': 'AUD',
                   'NZD$': 'NZD', 'HKD$': 'HKD', 'SGD$': 'SGD'}


def _text(value, limit):
    return re.sub(r'\s+', ' ', value).strip()[:limit] if isinstance(value, str) else ''


def _amount(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        amount = Decimal(str(value))
        if not amount.is_finite() or not 0 < amount <= 1_000_000_000:
            return None
        rounded = amount.quantize(Decimal('.01'))
        return float(rounded) if rounded > 0 else None
    except (InvalidOperation, ValueError):
        return None


def _date(value, today):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        return None
    try:
        parsed = date.fromisoformat(value)
        return value if date(1900, 1, 1) <= parsed <= today else None
    except ValueError:
        return None


def _url(value):
    if (not isinstance(value, str) or len(value) > 2000 or
            re.search(r'[\s\x00-\x1f\\]', value)):
        return None
    try:
        url = urlsplit(value.strip())
        if url.scheme not in ('https', 'http') or not url.hostname or url.username or url.password:
            return None
        host = url.hostname.lower().removeprefix('www.')
        if ('.' not in host or not re.fullmatch(r'[a-z0-9.-]+', host) or
                host.endswith(('.local', '.internal', '.localhost', '.test', '.example', '.invalid'))):
            return None
        try:
            ipaddress.ip_address(host)
            return None
        except ValueError:
            pass
        if url.port not in (None, 80, 443):
            return None
        return url, host
    except ValueError:
        return None


def _identity(value):
    parsed = _url(value)
    if not parsed:
        return ''
    url, host = parsed
    # Match the app's market_scan.canonical_url treatment of mobile and all
    # international eBay hosts. One item ID is one offer regardless of locale.
    if host.startswith('ebay.') or '.ebay.' in host:
        match = re.search(r'/itm/(?:[^/]+/)?(\d+)(?:/|$)', url.path)
        if match:
            return 'ebay:' + match.group(1)
    query = [(key, value) for key, value in parse_qsl(url.query)
             if not key.lower().startswith('utm_') and key.lower() not in
             {'fbclid', 'gclid', 'msclkid', '_trksid', '_trkparms'}]
    return host + url.path.rstrip('/') + ('?' + urlencode(sorted(query)) if query else '')


def _source(raw, listing_url, as_of, currency, today):
    if not isinstance(raw, dict):
        return None
    parsed = _url(raw.get('url'))
    if not parsed:
        return None
    url, host = parsed
    kind = raw.get('kind')
    # Research is responsible for source quality. Specialist auction archives
    # are valid too; a domain allowlist would silently discard their evidence.
    if (kind not in ('sold', 'price_guide') or not url.path.strip('/') or
            any(host == root or host.endswith('.' + root)
                for root in ('google.com', 'bing.com', 'duckduckgo.com')) or
            re.search(r'(?:^|/)(?:search|sch|search-results)(?:/|$)', url.path, re.I) or
            any(key.lower() in {'q', 'query', '_nkw', 'search'} for key, _ in parse_qsl(url.query)) or
            _identity(raw['url']) == _identity(listing_url)):
        return None
    title, grade = _text(raw.get('title'), 180), _text(raw.get('grade'), 120)
    match = raw.get('match', 'exact')
    observed = _date(raw.get('date'), today)
    amount = _amount(raw.get('amount'))
    if (match not in ('exact', 'adjacent_grade', 'related_variety') or
            not title or not grade or observed is None or observed > as_of or
            amount is None or raw.get('currency') != currency):
        return None
    return dict(kind=kind, url=urlunsplit((url.scheme, url.netloc, url.path, url.query, '')),
                title=title, date=observed, amount=amount, currency=currency, grade=grade, match=match)


def normalize(value, listing_url='', *, today=None):
    """Return a copied estimate, or None when required evidence is missing."""
    if not isinstance(value, dict):
        return None
    today = today or date.today()
    low, high = _amount(value.get('low')), _amount(value.get('high'))
    currency, confidence = value.get('currency'), value.get('confidence')
    as_of, grade = _date(value.get('as_of'), today), _text(value.get('grade'), 240)
    if (low is None or high is None or low >= high or not isinstance(currency, str) or
            currency not in _CURRENCIES or not isinstance(confidence, str) or
            confidence not in {'low', 'medium', 'high'} or not as_of or not grade or
            not isinstance(value.get('sources'), list)):
        return None
    if (today - date.fromisoformat(as_of)).days > MAX_ESTIMATE_AGE_DAYS:
        return None
    sources, seen = [], set()
    for raw in value['sources'][:12]:
        source = _source(raw, listing_url, as_of, currency, today)
        if source and _identity(source['url']) not in seen:
            sources.append(source)
            seen.add(_identity(source['url']))
        if len(sources) == 6:
            break
    if not sources:
        return None
    proxy = any(source['match'] != 'exact' for source in sources)
    adjustments = _text(value.get('adjustments'), 320)
    if proxy and not adjustments:
        return None
    # Thin or old evidence cannot be presented with high confidence.
    recent_sales = sum(source['kind'] == 'sold' and
                       (today - date.fromisoformat(source['date'])).days <= 1096
                       for source in sources)
    if proxy or not recent_sales:
        confidence = 'low'
    elif recent_sales < 3 and confidence == 'high':
        confidence = 'medium'
    return dict(low=low, high=high, currency=currency, as_of=as_of,
                confidence=confidence, grade=grade, sources=sources,
                adjustments=adjustments, basis='proxy' if proxy else 'direct')


def money(amount, currency):
    digits = f'{amount:,.0f}' if amount == int(amount) else f'{amount:,.2f}'
    return _PREFIX.get(currency, currency + ' ') + digits


def _asking_price(item):
    """Only a fixed ask with one explicit currency/amount, never a bid or FX.

    Saved recommendations already use these currency-bearing price formats.
    Deliberately do not strip arbitrary text: bids, ranges, shipping totals and
    conversion suffixes must not become a misleading asking-price indicator.
    """
    if (str(item.get('sale_type') or '').strip().lower() != 'fixed' or
            item.get('price_kind') not in (None, '', 'asking', 'fixed', 'buy_now')):
        return None
    text = item.get('price')
    if not isinstance(text, str) or len(text) > 120:
        return None
    text = text.strip()
    currency, number = None, ''
    for symbol in sorted(_ASKING_SYMBOLS, key=len, reverse=True):
        # eBay's observed cards use "US $299.00" (including nonbreaking
        # spaces). Keep the currency designator anchored and explicit.
        pattern = (re.escape(symbol[:-1]) + r'[ \u00a0\u202f]*\$'
                   if symbol.endswith('$') else re.escape(symbol))
        match = re.match(pattern, text, re.I)
        if match:
            currency, number = _ASKING_SYMBOLS[symbol], text[match.end():].strip()
            break
    if currency is None:
        match = re.fullmatch(r'([A-Za-z]{3})\s*([\d.,]+)|([\d.,]+)\s+([A-Za-z]{3})', text)
        if match:
            currency = (match[1] or match[4]).upper()
            number = match[2] or match[3]
    if currency not in _CURRENCIES:
        return None
    if re.fullmatch(r'\d+(?:\.\d{1,2})?', number):
        canonical = number
    elif re.fullmatch(r'\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?', number):
        canonical = number.replace(',', '')
    elif re.fullmatch(r'\d+(?:,\d{1,2})', number):
        canonical = number.replace(',', '.')
    elif re.fullmatch(r'\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?', number):
        canonical = number.replace('.', '').replace(',', '.')
    else:
        return None
    amount = Decimal(canonical)
    return (currency, amount) if 0 < amount <= 1_000_000_000 else None


def _comparison(item, value):
    empty = dict(benchmark=None, benchmark_label='', ratio=None, percent=None, band='', title='')
    price = _asking_price(item)
    if price is None or price[0] != value['currency']:
        return empty
    midpoint = (Decimal(str(value['low'])) + Decimal(str(value['high']))) / 2
    asking = price[1]
    # Classify before any presentation rounding, including half-cent midpoints.
    band = 'green' if asking <= midpoint else 'yellow' if asking <= midpoint * Decimal('1.30') else 'red'
    ratio = asking / midpoint
    percent = (ratio - 1) * 100
    decimal_places = max(0, -midpoint.normalize().as_tuple().exponent)
    benchmark_label = (_PREFIX.get(value['currency'], value['currency'] + ' ') +
                       f'{midpoint:,.{max(2, decimal_places) if decimal_places else 0}f}')
    rounded = percent.quantize(Decimal('.01'))
    percent_text = format(rounded, 'f').rstrip('0').rstrip('.') if '.' in format(rounded, 'f') else str(rounded)
    if band == 'green':
        explanation = 'At/below market estimate'
    elif band == 'red' and rounded <= 30:
        explanation = 'Over 30% above market estimate'
    elif rounded == 0:
        explanation = 'Above market estimate'
    else:
        explanation = percent_text + '% above market estimate'
    return dict(benchmark=float(midpoint), benchmark_label=benchmark_label,
                ratio=float(ratio), percent=float(percent), band=band,
                title=f'{explanation} · benchmark {benchmark_label} (range midpoint)')


def display(item, *, today=None):
    """Terse view model for new, cached and observed cards. No I/O or mutation."""
    item = item if isinstance(item, dict) else {}
    value = normalize(item.get('valuation'), item.get('listing_url', ''), today=today)
    if value is None:
        return dict(label='No estimate', evidence=[], as_of='', confidence='', grade='', adjustments='', basis_note='',
                    benchmark=None, benchmark_label='', ratio=None, percent=None, band='', title='')
    evidence = [dict(source, amount_label=money(source['amount'], source['currency']))
                for source in value['sources']]
    return dict(label=money(value['low'], value['currency']) + '–' +
                money(value['high'], value['currency']), evidence=evidence,
                as_of=value['as_of'], confidence=value['confidence'], grade=value['grade'],
                adjustments=value['adjustments'],
                basis_note='Low confidence · based on similar notes' if value['basis'] == 'proxy' else '',
                **_comparison(item, value))
