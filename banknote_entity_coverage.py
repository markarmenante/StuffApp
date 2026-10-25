"""Collection coverage by direct issues and documented regional currencies.

This is deliberately separate from ``banknote_entities.entity_for_row``:
regional holdings can cover a territory without becoming that territory's
separate issue for candidate identity, catalogue numbering or list filing.
Callers retain responsibility for access restrictions and purchase status.
"""
import re

import banknote_catalog as catalog
import banknote_entities as entities


# MAS identifies the five participating territories. Sarawak Museum preserves
# the 1953-dated notes; MAS's 1954 date describes their introduction in Singapore.
# BNM records the board's replacement on 12 June 1967. The IMF records Malaya's
# 1957 independence, the 1963 federation and Singapore's 1965 independence.
# Coverage here uses complete pre-transition years, not later circulation.
REGIONAL_SOURCES = (
    'https://www.mas.gov.sg/currency/history-of-currency-in-singapore',
    'https://sites.google.com/view/jms-pameran-numismatik-2021-en/'
    'exploring-sarawak-museum-collections/british-borneo-era',
    'https://www.bnm.gov.my/significant-milestones-in-the-malaysian-foreign-exchange-market',
    'https://www.elibrary.imf.org/display/book/9781455215935/ch004.xml',
)

_BOARD_ENTITY = 'british-malaya-and-british-borneo'
_MEMBERS = (
    ('british-malaya', 1957),
    ('british-singapore', 1965),
    ('british-sarawak', 1963),
    ('british-british-north-borneo', 1963),
    ('british-brunei', 1967),
)


def _issuer_token(value):
    if not isinstance(value, str):
        return ''
    value = re.sub(r'^\s*the\s+', '', value, flags=re.I)
    return catalog.fold(value.replace('&', ' and '))


# The short form appears on notes beneath the separately printed regional name.
# It is accepted only alongside the existing exact regional filing identity.
_BOARD_ISSUERS = frozenset(_issuer_token(name) for name in (
    'Board of Commissioners of Currency',
    'Board of Commissioners of Currency, Malaya and British Borneo',
    'Commissioners of Currency, Malaya and British Borneo',
    'Malaya and British Borneo Board of Commissioners of Currency',
))


def _regional_year(row, primary):
    if not primary or primary['key'] != _BOARD_ENTITY:
        return None
    if _issuer_token(row.get('issuer')) not in _BOARD_ISSUERS:
        return None
    first = catalog.exact_year(row.get('date_1'))
    last_value = row.get('date_2')
    last = first if last_value in (None, '') else catalog.exact_year(last_value)
    if first is None or last is None or not 1953 <= first <= last < 1967:
        return None
    # A range crossing a member's transition cannot establish the earlier period.
    return last


def entities_for_row(row, classification=None):
    """Return copied entity definitions with explicit direct/regional coverage.

    ``coverage_kind`` is ``direct`` for the existing primary identity and
    ``regional`` for an additional documented member. ``coverage_note`` explains
    shared coverage without claiming a separate territorial issue. Unknown,
    transition-year, conflicting-issuer and successor notes gain no regional
    coverage. No record, entity definition, or supplied classification changes.
    """
    values = dict(row)
    primary = entities.entity_for_row(row, classification)
    result = ([{**primary, 'coverage_kind': 'direct', 'coverage_note': ''}]
              if primary else [])
    year = _regional_year(values, primary)
    if year is None:
        return tuple(result)
    for key, end in _MEMBERS:
        if year >= end:
            continue
        entity = entities.ENTITY_BY_KEY[key]
        result.append({
            **entity,
            'coverage_kind': 'regional',
            'coverage_note': (
                'Covered by a shared Malaya and British Borneo currency-board '
                f"note used in {entity['label']}. "
                'This does not establish ownership of a separate territorial issue.'
            ),
        })
    return tuple(result)
