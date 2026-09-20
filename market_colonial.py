"""Conservative colonial offer eligibility, separate from collection filing.

A historical collection family is never evidence that a later issue is colonial.
Year boundaries deliberately exclude transition years; see docs/market-validation.md.
"""
import re
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
    r'banque centrale|bceao|beac|banco nacional (?:de angola|da guine)|'
    r'banco de (?:mocambique|mozambique|cabo verde)|bank of mauritius|'
    r'bank of (?:jamaica|guyana)|central bank of (?:cyprus|malta)|'
    r'republic of (?:india|kenya|cuba)|independent republic',re.I)


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

    Separate domestic-US/non-colonial themes remain eligible. Unknown colonial
    administrations/dates/transition issues stay out until evidence is reviewed.
    """
    country = catalog.canonical_country(str(item.get('country') or ''))
    theme = str(item.get('theme') or '')
    if country == 'United States of America':
        return 'Domestic US issue is not colonial' if theme.startswith(('colonial-', 'wantlist-british', 'wantlist-french', 'wantlist-other')) else ''
    colonial = bool(item.get('empire')) or theme.startswith(('colonial-', 'wantlist-')) or theme == 'analysis-gaps'
    if not colonial:
        return ''
    evidence = ' '.join(str(item.get(k) or '') for k in ('title','issuer','series'))
    if victory_label(item):
        return ''
    if SUCCESSOR.search(evidence):
        return 'Independent / successor issuer or series, not a colonial issue'
    if country == 'Philippines':
        if re.search(r'japan|occupation|central bank|overprint', evidence, re.I):
            return 'Philippine occupation or overprinted issue needs separate administration evidence'
    periods = PERIODS.get(country)
    if not periods and country not in DEPENDENCIES:
        return 'Colonial administration period not established for this territory'
    years = []
    for key in ('issue_year_start','issue_year_end'):
        value = item.get(key)
        if value is not None:
            try: years.append(int(value))
            except (ValueError,TypeError): return 'Issue-year range is not established'
    if years and (not item.get('issue_date_source') or not str(item['issue_date_source']).startswith(('https://','http://'))):
        return 'Actual issue-year range has no corroborating source'
    if not years:
        if re.search(r'\bN\.?D\.?\b|undated|reissue|overprint',evidence,re.I):
            return 'Undated / reissued note needs actual issue-year evidence'
        try: years=[int(item.get('date_1'))]
        except (ValueError,TypeError): return 'Colonial issue date is not established'
    if min(years) < 1500 or max(years) > 2100:
        return 'Colonial issue date is not established'
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
