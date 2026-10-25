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


def _natural(value):
    return tuple((1, int(part)) if part.isdigit() else (0, part)
                 for part in re.split(r"(\d+)", _fold(value)) if part)


def _catalogue_identity(row, country, catalog_references):
    refs = sorted(catalog_references(row)) if catalog_references else []
    # An extra equivalent catalogue citation must not split the same type.
    # Prefer the principal catalogue, retaining every variety suffix. No
    # serial, certificate, grade or asking price contributes to this identity.
    priority = ("criswell", "friedberg", "pick", "tbb", "other") if country == "United States of America" else ("pick", "tbb", "other", "friedberg", "criswell")
    for namespace in priority:
        selected = tuple(ref for ref in refs if ref.startswith(namespace + ":"))
        if selected:
            labels = {"pick": "P-", "friedberg": "Fr. ", "tbb": "B", "criswell": "Criswell ", "other": ""}
            title = "; ".join(labels[namespace] + ref.split(":", 1)[1].upper() for ref in selected)
            return selected, title
    return (), "Catalogue not specified"


def _banknote_identity(row, note_type, observed, catalog_references):
    country = _text(banknote_catalog.canonical_country(row.get("country")))
    series = observed_series(row.get("title")) if observed or row.get("_market_card_kind") == "observed" else _series(row.get("series"))
    issuer = _text(row.get("issuer"))
    if _fold(issuer) in ("unknown", "unknown issuer", "not specified", "n/a", "none", "-", "—"):
        issuer = ""
    kind = ""
    if country == "United States of America" and note_type:
        kind = _text(note_type(row))
    references, reference_title = _catalogue_identity(row, country, catalog_references)
    # A missing issuer is a labelled bucket, never an issuer inferred from a
    # country, series or seller's title. Country scopes generic issuer names
    # such as "Government"; successors and colonies retain their own scope.
    issuer_identity = ("banknotes", _fold(country), _fold(issuer))
    issuer_title = (issuer or "Unknown issuer") + " · " + (country or "Country not specified")
    parts = [kind] if kind else []
    if series:
        parts.append("Series of " + series.upper() if re.fullmatch(r"\d{4}[a-z]?", series, re.I)
                     else "Series: " + series)
    else:
        parts.append("Series not specified")
    parts.append(reference_title)
    # Known issue dates can distinguish otherwise unspecified series, but are
    # never promoted into a series label. Unknown dates stay explicitly sparse.
    year = str(row.get("date_1") or "") if not series else ""
    year = year if re.fullmatch(r"\d{4}", year) else ""
    if year:
        parts.insert(0, "Issued " + year)
    identity = issuer_identity + (_fold(series), _fold(kind), references, year)
    return issuer_identity, issuer_title, identity, " · ".join(parts), series


def _key(identity):
    return hashlib.sha256(json.dumps(identity, ensure_ascii=False).encode()).hexdigest()[:20]


def group_rows(rows, category, *, coin_fields=None, note_type=None, observed=False,
               catalog_references=None, banknote_order=None):
    """Gather banknotes by explicit issuer, then similar series/catalogue type.

    Every result is a new dict. Metadata is derived only for rendering; no
    eligibility decisions, stored ranks, references or source fields change.
    Issuer blocks retain first-encounter relevance. Inside them, known years
    and numeric denominations lead; equal or missing evidence retains rank.
    Coins retain their existing region grouping and rank order.
    """
    issuers = {}
    for original in rows:
        row = dict(original)
        if category == "coins":
            fields = coin_fields(dict(row)) if coin_fields else row
            region = _text(fields.get("region"))
            identity, title = ("coins", _fold(region)), region or "Region not specified"
            issuer_key, issuer_title = "coins", ""
            order = ()
        elif category == "banknotes":
            issuer_identity, issuer_title, identity, title, series = _banknote_identity(row, note_type, observed, catalog_references)
            issuer_key = _key(issuer_identity)
            order = tuple(banknote_order(dict(row, series=series))) if banknote_order else ()
        else:
            raise ValueError("Market grouping supports coins and banknotes only")
        key = _key(identity)
        issuer = issuers.setdefault(issuer_key, {"title": issuer_title, "groups": {}, "count": 0})
        issuer["count"] += 1
        group = issuer["groups"].setdefault(key, {"title": title, "rows": [], "order": order})
        group["rows"].append((order, row))
        group["order"] = min(group["order"], order)
    out = []
    for issuer_key, issuer in issuers.items():
        groups = list(issuer["groups"].items())
        if category == "banknotes" and banknote_order:
            groups.sort(key=lambda entry: (entry[1]["order"], _natural(entry[1]["title"])))
        issuer_first = True
        for key, group in groups:
            count = len(group["rows"])
            for index, (_, row) in enumerate(sorted(group["rows"], key=lambda entry: entry[0])):
                row["_market_group"] = {"key": key, "title": group["title"], "count": count, "heading": index == 0}
                if category == "banknotes":
                    row["_market_issuer"] = {"key": issuer_key, "title": issuer["title"], "count": issuer["count"], "heading": issuer_first}
                    issuer_first = False
                out.append(row)
    return out
