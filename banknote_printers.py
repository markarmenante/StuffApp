"""Conservative printer identities for analysis; never rewrite catalogue credits."""
import re


def _key(value):
    # Only harmless name punctuation is ignored. In particular, retain ?, /,
    # semicolons and other qualification marks so uncertain or joint credits
    # cannot accidentally become a single confirmed printer.
    value = value.casefold().replace('&', ' and ')
    return ' '.join(re.sub(r'[.,()]', ' ', value).split())


_COMPANY = r'(?: (?:and )?(?:co|company))?(?: (?:limited|ltd|plc))?'
_BRITISH_COUNTRIES = (
    'England', 'United Kingdom', 'UK', 'U.K.', 'Great Britain',
    'England, United Kingdom', 'England, UK', 'England, U.K.',
    'England, Great Britain',
)


def _places(cities, countries):
    return (*cities, *countries,
            *(f'{city}, {country}' for city in cities for country in countries))


def _identity(names, places, company_suffix=False):
    name = '(?:' + '|'.join(re.escape(_key(n)) for n in names) + ')'
    if company_suffix:
        name += _COMPANY
    location = '(?:' + '|'.join(re.escape(_key(p)) for p in places) + ')'
    # A repeated identity covers both "Thomas De La Rue (TDLR)" and
    # "BWC (Bradbury Wilkinson and Company)". Both parts must name the
    # SAME firm; this deliberately does not parse a multi-printer credit.
    return re.compile(rf'{name}(?: {name})?(?: {location})?')


_PRINTERS = (
    ('Thomas De La Rue', _identity(
        ('Thomas De La Rue', 'De La Rue', 'TDLR', 'T.D.L.R.'),
        _places(('London',), _BRITISH_COUNTRIES), company_suffix=True)),
    ('Bradbury Wilkinson', _identity(
        ('Bradbury Wilkinson', 'Bradbury & Wilkinson', 'BWC', 'B.W.C.'),
        _places(('London', 'New Malden', 'New Malden, Surrey', 'Surrey'),
                _BRITISH_COUNTRIES), company_suffix=True)),
    ('Banque de France', _identity(
        ('Banque de France', 'BdF', 'B.d.F.'),
        _places(('Paris',), ('France',)))),
)


def canonical_printer(value):
    """Group known name, abbreviation and address variants of the same firm.

    Require a whole-value match. Unknown firms, uncertain attributions, joint
    credits and unrecognized qualifiers retain their original wording; an
    acquisition or a shared word is not evidence that two printers are one.
    """
    original = str(value).strip() if value is not None else ''
    key = _key(original)
    for label, pattern in _PRINTERS:
        if pattern.fullmatch(key):
            return label
    return original
