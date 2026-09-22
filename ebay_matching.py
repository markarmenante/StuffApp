"""Conservative, explainable identity matching for banknote purchase titles."""
from collections import Counter, defaultdict
from datetime import date
from fractions import Fraction
import re
import unicodedata


COUNTRY_ALIASES = {
    'united states of america': ('united states', 'usa', 'us'),
    'british east africa': ('east africa', 'east african'),
    'french indo china': ('french indochina', 'indochina', 'french indo china'),
    'netherlands indies': ('netherlands east indies', 'dutch east indies'),
    'faroe islands': ('faeroe islands', 'foroyar'),
    'macau': ('macao',),
    'portuguese timor': ('portugal timor', 'timor'),
    'timor': ('portuguese timor', 'portugal timor'),
    'hong kong': ('hongkong',),
    'rhodesia and nyasaland': ('rhodesia nyasaland',),
    'saint pierre and miquelon': ('st pierre miquelon', 'st pierre and miquelon'),
    'saint helena': ('st helena',),
}
UNITS = {
    'dollar': ('dollars', 'dollar'), 'pound': ('pounds', 'pound'),
    'franc': ('francs', 'franc', 'franken'), 'cent': ('cents', 'cent'),
    'centime': ('centimes', 'centime'), 'peso': ('pesos', 'peso'),
    'piastre': ('piastres', 'piastre'), 'dong': ('dong',),
    'shilling': ('shillings', 'shilling', 'schillings'), 'escudo': ('escudos', 'escudo', 'esc'),
    'rupee': ('rupees', 'rupee', 'rupien', 'rupie'),
    'rupiah': ('roepiah', 'rupiah'), 'gulden': ('gulden', 'guilders', 'guilder'),
    'dinar': ('dinara', 'dinars', 'dinar'), 'pataca': ('patacas', 'pataca'),
    'krone': ('kronen', 'kronur', 'kroner', 'krona', 'krone'),
    'somali': ('somali', 'somalo'), 'drachma': ('drachmai', 'drachmae', 'drachmas', 'drachma'),
    'peseta': ('pesetas', 'pessetas', 'peseta', 'pesseta'),
    'lira': ('lire', 'lira'), 'ruble': ('rubles', 'roubles', 'ruble'),
    'mark': ('marks', 'marka', 'mark'), 'ore': ('ore',),
    'afghani': ('afghanis', 'afghani'), 'baht': ('baht',), 'yen': ('yen',),
    'yuan': ('yuan',), 'kip': ('kip',), 'sen': ('sen',), 'centavo': ('centavos', 'centavo'),
    'lirot': ('lirot',), 'rial': ('rials', 'rial'), 'sum': ('sum',),
    'mils': ('mils',), 'fils': ('fils',), 'pruta': ('pruta',),
    'dobra': ('dobras', 'dobra'), 'kwacha': ('kwacha',), 'ringgit': ('ringgit',),
    'angolar': ('angolar',), 'rufiyaa': ('rufiyaa',),
}
UNIT_KEYS = {alias: unit for unit, aliases in UNITS.items() for alias in aliases}
UNIT_RE = '|'.join(sorted(UNIT_KEYS, key=len, reverse=True))
NUMBER = r'\d+(?:,\d{3})*(?:/\d+|\.\d+)?'
DENOM_RE = re.compile(r'(?<![\w/])(' + NUMBER + r')\s*(?:/-\s*|egyptian\s+)?(' + UNIT_RE + r')\b')
CATALOG_RE = re.compile(
    r'\b(pick|pk|p(?=[\d\s.#-])|friedberg|fr|bc|knb)\s*[.#-]*\s*'
    r'([a-z]?\d+(?:[a-z]{1,2}\d*)?)(?![a-z0-9])'
    r'(?:[\s-]+([a-z]{1,2})(?![a-z0-9/]))?', re.I)
GRADE_WORDS = r'(?:choice|gem|superb|about|uncirculated|unc|circulated|au|vf|ef|xf|fine|very|extremely|banknote|currency|certified|grade|ms|ch|cu)'
GRADE_RE = re.compile(
    r'\b(?:pmg|pcgs)\s*[-:]*\s*(?:' + GRADE_WORDS + r'[\s.:-]+)*[*]*(\d{1,2})(?!\d)'
    r'|\b(\d{1,2})(?!\d)\s*[*+]*\s*(?:epq|ppq|gem|unc)\b'
    r'|\b(?:unc|au|vf|ef|xf)\s*[*]*(\d{1,2})(?!\d)', re.I)


def words(value):
    value = unicodedata.normalize('NFKD', str(value or '').replace('\u00f8', 'o'))
    value = ''.join(c for c in value if not unicodedata.combining(c)).lower()
    return ' '.join(re.findall(r'[a-z0-9]+', value.replace('&', ' and ')))


def compact(value):
    return words(value).replace(' ', '')


def amount(value):
    try:
        return Fraction(value.replace(',', ''))
    except (ValueError, ZeroDivisionError):
        return None


def denominations(value):
    value = unicodedata.normalize('NFKD', str(value or '').lower().replace('\u00f8', 'o'))
    value = ''.join(c for c in value if not unicodedata.combining(c))
    for word, number in {'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'ten': 10,
                         'twenty': 20, 'fifty': 50, 'hundred': 100}.items():
        value = re.sub(r'\b' + word + r'\b', str(number), value)
    found = {(amount(n), UNIT_KEYS[u]) for n, u in DENOM_RE.findall(value) if amount(n) is not None}
    found.update((Fraction(n), 'cent') for n in re.findall(r'(?<![\w.])([1-9]\d?)c\b', value))
    for symbol, unit in [('$', 'dollar'), ('\u00a3', 'pound')]:
        found.update((amount(n), unit)
                     for n in re.findall(re.escape(symbol) + r'\s*(' + NUMBER + r')(?!\d)', value)
                     if amount(n) is not None)
    found.update((n * 100, 'cent') for n, u in list(found) if u == 'dollar' and 0 < n < 1)
    return found


def catalogs(value):
    found = defaultdict(set)
    for prefix, number, suffix in CATALOG_RE.findall(str(value or '')):
        prefix = prefix.lower()
        prefix = {'pick': 'p', 'pk': 'p', 'friedberg': 'fr'}.get(prefix, prefix)
        # ND is a date qualifier, not a two-letter catalogue suffix.
        suffix = '' if suffix.lower() in ('nd', 'fr', 'au', 'ch', 'to') else suffix.lower()
        found[prefix].add(number.lower() + suffix)
    return dict(found)


def profile(value):
    without_catalog = CATALOG_RE.sub(' ', value)
    grades = {int(next(v for v in group if v)) for group in GRADE_RE.findall(without_catalog)}
    grades = {g for g in grades if 1 <= g <= 70}
    years = set(re.findall(r'\b(?:17|18|19|20)\d{2}(?!\d)', value))
    for start, tail in re.findall(r'\b((?:17|18|19|20)\d{2})\s*[-~]\s*(\d{1,2})\b', value):
        end = int(start[:-len(tail)] + tail)
        if int(start) <= end <= int(start) + 30:
            years.update(str(y) for y in range(int(start), end + 1))
    return {'text': words(value), 'catalogs': catalogs(value), 'denominations': denominations(without_catalog),
            'years': years, 'grades': grades,
            'graders': set(re.findall(r'\b(?:PMG|PCGS)(?![A-Z])', value.upper()))}


def country_matches(country, title):
    key = words(country)
    aliases = (key, *COUNTRY_ALIASES.get(key, ()))
    text = ' ' + title['text'] + ' '
    if key == 'british east africa' and re.search(r'\b(?:german|deutsch)\b', text):
        return False
    if any(' ' + alias + ' ' in text for alias in aliases if alias):
        return True
    # Friedberg is the US catalogue; many US listings omit the country.
    return ((key == 'united states of america' and bool(title['catalogs'].get('fr')))
            or (key == 'canada' and bool(title['catalogs'].get('bc'))))


def day(value):
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def seller_key(value):
    value = re.sub(r'\([^)]*\)', '', str(value or ''))
    value = re.sub(r'\b(?:www|com|ebay|store|shop|the|llc)\b', '', words(value))
    return compact(value)


def comparison(note, item, title, aliases):
    """Hard identity conflicts disqualify a pair, regardless of its score."""
    if not country_matches(note.get('country'), title):
        return None
    denom = denominations(note.get('denomination'))
    if not denom or not (denom & title['denominations']):
        return None
    evidence = ['Country', 'Denomination']
    serial = compact(note.get('serial_number'))
    explicit_serial = re.search(r'\b(?:s/n|sn[#:]|serial(?:\s+number)?[:#]?)\s*([a-z]{0,3}[/ ]?\d{4,}[a-z*]?)\b', item['title'], re.I)
    if serial and explicit_serial:
        stated = compact(explicit_serial[1])
        if stated != serial and not (stated.isdigit() and serial.endswith(stated)):
            return None
    identity = False
    for field, label, minimum in [('slab_number', 'Certificate number', 7), ('serial_number', 'Serial number', 6)]:
        token = compact(note.get(field))
        if len(token) >= minimum and re.search(r'(?<![a-z0-9])' + r'[\W_]*'.join(map(re.escape, token)) + r'(?![a-z0-9])', item['title'], re.I):
            evidence.append(label)
            identity = True
    mine = catalogs((note.get('pick_number') or '') + ' ' + (note.get('other_catalog') or ''))
    shared = set(mine) & set(title['catalogs'])
    catalog = any(mine[k] & title['catalogs'][k] for k in shared)
    family = False
    for key in shared:
        if mine[key] & title['catalogs'][key]:
            continue
        # A title can omit a variety letter, but different explicit varieties conflict.
        if not any(a == b or (a.isdigit() and re.fullmatch(re.escape(a) + '[a-z]+[0-9]*', b))
                   or (b.isdigit() and re.fullmatch(re.escape(b) + '[a-z]+[0-9]*', a))
                   for a in mine[key] for b in title['catalogs'][key]):
            return None
        family = True
    if catalog:
        evidence.append('Catalog number')
    elif family:
        evidence.append('Catalog number (variety omitted)')
    try:
        grade = float(note['grade_numeric'])
    except (KeyError, TypeError, ValueError):
        grade = None
    if grade is not None and title['grades'] and title['grades'] != {grade}:
        return None
    grade_match = grade is not None and title['grades'] == {grade}
    if grade_match:
        evidence.append('Grade')
    grader = re.search(r'\b(?:PMG|PCGS)\b', (note.get('grading_authority') or '').upper())
    if grader and title['graders'] and grader[0] not in title['graders']:
        return None
    years = {str(note[k]) for k in ('date_1', 'date_2') if note.get(k)}
    years.update(re.findall(r'\b(?:17|18|19|20)\d{2}\b', note.get('series') or ''))
    if years and title['years'] and not years & title['years']:
        return None
    year = bool(years & title['years'])
    if year:
        evidence.append('Issue year')
    seller, vendor = seller_key(item.get('seller')), seller_key(note.get('vendor'))
    seller_match = bool(seller and vendor and (seller == vendor or (vendor, seller) in aliases))
    if seller_match:
        evidence.append('Seller')
    bought, ordered = day(note.get('purchase_date')), day(item.get('ordered_at'))
    distance = abs((bought - ordered).days) if bought and ordered else None
    purchase = distance is not None and distance <= 3
    if purchase:
        evidence.append('Purchase date')
    if distance is not None and distance > 14 and not identity:
        return None
    automatic = identity or catalog or (family and grade_match and (year or seller_match or purchase)) or (
        grade_match and year and seller_match and purchase)
    if not (identity or catalog or family or (year and (grade_match or seller_match or purchase))):
        return None
    return {'banknote_id': note['id'], 'cat_id': note.get('cat_id'),
            'label': ' '.join(str(note.get(k) or '') for k in ('cat_id', 'country', 'denomination', 'date_1')).strip(),
            'evidence': evidence, 'automatic': bool(automatic), 'score': len(evidence) + 5 * identity}


def plan_matches(notes, orders, links, purchase_links=None):
    """Two-way uniqueness includes owned notes and already-linked purchases."""
    notes = [dict(n) for n in notes if (n.get('status') or 'Own') in ('Own', 'Owned', 'Ordered')]
    by_note = {n['id']: n for n in notes}
    by_order = {o['line_key']: o for o in orders}
    aliases = set()
    for link in links:
        if link['matched_by'] not in ('listing', 'manual'):
            continue
        note, item = by_note.get(link['banknote_id']), by_order.get(link['line_key'])
        if note and item:
            aliases.add((seller_key(note.get('vendor')), seller_key(item.get('seller'))))
    occupied_notes = {l['banknote_id']: l['line_key'] for l in links}
    occupied_orders = {l['line_key']: l['banknote_id'] for l in links}
    counts = Counter(o['item_id'] for o in orders)
    sources = defaultdict(set)
    for item_id, note_ids in (purchase_links or {}).items():
        for note_id in note_ids:
            sources[note_id].add(item_id)
    candidates, contenders = {}, defaultdict(set)
    for item in orders:
        title = profile(item['title'])
        found = []
        for note in notes:
            if sources[note['id']] and sources[note['id']] != {item['item_id']}:
                continue
            pair = comparison(note, item, title, aliases)
            if pair:
                # Proven links resolve competition; descriptive guesses do not.
                if note['id'] in occupied_notes and occupied_notes[note['id']] != item['line_key']:
                    continue
                if item['line_key'] in occupied_orders and occupied_orders[item['line_key']] != note['id']:
                    continue
                found.append(pair)
                contenders[note['id']].add(item['line_key'])
        candidates[item['line_key']] = sorted(found, key=lambda c: -c['score'])
    automatic, suggestions = {}, {}
    for item in orders:
        key = item['line_key']
        bundle = re.search(r'\b(?:lot|set|bundle|pair)\s*(?:of\s*)?[2-9]\d*\b|\bpair of\b'
                           r'|\b[2-9]\d*\s+(?:consecutive\s+)?(?:serial\s+)?(?:notes|banknotes)\b', item['title'], re.I)
        if key in occupied_orders or item.get('ignored') or item['quantity'] != 1 or item.get('attention') or bundle:
            continue
        found = candidates[key]
        if found:
            suggestions[key] = found[:3]
        if (len(found) == 1 and found[0]['automatic'] and counts[item['item_id']] == 1
                and len(contenders[found[0]['banknote_id']]) == 1):
            automatic[key] = found[0]
    return automatic, suggestions
