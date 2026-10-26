"""Banknote filing catalogue: spelling aliases and historical collection groups.

These are collection relationships, not claims of present sovereignty. Country,
issuer and date remain separate facts. See docs/banknote-catalog.md for sources,
transition-year limitations and the explicitly requested Philippine exception.
"""
import re
import math
import unicodedata
from functools import lru_cache
import banknote_africa


PUERTO_RICO_1928 = {
    'label': 'Puerto Rico distribution, 1948–1949 · Woods–Woodin signatures',
    'body': ('Series 1928 $1 United States Note (legal tender), Fr. 1500, with a red seal '
             'and Woods–Woodin signatures. Printed in March–April 1933; a small number '
             'were released at the Treasury in Washington that year. The remaining '
             'reserve was shipped to Puerto Rico from November 1948 through April 1949 '
             'to meet demand for $1 notes while keeping legal tender notes separate '
             'from mainland silver certificates. This is the type’s distribution history, '
             'not proof that this individual note circulated there. Woods–Woodin also '
             'appears on 1928C $1 silver certificates and 1928D $5 Federal Reserve Notes.'),
    'source': 'https://s3.amazonaws.com/pmarchives.spmc/pm283-2013-series-1928-1-united-states-notes.pdf',
    'source_label': 'Jamie Yakes, Paper Money, Jan/Feb 2013, pp. 40–51',
}


def distribution_callout(row):
    """Catalogue-specific history, separate from sovereign/era classification.

    Require the actual Friedberg identity; a 1928 date, signature pair or a
    passing Puerto Rico mention cannot distinguish Fr. 1500 from Fr. 1603.
    Supports dicts and sqlite Rows without changing stored catalogue data.
    """
    if row is None:
        return None
    def value(key):
        return str(row[key] or '') if key in row.keys() else ''
    if canonical_country(value('country')) != 'United States of America':
        return None
    catalogs = ' '.join(value(k) for k in ('pick_number', 'other_catalog'))
    if re.search(r'\b(?:fr(?:iedberg)?\.?\s*#?\s*)1500(?:\*)?(?![\w])', catalogs, re.I):
        return dict(PUERTO_RICO_1928)
    return None


def fold(value):
    return re.sub(r'[^a-z0-9]', '', unicodedata.normalize('NFKD', value or '')
                  .encode('ascii', 'ignore').decode().lower())


# Only spelling equivalents; never merge a successor state or currency area.
ALIASES = {
    'United States of America': ('United States', 'USA', 'US', 'U.S.A.', 'U.S.'),
    # This legacy label explicitly names the colony, not the later US state.
    # Keep generic United States and other American colonial names distinct.
    'Pennsylvania Colony': ('United States (Colonial - Pennsylvania)',),
    'French Indo-China': ('French Indochina', 'French Indo China', 'Indochina',
                         'Indo-China', 'Indo China'),
    'French Territory of the Afars and Issas': (
        'French Afars and Issas', 'French Afars & Issas',
        'French Afars and the Issas', 'French Afars & the Issas',
        'French Territory of the Afars and the Issas',
        'French Territory of the Afars & Issas',
        'French Territory of the Afars & the Issas',
        'French Territory of Afars and Issas', 'French Territory of Afars & Issas',
        'Territory of the Afars and Issas', 'Territory of the Afars & Issas',
        'Territory of the Afars and the Issas',
        'Territoire français des Afars et des Issas'),
    'Rhodesia and Nyasaland': ('Rhodesia & Nyasaland',),
    'Saint Pierre and Miquelon': ('Saint Pierre & Miquelon', 'St. Pierre and Miquelon'),
    'São Tomé and Príncipe': ('Sao Tome and Principe', 'São Tomé & Príncipe'),
    'Réunion': ('Reunion',),
    'Sarawak': ('Sarawak (Malaysia)',),
    'South Vietnam': ('Viet Nam - South (South Vietnam)', 'Viet Nam - South',
                      'Vietnam - South', 'South Viet Nam'),
    'Netherlands Indies': ('Netherlands East Indies', 'Dutch East Indies'),
    'Macau': ('Macao',),
    'Manchukuo': ('Manchoukuo', 'China - Manchukuo', 'China - Manchoukuo'),
}
_ALIAS_LOOKUP = {fold(name): canonical for canonical, names in ALIASES.items()
                 for name in (canonical,) + names}


def canonical_country(value):
    if not isinstance(value, str):
        return value
    value = unicodedata.normalize('NFC', value).strip()
    key = fold(value)
    # Preserve the established handling of catalogue-prefixed Manchukuo.
    if 'manchukuo' in key or 'manchoukuo' in key:
        return 'Manchukuo'
    return _ALIAS_LOOKUP.get(key, value)


_CONFEDERATE_COUNTRIES = frozenset({'confederatestates', 'confederatestatesofamerica'})


# A generic "Treasury Note" label also occurs on state, territorial and
# Confederate paper. The federal coin-note class belongs to the 1890/1891
# series only (BEP currency history); do not infer it from that phrase alone.
_FEDERAL_TREASURY_ISSUERS = frozenset({
    'unitedstates', 'unitedstatesofamerica', 'unitedstatestreasury',
    'unitedstatesofamericatreasury', 'ustreasury', 'treasuryoftheunitedstates',
    'unitedstatesdepartmentofthetreasury', 'departmentofthetreasury',
    'treasurydepartment', 'bureauofengravingandprinting',
})


def treasury_coin_note_eligible(country, year, issuer):
    """Require the federal series period and a compatible issuing authority.

    A missing issuer can use a dated, explicitly named coin-note type. A
    supplied issuer must identify the federal Treasury, not merely mention
    the United States in a state/territory name or a narrative comparison.
    """
    if year not in (1890, 1891):
        return False
    country = canonical_country(country) or ''
    if country and not country.lower().startswith('united states'):
        return False
    issuer = (issuer or '').strip()
    if not issuer:
        return True
    # Location notes after a known issuer do not change its authority.
    base = re.sub(r'\s*\([^)]*\)\s*$', '', issuer).strip()
    base = re.sub(r'^the\s+', '', base, flags=re.I)
    return fold(base) in _FEDERAL_TREASURY_ISSUERS


def virginia_treasury_history(issuer, year):
    """State history for a positively identified Civil War Virginia treasury.

    A Richmond location, a Virginia bank or a Confederate national issuer
    alone cannot identify the Commonwealth's separate obligation. Source:
    https://old.lva.virginia.gov/exhibits/destiny/work/government.htm
    """
    if year is None or not 1861 <= year <= 1865:
        return None
    if not re.search(r'^\s*(?:the )?(?:commonwealth of virginia|state of virginia|'
                     r'virginia (?:state )?treasury|'
                     r'treasury of (?:the commonwealth of )?virginia)\b',
                     issuer or '', re.I):
        return None
    return {
        'label': 'Virginia Civil War finance',
        'span': '1861–1865',
        'body': ('After joining the Confederacy, the Commonwealth of Virginia '
                 'retained its own state government, Treasury and expenses. '
                 'It issued its own obligations to help finance wartime needs, '
                 'alongside Confederate national currency. The 1862 Virginia '
                 'notes pledged the Commonwealth’s credit and were receivable '
                 'for state taxes and other public dues. Virginia was therefore '
                 'the issuer; Confederate States describes the wider historical '
                 'grouping. These state obligations were separate from '
                 'Confederate national notes and United States federal issues.'),
    }



# Type-level design evidence, not personal provenance or a grading opinion.
# Heritage's original lot description supplies the full name, layout and
# orange protectors; NNP independently preserves the same Cr. 6 layout.
_VIRGINIA_CR6_DESIGN_SOURCE = (
    'Virginia 1862 $100 Cr. 6 design: Heritage Auctions lot 95435 '
    '(John Letcher center, Washington left, Native American figure right, orange C protectors): '
    'https://currency.ha.com/itm/obsoletes-by-state/virginia/'
    'richmond-va-commonwealth-of-virginia-100-oct-15-1862-cr-6-pmg-about-uncirculated-50/'
    'a/62324-95435.s ; '
    'NNP / Heritage catalogue corroboration: https://nnp.wustl.edu/library/ImageDetail/599348 . '
    'These are type-design references, not this purchase or grade.'
)



def exact_year(value):
    """A finite integral year; never truncate a model's fraction or boolean."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if math.isfinite(value) and value.is_integer() else None
    if isinstance(value, str) and re.fullmatch(r'[+-]?\d{1,6}', value.strip()):
        return int(value.strip())
    return None



# Pick 28b spans several dated signature combinations: the 1961 issue has
# Parcher/Cottrell/Melhado. Only this positively identified 1964 issue is covered.
_BRITISH_HONDURAS_1964_SIGNATURE_SOURCE = (
    'British Honduras Government $1, 1 April 1964, Pick 28b signatures: '
    'Henry Edney Conrad Cain; Rafael Aloysius Fonseca; Henry Ignatius Melhado. '
    'Numista dated 1964-Apr-01 variety: https://en.numista.com/202483 ; '
    'Noonans 31 May 2022, lots 2349–2351 (Cain/Fonseca/Melhado, Pick 28b): '
    'https://www.noonans.co.uk/auctions/calendar/647/download-pdf/ . '
    'This is a dated catalogue signature reference, not a transcription of this specimen.'
)


def signature_reference(row):
    """Signatures for a verified dated variety, never a whole-series name list."""
    def value(key):
        return row[key] if row is not None and key in row.keys() else None
    for key in ('country', 'issuer', 'pick_number', 'other_catalog'):
        if value(key) is not None and not isinstance(value(key), str):
            return None
    if (value('country') or '').strip().lower() != 'british honduras':
        return None
    issuer = re.sub(r'^the\s+', '', (value('issuer') or '').strip(), flags=re.I)
    if fold(issuer) not in {
        'governmentofbritishhonduras',
        'governmentofbritishhondurascommissionersofcurrency',
        'governmentofbritishhondurasboardofcommissionersofcurrency',
        'boardofcommissionersofcurrency', 'commissionersofcurrency',
    }:
        return None
    if exact_year(value('date_1')) != 1964:
        return None
    if value('date_2') not in (None, '') and exact_year(value('date_2')) != 1964:
        return None
    denomination = value('denomination')
    if isinstance(denomination, bool):
        return None
    if isinstance(denomination, (int, float)):
        if denomination != 1:
            return None
    elif not (isinstance(denomination, str) and re.fullmatch(
            r'(?:\$|BH\s*\$)?\s*1(?:\.0+)?(?:\s*dollars?)?',
            denomination.strip(), re.I)):
        return None
    refs = []
    for key in ('pick_number', 'other_catalog'):
        # Check may annotate this verified cross-reference with its source.
        # Strip only that exact TBB127 annotation before splitting its comma;
        # never discard arbitrary qualifiers that could hide another Pick.
        text = re.sub(r'(\bTBB\s*#?\s*B?\s*127)\s*'
                      r'\(\s*type[- ]level\s*,\s*per\s+Numista\s*\)',
                      r'\1', value(key) or '', flags=re.I)
        for part in re.split(r'[,;]', text):
            part = part.strip()
            if re.search(r'(?<!\w)(?:pick|p)\s*[-.#]?\s*\d', part, re.I):
                # Reject alternatives, uncertain attributions, missing variety
                # suffixes and references embedded in unrelated prose.
                if not re.fullmatch(r'(?:pick|p)\s*[-.#]?\s*28b', part, re.I):
                    return None
                refs.append('28b')
            elif re.fullmatch(r'(?:TBB\s*#?\s*B?\s*|B\s*)127', part, re.I):
                # The app stores cross-references in the same catalogue field.
                # This series' verified TBB number is not a competing Pick.
                continue
            elif part and (key == 'pick_number' or re.fullmatch(r'\d+[a-z]*', part, re.I)):
                return None
    if not refs:
        return None
    return {
        'fields': {'signatures': ('Henry Edney Conrad Cain; Rafael Aloysius Fonseca; '
                                  'Henry Ignatius Melhado')},
        'source': _BRITISH_HONDURAS_1964_SIGNATURE_SOURCE,
    }


def design_reference(row):
    """Known type design only when issuer, year, denomination and catalog agree.

    A date/denomination or a Virginia location alone cannot distinguish this
    state issue from national Confederate notes. Do not derive an identity
    from historical prose, related listings, a printer or an ambiguous P-6.
    """
    def value(key):
        return row[key] if row is not None and key in row.keys() else None
    year = exact_year(value('date_1'))
    for key in ('issuer', 'country', 'pick_number', 'other_catalog'):
        if value(key) is not None and not isinstance(value(key), str):
            return None
    if year != 1862 or not virginia_treasury_history(value('issuer'), year):
        return None
    denomination = value('denomination')
    if isinstance(denomination, bool):
        return None
    if isinstance(denomination, (int, float)):
        if denomination != 100:
            return None
    elif not (isinstance(denomination, str) and re.fullmatch(
            r'(?:\$|US\s*\$|USD\s*)?100(?:\s*(?:dollars?|USD))?',
            denomination.strip(), re.I)):
        return None
    catalogs = ' '.join(value(key) or '' for key in ('pick_number', 'other_catalog'))
    refs = re.findall(r'\b(?:VA[\s.-]*)?(?:cr(?:iswell)?\.?\s*[-#]?\s*)(\d+[a-z]?)\b', catalogs, re.I)
    if {ref.lower() for ref in refs} != {'6'}:
        return None
    country = canonical_country(str(value('country') or '')) or ''
    if country and country.lower() not in ('united states of america',
                                           'confederate states',
                                           'confederate states of america', 'virginia'):
        return None
    front = ('Obv: John Letcher center; George Washington left; '
             'allegorical Native American maiden right; orange C protectors.')
    # The catalogue establishes the front. Keep an already transcribed
    # reverse instead of silently discarding it or inventing a blank back.
    reverse = re.search(r'(?:^|/)\s*(Rev(?:erse)?\s*:.*)$',
                        str(value('obv_rev') or ''), re.I | re.S)
    if reverse:
        front += ' / ' + reverse.group(1).strip()
    return {
        'fields': {
            'official': ('John Letcher, Governor of Virginia; George Washington; '
                         'allegorical Native American maiden'),
            'obv_rev': front,
            'history_context': (
                'The October 15, 1862 $100 Virginia Treasury note (Cr. 6) was '
                'the largest denomination in the Commonwealth’s second and '
                'final emission, intended to redeem earlier interest-bearing '
                'Treasury notes. It was a Virginia state obligation, distinct '
                'from Confederate national currency.'),
        },
        'source': _VIRGINIA_CR6_DESIGN_SOURCE,
    }


def country_spellings(value):
    canonical = canonical_country(value) or ''
    return (canonical,) + ALIASES.get(canonical, ())


def country_search(value):
    # Collection discovery only. These lineage terms must not enter the
    # canonical-country normalizer used by saved facts and catalogue matching.
    if fold(value) in {fold(name) for name in ('Tahiti', 'French Oceania', 'French Polynesia', 'Tahiti / French Oceania')}:
        return ' '.join((str(value), 'Tahiti French Oceania French Polynesia'))
    return ' '.join(country_spellings(value))


GROUPS = (
    ('british', 'British Empire & Commonwealth',
     'Dominions, colonies, protectorates, dependencies and related currency areas; independent Commonwealth issues are identified separately.'),
    ('french', 'French colonial empire & overseas territories',
     'Colonial, protectorate, mandate and overseas issues, with successor currency areas identified separately.'),
    ('spanish', 'Spanish overseas territories', 'Overseas colonial and territorial issues.'),
    ('portuguese', 'Portuguese overseas territories', 'Colonial and overseas provincial issues.'),
    ('dutch', 'Netherlands overseas territories', 'Dutch colonial and territorial issues.'),
    ('belgian', 'Belgian colonial territories', 'Congo and related colonial currency areas.'),
    ('german', 'German colonial territories', 'Overseas colonial issues.'),
    ('italian', 'Italian territories & trusteeship', 'Colonial issues and the distinct United Nations trusteeship in Somalia.'),
    ('us', 'United States & Philippine issues',
     'United States issues and the Philippine collection, including its Spanish, American, Japanese occupation and Republic periods.'),
    ('japanese', 'Japanese empire & occupation issues',
     'Dependent-state and occupation currencies; the Philippine collection is filed under United States.'),
    ('danish', 'Danish realm & dependencies', 'Territorial and autonomous issues, identified by period.'),
    ('joint', 'Joint administrations', 'Territories administered jointly by more than one power.'),
    ('other', 'Independent & other issues',
     'Independent national issues and records without an established historical grouping; this does not imply that a country was never colonized.'),
)
GROUP_BY_KEY = {key: {'key': key, 'rank': rank, 'title': title, 'description': description}
                for rank, (key, title, description) in enumerate(GROUPS)}

# Last full year before a change of sovereignty. The transition year is handled
# separately, without inventing a day/month when only a year was recorded.
# Explicit historic territory names stay distinct from their successor states.
PERIODS = {
    'Algeria': ('french', 1830, 1962, 'French Algeria'),
    'Tunisia': ('french', 1881, 1956, 'French protectorate'),
    'Morocco': ('french', 1912, 1956, 'French protectorate — Bank of Morocco currency area'),
    'Madagascar': ('french', 1896, 1960, 'French colonial administration'),
    'Comoros': ('french', 1886, 1975, 'French colonial administration'),
    'Cameroon': ('french', 1916, 1960, 'French mandate / trust territory'),
    'Togo': ('french', 1916, 1960, 'French mandate / trust territory'),
    'Lebanon': ('french', 1920, 1943, 'French mandate'),
    'Laos': ('french', 1893, 1953, 'French protectorate / associated state'),
    'Cuba': ('spanish', 1511, 1898, 'Spanish colonial administration'),
    'Puerto Rico': ('spanish', 1508, 1898, 'Spanish colonial administration'),
    'Equatorial Guinea': ('spanish', 1778, 1968, 'Spanish colonial / provincial administration'),
    'Angola': ('portuguese', 1575, 1975, 'Portuguese colonial / overseas provincial administration'),
    'Mozambique': ('portuguese', 1505, 1975, 'Portuguese colonial / overseas provincial administration'),
    'Cape Verde': ('portuguese', 1462, 1975, 'Portuguese colonial / overseas provincial administration'),
    'São Tomé and Príncipe': ('portuguese', 1470, 1975, 'Portuguese colonial / overseas provincial administration'),
    'Macau': ('portuguese', 1557, 1999, 'Portuguese administration'),
    'India': ('british', 1858, 1947, 'British India'),
    'Burma': ('british', 1886, 1948, 'British colonial administration'),
    'Bahamas': ('british', 1718, 1973, 'British colonial administration'),
    'Barbados': ('british', 1627, 1966, 'British colonial administration'),
    'Belize': ('british', 1973, 1981, 'British dependent territory'),
    'Cyprus': ('british', 1878, 1960, 'British administration'),
    'Egypt': ('british', 1882, 1922, 'British occupation / protectorate'),
    'Fiji': ('british', 1874, 1970, 'British colonial administration'),
    'Hong Kong': ('british', 1841, 1997, 'British administration'),
    'Jamaica': ('british', 1655, 1962, 'British colonial administration'),
    'Kenya': ('british', 1895, 1963, 'British colonial / protectorate administration'),
    'Malawi': ('british', 1891, 1964, 'British protectorate / independence transition'),
    'Malaya': ('british', 1786, 1957, 'British settlements, protected states and Federation of Malaya'),
    'Tonga': ('british', 1900, 1970, 'British protected state'),
    'Maldives': ('british', 1887, 1965, 'British protected state'),
    'Malta': ('british', 1800, 1964, 'British colonial administration'),
    'Mauritius': ('british', 1810, 1968, 'British colonial administration'),
    'Seychelles': ('british', 1814, 1976, 'British colonial administration'),
    # SIMA introduced the first Solomon Islands dollar notes in October 1977,
    # before independence on 7 July 1978. Earlier protectorate pound notes use
    # their explicit British Solomon Islands identity, not this modern name.
    'Solomon Islands': ('british', 1977, 1978,
                       'Solomon Islands Monetary Authority — British protectorate issue'),
    'Ceylon': ('british', 1796, 1948, 'British colonial administration'),
    'South Africa': ('british', 1910, 1961, 'Union of South Africa — self-governing Dominion / Commonwealth'),
}
HISTORIC = {
    'British Guiana': ('british', 'British colony'),
    'British Honduras': ('british', 'British colony'),
    'British West Africa': ('british', 'West African Currency Board — regional currency area'),
    'British Caribbean Territories': ('british', 'British Caribbean Currency Board — regional currency area'),
    'East Caribbean States': ('british', 'East Caribbean regional currency authority — successor currency area'),
    'Straits Settlements': ('british', 'British Crown colony'),
    'Malaya and British Borneo': ('british', 'Regional currency board — Malaya and British Borneo'),
    'Sarawak': ('british', 'Raj of Sarawak / British protected state'),
    'Rhodesia and Nyasaland': ('british', 'Federation of Rhodesia and Nyasaland'),
    'Northern Rhodesia': ('british', 'British protectorate'),
    'Southern Rhodesia': ('british', 'Self-governing British colony'),
    'French Equatorial Africa': ('french', 'French colonial federation'),
    'French West Africa': ('french', 'French colonial federation'),
    'French Somaliland': ('french', 'French Somaliland — colonial territory'),
    'French Territory of the Afars and Issas': ('french', 'French overseas territory'),
    'French Cochin-China': ('french', 'French colony of Cochin-China'),
    'Portuguese Guinea': ('portuguese', 'Portuguese colonial / overseas provincial administration'),
    'Portuguese Timor': ('portuguese', 'Portuguese colonial / overseas provincial administration'),
    'Netherlands Indies': ('dutch', 'Netherlands East Indies — colonial currency area'),
    'Belgian Congo': ('belgian', 'Belgian colonial currency area'),
    'German East Africa': ('german', 'German colonial administration'),
}
BRITISH_DEPENDENCIES = {'Bermuda', 'Cayman Islands', 'Falkland Islands', 'Gibraltar',
                        'Saint Helena', 'Turks and Caicos Islands', 'Montserrat'}
FRENCH_OVERSEAS = {'French Guiana', 'Guadeloupe', 'Martinique', 'Réunion',
                   'New Caledonia', 'Saint Pierre and Miquelon', 'French Polynesia'}


def _year(value):
    m = re.search(r'(?<!\d)(1[5-9]\d{2}|20\d{2})(?!\d)', str(value or ''))
    return int(m.group()) if m else None


# Display/filing identities, deliberately separate from country normalization.
# A territorial suffix is specimen attribution, not another currency authority.
EASTERN_CARIBBEAN_ISSUERS = {
    'bccb': {
        'rank': 0, 'title': 'British Caribbean Territories — Eastern Group (BCCB)',
        'span': '1950–1965', 'entity_country': 'British Caribbean Territories',
        'denoms': '$1, $2, $5, $10, $20, $100',
        'denoms_note': 'Denominations issued by this authority across its history, including those not held in the collection.',
        'history': 'The British Caribbean Currency Board administered the common currency of the British Caribbean Territories (Eastern Group) from 1950. Its first unified banknotes entered circulation in 1951. The East Caribbean Currency Authority succeeded the Board in 1965; the two are separate issuing authorities.',
    },
    'ecca': {
        'rank': 1, 'title': 'East Caribbean States — Currency Authority (ECCA)',
        'span': '1965–1983', 'entity_country': 'East Caribbean States',
        'denoms': '$1, $5, $20, $100',
        'denoms_note': 'Denominations issued by the Currency Authority, including those not held in the collection.',
        'history': 'The East Caribbean Currency Authority succeeded the British Caribbean Currency Board in 1965 and first issued notes on 6 October 1965. Grenada joined the currency arrangement in 1968. Catalogue descriptions such as ND (1965) identify an undated note family, not the issue date of every territorial or signature variety. The full catalogue suffix and territorial attribution remain significant. The Eastern Caribbean Central Bank succeeded the Authority in 1983.',
    },
    'eccb': {
        'rank': 2, 'title': 'East Caribbean States — Central Bank (ECCB)',
        'span': 'Established 1983 · notes from 1984', 'entity_country': 'East Caribbean States',
        'denoms': '$1, $2, $5, $10, $20, $50, $100',
        'denoms_note': 'Across all Central Bank issues, including the withdrawn $1 and the $2 circulation commemorative. Denominations vary by series.',
        'history': 'The Eastern Caribbean Central Bank was established on 1 October 1983 as successor to the East Caribbean Currency Authority. Its first banknotes entered circulation on 15 November 1984. These central-bank issues form a separate issuer section within the continuing Eastern Caribbean currency area; territorial codes and full catalogue varieties are retained.',
    },
}
_CARIBBEAN_ISSUER_NAMES = {
    'bccb': ('British Caribbean Currency Board', 'BCCB',
             'British Caribbean Territories Currency Board',
             'British Caribbean Currency Board (The British Caribbean Territories, Eastern Group)',
             'Board of Commissioners of Currency, British Caribbean Territories (Eastern Group)',
             'Board of Commissioners of Currency British Caribbean Territories Eastern Group',
             'British Caribbean Territories (Eastern Group) Currency Board'),
    'ecca': ('East Caribbean Currency Authority', 'Eastern Caribbean Currency Authority', 'ECCA'),
    'eccb': ('Eastern Caribbean Central Bank', 'East Caribbean Central Bank', 'ECCB'),
}
_CARIBBEAN_ISSUER_LOOKUP = {fold(name): key for key, names in _CARIBBEAN_ISSUER_NAMES.items() for name in names}
_CARIBBEAN_COUNTRY_BOARD = {fold(name) for name in (
    'British Caribbean Territories', 'British Caribbean Territories (Eastern Group)',
    'British Caribbean Territories - Eastern Group', 'British Caribbean Territories Eastern Group')}
_CARIBBEAN_TERRITORIES = ('Anguilla', 'Antigua', 'Antigua and Barbuda', 'Barbados',
    'Dominica', 'Grenada', 'Montserrat', 'Saint Kitts', 'Saint Kitts and Nevis',
    'Saint Lucia', 'Saint Vincent', 'Saint Vincent and the Grenadines',
    'St. Kitts', 'St. Kitts and Nevis', 'St. Lucia', 'St. Vincent',
    'St. Vincent and the Grenadines')
_CARIBBEAN_COUNTRY_STATES = {fold(base + suffix) for base in ('East Caribbean States', 'Eastern Caribbean States')
    for suffix in ('',) + tuple(' - ' + territory for territory in _CARIBBEAN_TERRITORIES)
                         + tuple(' (' + territory + ')' for territory in _CARIBBEAN_TERRITORIES)}


def eastern_caribbean_issue(country, date=None, issuer=None, series=None):
    """Resolve explicit regional identity only; never infer an issuer from 1965.

    Raw country/issuer fields are not changed. A blank country with a named
    regional issuer is supported; a standalone territorial country is not an
    alias for the regional currency. Unknown/conflicting issuer text retains
    its own subsection and receives no borrowed Board/Authority history.
    """
    country_token = fold(country)
    country_issuer = _CARIBBEAN_ISSUER_LOOKUP.get(country_token)
    regional = country_token in _CARIBBEAN_COUNTRY_BOARD or country_token in _CARIBBEAN_COUNTRY_STATES or country_issuer
    issuer_text = str(issuer or '').strip()
    issuer_key = _CARIBBEAN_ISSUER_LOOKUP.get(fold(issuer_text))
    member = country_token in {fold(name) for name in _CARIBBEAN_TERRITORIES}
    if not regional and not ((not country_token or member) and issuer_key):
        return None
    # The actual named issuer takes precedence over a regional country label.
    key = issuer_key if issuer_text else (country_issuer or ('bccb' if country_token in _CARIBBEAN_COUNTRY_BOARD else None))
    if key:
        return {'family': 'Eastern Caribbean', 'key': key, **EASTERN_CARIBBEAN_ISSUERS[key]}
    return {
        'family': 'Eastern Caribbean', 'key': 'unresolved', 'rank': 3,
        'title': issuer_text or 'East Caribbean States — issuer not established',
        'span': '', 'entity_country': None,
        'history': 'The saved regional attribution is retained. The issuing authority has not been established; a recorded year alone does not identify the Currency Board, Currency Authority or Central Bank.',
    }


def eastern_caribbean_series(country, date=None, issuer=None, series=None):
    """A series filing key, not a claim about an undated variety's issue date."""
    regional = eastern_caribbean_issue(country, date, issuer, series)
    if not regional:
        return ''
    text = str(series or '').strip()
    years = re.findall(r'(?<!\d)(?:1[5-9]\d{2}|20\d{2})(?!\d)', text)
    if years:
        start, end = years[0], years[-1]
        # Only the reviewed BCCB 1953–1964 wording variants share a range
        # key; other descriptions can identify distinct designs/series.
        descriptor = fold(re.sub(r'(?<!\d)(?:1[5-9]\d{2}|20\d{2})(?!\d)', '', text))
        board_equivalent = (regional['key'] == 'bccb' and (start, end) == ('1953', '1964')
                            and descriptor in ('', 'currencyboardissue', 'elizabethiiissue'))
        if board_equivalent or re.fullmatch(r'(?:ND\s*)?\(?\s*\d{4}\s*\)?', text, re.I):
            return start + ':' + end
        return start + ':' + end + ':' + fold(text)
    if text:
        return str(_year(date) or 99999) + ':' + fold(text)
    year = str(_year(date) or 99999)
    return year + ':' + year


def catalogue_reference_sort(value):
    """Natural full-reference ordering; keeps namespace and every suffix."""
    text = re.sub(r'^\s*(?:pick|p)\s*[-.#]?\s*(?=\d)', 'p', str(value or ''), flags=re.I)
    text = re.sub(r'\s+', '', text.casefold())
    if text[:1].isdigit():
        text = 'p' + text
    return re.sub(r'\d+', lambda m: m.group().zfill(12), text) or '~'


def eastern_caribbean_denomination(value):
    """Read known written dollar denominations for filing, without saving edits."""
    words = {'one': '1', 'two': '2', 'five': '5', 'ten': '10', 'twenty': '20',
             'fifty': '50', 'one hundred': '100', 'hundred': '100'}
    match = re.fullmatch(r'\s*(one hundred|hundred|one|two|five|ten|twenty|fifty)\s+(dollars?)\s*', str(value or ''), re.I)
    return words[match[1].lower()] + ' ' + match[2] if match else value


_PACIFIC_BRANCHES = {
    'polynesia': ('Tahiti / French Polynesia', 0, ('Tahiti', 'French Oceania', 'French Polynesia', 'Tahiti / French Oceania')),
    'new-caledonia': ('New Caledonia', 1, ('New Caledonia', 'Nouvelle-Calédonie')),
    'common': ('Common French Pacific issues', 2, ('French Pacific Territories',)),
}
_PACIFIC_COUNTRIES = {fold(name): key for key, (_, _, names) in _PACIFIC_BRANCHES.items() for name in names}
_PACIFIC_IEOM = {fold(name) for name in ('IEOM', "Institut d'Émission d'Outre-Mer", "Institut d'Émission d'Outre-Mer (IEOM)")}
_PACIFIC_BDI = {fold(name) for name in ("Banque de l'Indochine", "Banque de l'Indo-Chine")}
_PACIFIC_BRANCH_ISSUERS = {
    branch: {fold(name) for name in (
        "Banque de l'Indochine, " + place, "Banque de l'Indochine " + place,
        "Banque de l'Indochine (" + place + ")", "Banque de l'Indochine (" + place + " branch)")}
    for branch, place in (('polynesia', 'Papeete'), ('new-caledonia', 'Nouméa'))
}


def french_pacific_issue(country, date=None, issuer=None, series=None):
    """Display lineage only. An IEOM issuer/date never supplies a territory."""
    branch = _PACIFIC_COUNTRIES.get(fold(country))
    if not branch:
        return None
    label, rank, _names = _PACIFIC_BRANCHES[branch]
    issuer_text = str(issuer or '').strip()
    token = fold(issuer_text)
    issuer_key = ('ieom' if token in _PACIFIC_IEOM else
                  'bdi' if branch != 'common' and token in (_PACIFIC_BDI | _PACIFIC_BRANCH_ISSUERS[branch]) else 'unresolved')
    if branch == 'polynesia':
        history = ('Tahiti and Papeete issues belong to the French Oceania / French Polynesia territorial lineage. '
                   'French Oceania was renamed French Polynesia in 1957. Banque de l’Indochine Papeete and later '
                   'IEOM territorial notes remain distinct from Nouméa issues and later common French Pacific notes. '
                   'This lineage grouping does not date a later note to the pre-1957 administration.')
        entity_country = 'French Polynesia' if fold(country) == fold('French Polynesia') else 'French Oceania'
    elif branch == 'new-caledonia':
        history = ('New Caledonian notes are filed by their Nouméa territorial attribution. Banque de l’Indochine '
                   'Nouméa issues and later IEOM territorial issues are distinct from Papeete / French Polynesia '
                   'and from the common French Pacific issues. Original dates, issuer wording and full catalogue varieties are retained.')
        entity_country = 'New Caledonia'
    else:
        history = ('This section contains notes explicitly attributed to the common French Pacific issue area. '
                   'IEOM introduced a common 10,000-franc note in 1986 and later removed territorial distinctions '
                   'across the note family. An IEOM issuer or date alone cannot distinguish these issues from earlier '
                   'Papeete or Nouméa notes. New Hebrides remains a separate Anglo-French currency history.')
        entity_country = 'French Pacific Territories'
    result = {
        'family_key': 'french-pacific', 'family': 'French Pacific', 'group': 'french',
        'family_description': 'Separate Polynesian, New Caledonian and common regional issues; historical names and catalogue scopes are retained.',
        'key': branch + '-' + issuer_key, 'branch': branch, 'rank': rank * 10 + {'bdi': 0, 'ieom': 1, 'unresolved': 9}[issuer_key],
        'title': label + ' — ' + ({'bdi': 'Banque de l’Indochine', 'ieom': 'IEOM'}.get(issuer_key) or issuer_text or 'issuer not established'),
        'span': '', 'history': history, 'entity_country': entity_country if issuer_key != 'unresolved' else None,
        'catalogue_scope': branch, 'issuer_key': issuer_key,
    }
    if issuer_key == 'unresolved':
        result['history'] += ' The issuing authority is not established by the recognized issuer labels; no issue roster is assumed.'
    elif issuer_key == 'ieom':
        result['denoms'] = ('500, 1,000, 5,000, 10,000 francs' if branch == 'common' else '100, 500, 1,000, 5,000 francs')
        result['denoms_note'] = ('Common regional IEOM note family; not a territorial Pick-number equivalence.' if branch == 'common' else
                                'IEOM territorial issues for this branch; denominations vary by series. The common 10,000-franc issue is filed separately.')
    return result


def collection_family_issue(country, date=None, issuer=None, series=None):
    """Shared display metadata. Family membership is never catalogue identity."""
    caribbean = eastern_caribbean_issue(country, date, issuer, series)
    if caribbean:
        return {**caribbean, 'family_key': 'eastern-caribbean', 'group': 'british',
                'family_description': 'One regional currency family, with separate Currency Board, Currency Authority and Central Bank issues.',
                'catalogue_scope': caribbean.get('entity_country')}
    pacific = french_pacific_issue(country, date, issuer, series)
    if pacific:
        return pacific
    return banknote_africa.regional_issue(country, date, issuer, series)


def collection_family_for_row(row):
    """Row-aware display scopes; original references never become aliases."""
    values = dict(row)
    family = collection_family_issue(*(values.get(k) for k in ('country', 'date_1', 'issuer', 'series')))
    if not family:
        return None
    if family['family_key'] == 'french-pacific' and family['key'] == 'new-caledonia-bdi':
        # Only explicit Pick references establish these researched type rosters.
        # Other namespaces, unknown dates and contradictory ranges stay broad.
        text = str(values.get('pick_number') or '').strip()
        picks = {match.lower() for match in re.findall(
            r'(?<![A-Za-z0-9])(?:Pick|P)\s*[#.-]?\s*(\d+[a-z]*)(?![A-Za-z0-9])', text, re.I)}
        if not picks and re.fullmatch(r'\d+[a-z]*', text, re.I):
            picks = {text.lower()}
        ref = re.fullmatch(r'(48|49|50)([a-z]*)', next(iter(picks))) if len(picks) == 1 else None
        year = exact_year(values.get('date_1'))
        if ref and ref[1] in ('48', '49') and year == 1944:
            family.update(section_key='new-caledonia-bdi-1944',
                          title=family['title'] + ' — 1944 Australian-printed issue',
                          denoms='5, 20 francs',
                          denoms_note='Exact 1944 Australian-printed Pick 48 and 49 issue; not the full Banque de l’Indochine denomination range.')
        elif ref and ref[1] == '50' and year and 1951 <= year <= 1963:
            family.update(section_key='new-caledonia-bdi-p50',
                          title=family['title'] + ' — 1951–1963 type',
                          denoms='20 francs',
                          denoms_note='Pick 50 type, dated 1951, 1954/1958 and 1963 by variety; the stored date and full suffix remain unchanged.')
    return family


def collection_family_section_key(family):
    key = family['family_key'] + '-' + family.get('section_key', family['key'])
    # Distinct unresolved authorities must not share report history identity.
    if 'unresolved' in family['key']:
        key += '-' + fold(family['title'])
    return key


def collection_family_series(country, date=None, issuer=None, series=None):
    family = collection_family_issue(country, date, issuer, series)
    if not family:
        return ''
    if family['family_key'] == 'eastern-caribbean':
        return eastern_caribbean_series(country, date, issuer, series)
    text = str(series or '').strip()
    year = _year(text) or _year(date) or 99999
    # Full design/range wording remains significant; plain dated/ND forms
    # share a key with the same recorded year without rewriting either field.
    suffix = '' if re.fullmatch(r'(?:ND\s*)?\(?\s*\d{4}\s*\)?', text, re.I) else fold(text)
    return str(year) + ':' + suffix


AMERICAN_COLONIES = {
    name: name + ' Colony' for name in (
        'Connecticut', 'Delaware', 'Georgia', 'Maryland', 'Massachusetts',
        'New Hampshire', 'New Jersey', 'New York', 'North Carolina', 'Pennsylvania',
        'Rhode Island', 'South Carolina', 'Virginia')
}
_AMERICAN_COUNTRIES = {
    spelling for name, colony in AMERICAN_COLONIES.items()
    for spelling in (name, colony, 'Colony of ' + name, 'Province of ' + name)
} | {'Massachusetts Bay', 'Rhode Island and Providence Plantations', 'Colonial America'}


def american_colonial_country(country, date=None, issuer=None, series=None):
    """Resolve a named pre-independence issue, never a generic 1776 date alone.

    The NYC Water Works series is specifically colonial, including its final
    March 5, 1776 issue. Other transition-year notes need an explicit colony
    or province issuer; later state and Continental Congress notes stay apart.
    """
    country = canonical_country(country) or ''
    if country not in _AMERICAN_COUNTRIES and country != 'United States of America':
        return None
    y = _year(date) or (_year(series) if not date else None)
    if y is None or not 1690 <= y <= 1776:
        return None
    evidence = fold(' '.join((issuer or '', series or '')))
    if (1774 <= y <= 1776 and 'waterworks' in evidence
            and country in {'United States of America', 'Colonial America', 'New York',
                            'New York Colony', 'Colony of New York', 'Province of New York'}
            and 'newyork' in fold(country + ' ' + (issuer or '') + ' ' + (series or ''))):
        return AMERICAN_COLONIES['New York']
    for name, colony in AMERICAN_COLONIES.items():
        if country not in {'United States of America', 'Colonial America', name, colony,
                           'Colony of ' + name, 'Province of ' + name}:
            continue
        token = fold(name)
        explicit_issuer = any(prefix + token in fold(issuer)
                              for prefix in ('colonyof', 'provinceof'))
        explicit_country = country in {colony, 'Colony of ' + name, 'Province of ' + name} and colony != name
        if explicit_issuer or explicit_country or (y < 1776 and country == name):
            return colony
    return None


@lru_cache(maxsize=8192)
def classify(country, date=None, issuer=None, series=None):
    country = canonical_country(country) or ''
    colonial_country = american_colonial_country(country, date, issuer, series)
    country = colonial_country or country
    y = _year(date)
    evidence = fold(' '.join((issuer or '', series or '')))
    def result(key, label, uncertain=False):
        return {**GROUP_BY_KEY[key], 'country': country, 'period': label, 'uncertain': uncertain}
    def other(label='Independent or other issue; administration not assigned', uncertain=False):
        return result('other', label, uncertain)
    if country == 'Solomon Islands':
        # Source: CBSI Currency Overview and research paper RP-012014; the
        # Solomon Islands Independence Order 1978 fixes 7 July 1978. SIMA
        # continued after independence, so its name or an ND series date alone
        # cannot establish a pre-independence issue. Keep transition years and
        # malformed/ranged dates unresolved, and do not overlook a later issuer.
        exact = exact_year(date)
        issuer_key = fold(issuer or '')
        compatible = issuer_key in {
            '', 'sima', 'solomonislandsmonetaryauthority',
            'thesolomonislandsmonetaryauthority',
            'solomonislandsmonetaryauthoritysima',
            'solomonislandmonetaryauthority',
        }
        if exact == 1977 and compatible:
            return result('british', PERIODS[country][3])
        if exact == 1978:
            return other('Independence transition — 7 July 1978; exact issue date needed', True)
        if exact and exact > 1978:
            return other('Independent Solomon Islands issue')
        return other('Date / issuer needed to establish pre-independence issue', True)
    regional = collection_family_issue(country, date, issuer, series)
    if regional:
        review = regional.get('review_note')
        return result(regional['group'], regional['title'] + (' — ' + review if review else ''),
                      'unresolved' in regional['key'] or bool(review))
    japanese = any(s in evidence for s in ('japanesegovernment', 'japaneseoccupation',
                   'southerndevelopmentbank', 'militaryyen', 'bankofchosen')) or (country == 'China' and y and 1938 <= y <= 1945
                    and any(s in evidence for s in ('federalreservebankofchina', 'centralreservebankofchina')))
    if country == 'Philippines':
        if japanese:
            label = 'Japanese occupation issue'
        elif y and y < 1898:
            label = 'Spanish colonial period'
        elif y and y >= 1946:
            label = 'Republic of the Philippines' if y > 1946 else 'Commonwealth / Republic transition (1946)'
        elif 'victory' in evidence or 'liberation' in evidence:
            label = 'Commonwealth — liberation issue'
        elif y and y >= 1935:
            label = 'Commonwealth of the Philippines'
        elif y and y >= 1898:
            label = 'American administration' if y > 1898 else 'Spanish / American transition (1898)'
        else:
            label = 'Philippine issue — period not established'
        return result('us', label, not bool(y))
    if japanese and country in {'Burma', 'Malaya', 'Netherlands Indies', 'China',
                                'French Indo-China', 'Hong Kong', 'Korea'}:
        return result('japanese', 'Japanese occupation / military currency')
    if country == 'Manchukuo':
        return result('japanese', 'Manchukuo — Japanese-dependent state')
    if country == 'Korea' and y and 1910 <= y <= 1945:
        return result('japanese', 'Korea under Japanese rule')
    if country in {'Canada', 'Australia', 'New Zealand'}:
        boundary = {'Canada': 1867, 'Australia': 1901, 'New Zealand': 1907}[country]
        return result('british', ('British colonial period' if y and y < boundary else
                      'Dominion / independent Commonwealth issue'))
    if country in {'Guernsey', 'Jersey', 'Isle of Man'}:
        return result('british', 'Crown Dependency')
    if country in BRITISH_DEPENDENCIES:
        return result('british', 'British dependent / overseas territory')
    if country == 'Rhodesia':
        return result('british', 'Rhodesia — UDI administration (unrecognized)' if y and y > 1965 else
                      ('Rhodesia — UDI transition year' if y == 1965 else 'Southern Rhodesia / Rhodesia'))
    if country == 'British East Africa':
        return result('british', 'East African Currency Board — independence transition' if y and y >= 1961
                      else 'East African Currency Board — colonial / protectorate currency area')
    if country == 'Yemen' and 'southarabiancurrencyauthority' in evidence:
        return result('british', 'South Arabian Currency Authority — Aden and South Arabian currency area')
    if country == 'Ceylon' and y and 1948 <= y < 1972:
        return result('british', 'Dominion of Ceylon — independent Commonwealth issue')
    if country in FRENCH_OVERSEAS:
        department = country in {'French Guiana', 'Guadeloupe', 'Martinique', 'Réunion'}
        label = ('French overseas department' if department and y and y >= 1946 else
                 'French overseas territory / colonial issue')
        if y and y >= 2000 and any(s in evidence for s in ('caissecentraledelafrance', 'banquedelaguyane', 'ccfom')):
            return result('french', label + ' — date / historical issuer needs review', True)
        return result('french', label)
    if country == 'French Indo-China':
        return result('french', 'Associated States of Cambodia, Laos and Vietnam — transitional issue'
                      if 'institutdemission' in evidence or (y and y >= 1952) else
                      'French Indo-China — colonial / protectorate currency area')
    if country.startswith('West African States'):
        return result('french', 'BCEAO — independent states / successor regional currency area')
    if country == 'Italian Somaliland':
        return result('italian', 'UN Trust Territory of Somaliland under Italian administration'
                      if y and 1950 <= y <= 1960 else 'Italian Somaliland — colonial period')
    if country == 'New Hebrides':
        return result('joint', 'Anglo-French condominium / Vanuatu transition (1980)' if y == 1980 else
                      'Anglo-French condominium', y == 1980 or not bool(y))
    if country in {'Faroe Islands', 'Greenland'}:
        return result('danish', ('Faroe Islands — autonomous territory of the Danish realm' if country == 'Faroe Islands'
                      and y and y >= 1948 else 'Greenland — Danish realm' if country == 'Greenland'
                      and y and y >= 1953 else 'Danish territorial administration'))
    if country == 'Puerto Rico' and y and y > 1898:
        return result('us', 'Puerto Rico — United States territory')
    if colonial_country:
        return result('british', 'British North America — colonial issue')
    if fold(country) in _CONFEDERATE_COUNTRIES:
        return result('us', 'Confederate States issue — separate from US federal issues')
    if country == 'United States of America':
        return result('us', 'United States issue')
    colonial_america = country in {'New Jersey', 'Pennsylvania Colony'} or (country.startswith('United States (') and 'colonial' in country.lower())
    if colonial_america and y and 1690 <= y <= 1776 and (('colony' in evidence) or y < 1776):
        return result('british', 'British North America — colonial issue')
    if country in _AMERICAN_COUNTRIES or country.startswith('United States ('):
        return result('us', 'American colonial / state issue — see issuer and date')
    if country == 'Timor' and 'banconacionalultramarino' in evidence and y and y < 1975:
        return result('portuguese', 'Portuguese Timor — overseas provincial issue')
    if country in HISTORIC:
        key, label = HISTORIC[country]
        return result(key, label)
    if country in PERIODS:
        key, start, end, label = PERIODS[country]
        # Independent issuers resolve mixed / boundary-year records before dates.
        independent = any(s in evidence for s in ('banquecentraledalgerie', 'banconacionaldecuba',
                         'reservebankofmalawi', 'republicofcyprus'))
        if independent:
            return other('Independent national issue')
        if y and start <= y < end:
            return result(key, label)
        if y == end:
            return result(key, label + ' — transition year; exact issue date matters', True)
        return other('Independent / successor issue' if y and y > end else
                     'Date needed to establish administration', not bool(y))
    return other()


def row_classification(row):
    values = dict(row)
    return classify(*(values.get(k) for k in ('country', 'date_1', 'issuer', 'series')))


def sort_country(country, date=None, issuer=None, series=None):
    # Domestic US issues lead their requested Philippine collection family.
    canonical = canonical_country(country) or 'zzz'
    family = collection_family_issue(country, date, issuer, series)
    if family:
        return family['family']
    if fold(canonical) in _CONFEDERATE_COUNTRIES:
        return '0 United States Confederate States'
    colony = american_colonial_country(canonical, date, issuer, series)
    if colony:
        # Keep each colony together before sorting its eras and issue dates.
        return '0 United States ' + colony
    us_family = canonical == 'United States of America' or canonical.startswith('United States (') or canonical in _AMERICAN_COUNTRIES
    return '0 United States' if us_family else canonical
