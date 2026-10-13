"""Presentation-only market sections; stored ranks and listing identities stay intact."""
import hashlib
import json
import re
import unicodedata

import banknote_catalog


def _text(value):
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", str(value or ""))).strip()


def _fold(value):
    return _text(value).casefold()


def _series(value):
    value = _text(value).replace("–", "-").replace("—", "-")
    value = re.sub(r"^series(?: of)?\s+", "", value, flags=re.I)
    value = re.sub(r"\s+series$", "", value, flags=re.I)
    # Spaces in a year suffix are formatting, not a separate issue. Keep the
    # complete suffix: 1934, 1934A and 1934B remain different groups.
    value = re.sub(r"\b(\d{4})[ -]+([a-z])\b", r"\1\2", value, flags=re.I)
    return value


def observed_series(title):
    """Only a series explicitly named in a card; a date alone proves nothing."""
    title = _text(title)
    match = re.search(r"\bseries(?: of)?\s+((?:1[6-9]|20)\d{2}(?:[ -]?[A-Z])?)(?![\w-])", title, re.I)
    if match:
        return _series(match.group(1))
    match = re.search(
        r"\b(Victory(?:[- ]CBP)?|Educational|Rainbow)\s+series\b"
        r"(?:\s+(?:no\.?\s*|#\s*)?(\d+[a-z]?(?:[-.][a-z0-9]+)*)(?![\w.-]))?",
        title, re.I)
    if not match:
        return ""
    # A number explicitly following the named series is part of its identity,
    # not a grade or an issue date borrowed from elsewhere in the title.
    return _series(match.group(1) + (" Series " + match.group(2) if match.group(2) else ""))


def _banknote_identity(row, note_type, observed):
    country = _text(banknote_catalog.canonical_country(row.get("country")))
    series = observed_series(row.get("title")) if observed else _series(row.get("series"))
    issuer = _text(row.get("issuer"))
    kind = ""
    if country == "United States of America" and note_type:
        kind = _text(note_type(row))
    # Missing series stays explicit. An issuer can make those otherwise sparse
    # sections useful without pretending an issue date is a series year.
    scope = kind or (issuer if not series else "")
    parts = [country or "Other banknote listings"]
    if series:
        parts.append("Series of " + series.upper() if re.fullmatch(r"\d{4}[a-z]?", series, re.I)
                     else "Series: " + series)
    else:
        parts.append("Series not specified")
    if scope and _fold(scope) not in _fold(series):
        parts.append(scope)
    return ("banknotes", _fold(country), _fold(series), _fold(scope)), " · ".join(parts)


def group_rows(rows, category, *, coin_fields=None, note_type=None, observed=False):
    """Gather interleaved peers in first-encounter order, retaining rank within each.

    Every result is a new dict. Metadata is derived only for rendering; no
    eligibility decisions, sorting scores, references or source fields change.
    """
    groups = {}
    for original in rows:
        row = dict(original)
        if category == "coins":
            fields = coin_fields(dict(row)) if coin_fields else row
            region = _text(fields.get("region"))
            identity, title = ("coins", _fold(region)), region or "Region not specified"
        elif category == "banknotes":
            identity, title = _banknote_identity(row, note_type, observed)
        else:
            raise ValueError("Market grouping supports coins and banknotes only")
        key = hashlib.sha256(json.dumps(identity, ensure_ascii=False).encode()).hexdigest()[:20]
        groups.setdefault(key, {"title": title, "rows": []})["rows"].append(row)
    out = []
    for key, group in groups.items():
        count = len(group["rows"])
        for index, row in enumerate(group["rows"]):
            row["_market_group"] = {"key": key, "title": group["title"], "count": count, "heading": index == 0}
            out.append(row)
    return out
