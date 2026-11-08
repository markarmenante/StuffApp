"""Face-value comparisons, separate from a banknote's collector value.

Domestic CPI preserves the original basket of goods; today's exchange rate
expresses both baskets in USD. Missing monetary continuity is never guessed.
Public datasets are shared across notes/owners; no collection data is sent.
"""
import calendar
from datetime import date, datetime, timezone
import html
import json
import math
import os
from pathlib import Path
import re
import threading
import unicodedata
import urllib.request

import banknote_catalog

FED_URL = 'https://www.minneapolisfed.org/about-us/monetary-policy/inflation-calculator/consumer-price-index-1800-'
BOE_URL = 'https://www.bankofengland.co.uk/monetary-policy/inflation/inflation-calculator'
WB_URL = 'https://api.worldbank.org/v2/country/{countries}/indicator/FP.CPI.TOTL?format=json&per_page=20000'
FX_URL = 'https://api.frankfurter.dev/v1/latest?base=USD'
ECB_URL = 'https://www.ecb.europa.eu/euro/intro/html/index.en.html'

# Country, present currency, earliest year in this monetary unit, unit spelling.
# The lower limit protects reforms; it is not a claim of CPI coverage.
UNITS = {
    'United States of America': ('USA', 'USD', 1792, r'dollars?|cents?'),
    'United Kingdom': ('GBR', 'GBP', 1700, r'pounds?|sterling|shillings?|pence|penny|pennies'),
    'England': ('GBR', 'GBP', 1700, r'pounds?|sterling|shillings?|pence|penny|pennies'),
    'Scotland': ('GBR', 'GBP', 1700, r'pounds?|sterling|shillings?|pence|penny|pennies'),
    'Northern Ireland': ('GBR', 'GBP', 1921, r'pounds?|sterling|shillings?|pence|penny|pennies'),
    'Canada': ('CAN', 'CAD', 1858, r'dollars?|cents?'),
    'Australia': ('AUS', 'AUD', 1966, r'dollars?|cents?'),
    'New Zealand': ('NZL', 'NZD', 1967, r'dollars?|cents?'),
    'Switzerland': ('CHE', 'CHF', 1850, r'francs?|franken|franchi'),
    'Japan': ('JPN', 'JPY', 1871, r'yen|sen'),
    'China': ('CHN', 'CNY', 1955, r'yuan|renminbi|jiao|fen'),
    'India': ('IND', 'INR', 1947, r'rupees?|annas?|paise|paisa'),
    'Brazil': ('BRA', 'BRL', 1994, r'real|reais'),
    'Mexico': ('MEX', 'MXN', 1993, r'(?:nuevos? )?pesos?'),
    'South Africa': ('ZAF', 'ZAR', 1961, r'rand'),
    'Hong Kong': ('HKG', 'HKD', 1935, r'dollars?|cents?'),
    'Singapore': ('SGP', 'SGD', 1967, r'dollars?|cents?'),
    'Malaysia': ('MYS', 'MYR', 1967, r'ringgit|dollars?|sen'),
    'Thailand': ('THA', 'THB', 1928, r'baht|satang'),
    'Indonesia': ('IDN', 'IDR', 1965, r'rupiah'),
    'Philippines': ('PHL', 'PHP', 1946, r'pesos?|piso|piso[s]?|centavos?|sentimos?'),
    'South Korea': ('KOR', 'KRW', 1962, r'won'),
    'Denmark': ('DNK', 'DKK', 1875, r'kroner?|kronor|ore'),
    'Sweden': ('SWE', 'SEK', 1873, r'kronor|krona|ore'),
    'Norway': ('NOR', 'NOK', 1875, r'kroner|krone|ore'),
    'Iceland': ('ISL', 'ISK', 1981, r'kronur|krona'),
    'Poland': ('POL', 'PLN', 1995, r'zloty|zlotych|zlote'),
    'Czech Republic': ('CZE', 'CZK', 1993, r'korun|koruna|koruny'),
    'Hungary': ('HUN', 'HUF', 1946, r'forint|forints'),
    'Romania': ('ROU', 'RON', 2005, r'lei|leu'),
    'Turkey': ('TUR', 'TRY', 2005, r'(?:new |yeni )?(?:lira|lirasi)'),
    'Israel': ('ISR', 'ILS', 1986, r'(?:new )?shekels?|sheqalim'),
}
# Irrevocable euro conversion rates, in old units per EUR (ECB).
EURO = {
    'France': ('FRA', 6.55957, r'francs?', 1960),
    'Germany': ('DEU', 1.95583, r'deutsche ?marks?|deutschmarks?|d[ -]?marks?', 1948),
    'Italy': ('ITA', 1936.27, r'lire|lira', 1861),
    'Spain': ('ESP', 166.386, r'pesetas?', 1868),
    'Portugal': ('PRT', 200.482, r'escudos?', 1911),
    'Austria': ('AUT', 13.7603, r'schillings?', 1945),
    'Belgium': ('BEL', 40.3399, r'francs?|franken', 1944),
    'Netherlands': ('NLD', 2.20371, r'guilders?|gulden', 1945),
    'Finland': ('FIN', 5.94573, r'markkaa|markka', 1963),
    'Ireland': ('IRL', .787564, r'pounds?|punt', 1928),
    'Greece': ('GRC', 340.750, r'drachmas?|drachmai|drachmes', 1954),
}
COUNTRIES = sorted({v[0] for v in UNITS.values()} | {v[0] for v in EURO.values()})
SEED = Path(__file__).resolve().parent / 'data' / 'banknote-economics.json'
_lock = threading.Lock()
_refreshing = False
_last_attempt = None


def _plain(value):
    return ''.join(c for c in unicodedata.normalize('NFKD', str(value or '')).casefold()
                   if not unicodedata.combining(c))


def years(value):
    """Gregorian dates only; no conversion of AH/BE/ROC calendar labels."""
    s = str(value or '')
    if re.search(r'\b(?:AH|BE|SH|ROC|Hijri|Buddhist)\b', s, re.I):
        return []
    found = sorted(set(int(y) for y in re.findall(r'(?<!\d)(1[7-9]\d{2}|20\d{2})(?!\d)', s)))
    if len(found) == 2 and re.search(r'\d{4}\s*(?:[-–—]|to)\s*\d{4}', s):
        return list(range(found[0], found[1] + 1))
    return found


def dates(note):
    """A printed/series year is never asserted as a verified actual issue date."""
    series = str(note.get('series') or '').strip()
    label = str(note.get('date_1_text') or note.get('date_1') or '').strip()
    series_label = ' · '.join(dict.fromkeys(v for v in (label, series) if v)) or 'Unknown'
    explicit = str(note.get('issue_date') or '').strip()
    if explicit:
        return dict(series=series_label, issue=explicit, years=years(explicit), basis='Saved probable issue date')
    # US series dates can precede production by many years. Other notes can
    # likewise carry an Act/law date. A plain catalogue year is a labelled proxy.
    is_series = ('series' in (series + ' ' + label).lower()
                 or re.search(r'\b(?:act|law|decree|lei|loi)\b', series + ' ' + label, re.I))
    if banknote_catalog.canonical_country(note.get('country')) == 'United States of America' or is_series:
        return dict(series=series_label, issue='Not established', years=[], basis='Series or law date alone does not establish when this note was issued')
    yy = years(label)
    return dict(series=series_label, issue=('c. ' + str(min(yy)) + ('–' + str(max(yy)) if len(yy) > 1 else '')) if yy else 'Not established',
                years=yy, basis='Catalogue year used as an estimate; actual issue date is unverified')


def _amount(text):
    for symbol, value in (('½','0.5'), ('¼','0.25'), ('¾','0.75')):
        text = str(text or '').replace(symbol, value)
    s = _plain(text).replace(',', '').strip()
    if re.match(r'^[1-9]\d{0,2}\.\d{3}(?!\d)', s): return None
    fraction = re.match(r'^(\d+)\s*/\s*(\d+)\b', s)
    if fraction:
        return int(fraction[1]) / int(fraction[2]) if int(fraction[2]) else None
    m = re.match(r'^(?:us\$|hk\$|a\$|c\$|[$£€])?\s*(\d+(?:\.\d+)?|[½¼¾])\s*', s)
    if not m:
        return None
    value = {'½': .5, '¼': .25, '¾': .75}.get(m[1])
    value = float(m[1]) if value is None else value
    tail = s[m.end():]
    if re.search(r'\d', tail): return None
    if re.match(r'thousand\b', tail): value *= 1_000
    elif re.match(r'million\b', tail): value *= 1_000_000
    elif re.match(r'billion\b', tail): value *= 1_000_000_000
    return value if 0 < value < 1e16 else None


def currency(note, year):
    country = banknote_catalog.canonical_country(note.get('country'))
    denom = _plain(note.get('denomination'))
    issuer = _plain(note.get('issuer'))
    kind = _plain(note.get('issue_type'))
    # Local vouchers, occupation currencies and competing dollar/rupee regimes
    # do not acquire the national currency's purchasing power merely by name.
    if (re.search(r'notgeld|occupation|scrip|private|military', kind)
            or re.search(r'confederate|japanese government|military|occupation|soviet|savings bond|coupon', issuer)):
        return None
    if re.search(r'\b(?:cruzeiros?|reis|milreis|reichsmarks?|rentenmarks?|gold yuan|customs gold|gold units?|yuan gold|yuan silver|old pesos?|silver dollars?|piastres?)\b', denom):
        return None
    # Units changed during these calendar years. The year alone cannot decide
    # which side of the reform an otherwise identical currency name denotes.
    if (country, year) in {('Brazil',1994),('China',1955),('Mexico',1993),('Poland',1995),
                           ('Iceland',1981),('Indonesia',1965),('South Korea',1962),
                           ('Romania',2005),('Turkey',2005)}:
        return None
    if country in EURO:
        iso, factor, pattern, first = EURO[country]
        if re.search(r'\beuros?\b', denom) and year >= 2002:
            return iso, 'EUR', 1.
        if first <= year < 2002 and re.search(r'\b(?:' + pattern + r')\b', denom):
            return iso, 'EUR', 1. / factor
        return None
    rule = UNITS.get(country)
    if not rule:
        return None
    iso, code, first, pattern = rule
    symbol = code == 'USD' and '$' in denom or code == 'GBP' and '£' in denom
    if year < first or not (symbol or re.search(r'\b(?:' + pattern + r')\b', denom)):
        return None
    factor = 1.
    if code == 'GBP':
        if re.search(r'\bshillings?\b', denom): factor = 1/20
        elif re.search(r'\b(?:pence|penny|pennies)\b', denom):
            # The decimalisation transition year is ambiguous without a date.
            if year == 1971: return None
            factor = 1/(240 if year < 1971 else 100)
    elif code == 'INR':
        if 'anna' in denom:
            if year >= 1957: return None
            factor = 1/16
        elif re.search(r'\b(?:paise|paisa)\b', denom):
            if year < 1957: return None
            factor = .01
    elif code == 'CNY':
        factor = .1 if 'jiao' in denom else .01 if 'fen' in denom else 1.
    elif re.search(r'\b(?:cents?|centavos?|sentimos?|sen|satang|ore)\b', denom):
        factor = .01
    return iso, code, factor


def money(value):
    if value is None: return 'Unavailable'
    if 0 < value < .01: return '<$0.01'
    return f'${value:,.2f}'


def calculate(note, data, today=None):
    today = today or date.today()
    when = dates(note)
    result = dict(year_series=when['series'], probable_issue_date=when['issue'],
                  issue_basis=when['basis'], at_issue=None, today=None, at_issue_display='Unavailable',
                  today_display='Unavailable', sources=[], data_dates=[], note='')
    yy = when['years']
    # A series date may still identify the monetary unit for today's nominal
    # amount, but cannot authorize an at-issue inflation calculation.
    unit_years = yy or years(note.get('date_1')) or years(note.get('series'))
    amount = _amount(note.get('denomination'))
    if not unit_years or amount is None:
        result['note'] = 'A Gregorian year and numeric face value are needed.'
        return result
    identities = [currency(note, y) for y in unit_years]
    if None in identities or len(set(identities)) != 1:
        result['note'] = 'No verified conversion to a current currency for this monetary issue.'
        return result
    iso, code, factor = identities[0]
    fx = data.get('fx', {})
    fx_date = fx.get('date', '')
    rate = 1. if code == 'USD' else fx.get('usd_per_unit', {}).get(code)
    if not isinstance(rate, (int, float)) or not math.isfinite(rate) or rate <= 0:
        result['note'] = 'A current USD exchange rate is unavailable.'
        return result
    nominal = amount * factor
    result.update(today=nominal * rate, today_display=money(nominal * rate))
    if code != 'USD':
        result['sources'].append(dict(name='ECB exchange rates via Frankfurter', url=FX_URL))
        result['data_dates'].append('FX ' + fx_date)
        if not fx_date or (today - date.fromisoformat(fx_date)).days > 7:
            result['note'] = 'Exchange-rate data is older than seven days; amounts use the displayed fixing.'
    if banknote_catalog.canonical_country(note.get('country')) in EURO and not re.search(r'\beuros?\b', _plain(note.get('denomination'))):
        result['sources'].append(dict(name='ECB fixed euro conversion rates', url=ECB_URL))
    series = data.get('cpi', {}).get(iso, {})
    values = series.get('values', {})
    current = series.get('current', {})
    end = current.get('value')
    current_years = years(current.get('period'))
    recent = current_years and 0 <= today.year-max(current_years) <= 2
    if yy and recent and all(str(y) in values and y <= today.year for y in yy) and isinstance(end, (int, float)) and end > 0:
        converted = [nominal * end / values[str(y)] * rate for y in yy if values[str(y)] > 0]
        if len(converted) == len(yy):
            lo, hi = min(converted), max(converted)
            result.update(at_issue=lo if lo == hi else [lo, hi],
                          at_issue_display='≈ ' + (money(lo) if lo == hi else money(lo) + '–' + money(hi)))
            result['sources'].append(dict(name=series.get('name', 'Consumer price index'), url=series['source_url']))
            result['data_dates'].append('CPI ' + str(current.get('period', '')))
            if min(yy) < (1913 if iso == 'USA' else 1988 if iso == 'GBR' else 0):
                result['data_dates'].append('historical CPI estimate')
            if current.get('estimated'):
                result['data_dates'].append('current CPI estimate')
    if result['at_issue'] is None:
        missing = 'Actual issue date is unverified.' if not yy else 'No comparable CPI data for the estimated issue year.'
        result['note'] = ' '.join(filter(None, [result['note'], missing]))
    # Preserve small nonzero equivalents rather than misreporting them as zero.
    result['method'] = 'At issue: face value × domestic CPI change × USD exchange rate. Today: the same nominal amount × USD exchange rate. Fixed euro conversions are applied where needed. These compare face-value spending power, not collector value or redemption eligibility.'
    return result


def parse_fed(document):
    values = {}
    for row in re.findall(r'<tr\b[^>]*>(.*?)</tr>', document, re.S | re.I):
        cells = [html.unescape(re.sub(r'<[^>]+>', '', c)).strip()
                 for c in re.findall(r'<td\b[^>]*>(.*?)</td>', row, re.S | re.I)]
        if len(cells) >= 2 and re.fullmatch(r'\d{4}\*?', cells[0]):
            try: value = float(cells[1].replace(',', ''))
            except ValueError: continue
            if value > 0: values[cells[0].rstrip('*')] = value
    if '1800' not in values or '2020' not in values: raise ValueError('Incomplete Fed CPI table')
    latest = max(values)
    return dict(name='Federal Reserve Bank of Minneapolis CPI', source_url=FED_URL,
                values=values, current=dict(period=latest, value=values[latest], estimated=int(latest) >= date.today().year))


def parse_boe(document):
    values = {y: float(v) for y, v in re.findall(r'\{\s*year:\s*"(\d{4})",\s*value:\s*([\d.]+)\s*\}', document)}
    monthly = re.findall(r'\{\s*year:\s*"([A-Za-z]{3}) (\d{2})",\s*value:\s*([\d.]+)\s*\}', document)
    if '1750' not in values or '2020' not in values: raise ValueError('Incomplete BoE CPI table')
    periods = {}
    for month, yr, value in monthly:
        n = list(calendar.month_abbr).index(month)
        periods[f'20{yr}-{n:02}'] = float(value)
    # Completed calendar years use annual averages, not their December level.
    for yr in {p[:4] for p in periods}:
        months = [v for p,v in periods.items() if p.startswith(yr)]
        if len(months) == 12: values[yr] = sum(months)/12
    period = max(periods) if periods else max(values)
    current = periods.get(period, values.get(period))
    return dict(name='Bank of England / ONS CPI', source_url=BOE_URL, values=values,
                current=dict(period=period, value=current, estimated=False))


def parse_worldbank(payload):
    if not isinstance(payload, list) or len(payload) != 2 or not isinstance(payload[1], list):
        raise ValueError('Invalid World Bank response')
    if payload[0].get('pages') != 1: raise ValueError('Incomplete World Bank response')
    results = {}
    for row in payload[1]:
        iso, yr, value = row.get('countryiso3code'), row.get('date'), row.get('value')
        if iso not in COUNTRIES or not isinstance(value, (int,float)) or not math.isfinite(value) or value <= 0 or not re.fullmatch(r'\d{4}', str(yr)):
            continue
        item = results.setdefault(iso, dict(name='World Bank / IMF consumer price index',
            source_url=f'https://data.worldbank.org/indicator/FP.CPI.TOTL?locations={iso}', values={}))
        item['values'][yr] = value
    for item in results.values():
        last = max(item['values'])
        item['current'] = dict(period=last + ' annual average', value=item['values'][last], estimated=False)
    if len(results) < 20: raise ValueError('Incomplete World Bank country coverage')
    return results


def parse_fx(payload):
    if payload.get('base') != 'USD': raise ValueError('Unexpected FX base')
    date.fromisoformat(payload['date'])
    rates = {code:1/value for code,value in payload.get('rates', {}).items()
             if re.fullmatch(r'[A-Z]{3}', code) and isinstance(value, (int,float)) and math.isfinite(value) and value > 0}
    if not {'EUR','GBP','CHF','JPY'} <= rates.keys(): raise ValueError('Incomplete FX table')
    return dict(date=payload['date'], usd_per_unit=rates)


def snapshot(data_dir):
    for path in (Path(data_dir) / 'banknote-economics.json', SEED):
        try:
            result = json.loads(path.read_text())
            if result.get('version') == 1 and isinstance(result.get('cpi'), dict) and isinstance(result.get('fx'), dict):
                return result
        except (OSError, ValueError, TypeError): pass
    return dict(version=1, cpi={}, fx={})


def _read(url):
    req = urllib.request.Request(url, headers={'User-Agent':'StuffApp/1.0 (public economic statistics)'})
    with urllib.request.urlopen(req, timeout=12) as response:
        content = response.read(8_000_001)
        if len(content) > 8_000_000: raise ValueError('Economic dataset exceeds limit')
        return content.decode('utf-8')


def refresh(data_dir):
    """One bounded public refresh; failures retain each last good dataset."""
    data = snapshot(data_dir)
    now = datetime.now(timezone.utc)
    if data.get('cpi_checked') != now.strftime('%Y-%m'):
        complete = True
        for url, parser, key in ((WB_URL.format(countries=';'.join(COUNTRIES)), lambda s: parse_worldbank(json.loads(s)), None),
                                  (FED_URL, parse_fed, 'USA'), (BOE_URL, parse_boe, 'GBR')):
            try:
                value = parser(_read(url))
                if key: data['cpi'][key] = value
                else: data['cpi'].update({k:v for k,v in value.items() if k not in ('USA','GBR')})
            except (OSError, ValueError, KeyError, TypeError): complete = False
        if complete: data['cpi_checked'] = now.strftime('%Y-%m')
    try: data['fx'] = parse_fx(json.loads(_read(FX_URL)))
    except (OSError, ValueError, KeyError, TypeError): pass
    data['refreshed_at'] = now.isoformat()
    target = Path(data_dir) / 'banknote-economics.json'
    temporary = target.with_suffix('.json.tmp')
    temporary.write_text(json.dumps(data, separators=(',', ':')))
    os.replace(temporary, target)


def request_refresh(data_dir):
    """Refresh at most daily, off the page request; no model calls or note writes."""
    global _refreshing, _last_attempt
    if os.environ.get('BANKNOTE_ECONOMICS_REFRESH') == '0': return
    with _lock:
        if _refreshing or _last_attempt == date.today(): return
        data = snapshot(data_dir)
        if str(data.get('refreshed_at', ''))[:10] == date.today().isoformat(): return
        _refreshing, _last_attempt = True, date.today()
    def run():
        global _refreshing
        try: refresh(data_dir)
        except (OSError, ValueError, TypeError): pass
        finally:
            with _lock: _refreshing = False
    threading.Thread(target=run, name='banknote-public-economics', daemon=True).start()
