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
SINGAPORE = 'https://www.mas.gov.sg/currency/history-of-currency-in-singapore'
MALAYSIA_HISTORY = 'https://www.malaysia.gov.my/en/government/learn-about-malaysia/malaysian-history'
UK_TERRITORIES = 'https://commonslibrary.parliament.uk/research-briefings/cbp-9706/'


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
    _entity('british', 'Singapore', sources=(SINGAPORE,),
            note='Colonial branch-bank and shared currency-board issues; independent Singapore national issues from 1967 are separate.'),
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

# Gap-search scope is distinct from broad collection-family membership. These
# conservative YEAR bounds reuse the reviewed filing/market policy; the end is
# exclusive because a printed year cannot establish which side of a transition
# date a note was actually issued. None means unresolved/excluded, not open-ended.
# Do not import market_colonial: its offer guard consumes this metadata.
def _scan_period(start, end, kind, source, note='', end_date=None):
    return dict(year_start=start, year_end=end, end_kind=kind, source=source,
                note=note or 'Reviewed administration scope; transition year excluded.',
                end_date=end_date)


for _entry in _entries:
    _entry.update(independence_date=None, independence_source=None, scan_period=None)
    for _name in _entry['countries']:
        _period = catalog.PERIODS.get(_name)
        if _entry['issued'] is True and _period and _period[0] == _entry['group']:
            _entry['scan_period'] = _scan_period(
                _period[1], _period[2], 'administration_end',
                'banknote_catalog.PERIODS; docs/banknote-catalog.md')
            break

# Already reviewed additional market periods. Explicit entity keys prevent a
# shared modern country name from lending its dates to another administration.
_REVIEWED_SCAN_PERIODS = {
    'british-canada': (1763, 1867, 'confederation'),
    'british-australia': (1788, 1901, 'federation'),
    'british-new-zealand': (1840, 1907, 'dominion'),
    'british-south-africa': (1806, 1910, 'union'),
    'us-philippines': (1565, 1946, 'independence'),
    'portuguese-portuguese-guinea': (1879, 1973, 'independence'),
    'portuguese-portuguese-timor': (1702, 1975, 'administration_end'),
    'portuguese-portuguese-india': (1510, 1961, 'transfer'),
    'french-french-india': (1674, 1954, 'transfer'),
    'french-french-indo-china': (1887, 1954, 'administration_end'),
    'french-french-cochin-china': (1862, 1949, 'administration_end'),
    'belgian-belgian-congo': (1908, 1960, 'independence'),
    'dutch-netherlands-indies': (1800, 1945, 'independence'),
    'british-british-guiana': (1831, 1966, 'independence'),
    'british-british-honduras': (1862, 1981, 'independence'),
    'british-straits-settlements': (1826, 1942, 'occupation'),
    'british-sarawak': (1888, 1963, 'transfer'),
    'british-british-north-borneo': (1881, 1963, 'transfer'),
    'british-rhodesia-and-nyasaland': (1953, 1963, 'dissolution'),
    'british-southern-rhodesia': (1923, 1965, 'administration_end'),
    'british-rhodesia': (1923, 1965, 'administration_end'),
    'british-british-east-africa': (1895, 1961, 'administration_end'),
    'british-british-west-africa': (1912, 1957, 'administration_end'),
    'british-british-caribbean-territories': (1950, 1962, 'administration_end'),
    'british-malaya-and-british-borneo': (1952, 1957, 'first_constituent_independence'),
    'french-french-west-africa': (1895, 1958, 'dissolution'),
    'french-french-equatorial-africa': (1910, 1958, 'dissolution'),
    'french-french-somaliland': (1896, 1967, 'renaming'),
    'french-french-territory-of-the-afars-and-issas': (1967, 1977, 'independence'),
    'joint-new-hebrides': (1906, 1980, 'independence'),
    'british-palestine': (1920, 1948, 'mandate_end'),
    'french-syria': (1920, 1943, 'independence'),
    'british-trinidad-and-tobago': (1899, 1962, 'independence'),
    'british-western-samoa': (1920, 1962, 'independence'),
    'british-bahrain': (1861, 1971, 'independence'),
    'british-qatar-and-dubai': (1916, 1971, 'administration_end'),
    'dutch-suriname': (1667, 1975, 'independence'),
    'danish-danish-west-indies': (1754, 1917, 'transfer'),
    'japanese-taiwan': (1899, 1945, 'administration_end'),
    'japanese-manchukuo': (1932, 1945, 'administration_end'),
    'italian-italian-east-africa': (1936, 1941, 'occupation_end'),
    'italian-italian-somaliland': (1889, 1941, 'occupation'),
    'german-german-east-africa': (1885, 1918, 'administration_end'),
    'german-german-south-west-africa': (1884, 1915, 'administration_end'),
    'german-kiautschou': (1898, 1914, 'occupation'),
    'british-zanzibar': (1890, 1963, 'independence'),
    # The entity matcher already bounds these documented historical issues.
    'british-newfoundland': (1850, 1949, 'confederation'),
    'british-grenada': (1837, 1974, 'independence'),
    'french-senegal': (1895, 1960, 'independence'),
    'french-ivory-coast': (1893, 1960, 'independence'),
    'danish-iceland': (1885, 1918, 'sovereignty'),
    'british-kuwait': (1899, 1961, 'independence'),
    'british-south-arabia': (1965, 1967, 'independence'),
    'german-kamerun': (1884, 1916, 'occupation'),
    'dutch-curacao': (1828, 1954, 'autonomy'),
}
for _entry in _entries:
    if _entry['key'] in _REVIEWED_SCAN_PERIODS and _entry['issued'] is True:
        _entry['scan_period'] = _scan_period(
            *_REVIEWED_SCAN_PERIODS[_entry['key']],
            'market_colonial.PERIODS / entity date rules; docs/market-validation.md')

# Exact independence dates are only populated from identified primary sources.
# Confederation, a name change, a transfer and the end of occupation are not
# silently called independence. Dates do not broaden the conservative year gate.
_INDEPENDENCE = {
    'british-india': ('1947-08-15', 'https://history.state.gov/countries/india'),
    'british-bahamas': ('1973-07-10', 'https://history.state.gov/countries/bahamas'),
    'british-barbados': ('1966-11-30', 'https://history.state.gov/countries/barbados'),
    'british-belize': ('1981-09-21', 'https://history.state.gov/countries/belize'),
    'british-british-honduras': ('1981-09-21', 'https://history.state.gov/countries/belize'),
    'british-brunei': ('1984-01-01', 'https://history.state.gov/countries/brunei'),
    'british-singapore': ('1965-08-09', 'https://www.mfa.gov.sg/about-mfa/histories-and-milestones/'),
    'british-malaya': ('1957-08-31', MALAYSIA_HISTORY),
    'french-dahomey': ('1960-08-01', 'https://www.gouv.bj/pages/histoire/'),
    'french-french-sudan': ('1960-09-22', 'https://independance.africamuseum.be/sites/independance.africamuseum.be/files/files/booklet_independance_en.pdf'),
    'us-philippines': ('1946-07-04', 'https://history.state.gov/countries/philippines'),
    'french-french-territory-of-the-afars-and-issas': (
        '1977-06-27', 'https://diplomatie.gouv.dj/djibouti-historique'),
}
_NEW_SCAN_PERIODS = {
    'dutch-aruba': _scan_period(1986, None, 'continuing_kingdom_member',
        'https://www.cbaruba.org/the-aruban-florin/',
        'Aruban florin from 1986 Status Aparte; autonomous country within the Kingdom, not an independence date.'),
    'dutch-netherlands-new-guinea': _scan_period(1950, 1962, 'transfer',
        'https://www.nationaalarchief.nl/onderzoeken/archief/2.10.60/download/pdf',
        'Distinct Dutch administration 1950–1962; UNTEA transfer on 1 October 1962: https://peacekeeping.un.org/sites/default/files/past/unsfbackgr.html',
        '1962-10-01'),
    'belgian-belgian-congo-and-ruanda-urundi': _scan_period(1952, 1960, 'administration_end',
        'https://www.bcc.cd/la-banque/histoire/historique-de-la-banque-centrale',
        'BCCBRU operational from October 1952 and liquidated in 1960; shared entity does not extend beyond Congolese independence.'),
    'belgian-ruanda-urundi': _scan_period(1960, 1962, 'administration_end',
        'https://archive.brb.bi/en/content/historic',
        'BERB common bank from August 1960; colonial scope ends before 1962 independence: https://www.fdnb.gov.bi/fr/le-1er-juillet-de-chaque-annee-date-memorable-pour-tout-burundais-ou-quil-soit'),
    'british-british-solomon-islands': _scan_period(1916, 1934, 'documented_issue',
        'https://banknote.news/files/tag-british-solomon-islands.php',
        'The Banknote Book publisher documents Government issues from 1916 through 1933; scope is the verified issue span, not an independence claim.'),
    'british-turks-and-caicos-islands': _scan_period(1928, 1929, 'documented_issue',
        'https://www.greysheet.com/prices/detail/10th-january-1928-sig-3-southby-frith-prefix-a-1-s-n-a-1-07105-07664/gsid/141809/60/0',
        'The documented 1928 circulating government issue is eligible; the territory remains dependent. Earlier issue bounds are not asserted.'),
    'french-french-polynesia': _scan_period(1957, None, 'continuing_dependency',
        'https://www.ispf.pf/publication/diagnostic-territorial-2021',
        'French Polynesia name and status from 1957; continuing French collectivity. French Oceania predecessor remains separately identified.'),
    'french-french-sudan': _scan_period(1895, 1960, 'independence',
        'app.COUNTRY_COLONIAL[mali]; https://independance.africamuseum.be/sites/independance.africamuseum.be/files/files/booklet_independance_en.pdf',
        'Reviewed French Sudan colonial scope; independent Mali and its national issues are excluded.'),
    'french-dahomey': _scan_period(1894, 1960, 'independence',
        'https://www.gouv.bj/pages/histoire/',
        'Government history dates the colony to 1894 and international sovereignty to 1 August 1960.'),
    'french-upper-senegal-and-niger': _scan_period(1904, 1920, 'renaming',
        'https://independance.africamuseum.be/sites/independance.africamuseum.be/files/files/booklet_independance_en.pdf',
        'Museum history dates Upper Senegal and Niger to 1904 and the French Sudan renaming to 1920; transition year excluded.'),
    'japanese-hong-kong': _scan_period(1941, 1945, 'occupation_end',
        'https://www.grs.gov.hk/ws/online/80VWR/en/home/index.html',
        'Hong Kong Government Records Service documents the 1941–1945 Japanese occupation and forced use of military notes.'),
    'british-singapore': _scan_period(1840, 1965, 'independence', SINGAPORE,
        'MAS records Singapore branch-bank notes from 1840; independence was 9 August 1965.'),
    'british-brunei': _scan_period(1967, 1984, 'independence',
        'https://cms.bdcb.gov.bn/storage/uploads/publications/17089426511258820.pdf',
        'Brunei Currency Board notes from 1967; independence was 1 January 1984.'),
    'british-bermuda': _scan_period(1914, None, 'continuing_dependency',
        'https://nmb.bm/exhibit/banknotes-of-bermuda/',
        'First Bermuda banknotes in 1914; continuing overseas territory, with no independence date. Status: ' + UK_TERRITORIES),
    'british-cayman-islands': _scan_period(1972, None, 'continuing_dependency',
        'https://www.cima.ky/currency',
        'Currency Board issue from 1 May 1972; continuing overseas territory. Status: ' + UK_TERRITORIES),
    'british-jersey': _scan_period(1941, None, 'continuing_crown_dependency',
        'https://www.gov.je/TaxesMoney/JerseyCurrency/Pages/CurrencyMakesMoney.aspx',
        'States notes from 1941, resumed in 1963; Crown Dependency, not an independent successor or a colony.'),
    'british-guernsey': _scan_period(1816, None, 'continuing_crown_dependency',
        'https://www.greysheet.com/prices/sp/guernsey-states-of-guernsey?nodeid=10705',
        'Documented States notes from 1816; Crown Dependency with no independence date. Status: ' + UK_TERRITORIES),
    'british-alderney': _scan_period(1810, 1811, 'documented_issue',
        'https://en.numista.com/234220',
        'Only the documented 1810 private circulating issue is presently scoped; no invented independence date.'),
    'british-gibraltar': _scan_period(1704, None, 'continuing_dependency',
        'app.COUNTRY_COLONIAL[gibraltar]; ' + UK_TERRITORIES,
        'Existing reviewed British administration from 1704; continuing overseas territory.'),
    'british-saint-helena': _scan_period(1659, None, 'continuing_dependency',
        'app.COUNTRY_COLONIAL[saint-helena]; ' + UK_TERRITORIES,
        'Existing reviewed English administration from 1659; continuing overseas territory.'),
    'danish-faroe-islands': _scan_period(1940, None, 'continuing_dependency', FAROE,
        'Existing app.COUNTRY_ERAS starts the distinct wartime currency in 1940; continuing self-governing part of Denmark.'),
    'french-saint-pierre-and-miquelon': _scan_period(1950, None, 'continuing_dependency',
        'app.BANKNOTE_COLONIAL_WANTLIST; https://www.iedom.fr/saint-pierre-et-miquelon/',
        'Existing reviewed 1950 circulating overprints; continuing French overseas collectivity, no independence date.'),
    'french-french-oceania': _scan_period(1905, None, 'continuing_dependency',
        'app.BANKNOTE_COLONIAL_WANTLIST; https://www.ieom.fr/polynesie-francaise/',
        'Existing reviewed Papeete issues from 1905; renamed French Polynesia remains a French collectivity, with no independence date.'),
}
for _entry in _entries:
    if _entry['key'] in _NEW_SCAN_PERIODS:
        _entry['scan_period'] = _NEW_SCAN_PERIODS[_entry['key']]
    if _entry['key'] in _INDEPENDENCE:
        _entry['independence_date'], _entry['independence_source'] = _INDEPENDENCE[_entry['key']]
        if _entry['scan_period']:
            _entry['scan_period']['end_kind'] = 'independence'
            _entry['scan_period']['end_date'] = _entry['independence_date']
    if _entry['key'] in {'british-british-north-borneo', 'british-sarawak'}:
        _entry['scan_period'].update(end_date='1963-09-16', source=MALAYSIA_HISTORY,
            note='Joined Malaysia on 16 September 1963; recorded as a transfer/formation cutoff, not an independence date.')
    if _entry['key'] == 'danish-iceland':
        _entry['scan_period']['note'] = ('Existing app.COUNTRY_COLONIAL distinguishes sovereignty in union in 1918 '
            'from the republic in 1944; the earlier sovereignty cutoff governs pre-independence gaps.')
    if _entry['key'] == 'german-kamerun':
        _entry['scan_period']['source'] = 'https://www.bundesarchiv.de/en/research-our-records/research-by-topic/sources-on-colonial-history/geographical-access-to-colonial-history-holdings/'
    if _entry['key'] == 'dutch-curacao':
        _entry['scan_period']['source'] = 'https://centralbank.cw/about-the-bank/history; app._COLONY_END'
    if _entry['key'] == 'british-south-arabia':
        _entry['scan_period']['source'] = 'https://en.numista.com/catalogue/issuing_entity.php?id=5825; app._COLONY_END'
    if _entry['key'] == 'british-kuwait':
        _entry['scan_period'].update(source='app.COUNTRY_COLONIAL[kuwait]',
            note='Protectorate ended in 1961. A year-only 1961 first issue cannot establish pre-independence timing and is conservatively excluded.')
    if _entry['countries'][0] in catalog.AMERICAN_COLONIES.values():
        _entry['independence_date'] = '1776-07-04'
        _entry['independence_source'] = 'https://www.archives.gov/milestone-documents/declaration-of-independence'
        _entry['scan_period'] = _scan_period(1690, 1776, 'independence', US_COLONIES,
            'American colonial paper-money era begins in 1690; this is not an asserted founding date for each colony.', '1776-07-04')
    if _entry['key'] == 'british-south-africa':
        # Earlier South African names can describe independent Boer republics.
        # Broad collection-family membership is insufficient colonial identity.
        _entry['scan_period'] = None

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
    'Singapore': ('british-singapore', 1840, 1965),
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
        if token == 'singapore' and not any(term in evidence for term in (
                'unionbankofcalcutta', 'boardofcommissionersofcurrencymalaya',
                'boardofcommissionersofcurrencythestraitssettlements',
                'boardofcommissionersofcurrencystraitssettlements')):
            return None
        if any(term in evidence for term in ('republic', 'banquecentraledesyrie')):
            return None
        return ENTITY_BY_KEY[key]
    return None
