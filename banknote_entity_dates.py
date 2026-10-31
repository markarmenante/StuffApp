"""Display-only dates for historical entity pills; never scan cutoffs.

The source-backed event descriptions distinguish independence from handovers,
transfers and other constitutional changes. Canonical entity labels, matching
and collection/Market Scan metadata are deliberately left untouched.
"""
from datetime import date

from banknote_entity_date_data import PILL_DATES, PILL_DATE_EXCLUSIONS


_COLONIAL_GROUPS = frozenset({
    'british', 'french', 'portuguese', 'dutch', 'belgian', 'german',
    'italian', 'spanish', 'japanese', 'danish', 'joint',
})


def pill_date(entity):
    """Return presentation fields without changing the entity or its identity.

    Reviewed exclusions take precedence over date fields: a broad region or
    continuing dependency must not acquire a misleading independence year.
    Only a verified exact independence date may supply the fallback. A scan's
    final year can instead mean a rename, a last known note or an occupation.
    """
    label, key = entity['label'], entity['key']
    result = {'display_label': label, 'date_note': '', 'date_source': ''}
    if key in PILL_DATE_EXCLUSIONS:
        exclusion = PILL_DATE_EXCLUSIONS[key]
        if isinstance(exclusion, str):
            result['date_note'] = exclusion
        else:
            result.update(date_note=exclusion.get('note', ''),
                          date_source=exclusion.get('source', ''))
        return result

    transition = PILL_DATES.get(key)
    if transition:
        result.update(display_label=f"{label} ({transition['year']})",
                      date_note=transition['note'], date_source=transition['source'])
        return result

    colonial = entity.get('group') in _COLONIAL_GROUPS or key == 'us-philippines'
    if colonial and entity.get('issued') is True and entity.get('independence_source'):
        try:
            independence = date.fromisoformat(entity.get('independence_date') or '')
        except (TypeError, ValueError):
            return result
        result.update(display_label=f'{label} ({independence.year})',
                      date_note=f'Independence: {independence.isoformat()}.',
                      date_source=entity['independence_source'])
    return result
