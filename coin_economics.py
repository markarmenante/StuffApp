"""Derived historical-wage comparisons and metal content, without I/O or edits."""
from datetime import datetime, timezone
import math
import re
import json
from urllib.parse import urlsplit

TROY_OUNCE_GRAMS = 31.1034768
AGORA_URL = ('https://agathe.gr/file?field=PDF&id=Agora%3APublication%3AAgora+Picture+Book+12'
             '&path=%2FAgora%2FPDFs%2FPicture+Books%2FAgora+Picture+Book+12.pdf')
BLS_URL = 'https://www.bls.gov/ooh/construction-and-extraction/construction-laborers-and-helpers.htm'
METALS_URL = 'https://gold-api.com/docs'
ATHENS_FINENESS_URL = 'https://en.numista.com/catalogue/catalogues/pdf/1974_2.pdf'
WAGE_HOURLY_USD = 22.44
WAGE_YEAR = '2025'
FINENESS_FIELDS = ('fineness', 'fineness_basis', 'fineness_source')
FINENESS_BASES = ('catalogue standard', 'assay', 'estimate')


def identity(record):
    return json.dumps({key: str(record.get(key) or '').strip().lower() for key in
                       ('region', 'mint', 'authority', 'denomination', 'metal',
                        'date_1', 'date_1_text', 'date_2', 'date_2_text')}, sort_keys=True)


def fineness_state(record):
    return json.dumps({key: record.get(key) for key in (*FINENESS_FIELDS, 'fineness_identity')}, sort_keys=True)


def fineness_record(value, basis, source, record):
    """Validate a complete explicit fraction + provenance; never infer purity."""
    value = _positive(value)
    basis = str(basis or '').strip().lower()
    source = str(source or '').strip()
    url = urlsplit(source)
    if (not value or value > 1 or basis not in FINENESS_BASES or len(source) > 2000
            or url.scheme != 'https' or not url.hostname or url.username or url.password):
        raise ValueError('Enter purity above 0% and at most 100%, a basis, and an HTTPS source URL.')
    return dict(fineness=value, fineness_basis=basis, fineness_source=source, fineness_identity=identity(record))


def researched_fineness(record):
    """Only verified, explicitly bounded catalogue rules belong here."""
    if _athenian_tetradrachm(record):
        return fineness_record(.99, 'estimate', ATHENS_FINENESS_URL, record)
    return None


def _positive(value):
    if isinstance(value, bool):
        return None
    try:
        value = float(value)
        return value if math.isfinite(value) and value > 0 else None
    except (TypeError, ValueError):
        return None


def _weight(value):
    match = re.fullmatch(r'\s*(\d+(?:\.\d+)?)\s*(?:g|grams?)?\s*', str(value or ''), re.I)
    return _positive(match[1]) if match else None


def _metal(value):
    text = str(value or '').strip().lower()
    gold = bool(re.search(r'\b(?:av|au|gold)\b', text))
    silver = bool(re.search(r'\b(?:ar|ag|silver)\b', text))
    if gold and silver:
        return None, None, 'Conflicting gold and silver metadata; correct Metal before calculating.'
    if re.search(r'\b(?:electrum|billon|plated|filled|silvered|gilt|bronze|copper|ae)\b', text):
        return None, None, 'Mixed, plated or unsupported metal; a verified composition is needed.'
    if not gold and not silver:
        return None, None, 'Identify gold (AV) or silver (AR) in Metal to calculate metal value.'
    fineness = []
    for match in re.finditer(r'(?<![\d.])(0?\.\d{2,4})(?!\d)', text):
        fineness.append(float(match[1]))
    for match in re.finditer(r'\b(\d+(?:\.\d+)?)\s*%', text):
        fineness.append(float(match[1]) / 100)
    for match in re.finditer(r'\b(\d+)\s*/\s*1000\b', text):
        fineness.append(float(match[1]) / 1000)
    karats = re.findall(r'\b(\d+(?:\.\d+)?)\s*(?:k|kt|karats?)\b', text)
    if karats and not gold:
        return None, None, 'Karat purity conflicts with silver metadata.'
    fineness.extend(float(value) / 24 for value in karats)
    if any(not 0 < value <= 1 for value in fineness) or (fineness and max(fineness) - min(fineness) > .0001):
        return None, None, 'Conflicting or invalid purity metadata; verify Metal before calculating.'
    return ('XAU' if gold else 'XAG'), (fineness[0] if fineness else None), ''


def _year(record, field):
    raw, text = record.get(field), str(record.get(field + '_text') or '').strip()
    numeric = None
    if raw not in (None, ''):
        try:
            value = float(raw)
            if not math.isfinite(value) or not value.is_integer() or value == 0:
                return None
            numeric = int(value)
        except (TypeError, ValueError):
            return None
    if text:
        match = re.fullmatch(r'(?:c(?:a)?\.?\s*)?(\d{1,4})\s*(BC|BCE|AD|CE)', text, re.I)
        if not match:
            return None
        parsed = int(match[1]) * (-1 if match[2].upper() in ('BC', 'BCE') else 1)
        if numeric is not None and numeric != parsed:
            return None
        numeric = parsed
    return numeric


def _athenian_tetradrachm(record):
    first = _year(record, 'date_1')
    has_last = record.get('date_2') not in (None, '') or bool(record.get('date_2_text'))
    last = _year(record, 'date_2') if has_last else first
    metal, _, error = _metal(record.get('metal'))
    return (str(record.get('region') or '').strip().lower() == 'attica'
            and str(record.get('mint') or '').strip().lower() == 'athens'
            and str(record.get('authority') or '').strip().lower() in ('athens', 'athens polis')
            and bool(re.fullmatch(r'tetradrachm(?:a|on)?', str(record.get('denomination') or '').strip(), re.I))
            and metal == 'XAG' and not error and first is not None and last is not None
            and -480 <= first <= last <= -400)


def _timestamp(value):
    try:
        result = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return result.astimezone(timezone.utc) if result.tzinfo else None
    except (TypeError, ValueError):
        return None


def calculate(record, inputs=None, now=None):
    """No collector-price input, ancient CPI extrapolation, or database writes.

    `inputs` contains public quotes and a US CPI series on one common base.
    Unknown fineness is an explicitly labelled 100%-metal upper bound.
    """
    inputs = inputs or {}
    now = now or datetime.now(timezone.utc)
    result = dict(wage_days=None, wage_days_display='No supported wage comparison',
                  wage_usd=None, wage_display='Unavailable', wage_label='Modern wage comparison · today’s USD',
                  wage_basis='Historical wages need a documented match for this coin’s place, denomination and period.',
                  wage_method='', metal_value=None, metal_display='Unavailable', metal_label='Metal value · USD',
                  metal_basis='', metal_method='', quote_status='No quote', data_dates=[], sources=[])
    result['fineness_percent'] = (_positive(record.get('fineness')) or 0) * 100 or ''
    result['fineness_basis'] = record.get('fineness_basis') or ''
    result['fineness_source'] = record.get('fineness_source') or ''
    result['fineness_identity'] = identity(record)
    result['fineness_state'] = fineness_state(record)
    if _athenian_tetradrachm(record):
        result.update(wage_days=4, wage_days_display='≈ 4 days of skilled pay',
                      wage_basis='Classical Athens period proxy: 4 drachmai at about 1 drachma per skilled workday. '
                                 'This is a broad 5th-century comparison, not a measured wage for the exact minting year.')
        result['sources'].append(dict(name='ASCSA: Athenian money and wages, pp. 7–8', url=AGORA_URL))
        cpi = inputs.get('cpi', {}).get('USA', {})
        base = _positive(cpi.get('values', {}).get(WAGE_YEAR))
        current = cpi.get('current', {})
        current_value = _positive(current.get('value'))
        period = str(current.get('period') or '')
        if base and current_value and re.fullmatch(r'20\d{2}(?:-\d{2})?', period) and period[:4] >= WAGE_YEAR:
            result['wage_usd'] = 4 * 8 * WAGE_HOURLY_USD * current_value / base
            result['wage_display'] = '≈ ${:,.2f}'.format(result['wage_usd'])
            result['wage_method'] = ('4 workdays × an assumed 8-hour modern day × $22.44/hour '
                                    '(US construction laborers and helpers, May 2025 median), then US CPI from 2025 to '
                                    + period + '. A modern worker-pay analogy, not an ancient-to-modern price index '
                                    'or an equivalent basket of goods.')
            result['data_dates'].append('Wage benchmark: May 2025 · US CPI: ' + period
                                        + (' (estimate)' if current.get('estimated') else ''))
            result['sources'].append(dict(name='BLS: construction laborers and helpers', url=BLS_URL))
            if cpi.get('source_url'):
                result['sources'].append(dict(name='US CPI: modern wage adjustment only', url=cpi['source_url']))
        else:
            result['wage_method'] = 'Four historical workdays; comparable US CPI inputs are unavailable for the modern wage estimate.'

    symbol, fineness, error = _metal(record.get('metal'))
    recorded_fineness = record.get('fineness')
    if recorded_fineness not in (None, ''):
        try:
            saved = fineness_record(recorded_fineness, record.get('fineness_basis'), record.get('fineness_source'), record)
            if record.get('fineness_identity') != saved['fineness_identity']:
                raise ValueError('Coin identity changed')
            if fineness is not None and abs(saved['fineness'] - fineness) > .0001:
                raise ValueError('Conflicting purity in Metal')
            fineness = saved['fineness']
        except (ValueError, TypeError):
            result['metal_basis'] = 'Recorded fineness needs review: verify its source and current coin identity.'
            return result
    weight = _weight(record.get('weight'))
    if error or not weight:
        result['metal_basis'] = error or 'A positive weight in grams is required.'
        return result
    metal = 'gold' if symbol == 'XAU' else 'silver'
    result['metal_label'] = 'Melt value · USD' if fineness is not None else 'Pure-' + metal + ' ceiling · USD'
    result['metal_basis'] = (('Recorded purity: {:g}%. '.format(fineness * 100)) if fineness is not None else
                             'Purity not recorded; assumes 100% ' + metal + ' and gives an upper bound. ')
    result['metal_basis'] += 'Spot metal content only; excludes refining costs, dealer margins and collector value.'
    if recorded_fineness not in (None, ''):
        result['metal_basis'] = result['metal_basis'].replace('Recorded purity:', str(record['fineness_basis']).title() + ':')
        if record['fineness_basis'] != 'assay':
            result['metal_basis'] += ' This is not an assay of this specimen.'
        if record['fineness_source'] == ATHENS_FINENESS_URL and record['fineness_basis'] == 'estimate':
            result['metal_basis'] += ' Published type estimate; specimen unassayed.'
        result['sources'].append(dict(name='Recorded fineness: ' + record['fineness_basis'], url=record['fineness_source']))
    quote = inputs.get('quotes', {}).get(symbol, {})
    price = _positive(quote.get('price'))
    quoted_at = _timestamp(quote.get('updated_at'))
    if not price or not quoted_at or (quoted_at - now).total_seconds() > 300:
        result['metal_basis'] += ' A valid dated USD spot quote is unavailable.'
        return result
    stale = (now - quoted_at).total_seconds() > 600
    result['quote_status'] = 'Stale quote — last available price' if stale else 'Latest available quote'
    result['metal_value'] = weight * (fineness if fineness is not None else 1) / TROY_OUNCE_GRAMS * price
    result['metal_display'] = ('≈ ' if fineness is not None else '≤ ') + '${:,.2f}'.format(result['metal_value'])
    result['metal_method'] = ('{:g} g × {:g} fineness ÷ 31.1034768 g/troy oz × ${:,.4f}/troy oz ({})'
                              .format(weight, fineness if fineness is not None else 1, price, symbol))
    result['data_dates'].append(metal.title() + ' spot: ' + quoted_at.strftime('%Y-%m-%d %H:%M:%S UTC')
                                + (' · stale' if stale else ''))
    result['sources'].append(dict(name='Gold API: USD spot quote per troy ounce', url=METALS_URL))
    return result
