"""Sourced banknote entities for collection coverage, not a sovereignty census.

``issued`` describes a separate circulating note issue in the stated entity's
scope: True = documented, False = documented absence, None = not established.
It never derives a negative from an empty collection or a missing catalogue hit.
Matching respects the existing historical filing first. See
docs/banknote-entities.md for scope, evidence and regional-currency limits.
"""
import re
import unicodedata

import banknote_catalog as catalog


TBB = 'https://www.greysheet.com/world-paper-money-prices'
BNU = 'https://www.bnu.tl/Institucional/Historia/Paginas/Historia-do-BNU.aspx'
BEAC = 'https://www.beac.int/billets-pieces/signes-monetaires/billets-de-type-ancien/'
US_COLONIES = 'https://www.uscurrency.gov/history'
FAROE = 'https://www.nationalbanken.dk/en/what-we-do/notes-and-coins/faroese-banknote-series'
DANISH_HISTORY = 'https://www.nationalbanken.dk/media/14xdu45n/nationalbanken-1818-2018-webappendix-en.pdf'
BSP = 'https://www.bsp.gov.ph/Pages/CoinsAndNotes/HistoryOfPhilippineMoney/HistoryOfPhilippineMoney.aspx'
KENYA = 'https://www.centralbank.go.ke/currency-history/'
VANUATU = 'https://www.rbv.gov.vu/index.php/en/about/our-history'


def _slug(value):
    ascii_value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode()
    return re.sub(r'[^a-z0-9]+', '-', ascii_value.lower()).strip('-')


def _entity(group, name, *, key=None, label=None, aliases=(), issued=True,
            sources=(TBB,), note='Documented circulating banknote issue; see the entity and issuer catalogue.'):
    return {
        'key': group + '-' + (key or _slug(name)), 'group': group,
        'label': label or name, 'countries': (name,) + tuple(aliases),
        'issued': issued, 'sources': tuple(sources), 'note': note,
    }


def _many(group, names, **kwargs):
    return [_entity(group, name, **kwargs) for name in names]


_entries = []
_entries += _many('british', (
    'Australia', 'Bahamas', 'Bahrain', 'Barbados', 'Belize', 'Bermuda',
    'British Caribbean Territories', 'British East Africa', 'British Guiana',
    'British Honduras', 'British North Borneo', 'British Solomon Islands',
    'British West Africa', 'Brunei', 'Burma', 'Canada', 'Cayman Islands', 'Ceylon',
    'Cyprus', 'Egypt', 'Falkland Islands', 'Fiji', 'Gibraltar', 'Grenada',
    'Guernsey', 'Hong Kong', 'India', 'Isle of Man', 'Jamaica', 'Jersey',
    'Kuwait', 'Malaya', 'Malaya and British Borneo', 'Maldives', 'Malta',
    'Mauritius', 'Newfoundland', 'New Zealand', 'Palestine', 'Qatar and Dubai',
    'Rhodesia', 'Rhodesia and Nyasaland', 'Sarawak', 'Seychelles',
    'South Africa', 'Southern Rhodesia', 'Saint Helena', 'Straits Settlements',
    'Tonga', 'Trinidad and Tobago', 'Turks and Caicos Islands', 'Western Samoa',
    'Zanzibar', 'Gilbert and Ellice Islands',
))
_entries += [
    _entity('british', 'Alderney', sources=('https://en.numista.com/234220',),
            note='Private circulating one-pound issue of 1810, Pick S181; current coin-only government issues do not erase this historical note.'),
    _entity('british', 'Pitcairn Islands', aliases=('Pitcairn',), issued=False,
            sources=('https://static1.squarespace.com/static/6526ff6fef608a3828c13d05/t/655839b56f256e21c55fe7e6/1781566287508/Currency+Ordinance.pdf',
                     'https://en.numista.com/catalogue/pitcairn-3.html'),
            note='No separate Pitcairn circulating banknote series: New Zealand notes are legal tender and local currency issuance is coinage. Private fantasy notes are excluded.'),
    _entity('british', 'East Caribbean States', note='Successor regional currency area; independent members are not described as British-controlled.'),
    _entity('british', 'Yemen', key='south-arabia', label='Aden / South Arabia',
            aliases=('South Arabia', 'South Arabian Federation', 'Aden'),
            note='South Arabian Currency Authority issue; matching Yemen still requires the existing issuer-based classification.'),
    _entity('british', 'Saint Kitts', aliases=('St. Kitts', 'Saint Christopher', 'St. Christopher'),
            note='Historical St. Christopher / St. Kitts note issues; regional East Caribbean notes remain separate.'),
    _entity('british', 'Cocos (Keeling) Islands', aliases=('Keeling-Cocos Islands', 'Cocos Keeling Islands'),
            note='Locally circulating estate/company paper included by the banknote catalogue; not a modern sovereign currency.'),
]
_entries += _many('british', tuple(catalog.AMERICAN_COLONIES.values()), sources=(US_COLONIES,),
                  note='British-American colonial paper money; later state and federal issues are separate.')
_entries += _many('british', (
    'Northern Rhodesia', 'Nyasaland', 'Malawi', 'Kenya', 'Uganda', 'Tanganyika',
    'Gold Coast', 'Nigeria', 'Sierra Leone', 'Gambia', 'British Somaliland',
    'British Cameroons', 'Montserrat', 'Anguilla',
), issued=None, sources=(KENYA, TBB),
    note='Regional currency and territorial history do not by themselves establish a separate territorial banknote issue; issuance remains unverified here.')

_entries += _many('french', (
    'Algeria', 'Tunisia', 'Morocco', 'Madagascar', 'Comoros', 'Cameroon', 'Togo',
    'Lebanon', 'Laos', 'French Guiana', 'Guadeloupe', 'Martinique', 'Réunion',
    'New Caledonia', 'Saint Pierre and Miquelon', 'French Polynesia',
    'French Indo-China', 'French Cochin-China', 'French Equatorial Africa',
    'French West Africa', 'French Somaliland', 'French Territory of the Afars and Issas',
    'French India', 'Syria', 'French Oceania', 'French Antilles',
    'French Pacific Territories', 'French Sudan', 'Senegal', 'Ivory Coast',
    'Dahomey', 'Upper Senegal and Niger',
))
_entries += [
    _entity('french', 'West African States', note='BCEAO successor currency area of independent states; not a claim of French administration.'),
]
_entries += _many('french', ('French Guinea', 'Gabon', 'Middle Congo', 'Ubangi-Shari', 'Chad', 'Upper Volta', 'Niger'),
    issued=None, sources=(BEAC, TBB),
    note='Regional issues circulated; a separate issue under this exact historical territorial identity is not established by this roster.')

_entries += _many('portuguese', ('Angola', 'Mozambique', 'Cape Verde', 'São Tomé and Príncipe',
                                'Macau', 'Portuguese Guinea', 'Portuguese Timor', 'Portuguese India'),
                  sources=(BNU, TBB), note='Portuguese overseas note issues; independent successor issues and later Macau issues remain separate.')
_entries += [
    _entity('portuguese', 'Nyassa Company', aliases=('Companhia do Nyassa', 'Niassa Company'), issued=None,
            note='Retained from the existing wantlist; a circulating banknote issue has not been verified. Chartered-company status alone is not evidence of notes.'),
    _entity('portuguese', 'Mozambique Company', aliases=('Companhia de Moçambique', 'Companhia de Mocambique'),
            note='Chartered-company circulating issue in Mozambique; kept distinct from BNU territorial issues.'),
]
_entries += _many('dutch', ('Netherlands Indies', 'Netherlands New Guinea', 'Suriname',
                           'Curaçao', 'Netherlands Antilles', 'Aruba'),
                  note='Distinct territorial or autonomous currency issue; the issue period determines the relationship.')
_entries += _many('belgian', ('Belgian Congo', 'Belgian Congo and Ruanda-Urundi', 'Ruanda-Urundi'))
_entries += [_entity('belgian', 'Congo Free State', issued=None,
                    note='A separate Free State circulating banknote issue is not established here; Belgian Congo issues must not be used as its evidence.')]
_entries += _many('german', ('German East Africa', 'German South West Africa', 'Kamerun', 'Kiautschou'))
_entries += _many('german', ('German New Guinea', 'German Samoa', 'Togoland', 'German Caroline Islands',
                            'German Mariana Islands', 'German Marshall Islands'), issued=None,
    note='A circulating issue under German administration is not established here. Later occupation notes and German commemorative Notgeld do not establish one.')
_entries += _many('italian', ('Italian East Africa', 'Italian Somaliland'))
_entries += _many('italian', ('Italian Eritrea', 'Italian Libya', 'Italian Dodecanese'), issued=None,
    note='Use of metropolitan lire does not establish a separate territorial issue; issuance remains unverified here.')
_entries += [
    _entity('us', 'United States of America', key='united-states', aliases=('United States', 'USA'), sources=(US_COLONIES,)),
    _entity('us', 'Confederate States', aliases=('Confederate States of America',),
            note='Confederate obligations remain distinct from United States federal issues within the existing collection family.'),
    _entity('us', 'Philippines', sources=(BSP,), note='All Philippine periods share this explicitly requested collection family; it does not imply continuous US rule.'),
    _entity('us', 'Puerto Rico', note='Issues in the US territorial period only; Spanish-period issues belong to the Spanish entity.'),
    _entity('other', 'Hawaii', note='Kingdom and Republic of Hawaii paper retain the existing independent/other filing. US federal Hawaii-overprint notes remain US federal issues.'),
]
_entries += _many('us', ('Guam', 'American Samoa', 'United States Virgin Islands'), issued=None,
    note='Use of US dollars does not establish whether a separate historic circulating note issue existed.')
_entries += _many('spanish', ('Cuba', 'Puerto Rico'))
_entries += _many('spanish', ('Equatorial Guinea', 'Spanish Sahara', 'Ifni', 'Spanish Morocco'), issued=None,
    note='A separate banknote issue under Spanish administration is not established here; successor-state or metropolitan notes are not evidence.')
_entries += _many('japanese', ('Manchukuo', 'Korea', 'Taiwan', 'Burma', 'Malaya',
                              'Netherlands Indies', 'China', 'French Indo-China', 'Hong Kong'),
                  note='Japanese-dependent or occupation issues only; independent national issues remain separate. Philippine issues stay in their requested US collection family.')
_entries += [_entity('japanese', 'Oceania', label='Japanese occupation · Oceania',
                    note='Japanese occupation shilling notes for Pacific territories; not an independent Oceanian state.')]
_entries += [
    _entity('danish', 'Faroe Islands', sources=(FAROE,), note='Distinct Faroese banknote series within the Danish realm.'),
    _entity('danish', 'Greenland', note='Historical local Greenlandic note issues. The absence of a modern separate series does not erase these earlier issues.'),
    _entity('danish', 'Danish West Indies', sources=(DANISH_HISTORY, TBB),
            note='Danish-West Indian banknotes; later US Virgin Islands currency is separate.'),
    _entity('danish', 'Iceland', sources=(DANISH_HISTORY, TBB),
            note='Icelandic notes in the Danish monetary/union period; independent Republic issues are separate.'),
    _entity('joint', 'New Hebrides', sources=(VANUATU, TBB),
            note='Anglo-French condominium issues; Vanuatu successor issues are separate.'),
    _entity('joint', 'Anglo-Egyptian Sudan', issued=None,
            note='Separate condominium banknote issuance is not established here; Egyptian circulation and later Sudanese national issues are not equivalent.'),
    _entity('joint', 'Tangier International Zone', issued=None,
            note='A separate international-zone banknote issue is not established here.'),
]

# Spelling or explicit historical-name equivalents only; never successor states.
_ALIASES = {
    'british-british-north-borneo': ('North Borneo',),
    'british-saint-helena': ('St. Helena',),
    'british-british-solomon-islands': ('British Solomon Islands Protectorate',),
    'french-french-territory-of-the-afars-and-issas': ('French Afars and Issas',),
    'german-kiautschou': ('Kiau-Chau', 'Kiaochow', 'Kiautschau'),
    'german-kamerun': ('German Kamerun', 'German Cameroon'),
    'danish-faroe-islands': ('Faeroe Islands',),
    'japanese-taiwan': ('Formosa',),
}
for _entry in _entries:
    _entry['countries'] += _ALIASES.get(_entry['key'], ())

_DIRECT_SOURCES = {
    'british-gilbert-and-ellice-islands': ('https://www.greysheet.com/prices/nc/gilbert-and-ellice-islands-world-paper-money/8491',),
    'french-french-india': ('https://www.greysheet.com/prices/nc/french-india-world-paper-money/8484',),
    'french-french-cochin-china': ('https://www.greysheet.com/prices/nc/french-cochinchina-world-paper-money/8482',),
    'italian-italian-east-africa': ('https://www.greysheet.com/prices/nc/italian-east-africa-world-paper-money/8375',),
    'german-kamerun': ('https://www.greysheet.com/prices/nc/kamerun-world-paper-money/8900',),
    'danish-greenland': ('https://www.greysheet.com/prices/nc/greenland-world-paper-money/8363',),
    'japanese-taiwan': ('https://museum.mof.gov.tw/eng/singlehtml/009e91624d7848449733665a5bc46832?cntId=40b0615d3772461288a3145b9c474187',),
    'british-brunei': ('https://cms.bdcb.gov.bn/storage/uploads/publications/17089426511258820.pdf', TBB),
    'dutch-suriname': ('https://www.cbvs.sr/nieuwsartikelen?catid=27&id=80%3Ahet-noodgeld-van-suriname&view=article', TBB),
}
for _entry in _entries:
    if _entry['key'] in _DIRECT_SOURCES:
        _entry['sources'] = _DIRECT_SOURCES[_entry['key']]

ENTITY_CATALOG = tuple(_entries)
ENTITY_BY_KEY = {entity['key']: entity for entity in ENTITY_CATALOG}


_BY_GROUP_COUNTRY = {
    (entity['group'], catalog.fold(catalog.canonical_country(name))): entity
    for entity in ENTITY_CATALOG for name in entity['countries']
}

# Explicit historic labels not recognized by the existing filing catalogue.
# This adds coverage only; it never changes a record's filing or list order.
_EXPLICIT_KEYS = (
    'british-alderney', 'british-pitcairn-islands', 'british-british-north-borneo',
    'british-british-solomon-islands', 'british-saint-helena',
    'british-qatar-and-dubai', 'british-gilbert-and-ellice-islands',
    'british-saint-kitts', 'british-cocos-keeling-islands',
    'british-nyasaland', 'british-gold-coast', 'british-british-somaliland',
    'british-british-cameroons', 'british-anguilla',
    'french-french-territory-of-the-afars-and-issas',
    'french-french-india', 'french-french-oceania', 'french-french-antilles',
    'french-french-pacific-territories', 'french-french-sudan',
    'french-dahomey', 'french-upper-senegal-and-niger', 'french-french-guinea',
    'french-middle-congo', 'french-ubangi-shari', 'french-upper-volta',
    'portuguese-portuguese-india', 'portuguese-nyassa-company',
    'portuguese-mozambique-company', 'dutch-netherlands-new-guinea',
    'dutch-curacao', 'dutch-netherlands-antilles', 'dutch-aruba',
    'belgian-belgian-congo-and-ruanda-urundi', 'belgian-ruanda-urundi',
    'belgian-congo-free-state', 'german-german-south-west-africa',
    'german-kamerun', 'german-german-new-guinea', 'german-german-samoa',
    'german-togoland', 'german-german-caroline-islands',
    'german-german-mariana-islands', 'german-german-marshall-islands',
    'italian-italian-east-africa', 'italian-italian-eritrea',
    'italian-italian-libya', 'italian-italian-dodecanese',
    'us-guam', 'us-american-samoa', 'us-united-states-virgin-islands',
    'spanish-spanish-sahara', 'spanish-ifni', 'spanish-spanish-morocco',
    'danish-danish-west-indies', 'danish-faroe-islands', 'joint-anglo-egyptian-sudan',
    'joint-tangier-international-zone',
)
_EXPLICIT_COUNTRIES = {
    catalog.fold(catalog.canonical_country(name)): ENTITY_BY_KEY[key]
    for key in _EXPLICIT_KEYS for name in ENTITY_BY_KEY[key]['countries']
}
# Additional names shared by historical and independent issues. End years are
# excluded where a year alone cannot resolve the actual transition date.
_DATED_COUNTRIES = {
    'Palestine': ('british-palestine', 1927, 1948),
    'Newfoundland': ('british-newfoundland', 1850, 1949),
    'Bahrain': ('british-bahrain', 1965, 1971),
    'Brunei': ('british-brunei', 1967, 1984),
    'Grenada': ('british-grenada', 1837, 1974),
    'Kuwait': ('british-kuwait', 1961, 1962),
    'Trinidad and Tobago': ('british-trinidad-and-tobago', 1814, 1962),
    'Western Samoa': ('british-western-samoa', 1914, 1962),
    'Zanzibar': ('british-zanzibar', 1890, 1963),
    'Suriname': ('dutch-suriname', 1667, 1975),
    'Syria': ('french-syria', 1920, 1943),
    'Senegal': ('french-senegal', 1895, 1960),
    'Ivory Coast': ('french-ivory-coast', 1893, 1960),
    'Iceland': ('danish-iceland', 1885, 1944),
}
_DATED_COUNTRIES = {catalog.fold(name): rule for name, rule in _DATED_COUNTRIES.items()}


def entity_for_row(row, classification=None):
    """Match coverage without changing the existing historical filing.

    An unlisted or ambiguous identity returns None, never a nonissuer claim.
    Exact historical names can match across the current filing groups; a
    successor's shared name needs a supported period and compatible issuer.
    """
    values = dict(row)
    info = classification or catalog.row_classification(row)
    group = info.get('key')
    country = catalog.canonical_country(info.get('country') or values.get('country') or '')
    if group == 'french' and country.startswith('West African States'):
        return ENTITY_BY_KEY['french-west-african-states']
    if group == 'portuguese' and country == 'Timor':
        return ENTITY_BY_KEY['portuguese-portuguese-timor']
    token = catalog.fold(country)
    match = _BY_GROUP_COUNTRY.get((group, token))
    if match:
        return match
    # Preserve an existing occupation or other positively assigned group.
    if group != 'other':
        return None
    evidence = catalog.fold(' '.join(str(values.get(k) or '') for k in ('issuer', 'series')))
    japanese = any(term in evidence for term in (
        'japanesegovernment', 'japaneseoccupation', 'southerndevelopmentbank',
        'militaryyen', 'bankofchosen'))
    year = catalog.exact_year(values.get('date_1'))
    if token in {'taiwan', 'formosa'}:
        if (year is not None and 1899 <= year < 1945 and
                (japanese or any(term in evidence for term in ('bankoftaiwan', 'taiwanbank')))):
            return ENTITY_BY_KEY['japanese-taiwan']
        return None
    if token in {'aden', 'southarabia', 'southarabianfederation'}:
        if 'southarabiancurrencyauthority' in evidence:
            return ENTITY_BY_KEY['british-south-arabia']
        return None
    if token == 'oceania' and japanese:
        return ENTITY_BY_KEY['japanese-oceania']
    if japanese:
        return None
    if token in {catalog.fold(name) for name in ENTITY_BY_KEY['german-kiautschou']['countries']}:
        if year is not None and 1898 <= year < 1914:
            return ENTITY_BY_KEY['german-kiautschou']
        return None
    if token in _EXPLICIT_COUNTRIES:
        entry = _EXPLICIT_COUNTRIES[token]
        if entry['key'] == 'british-saint-kitts':
            if ((year is not None and year >= 1983) or any(term in evidence for term in (
                    'easterncaribbeancentralbank', 'eastcaribbeancurrencyauthority',
                    'easterncaribbeancurrencyauthority', 'britishcaribbeancurrencyboard'))):
                return None
        if entry['group'] == 'german' and entry['issued'] is None:
            if year is None or not 1884 <= year < 1914:
                return None
        return entry
    if token in _DATED_COUNTRIES:
        key, start, end = _DATED_COUNTRIES[token]
        if year is None or not start <= year < end:
            return None
        # The first Currency Board issue preceded independence in 1961.
        # Require that authority instead of guessing from the year alone.
        if token == 'kuwait' and 'kuwaitcurrencyboard' not in evidence:
            return None
        if any(term in evidence for term in ('republic', 'banquecentraledesyrie')):
            return None
        return ENTITY_BY_KEY[key]
    return None
