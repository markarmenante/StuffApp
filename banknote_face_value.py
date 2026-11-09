"""Read a recorded face value without changing its original denomination text."""
import math
import re
import unicodedata


_WORDS = {
    'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6,
    'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10, 'eleven': 11,
    'twelve': 12, 'thirteen': 13, 'fourteen': 14, 'fifteen': 15,
    'sixteen': 16, 'seventeen': 17, 'eighteen': 18, 'nineteen': 19,
    'twenty': 20, 'thirty': 30, 'forty': 40, 'fifty': 50, 'sixty': 60,
    'seventy': 70, 'eighty': 80, 'ninety': 90, 'half': .5, 'quarter': .25,
}
_SCALES = {'hundred': 100, 'thousand': 1000, 'million': 1000000, 'billion': 1000000000}


def _plain(value):
    return ''.join(c for c in unicodedata.normalize('NFKD', str(value or '')).casefold()
                   if not unicodedata.combining(c))


def parse(text):
    """Return amount and leading unit, preserving explicit subunit arithmetic.

    Parenthesized equivalents and ``=``/overprint descriptions do not become a
    second face value. Conflicting same-symbol equivalents remain unresolved.
    """
    raw = str(text or '').strip()
    for symbol, value in (('½', '1/2'), ('¼', '1/4'), ('¾', '3/4')):
        raw = raw.replace(symbol, ' ' + value)
    value = _plain(raw).strip()
    prefix = re.match(r'^(us\$|hk\$|a\$|c\$|[$£€])\s*', value)
    symbol = prefix[1] if prefix else ''
    if prefix:
        value = value[prefix.end():]
    number = re.match(r'^(\d+(?:,\d{3})*(?:\.\d+)?)(?:\s+(\d+)\s*/\s*(\d+)|\s*/\s*(\d+))?\s*', value)
    if number:
        amount = float(number[1].replace(',', ''))
        # A lone decimal-looking thousands separator is locale-ambiguous.
        if re.fullmatch(r'[1-9]\d{0,2}\.\d{3}', number[1]):
            return None
        if number[4]:
            if int(number[4]) == 0:
                return None
            amount /= int(number[4])
        elif number[2]:
            if int(number[3]) == 0:
                return None
            amount += int(number[2]) / int(number[3])
        rest = value[number.end():]
        if rest and rest[:1] in ',.':
            return None
        scale = re.match(r'^(thousand|million|billion)\b\s*', rest)
        if scale:
            amount *= _SCALES[scale[1]]
            rest = rest[scale.end():]
    else:
        tokens = re.findall(r'[^\s-]+', value)
        amount, subtotal, consumed = 0, 0, []
        for token in tokens:
            if token in _WORDS:
                if consumed and consumed[-1] in _WORDS and not (_WORDS[consumed[-1]] >= 20 and _WORDS[consumed[-1]] % 10 == 0 and _WORDS[token] < 10):
                    return None
                subtotal += _WORDS[token]
            elif token == 'hundred' and subtotal:
                subtotal *= 100
            elif token in _SCALES and subtotal:
                amount += subtotal * _SCALES[token]
                subtotal = 0
            elif token == 'and' and consumed:
                pass
            else:
                break
            consumed.append(token)
        if not consumed:
            return None
        amount += subtotal
        pattern = r'^' + r'[\s-]+'.join(re.escape(word) for word in consumed) + r'\s*'
        rest = re.sub(pattern, '', value, count=1)
    if not math.isfinite(amount) or not 0 < amount < 1e16:
        return None
    compound = re.match(r'^shillings?\s*,?\s*(\d+)\s+pence\b', rest)
    if compound:
        pence = int(compound[1])
        if pence >= 12:
            return None
        amount += pence / 12
        unit = 'shillings'
        suffix = rest[compound.end():]
    else:
        parts = re.split(r'\s*(?:\(|=|\bon\b|\boverprinted\b)\s*', rest, maxsplit=1)
        unit = parts[0].strip()
        suffix = rest[len(parts[0]):]
        if re.search(r'\d', unit):
            return None
    if not unit:
        unit = {'£': 'pounds', '€': 'euros'}.get(symbol, 'dollars' if '$' in symbol else '')
    if not unit:
        return None
    if symbol == '£' and not re.fullmatch(r'(?:sterling )?pounds?(?: sterling)?', unit): return None
    if symbol == '€' and not re.fullmatch(r'euros?', unit): return None
    if symbol.endswith('$') and not re.fullmatch(r'dollars?|pesos?', unit): return None
    # Redundant symbol spellings are safe only if they agree numerically.
    aliases = re.findall(r'\(\s*([$£€])\s*(\d+(?:\.\d+)?)\s*\)', suffix)
    for alias_symbol, alias_amount in aliases:
        same_unit = (alias_symbol == '£' and re.search(r'\bpounds?\b', unit)
                     or alias_symbol == '$' and re.search(r'\bdollars?\b', unit)
                     or alias_symbol == '€' and re.search(r'\beuros?\b', unit))
        if same_unit and float(alias_amount) != amount:
            return None
    return dict(amount=amount, unit=unit, symbol=symbol)
