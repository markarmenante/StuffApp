"""Reviewed African currency families for display, never record migration.

An issuing authority plus a bounded territorial attribution identifies a
section. The full saved country, catalogue reference and series still belong
to the note; these families are not duplicate-detection namespaces or a claim
that each member territory is represented in the collection.

Primary source evidence and denomination scopes: docs/banknote-africa.md.
"""
import re
import unicodedata


def _fold(value):
    return re.sub(r'[^a-z0-9]', '', unicodedata.normalize(
        'NFKD', str(value or '')).encode('ascii', 'ignore').decode().lower())


def _tokens(values):
    return frozenset(_fold(value) for value in values)


def _exact_year(value):
    text = str(value or '').strip()
    return int(text) if re.fullmatch(r'(?:1[5-9]|20)\d{2}', text) else None


_WEST_MEMBERS = (
    'Senegal', 'Togo', 'Ivory Coast', "Côte d'Ivoire", 'Dahomey', 'Benin',
    'Upper Volta', 'Burkina Faso', 'Niger', 'Mali', 'French Sudan',
    'Guinea', 'French Guinea', 'Mauritania', 'Guinea-Bissau',
)
_WEST_REGIONS = ('French West Africa', 'Afrique Occidentale Française',
                 'West African States', 'États de l’Afrique de l’Ouest')
_WEST_COUNTRIES = _tokens(_WEST_REGIONS + _WEST_MEMBERS + tuple(
    base + suffix for base in ('West African States', 'French West Africa')
    for member in _WEST_MEMBERS for suffix in (' (' + member + ')', ' - ' + member)))

_CENTRAL_MEMBERS = (
    'Cameroon', 'Cameroun', 'French Cameroon', 'French Cameroun',
    'Gabon', 'Middle Congo', 'Moyen-Congo', 'French Congo',
    'Republic of the Congo', 'Congo Republic', 'Congo-Brazzaville',
    'Central African Republic', 'République Centrafricaine',
    'Ubangi-Shari', 'Oubangui-Chari', 'Chad', 'Tchad', 'Equatorial Guinea',
)
_CENTRAL_REGIONS = ('French Equatorial Africa', 'Afrique Équatoriale Française',
                    'Central African States', 'États de l’Afrique Centrale')
_CENTRAL_COUNTRIES = _tokens(_CENTRAL_REGIONS + _CENTRAL_MEMBERS + tuple(
    base + suffix for base in ('Central African States', 'French Equatorial Africa')
    for member in _CENTRAL_MEMBERS for suffix in (' (' + member + ')', ' - ' + member)))
# Equatorial Guinea joined BEAC in 1985. It was not an AEF/Cameroon territory.
_COLONIAL_CENTRAL_COUNTRIES = _CENTRAL_COUNTRIES - _tokens(
    ('Equatorial Guinea',) + tuple(base + suffix for base in
     ('Central African States', 'French Equatorial Africa') for suffix in
     (' (Equatorial Guinea)', ' - Equatorial Guinea')))

_ISSUER_NAMES = {
    'bao': ('Banque de l’Afrique Occidentale', 'BAO',
            'Banque de l’Afrique Occidentale (BAO)', 'Bank of French West Africa'),
    'bceao': ('Banque Centrale des États de l’Afrique de l’Ouest', 'BCEAO',
              'Banque Centrale des États de l’Afrique de l’Ouest (BCEAO)',
              'Central Bank of West African States',
              'Central Bank of the West African States'),
    'ccfom': ('Caisse Centrale de la France d’Outre-Mer', 'CCFOM',
              'Caisse Centrale de la France d’Outre-Mer (CCFOM)'),
    'ieaefc': ('Institut d’Émission de l’Afrique Équatoriale Française et du Cameroun',
               'Institut d’Émission de l’Afrique Équatoriale Française et du Cameroun (IEAEFC)',
               'Institut d’Émission de l’Afrique Équatoriale et du Cameroun', 'IEAEFC'),
    'beac': ('Banque des États de l’Afrique Centrale', 'BEAC',
             'Banque des États de l’Afrique Centrale (BEAC)',
             'Bank of Central African States', 'Bank of the Central African States'),
}
_ISSUER_LOOKUP = {_fold(name): key for key, names in _ISSUER_NAMES.items() for name in names}

_FAMILIES = {
    'west-african-franc': {
        'family': 'West African franc area',
        'family_description': 'French West African issues and the later regional currency of the independent West African states. Issuing authorities and territorial catalogue varieties remain separate.',
    },
    'central-african-franc': {
        'family': 'Central African franc area',
        'family_description': 'French Equatorial African and Cameroon issues, followed by the regional currency of independent Central African states. Issuing authorities and territorial catalogue varieties remain separate.',
    },
}

_ISSUERS = {
    'bao': {
        'family_key': 'west-african-franc', 'rank': 0,
        'title': 'French West Africa — Banque de l’Afrique Occidentale (BAO)',
        'span': '1901–1955', 'entity_country': 'French West Africa',
        'denoms': '5, 10, 25, 50, 100, 500, 1,000, 5,000 francs',
        'denoms_note': 'Documented West African BAO denominations across its issues, including values not held. The same institution also issued for other territories; those catalogue attributions remain separate.',
        'history': 'The Banque de l’Afrique Occidentale succeeded the Banque du Sénégal in 1901. Its West African note issues preceded the Institut d’Émission de l’Afrique Occidentale Française et du Togo, established in 1955, and the BCEAO created in 1959. They are separate issuing authorities.',
    },
    'bceao': {
        'family_key': 'west-african-franc', 'rank': 2,
        'title': 'West African States — BCEAO',
        'span': '1959–present · independent monetary union from 1962',
        'entity_country': 'West African States',
        'denoms': '50, 100, 500, 1,000, 2,000, 2,500, 5,000, 10,000 francs',
        'denoms_note': 'Denominations across BCEAO issues, including withdrawn notes and the 2,000-franc note introduced in 2003. Not every value was issued in every series or territorial variety.',
        'history': 'The BCEAO replaced the Institut d’Émission de l’Afrique Occidentale Française et du Togo on 4 April 1959. The independent states formed the West African Monetary Union in 1962; Togo joined in December 1963. Regional notes retain their country attribution and full catalogue suffix. A catalogue family date does not establish the issue date of every territorial variety.',
    },
    'ccfom': {
        'family_key': 'central-african-franc', 'rank': 1,
        'title': 'Equatorial Africa & Cameroon — CCFOM', 'span': '1944–1955',
        'entity_country': None,
        'denoms': '5, 10, 20, 50, 100, 500, 1,000, 5,000 francs',
        'denoms_note': 'Central African CCFOM denominations documented across the Biang and Bifra series. Other territories served by CCFOM retain their own catalogue identity.',
        'history': 'The Caisse Centrale de la France d’Outre-Mer was created in 1944, succeeding the Caisse Centrale de la France Libre. Its Central African issues include the British-printed Biang and French-printed Bifra series. The AEF and Cameroon issuing institute took over the regional issue privilege in 1955.',
    },
    'ieaefc': {
        'family_key': 'central-african-franc', 'rank': 2,
        'title': 'Equatorial Africa & Cameroon — Institut d’Émission',
        'span': '1955–1959 · notes from 1957', 'entity_country': None,
        'denoms': '5, 10, 20, 50, 100, 500, 1,000 francs',
        'denoms_note': 'Includes the 1957 5-, 10- and 20-franc CCFOM-Bifra designs modified to carry IEAEFC, as well as its 50-, 100-, 500- and 1,000-franc series.',
        'history': 'The Institut d’Émission de l’Afrique Équatoriale Française et du Cameroun was established in 1955 and began its note issues in 1957. It succeeded CCFOM for this region and was replaced by the Banque Centrale des États de l’Afrique Équatoriale et du Cameroun in 1959. These institutional names identify different issuers, not interchangeable spellings.',
    },
    'beac': {
        'family_key': 'central-african-franc', 'rank': 4,
        'title': 'Central African States — BEAC',
        'span': 'Established 1972 · operations from 1973',
        'entity_country': 'Central African States',
        'denoms': '500, 1,000, 2,000, 5,000, 10,000 francs',
        'denoms_note': 'Across BEAC issues; the 2,000-franc denomination joined the range in 1993. Earlier national-face designs and later country identification codes remain distinct catalogue varieties.',
        'history': 'The Banque des États de l’Afrique Centrale was established in 1972 and began operations in 1973, succeeding the BCEAEC. These are issues of a regional bank serving independent states, not French colonial issues. Equatorial Guinea joined in 1985. Earlier notes show country-specific designs; later common designs retain country identification codes.',
    },
}


def regional_issue(country, date=None, issuer=None, series=None):
    """Return new display metadata only for an explicit, compatible issuer.

    No substring bank matching, chronology-based issuer guess, country mutation,
    or reuse of a broad currency-family key as a catalogue identity is allowed.
    BAO and CCFOM worked outside these regions, so a blank country is insufficient.
    """
    country_text = str(country or '').strip()
    country_key = _fold(country_text)
    issuer_text = str(issuer or '').strip()
    key = _ISSUER_LOOKUP.get(_fold(issuer_text))
    if not issuer_text:
        key = _ISSUER_LOOKUP.get(country_key)
    if not key:
        return None

    if key in ('bao', 'bceao'):
        allowed = country_key in _WEST_COUNTRIES
    else:
        allowed = country_key in (_COLONIAL_CENTRAL_COUNTRIES
                                  if key in ('ccfom', 'ieaefc') else _CENTRAL_COUNTRIES)
    if not allowed:
        # These names uniquely identify a regional bank, unlike BAO or CCFOM.
        allowed = key in ('bceao', 'ieaefc', 'beac') and (
            not country_key or _ISSUER_LOOKUP.get(country_key) == key)
    if not allowed:
        return None

    result = {'group': 'french', 'key': key, **_ISSUERS[key]}
    result.update(_FAMILIES[result['family_key']])
    # Keep the exact territorial attribution available to consumers. This is
    # descriptive metadata, not a replacement namespace for Pick matching.
    result['catalogue_scope'] = country_text or 'Regional issue — territory unspecified'
    if key in ('ccfom', 'ieaefc'):
        if country_key in _tokens(('French Equatorial Africa', 'Afrique Équatoriale Française')):
            result['entity_country'] = 'French Equatorial Africa'
        elif country_key in _tokens(('Cameroon', 'Cameroun', 'French Cameroon', 'French Cameroun')):
            result['entity_country'] = 'Cameroon'

    year = _exact_year(date)
    notes = []
    if key == 'bceao' and year and year < 1959:
        notes.append(f'Review date: saved {year} predates the BCEAO’s creation in 1959; verify the catalogue date against the actual issue.')
    is_togo = country_key == _fold('Togo') or country_key in _tokens(
        ('West African States (Togo)', 'West African States - Togo'))
    if key == 'bceao' and is_togo and year and year < 1963:
        notes.append(f'Review territorial date: Togo joined UMOA in December 1963; saved {year} does not establish the issue date of this Togo variety.')
    if key == 'beac' and year and year < 1973:
        notes.append(f'Review issue date: BEAC began operations in 1973; saved {year} may identify a design rather than this issuer’s issue date.')
    if key == 'beac' and country_key == _fold('Equatorial Guinea') and year and year < 1985:
        notes.append(f'Review territorial date: Equatorial Guinea joined BEAC in 1985; verify saved {year} against the territorial issue.')
    if notes:
        result['review_note'] = ' '.join(notes)
    return result
