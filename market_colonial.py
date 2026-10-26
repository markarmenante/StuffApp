"""Colonial, dependent-territory and occupation offer eligibility.

A historical collection family is never evidence that a later issue is colonial.
Legacy year boundaries exclude transition years; sourced issue/administration
evidence supports additional territories and periods. See docs/market-validation.md.
"""
import re
from urllib.parse import urlsplit
import banknote_catalog as catalog
import banknote_entities

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


def _entity_gap_problem(item):
    """Known entity bounds cannot be widened by model-supplied administration.

    This applies only to missing-entity themes. Existing domestic-US searches,
    broad discovery and the separately requested Philippine Victory exception
    keep their established rules.
    """
    if not str(item.get('theme') or '').startswith('entity-gap-'):
        return ''
    evidence = ' '.join(str(item.get(key) or '') for key in ('title', 'issuer', 'series'))
    values = [item.get('issue_year_start'), item.get('issue_year_end')]
    if any(value not in (None, '') for value in values):
        years = [_year(value) for value in values]
        if None in years or years[0] > years[1]:
            return 'Missing-entity offer needs a complete actual issue-year range'
        if not _source(item.get('issue_date_source')):
            return 'Missing-entity issue-year range has no corroborating source'
    else:
        if re.search(r'\bN\.?D\.?\b|undated|reissue|overprint', evidence, re.I):
            return 'Missing-entity undated or reissued note needs actual issue-year evidence'
        year = _year(item.get('date_1'))
        if year is None:
            return 'Missing-entity issue date is not established'
        years = [year]
    # Actual issue evidence takes precedence over a potentially older printed
    # date when identifying the historical entity, then bounds the whole range.
    entity = banknote_entities.ENTITY_BY_KEY.get(str(item.get('entity_key') or ''))
    primary = banknote_entities.entity_for_row(dict(item, date_1=years[0]))
    period = entity.get('scan_period') if entity else None
    if (not entity or not primary or
            banknote_entities.coverage_entity(primary)['key'] !=
            banknote_entities.coverage_entity(entity)['key'] or
            entity['issued'] is not True or not isinstance(period, dict)):
        return 'Missing-entity offer does not match its requested historical entity'
    family = ('british' if entity['group'] == 'british' else
              'french' if entity['group'] in {'french', 'portuguese', 'dutch'} else 'other')
    if item.get('theme') != 'entity-gap-' + family:
        return 'Missing-entity offer does not belong to this requested theme'
    # A shared Board issue cannot become a member's separate territorial issue
    # merely because a model supplied that member as country/entity_key.
    members = {'british-british-north-borneo', 'british-sarawak', 'british-brunei',
               'british-malaya', 'british-singapore'}
    issuer = catalog.fold(re.sub(r'^the\s+', '', str(item.get('issuer') or '').strip(),
                                 flags=re.I).replace('&', ' and '))
    regional_board = ('malayaandbritishborneo' in issuer or
                      (issuer in {'boardofcommissionersofcurrency', 'commissionersofcurrency'}
                       and 1953 <= min(years) <= max(years) < 1967))
    if entity['key'] in members and regional_board:
        return 'Shared Malaya and British Borneo Board issue is not a separate territorial issue'
    start, end = period['year_start'], period['year_end']
    # A shared pill may request the territorial lineage under its earlier
    # name. Matching that coverage alias must not widen either the requested
    # period or the actual note's reviewed period (e.g. French Polynesia 1957+).
    primary_period = primary.get('scan_period')
    if isinstance(primary_period, dict):
        start = max(start, primary_period['year_start'])
        primary_end = primary_period['year_end']
        if primary_end is not None:
            end = min(end, primary_end) if end is not None else primary_end
    independence = entity.get('independence_date')
    if independence:
        independence_year = int(independence[:4])
        end = min(end, independence_year) if end is not None else independence_year
    if min(years) < start or (end is not None and max(years) >= end):
        return 'Missing-entity issue falls outside its reviewed pre-independence period'
    administration = normalize_administration(item.get('administration'))
    admin_end = _year(administration.get('year_end'))
    if end is not None and admin_end is not None and admin_end > end:
        return 'Missing-entity administration exceeds the reviewed historical cutoff'
    stated = [int(year) for year in re.findall(r'\b(?:1[5-9]\d{2}|20\d{2})\b', evidence)]
    if end is not None and stated and max(stated) >= end:
        return 'Missing-entity title or series identifies a later issue'
    return ''


def problem(item):
    """Internal exclusion reason, or empty for a supported eligible issue.

    Separate domestic-US/non-colonial themes remain eligible. Additional
    administrations need issue-specific source attribution, not a country guess.
    """
    gap_problem = _entity_gap_problem(item)
    if gap_problem:
        return gap_problem
    country = catalog.canonical_country(str(item.get('country') or ''))
    theme = str(item.get('theme') or '')
    if country == 'United States of America' and not item.get('administration'):
        return 'Domestic US issue is not colonial' if theme.startswith(('colonial-', 'wantlist-british', 'wantlist-french', 'wantlist-other', 'entity-gap-')) else ''
    evidence = ' '.join(str(item.get(k) or '') for k in ('title','issuer','series'))
    special = bool(SPECIAL_ISSUE.search(evidence))
    colonial = bool(item.get('empire') or item.get('administration')) or special or theme.startswith(('colonial-', 'wantlist-', 'entity-gap-')) or theme == 'analysis-gaps'
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
    # SIMA's first dollar notes were actually issued in October 1977, before
    # independence on 7 July 1978. The generic lower bound excludes an
    # administration's transition year; this reviewed start is an issue year,
    # so the established 1977 SIMA issue is eligible. Neither a model-supplied
    # administration nor an old printed date may admit a later/unknown issue.
    solomon_1977 = country == 'Solomon Islands' and bool(item.get('issuer')) and all(
        catalog.classify(country, year, item.get('issuer'), item.get('series'))['key'] == 'british'
        for year in years)
    if country == 'Solomon Islands' and not solomon_1977:
        return 'Solomon Islands pre-independence issue date / Monetary Authority issuer not established'
    if solomon_1977:
        stated = [int(y) for y in re.findall(r'\b(?:1[5-9]\d{2}|20\d{2})\b', evidence)]
        if stated and max(stated) >= 1978:
            return 'Solomon Islands title or series identifies a transition / independent issue'
        admin_end = _year(normalize_administration(item.get('administration')).get('year_end'))
        if admin_end is not None and admin_end > 1978:
            return 'Solomon Islands administration exceeds independence on 7 July 1978'
    if item.get('administration'):
        return _administration_problem(item, years)
    if special or (country == 'Philippines' and re.search(r'japan|overprint', evidence, re.I)):
        return 'Occupation or overprinted issue needs separate administration evidence'
    periods = PERIODS.get(country)
    if not periods and country not in DEPENDENCIES:
        return 'Administration period not established; supply sourced issue and administration evidence'
    if periods:
        start,end=periods
        if (min(years) <= start and not solomon_1977) or max(years) >= end:
            return 'Issue date is outside a confirmed colonial period or in a transition year'
    # Cross-check dates explicitly carried by a series/reissue title, rather
    # than allowing a historic printed date to hide a post-independence issue.
    stated=[int(y) for y in re.findall(r'\b(?:1[5-9]\d{2}|20\d{2})\b',evidence)]
    if periods and stated and max(stated) >= periods[1]:
        return 'Title or series identifies a transition / post-colonial issue'
    return ''
