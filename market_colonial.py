"""Colonial, dependent-territory and occupation offer eligibility.

A historical collection family is never evidence that a later issue is colonial.
Legacy year boundaries exclude transition years; sourced issue/administration
evidence supports additional territories and periods. See docs/market-validation.md.
"""
import re
from urllib.parse import urlsplit
import banknote_catalog as catalog

# Reuse documented sovereign-period metadata, not collection-family membership.
PERIODS = {name:(start,end) for name,(_,start,end,_) in catalog.PERIODS.items()}
PERIODS.update({
    'Canada':(1763,1867), 'Australia':(1788,1901), 'New Zealand':(1840,1907),
    'South Africa':(1806,1910), 'Philippines':(1565,1946),
    'Portuguese Guinea':(1879,1973), 'Guinea-Bissau':(1879,1973),
    'Guinea':(1891,1958), 'Portuguese Timor':(1702,1975), 'Timor':(1702,1975),
    'Portuguese India':(1510,1961), 'French India':(1674,1954),
    'French Indo-China':(1887,1954), 'French Cochin-China':(1862,1949),
    'Belgian Congo':(1908,1960), 'Netherlands Indies':(1800,1945),
    'British Guiana':(1831,1966), 'British Honduras':(1862,1981),
    'Straits Settlements':(1826,1942), 'Sarawak':(1888,1963),
    'British North Borneo':(1881,1963), 'North Borneo':(1881,1963),
    'Rhodesia and Nyasaland':(1953,1963), 'Northern Rhodesia':(1924,1964),
    'Southern Rhodesia':(1923,1965), 'Rhodesia':(1923,1965),
    'British East Africa':(1895,1961), 'British West Africa':(1912,1957),
    'British Caribbean Territories':(1950,1962), 'Malaya and British Borneo':(1952,1957),
    'French West Africa':(1895,1958), 'French Equatorial Africa':(1910,1958),
    'French Somaliland':(1896,1967), 'French Territory of the Afars and Issas':(1967,1977),
    'New Hebrides':(1906,1980), 'Palestine':(1920,1948), 'Syria':(1920,1946),
    'Trinidad and Tobago':(1899,1962), 'Western Samoa':(1920,1962),
    'Bahrain':(1861,1971), 'Qatar and Dubai':(1916,1971),
    'Suriname':(1667,1975), 'Danish West Indies':(1754,1917),
    'Taiwan':(1895,1945), 'Manchukuo':(1932,1945),
    'Italian East Africa':(1936,1941), 'Italian Somaliland':(1889,1941),
    'German East Africa':(1885,1918), 'German South West Africa':(1884,1915),
    'Kiautschou':(1898,1914), 'Zanzibar':(1890,1963),
})
# These names unambiguously identify a continuing dependency, not a successor
# national currency. Crown Dependencies are deliberately not called colonies.
DEPENDENCIES = catalog.BRITISH_DEPENDENCIES
SUCCESSOR = re.compile(
    r'central bank of the philippines|bangko sentral|republ(?:ic|ika).*philipp|'
    r'central bank of ceylon|reserve bank of (?:australia|new zealand|malawi)|'
    r'bank of canada|commonwealth of australia|dominion of canada|'
    r'bceao|beac|banco nacional (?:de angola|da guine)|'
    r'banco de (?:mocambique|mozambique|cabo verde)|bank of mauritius|'
    r'bank of (?:jamaica|guyana)|central bank of (?:cyprus|malta)|'
    r'republic of (?:india|kenya|cuba)|independent republic',re.I)

# This describes the relationship, not a whitelist of empires or territories.
ADMINISTRATION_KINDS = {
    'colony', 'protectorate', 'mandate', 'trust territory', 'dependency',
    'condominium', 'military occupation', 'leased territory', 'client state',
}
SPECIAL_ISSUE = re.compile(
    r'occupation|occupied|military currency|invasion (?:money|currency)|'
    r'japanese government|gunpyo', re.I)


def _year(value):
    # Do not silently truncate fractions, booleans or an ambiguous date string.
    text = str(value or '').strip()
    return int(text) if re.fullmatch(r'(?:1[5-9]|20)\d{2}|2100', text) else None


def _source(value):
    try:
        url = urlsplit(str(value or ''))
        return url.scheme in ('http', 'https') and bool(url.hostname) and not url.username
    except ValueError:
        return False


def normalize_administration(value):
    """Keep bounded source attribution in the candidate JSON, never collection data."""
    if not isinstance(value, dict):
        return {}
    result = {key: str(value.get(key) or '').strip()[:limit] for key, limit in (
        ('kind', 40), ('name', 160), ('territory', 80), ('source', 1000), ('evidence', 1200))}
    result['kind'] = result['kind'].lower()
    result.update({key: value.get(key) for key in ('year_start', 'year_end')})
    return result


def _administration_problem(item, years):
    admin = normalize_administration(item.get('administration'))
    if admin.get('kind') not in ADMINISTRATION_KINDS or not admin.get('name'):
        return 'Issuing administration and relationship are not established'
    territory = catalog.canonical_country(admin.get('territory', ''))
    if not territory or territory != catalog.canonical_country(str(item.get('country') or '')):
        return 'Administration evidence does not identify this territory'
    if not _source(admin.get('source')) or not admin.get('evidence'):
        return 'Issuing administration has no corroborating source and issue evidence'
    if not item.get('issuer') or not (item.get('pick_number') or item.get('other_catalog')):
        return 'Administration evidence needs an issuer and catalogue identity for this issue'
    start, end = (_year(admin.get(key)) for key in ('year_start', 'year_end'))
    if start is None or end is None or start > end:
        return 'Issuing administration period is not established'
    if any(_year(item.get(key)) is None for key in ('issue_year_start', 'issue_year_end')):
        return 'Additional administration needs a sourced actual issue-year range'
    if min(years) < start or max(years) > end:
        return 'Actual issue range falls outside the sourced administration period'
    evidence = ' '.join(str(item.get(key) or '') for key in ('title', 'series', 'issuer'))
    stated = [int(y) for y in re.findall(r'\b(?:1[5-9]\d{2}|20\d{2})\b', evidence)]
    if stated and max(stated) > end:
        return 'Title or series identifies an issue after the sourced administration'
    return ''


def administration_label(item):
    admin = normalize_administration(item.get('administration'))
    if admin.get('kind') in ADMINISTRATION_KINDS and admin.get('name'):
        return f"{admin['name']} · {admin['kind']}"
    country = catalog.canonical_country(str(item.get('country') or ''))
    if country in DEPENDENCIES:
        return f'{country} · dependency'
    return ''


def victory_label(item):
    """Mark's explicit exception: real Philippine Victory notes, any issue period."""
    if catalog.canonical_country(str(item.get('country') or '')) != 'Philippines':
        return ''
    evidence = ' '.join(str(item.get(k) or '') for k in ('title', 'series', 'issuer'))
    if not re.search(r'\bvictory\b', evidence, re.I) or re.search(r'replica|facsimile|reproduction|medal', evidence, re.I):
        return ''
    pick = str(item.get('pick_number') or '')
    original = bool(re.search(r'\bp(?:ick)?[.#\s-]*(?:9[4-9]|10[01])[a-z]?(?![a-z0-9])',pick,re.I))
    cbp = bool(re.search(r'central bank of the philippines|victory[- ]cbp|cbp|central bank.*overprint',evidence,re.I))
    # CBP needs an actual catalogue identifier and the Philippine Victory type,
    # not just a seller's use of a celebratory word.
    if cbp and re.search(r'\bp(?:ick)?[.#\s-]*(?:11[7-9]|12[0-4])[a-z]?(?![a-z0-9])',pick,re.I):
        return 'Philippine Victory–CBP · post-independence'
    if original:
        return 'Philippine Victory issue'
    # Missing catalogue numbers need explicit series AND issuer evidence.
    # An incompatible supplied Pick is a conflict, never a keyword fallback.
    if not pick.strip() and re.search(r'\bvictory(?:[- ]cbp|\s+(?:series\s*)?66)\b', str(item.get('series') or ''), re.I):
        issuer = str(item.get('issuer') or '')
        if re.search(r'central bank of the philippines', issuer, re.I):
            return 'Philippine Victory–CBP · post-independence'
        if re.search(r'(?:commonwealth|treasury|government).*philipp|philipp.*(?:treasury|commonwealth)', issuer, re.I):
            return 'Philippine Victory issue'
    return ''


def problem(item):
    """Internal exclusion reason, or empty for a supported eligible issue.

    Separate domestic-US/non-colonial themes remain eligible. Additional
    administrations need issue-specific source attribution, not a country guess.
    """
    country = catalog.canonical_country(str(item.get('country') or ''))
    theme = str(item.get('theme') or '')
    if country == 'United States of America' and not item.get('administration'):
        return 'Domestic US issue is not colonial' if theme.startswith(('colonial-', 'wantlist-british', 'wantlist-french', 'wantlist-other')) else ''
    evidence = ' '.join(str(item.get(k) or '') for k in ('title','issuer','series'))
    special = bool(SPECIAL_ISSUE.search(evidence))
    colonial = bool(item.get('empire') or item.get('administration')) or special or theme.startswith(('colonial-', 'wantlist-')) or theme == 'analysis-gaps'
    if not colonial:
        return ''
    if victory_label(item):
        return ''
    if SUCCESSOR.search(evidence):
        return 'Independent / successor issuer or series, not a colonial issue'
    years = []
    for key in ('issue_year_start','issue_year_end'):
        value = item.get(key)
        if value is not None:
            year = _year(value)
            if year is None:
                return 'Issue-year range is not established'
            years.append(year)
    if len(years) == 2 and years[0] > years[1]:
        return 'Issue-year range is reversed'
    if years and not _source(item.get('issue_date_source')):
        return 'Actual issue-year range has no corroborating source'
    if not years:
        if re.search(r'\bN\.?D\.?\b|undated|reissue|overprint',evidence,re.I):
            return 'Undated / reissued note needs actual issue-year evidence'
        year = _year(item.get('date_1'))
        if year is None:
            return 'Colonial issue date is not established'
        years = [year]
    if item.get('administration'):
        return _administration_problem(item, years)
    if special or (country == 'Philippines' and re.search(r'japan|overprint', evidence, re.I)):
        return 'Occupation or overprinted issue needs separate administration evidence'
    periods = PERIODS.get(country)
    if not periods and country not in DEPENDENCIES:
        return 'Administration period not established; supply sourced issue and administration evidence'
    if periods:
        start,end=periods
        if min(years) <= start or max(years) >= end:
            return 'Issue date is outside a confirmed colonial period or in a transition year'
    # Cross-check dates explicitly carried by a series/reissue title, rather
    # than allowing a historic printed date to hide a post-independence issue.
    stated=[int(y) for y in re.findall(r'\b(?:1[5-9]\d{2}|20\d{2})\b',evidence)]
    if periods and stated and max(stated) >= periods[1]:
        return 'Title or series identifies a transition / post-colonial issue'
    return ''
