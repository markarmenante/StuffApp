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
import banknote_face_value
import banknote_historical_rates

FED_URL = 'https://www.minneapolisfed.org/about-us/monetary-policy/inflation-calculator/consumer-price-index-1800-'
BOE_URL = 'https://www.bankofengland.co.uk/monetary-policy/inflation/inflation-calculator'
WB_URL = 'https://api.worldbank.org/v2/country/{countries}/indicator/FP.CPI.TOTL?format=json&per_page=20000'
FX_URL = 'https://api.frankfurter.dev/v1/latest?base=USD'
ECB_URL = 'https://www.ecb.europa.eu/euro/intro/html/index.en.html'
HISTORICAL_US_CPI_URL = 'https://hsus.cambridge.org/HSUSWeb/toc/treeTablePathIdCc1-2.html'
CONNECTICUT_CURRENCY_URL = 'https://research.colonialwilliamsburg.org/DigitalLibrary/view/index.cfm?doc=ResearchReports%5CRR0066.xml'
# Historical Statistics table Cc1: 1776 CPI, on the 1982–1984 = 100 base.
# This is a historical reconstruction, not a contemporary BLS measurement.
CONNECTICUT_1776_CPI = 8.735

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


def _expanded_ranges(value):
    # A same-century abbreviated range is catalogue notation, not a new date.
    # Reversed endings stay reversed and are rejected by comparison_dates.
    return re.sub(r'(?<!\d)((?:1[7-9]|20)\d{2})\s*([-–—]|to)\s*(\d{2})(?!\d|[-/.]\d{1,2}\b)',
                  lambda match: match[1] + '–' + match[1][:2] + match[3], str(value or ''), flags=re.I)


def years(value):
    """Gregorian dates only; no conversion of AH/BE/ROC calendar labels."""
    s = _expanded_ranges(value)
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


def comparison_dates(note):
    """Use the displayed Year (Series), independently of actual issue metadata."""
    primary = _expanded_ranges(note.get('date_1_text') or note.get('date_1')).strip()
    series = _expanded_ranges(note.get('series')).strip()

    def candidate(text):
        # Do not truncate a numeric fractional year. A dotted full date such
        # as 1776.05.10 remains a date, and integral 1776.0 is a whole year.
        fractions = re.findall(r'(?<![\d.])(?:1[7-9]|20)\d{2}\.(\d+)(?![\d.])', text)
        if any(any(digit != '0' for digit in fraction) for fraction in fractions):
            return [], 'The comparison year must be a whole Gregorian year, date or explicit range.'
        found = years(text)
        if len(found) <= 1:
            return found, ''
        bounds = re.findall(r'(?<!\d)(1[7-9]\d{2}|20\d{2})\s*(?:[-–—]|to)\s*(1[7-9]\d{2}|20\d{2})(?!\d)', text, re.I)
        if len(bounds) != 1 or int(bounds[0][0]) > int(bounds[0][1]) or found != list(range(int(bounds[0][0]), int(bounds[0][1]) + 1)):
            return [], 'The comparison year contains unrelated or ambiguous years.'
        return found, ''

    selected, error = candidate(primary)
    family, family_error = candidate(series)
    explicit_series = bool(re.search(r'\bseries\s*(?:of\s*)?[:\-]?\s*(?:1[7-9]|20)\d{2}\b', series, re.I)
                           or re.fullmatch(r'(?:1[7-9]|20)\d{2}', series)
                           or re.search(r'\d{4}\s*(?:[-–—]|to)\s*\d{4}', series, re.I))
    source = 'Catalogue year'
    if not error and selected and explicit_series:
        # A broader emission-family range may contain the precise printed year.
        if family_error or (family and not set(selected).issubset(family)):
            error = 'The Year (Series) field conflicts with the stated series year.'
        elif family:
            source = 'Series year'
    if not selected and not error:
        selected, error, source = family, family_error, 'Series year'
    if error:
        return dict(years=[], label='Unavailable', basis=error + ' Verify Year (Series) and Series; saved dates have not been changed.')
    if not selected:
        return dict(years=[], label='Unavailable', basis='A Gregorian series or catalogue year is needed for this comparison.')
    if re.search(r'\b(?:act|law|decree|lei|loi)\b', primary if years(primary) else series, re.I):
        source = 'Printed law year'
    label = str(selected[0]) + ('–' + str(selected[-1]) if len(selected) > 1 else '')
    return dict(years=selected, label=label,
                basis=source + ' used for an approximate comparison; not a verified issue date.')


def _connecticut_1776(note, year):
    """A bounded local-money relation, never a sterling rule for all shillings."""
    country = banknote_catalog.fold(banknote_catalog.canonical_country(note.get('country')))
    issuer = banknote_catalog.fold(note.get('issuer') or '')
    return (year == 1776
            and country in {'connecticutcolony', 'colonyofconnecticut', 'provinceofconnecticut'}
            and issuer in {'colonyofconnecticut', 'thecolonyofconnecticut', 'connecticutcolony'}
            and bool(re.fullmatch(r'(?:\d+(?:\.\d+)?|\d+\s*/\s*\d+|[½¼¾])\s+shillings?', _plain(note.get('denomination'))))
            and not re.search(r'sterling|continental|state of connecticut|old tenor|new tenor',
                              _plain(note.get('series'))))


def _amount(text):
    parsed = banknote_face_value.parse(text)
    return parsed['amount'] if parsed else None


def _symbol_matches(note, parsed):
    if not parsed: return False
    country = banknote_catalog.canonical_country(note.get('country'))
    required = {'us$': 'United States of America', 'hk$': 'Hong Kong', 'a$': 'Australia', 'c$': 'Canada'}
    return parsed['symbol'] not in required or country == required[parsed['symbol']]


def currency(note, year):
    country = banknote_catalog.canonical_country(note.get('country'))
    parsed = banknote_face_value.parse(note.get('denomination'))
    if parsed and not _symbol_matches(note, parsed): return None
    denom = parsed['unit'] if parsed else _plain(note.get('denomination'))
    issuer = _plain(note.get('issuer'))
    kind = _plain(note.get('issue_type'))
    national_japan = (country == 'Japan' and kind == 'national' and re.search(r'japanese government|bank of japan', issuer) and not re.search(r'occupation|military', issuer))
    national_us = (country == 'United States of America' and
                   re.search(r'united states treasury|federal reserve bank', issuer) and
                   not re.search(r'military payment|coupon|savings bond', issuer + ' ' + _plain(note.get('series'))))
    if national_us and re.fullmatch(r'silver dollars?', denom): denom = 'dollars'
    if re.search(r'\b(?:cfa|cfp)\b', denom): return None
    if country == 'France' and re.search(r'\b(?:old|ancien|anciens|ancienne|anciennes)\b', denom): return None
    if country == 'Germany' and re.search(r'deutsche notenbank|staatsbank|\bddr\b|german democratic|ostmark', issuer + ' ' + denom): return None
    # Local vouchers, occupation currencies and competing dollar/rupee regimes
    # do not acquire the national currency's purchasing power merely by name.
    if (re.search(r'notgeld|scrip|private|counterfeit', kind) or (not national_us and re.search(r'occupation|military', kind))
            or (not national_japan and re.search(r'confederate|japanese government|military|occupation|soviet|savings bond|coupon', issuer))):
        return None
    if re.search(r'\b(?:cruzeiros?|reis|milreis|reichsmarks?|rentenmarks?|gold yuan|customs gold|gold units?|yuan gold|yuan silver|old pesos?|silver dollars?|piastres?)\b', denom):
        return None
    if _connecticut_1776(note, year):
        # Table XIII records six Connecticut shillings per Spanish milled
        # dollar. This supports a historical face-value estimate only.
        return 'USA', 'USD', 1 / 6
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
    comparison = comparison_dates(note)
    result = dict(year_series=when['series'], probable_issue_date=when['issue'],
                  issue_basis=when['basis'], at_issue=None, today=None, at_issue_display='Unavailable',
                  today_display='Unavailable', sources=[], data_dates=[], note='',
                  comparison_year=comparison['label'], comparison_basis=comparison['basis'],
                  estimate_kind='unavailable', estimate_basis='')
    yy = comparison['years']
    # A series/catalogue year is an explicit comparison basis, never a claim
    # about release. Saved issue_date remains separate and does not replace it.
    unit_years = yy
    amount = _amount(note.get('denomination'))
    if not unit_years or amount is None:
        result['note'] = comparison['basis'] if not unit_years else ('No monetary face denomination is recorded. Verify the Denomination field before a face-value comparison.' if not note.get('denomination') else 'The face amount or its unit is ambiguous. Verify the recorded Denomination; no value has been guessed.')
        return result
    parsed = banknote_face_value.parse(note.get('denomination'))
    if not _symbol_matches(note, parsed):
        result['note'] = 'The denomination’s currency prefix conflicts with the recorded country.'
        return result
    identities = [currency(note, y) for y in unit_years]
    historical = None
    parsed = banknote_face_value.parse(note.get('denomination'))
    if None in identities or len(set(identities)) != 1:
        rules = [banknote_historical_rates.reference(note, y, parsed['unit']) for y in unit_years]
        if any(rule is None for rule in rules):
            result['note'] = banknote_historical_rates.unavailable_reason(note, unit_years, parsed['unit'])
            return result
        signatures = {(r['iso'], r['code'], r['family']) for r in rules}
        if len(signatures) != 1:
            result['note'] = 'The comparison range crosses a monetary-regime change; a more precise series year is needed.'
            return result
        historical = rules[0]
        iso, code, factor = historical['iso'], historical['code'], historical['factor']
    else:
        iso, code, factor = identities[0]
    colonial = all(_connecticut_1776(note, year) for year in unit_years)
    result.update(estimate_kind=historical['kind'] if historical else 'historical_parity' if colonial else 'domestic_cpi',
                  estimate_basis=historical['basis'] if historical else 'US purchasing-power benchmark at historical face-value parity.' if colonial else 'Domestic consumer-price comparison, expressed in today’s USD.')
    fx = data.get('fx', {})
    fx_date = fx.get('date', '')
    rate = 1. if code == 'USD' else fx.get('usd_per_unit', {}).get(code)
    if not isinstance(rate, (int, float)) or not math.isfinite(rate) or rate <= 0:
        result['note'] = 'A current USD exchange rate is unavailable.'
        return result
    nominal = amount * factor
    if historical:
        result['note'] = 'Historical benchmark only; this monetary issue has no verified current nominal spending amount. Local inflation, exchange restrictions and paper-money discounts may differ.'
        result['sources'].extend(historical['sources'])
    elif colonial:
        result['note'] = 'Obsolete Connecticut currency has no current nominal spending amount. The historical estimate uses face-value parity; wartime paper-money discounts are not measured.'
        result['sources'].extend([
            dict(name='Colonial Williamsburg: Connecticut currency, Table XIII', url=CONNECTICUT_CURRENCY_URL),
            dict(name='Historical Statistics of the United States: 1776 CPI, table Cc1', url=HISTORICAL_US_CPI_URL),
        ])
    else:
        result.update(today=nominal * rate, today_display=money(nominal * rate))
    if code != 'USD':
        result['sources'].append(dict(name='ECB exchange rates via Frankfurter', url=FX_URL))
        result['data_dates'].append('FX ' + fx_date)
        if not fx_date or (today - date.fromisoformat(fx_date)).days > 7:
            result['note'] = 'Exchange-rate data is older than seven days; amounts use the displayed fixing.'
    if banknote_catalog.canonical_country(note.get('country')) in EURO and not re.search(r'\beuros?\b', _plain(note.get('denomination'))):
        result['sources'].append(dict(name='ECB fixed euro conversion rates', url=ECB_URL))
    series = data.get('cpi', {}).get(iso, {})
    original_values = series.get('values', {})
    values, extended = banknote_historical_rates.cpi_values(iso, series)
    if not colonial and extended and any(str(y) not in original_values and str(y) in values for y in yy):
        result['sources'].append(dict(name='Historical Statistics of the United States: CPI table Cc1' if iso == 'USA' else 'Jordà–Schularick–Taylor historical CPI (CC BY-NC-SA 4.0)', url=HISTORICAL_US_CPI_URL if iso == 'USA' else banknote_historical_rates.JST_URL))
        result['data_dates'].append('HSUS reconstructed historical CPI; modern 1982–84 base' if iso == 'USA' else 'JST release 6 historical CPI; rebased at 2010')
    current = series.get('current', {})
    end = current.get('value')
    current_years = years(current.get('period'))
    recent = current_years and 0 <= today.year-max(current_years) <= 2
    if colonial:
        # Rebase on the documented modern CPI base, not a splice at 1800:
        # the two sources' eighteenth-century reconstructions differ.
        anchors = [values.get(str(year)) for year in (1982, 1983, 1984)]
        valid_base = all(isinstance(v, (int, float)) and not isinstance(v, bool)
                         and math.isfinite(v) and v > 0 for v in anchors)
        values = {'1776': CONNECTICUT_1776_CPI * (sum(anchors) / 3) / 100} if valid_base else {}
    if (yy and recent and all(str(y) in values and y <= today.year for y in yy)
            and isinstance(end, (int, float)) and not isinstance(end, bool)
            and math.isfinite(end) and end > 0):
        converted = [amount * (rules[i]['factor'] if historical else factor) * end / values[str(y)] * rate for i, y in enumerate(yy)
                     if isinstance(values[str(y)], (int, float)) and not isinstance(values[str(y)], bool)
                     and math.isfinite(values[str(y)]) and values[str(y)] > 0]
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
    if result['at_issue'] is None and not historical and not colonial:
        rules = [banknote_historical_rates.reference(note, y, parsed['unit']) for y in yy]
        if rules and all(r is not None for r in rules):
            proxy = _reference_estimate(rules, amount, yy, data, today)
            if proxy:
                proxy['sources'] = result['sources'] + proxy['sources']
                proxy['data_dates'] = result['data_dates'] + proxy['data_dates']
                result.update(proxy)
                result['note'] = ' '.join(filter(None, [result['note'], 'Historical reference benchmark; local prices and exchange restrictions may differ.']))
    if result['at_issue'] is None:
        missing = 'No comparable ' + iso + ' CPI data for ' + comparison['label'] + '; a sourced price series or historical exchange benchmark is needed.'
        result['note'] = ' '.join(filter(None, [result['note'], missing]))
    # Preserve small nonzero equivalents rather than misreporting them as zero.
    result['method'] = ('Official annual FX benchmark: face value ÷ the selected year’s published local-currency units per USD × US CPI change to the current source period. This estimates US-dollar purchasing power, not the local basket or unofficial exchange value.' if historical and historical['kind'] == 'historical_fx' else 'Historical benchmark: face value × documented parity × reference-country CPI change × current USD exchange rate. ' + historical['basis'] if historical else result.get('method') or ('Historical face-value estimate: 6 shillings in Connecticut money = 1 Spanish milled dollar; apply US CPI change from 1776 with both indices on the 1982–1984 base. This is an approximate dollar purchasing-power comparison, not a measured Connecticut price basket, paper-money trading value, collector value or redemption amount.'
                        if colonial else
                        'Series-year comparison: face value × domestic CPI change × USD exchange rate. Today: the same nominal amount × USD exchange rate. Fixed euro conversions are applied where needed. These compare face-value spending power, not collector value or redemption eligibility; the comparison year is not a verified issue date.'))
    if historical and historical['kind'] == 'historical_fx':
        result['data_dates'].append('Official annual FX ' + comparison['label'])
    result['sources'] = list({source['url']: source for source in result['sources']}.values())
    result['data_dates'] = list(dict.fromkeys(result['data_dates']))
    return result


def _reference_estimate(rules, amount, yy, data, today):
    signature = {(r['iso'], r['code'], r['family']) for r in rules}
    if len(signature) != 1: return None
    rule = rules[0]
    series = data.get('cpi', {}).get(rule['iso'], {})
    current = series.get('current', {})
    periods = years(current.get('period'))
    if not periods or not 0 <= today.year - max(periods) <= 2: return None
    values, extended = banknote_historical_rates.cpi_values(rule['iso'], series)
    rate = 1 if rule['code'] == 'USD' else data.get('fx', {}).get('usd_per_unit', {}).get(rule['code'])
    end = current.get('value')
    numbers = [rate, end] + [values.get(str(y)) for y in yy]
    if not all(isinstance(v, (float, int)) and not isinstance(v, bool) and math.isfinite(v) and v > 0 for v in numbers): return None
    converted = [amount * r['factor'] * rate * end / values[str(y)] for r, y in zip(rules, yy)]
    lo, hi = min(converted), max(converted)
    sources = list(rule['sources']) + [dict(name=series.get('name', 'Consumer price index'), url=series['source_url'])]
    if extended and any(str(y) not in series.get('values', {}) for y in yy):
        sources.append(dict(name='Historical Statistics of the United States: CPI table Cc1' if rule['iso'] == 'USA' else 'Jordà–Schularick–Taylor historical CPI', url=HISTORICAL_US_CPI_URL if rule['iso'] == 'USA' else banknote_historical_rates.JST_URL))
    if rule['code'] != 'USD': sources.append(dict(name='ECB exchange rates via Frankfurter', url=FX_URL))
    return dict(at_issue=lo if lo == hi else [lo, hi], at_issue_display='≈ ' + (money(lo) if lo == hi else money(lo) + '–' + money(hi)),
                estimate_kind=rule['kind'], estimate_basis=rule['basis'], sources=sources,
                data_dates=['Reference CPI ' + str(current.get('period'))] + (['Official annual FX ' + str(min(yy)) + ('–' + str(max(yy)) if len(yy)>1 else '')] if rule['kind'] == 'historical_fx' else ['FX ' + str(data.get('fx', {}).get('date', ''))] if rule['code'] != 'USD' else []),
                method=('Official annual FX benchmark: face value ÷ selected-year local-currency units per USD × US CPI change. ' if rule['kind'] == 'historical_fx' else 'Historical benchmark: face value × documented monetary parity × reference-country CPI change × current USD exchange rate. ') + rule['basis'])


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
