"""Read title identity for market display/matching; never rewrite source fields."""
from functools import lru_cache
import re
import unicodedata

import banknote_catalog as catalog
import banknote_entities


_EMPTY = {'', 'unknown', 'unknown issuer', 'unknown country', 'country not specified',
          'not specified', 'n/a', 'none', '-', '—'}
# Spelling equivalents only. Historical territories keep their own identities;
# the entity coverage catalogue's successor/administration relationships do not
# turn into title aliases here.
_ALIASES = {
    'British North Borneo': ('North Borneo',),
    'Malaya and British Borneo': ('Malaya & British Borneo',),
    'Georgia': ('Republic of Georgia',),
}
_AMBIGUOUS = {'georgia', 'congo', 'korea', 'virgin islands'}
_NAMED_NATIONAL_BANK = r'(?:First|Second|Third|Fourth|Fifth|City|Citizens|Merchants|Farmers|Commercial|Union|Central|Security|Peoples) National Bank'


def text(value):
    return re.sub(r'\s+', ' ', str(value or '')).strip()


def _words(value):
    value = unicodedata.normalize('NFKD', text(value)).encode('ascii', 'ignore').decode().casefold()
    return re.sub(r'[^a-z0-9]+', ' ', value).strip()


def _present(value):
    return text(value) if text(value).casefold() not in _EMPTY else ''


@lru_cache(maxsize=8)
def _names(extra_countries):
    names = (set(catalog.PERIODS) | set(catalog.ALIASES) | set(extra_countries)
             | {'British India', 'Honduras'} | {name.title() for name in _AMBIGUOUS})
    names.update(name for entry in banknote_entities.ENTITY_CATALOG for name in entry['countries'])
    aliases = {}
    for name in sorted(names):
        canonical = catalog.canonical_country(name)
        for spelling in catalog.country_spellings(canonical):
            aliases.setdefault(_words(spelling), set()).add(canonical)
    for canonical, spellings in _ALIASES.items():
        for spelling in (canonical,) + spellings:
            aliases[_words(spelling)] = {canonical}
    # Plain "us" is also an English word. Short country abbreviations require
    # their explicit uppercase form below, rather than case-insensitive search.
    patterns = [(re.compile(r'(?<![a-z0-9])' + re.escape(alias) + r'(?![a-z0-9])'), values)
                for alias, values in aliases.items() if len(alias.replace(' ', '')) > 2]
    return aliases, patterns


def _title_country(title, extra_countries, us_states):
    _, patterns = _names(extra_countries)
    # Currency prefixes in prices are not mentions of the issuing country.
    identity_title = re.sub(r'(?<!\w)(?:USA|US|U\.S\.(?:A\.)?)\s*\$(?=\s*\d)', '$', title)
    words = _words(identity_title)
    matches = [(m.start(), m.end(), values, m.group()) for pattern, values in patterns for m in pattern.finditer(words)]
    # "British Honduras" and "French Somaliland" outrank their contained
    # country words, but two non-overlapping countries remain ambiguous.
    matches = [m for m in matches if not any(n[0] <= m[0] and n[1] >= m[1] and
               n[1] - n[0] > m[1] - m[0] for n in matches)]
    countries = set().union(*(m[2] for m in matches)) if matches else set()
    ambiguous = any(m[3] in _AMBIGUOUS for m in matches)
    if re.search(r'(?<!\w)(?:USA|US|U\.S\.(?:A\.)?)(?!\w)(?!\s*\$)', identity_title):
        countries.add('United States of America')
    national = bool(re.search(r'\b' + _NAMED_NATIONAL_BANK + r'\b', title, re.I))
    state_pattern = '|'.join(re.escape(state) for state in sorted(us_states, key=len, reverse=True))
    states = {m.group().casefold() for m in re.finditer(r'(?<!\w)(?:' + state_pattern + r')(?!\w)', title, re.I)} if state_pattern else set()
    if national and len(states) == 1:
        # Georgia is a state here only when an explicitly named US national
        # bank accompanies it; "National Bank of Georgia" does not qualify.
        if countries == {'Georgia'} and not re.search(r'\bRepublic of Georgia\b', title, re.I):
            countries.clear(); ambiguous = False
        countries.add('United States of America')
    if not countries and not ambiguous and re.search(r'(?<!\w)(?:Fr\.?|Friedberg)\s*[.#:-]?\s*\d', title, re.I):
        countries.add('United States of America')
    return (next(iter(countries)) if len(countries) == 1 and not ambiguous else '',
            ambiguous or len(countries) > 1)


def _title_issuer(title, country, extra_countries, us_states):
    if not country:
        return ''
    aliases, _ = _names(extra_countries)
    spellings = [alias for alias, values in aliases.items() if values == {country}]
    country_pattern = '|'.join(re.escape(name).replace(r'\ ', r'[\s.\-]+') for name in sorted(spellings, key=len, reverse=True))
    found = []
    if country_pattern:
        pattern = (r'\b(?:(?:Government|Central Bank|Reserve Bank|National Bank|Bank) of (?:the )?(?:' + country_pattern +
                   r')|(?:' + country_pattern + r') (?:Monetary Authority|Currency Board))\b')
        found.extend(text(m.group()) for m in re.finditer(pattern, title, re.I))
    if country == 'United States of America' and us_states:
        state_pattern = '|'.join(re.escape(s) for s in sorted(us_states, key=len, reverse=True))
        # A bare bank name is not enough to combine cities. Keep the location
        # only when it is explicitly printed beside the bank in the title.
        place = r'(?P<city>[A-Za-z]+(?:[ -][A-Za-z]+){0,3}?)[, ]+(?P<state>' + state_pattern + r')'
        pattern = r'(?:^|\d\s+)'+place+r'[, ]+(?:The )?(?P<bank>'+_NAMED_NATIONAL_BANK+r')\b'
        for match in re.finditer(pattern, title, re.I):
            found.append(text(match['bank']) + ' (' + text(match['city']) + ', ' + text(match['state']) + ')')
    unique = {_words(value) for value in found}
    return found[0] if len(unique) == 1 else ''


def resolve(row, *, country_names=(), us_states=()):
    """Return derived country/issuer and ambiguity without mutating the row.

    Explicit structured facts lead. Otherwise match bounded title words against
    the complete available roster, independent of which countries are held.
    """
    extra = tuple(sorted(set(country_names)))
    title = text(row.get('title'))[:2000]
    country = _present(row.get('country'))
    ambiguous = False
    if country:
        country = catalog.canonical_country(country)
        aliases, _ = _names(extra)
        equivalent = aliases.get(_words(country), set())
        if len(equivalent) == 1:
            country = next(iter(equivalent))
    else:
        country, ambiguous = _title_country(title, extra, us_states)
    issuer = _present(row.get('issuer')) or _title_issuer(title, country, extra, us_states)
    return dict(country=country, issuer=issuer, ambiguous=ambiguous)
