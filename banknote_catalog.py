"""Banknote filing catalogue: spelling aliases and historical collection groups.

These are collection relationships, not claims of present sovereignty. Country,
issuer and date remain separate facts. See docs/banknote-catalog.md for sources,
transition-year limitations and the explicitly requested Philippine exception.
"""
import re
import unicodedata
from functools import lru_cache


def fold(value):
    return re.sub(r'[^a-z0-9]', '', unicodedata.normalize('NFKD', value or '')
                  .encode('ascii', 'ignore').decode().lower())


# Only spelling equivalents; never merge a successor state or currency area.
ALIASES = {
    'United States of America': ('United States', 'USA', 'US', 'U.S.A.', 'U.S.'),
    'French Indo-China': ('French Indochina', 'French Indo China', 'Indochina',
                         'Indo-China', 'Indo China'),
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


def country_spellings(value):
    canonical = canonical_country(value) or ''
    return (canonical,) + ALIASES.get(canonical, ())


def country_search(value):
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


@lru_cache(maxsize=8192)
def classify(country, date=None, issuer=None, series=None):
    country = canonical_country(country) or ''
    y = _year(date)
    evidence = fold(' '.join((issuer or '', series or '')))
    def result(key, label, uncertain=False):
        return {**GROUP_BY_KEY[key], 'country': country, 'period': label, 'uncertain': uncertain}
    def other(label='Independent or other issue; administration not assigned', uncertain=False):
        return result('other', label, uncertain)
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
    if country == 'United States of America':
        return result('us', 'United States issue')
    colonial_america = country in {'New Jersey', 'Pennsylvania Colony'} or (country.startswith('United States (') and 'colonial' in country.lower())
    if colonial_america and (('colony' in evidence) or (y and y < 1776)):
        return result('british', 'British North America — colonial issue')
    if country in {'New Jersey', 'Pennsylvania Colony', 'Rhode Island and Providence Plantations'} or country.startswith('United States ('):
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


def sort_country(country):
    # Domestic US issues lead their requested Philippine collection family.
    canonical = canonical_country(country) or 'zzz'
    us_family = canonical == 'United States of America' or canonical.startswith('United States (') or canonical in {
        'New Jersey', 'Pennsylvania Colony', 'Rhode Island and Providence Plantations'}
    return '0 United States' if us_family else canonical
