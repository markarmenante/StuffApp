"""Bounded public catalogue discovery using native Perplexity Search excerpts.

No model-generated prose or citation URL alone is accepted as source text.
The caller still validates exact country, reference, denomination and variety.
API contract: https://docs.perplexity.ai/api-reference/search-post
"""
import json
import math
import re
from urllib.parse import urlsplit
from urllib.request import Request, HTTPRedirectHandler, build_opener

import banknote_catalog_lookup as catalogue

ENDPOINT = 'https://api.perplexity.ai/search'
MAX_SECONDS = 15
MAX_BYTES = 1000000
MAX_SNIPPET = 60000
PREFIXES = {
    'pick': ('P', 'Pick '), 'friedberg': ('Fr.', 'Friedberg '),
    'tbb': ('TBB ', 'The Banknote Book '), 'criswell': ('Cr.', 'Criswell '),
    'haxby': ('Haxby ', 'Haxby '), 'rosenberg': ('Rosenberg ', 'Rosenberg '),
    'grabowski': ('Grabowski ', 'Grabowski '), 'mehl': ('Mehl ', 'Mehl '),
    'funck': ('Funck ', 'Funck '), 'menzel': ('Menzel ', 'Menzel '),
    'tieste': ('Tieste ', 'Tieste '), 'lamb': ('Lamb ', 'Lamb '),
}


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def queries(note):
    """Only public type identity; never send item, purchase or photo details."""
    country = catalogue.text(note.get('country'))
    if not country or len(country) > 120:
        return []
    parts = [part.strip() for field in ('pick_number', 'other_catalog')
             for part in re.split(r'[,;]', catalogue.text(note.get(field))) if part.strip()]
    keys = [catalogue.reference(part) for part in parts]
    if not keys or len(keys) > 4 or any(not key for key in keys):
        return []
    keys = sorted(set(keys))
    # Competing varieties are ambiguous and cannot authorize a type lookup.
    if len({key.split(':', 1)[0] for key in keys}) != len(keys):
        return []
    out = []
    for spelling in (0, 1):
        refs = []
        for key in keys:
            namespace, number = key.split(':', 1)
            refs.append('"' + PREFIXES[namespace][spelling] + number + '"')
        query = country + ' ' + ' '.join(refs)
        # Namespaces without a second abbreviation still get a distinct,
        # minimal catalogue query without unrelated identity/field words.
        if query in out:
            query += ' catalogue'
        out.append(query)
    return out


def _safe_url(url):
    if not isinstance(url, str) or len(url) > 4096 or re.search(r'[\x00-\x20\\]', url):
        return False
    try:
        parsed = urlsplit(url)
        allowed = catalogue.web_fetch_tool()['allowed_domains']
        return (parsed.scheme == 'https' and not parsed.username and not parsed.password
                and parsed.port in (None, 443) and parsed.hostname
                and any(parsed.hostname == host or parsed.hostname.endswith('.' + host) for host in allowed)
                and not re.search(r'/login|/account|/forum', parsed.path, re.I))
    except (ValueError, TypeError):
        return False


def sources(payload):
    """Accept only native Search result text and its own safe source URL."""
    if not isinstance(payload, dict) or not isinstance(payload.get('results'), list):
        return {}
    found = {}
    for item in payload['results'][:5]:
        if not isinstance(item, dict) or not _safe_url(item.get('url')):
            continue
        title, snippet = item.get('title'), item.get('snippet')
        if not isinstance(title, str) or not isinstance(snippet, str) or not snippet.strip():
            continue
        if len(title) > 2000 or len(snippet) > MAX_SNIPPET:
            continue
        url = item['url']
        # Duplicate rows cannot cause one page to replace another's proof.
        if url not in found:
            found[url] = dict(title=title, quotes=[snippet], document_text=snippet)
    return found


def search(note, api_key, timeout=MAX_SECONDS):
    """One request, no retries, clamped to the caller's remaining time budget.

    Return URL -> {title, quotes, document_text}. Empty/unavailable/malformed
    provider results carry no evidence. This function never changes the note.
    """
    if not isinstance(api_key, str) or not api_key.strip() or not isinstance(note, dict):
        return {}
    try:
        timeout = min(float(timeout), MAX_SECONDS)
        if not math.isfinite(timeout) or timeout <= 0:
            return {}
    except (ValueError, TypeError):
        return {}
    selected = queries(note)
    if not selected:
        return {}
    body = dict(query=selected, max_results=5, max_tokens=12000,
                max_tokens_per_page=4000,
                search_domain_filter=catalogue.web_fetch_tool()['allowed_domains'])
    req = Request(ENDPOINT, data=json.dumps(body).encode('utf-8'), method='POST', headers={
        'Authorization': 'Bearer ' + api_key.strip(), 'Content-Type': 'application/json',
        'Accept': 'application/json'})
    try:
        with build_opener(_NoRedirect()).open(req, timeout=timeout) as response:
            data = response.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            return {}
        return sources(json.loads(data.decode('utf-8')))
    except Exception:
        # No provider response body, credentials or private input in logs/errors.
        return {}
