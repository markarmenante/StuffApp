"""Resolve Witter discovery pages only from their observed, unique item links."""
from html.parser import HTMLParser
import re
from urllib.parse import urljoin, urlsplit

HOSTS = ('wittercoin.com', 'www.wittercoin.com')


def discovery_url(url):
    try:
        p = urlsplit(str(url or ''))
        return (p.scheme == 'https' and p.hostname in HOSTS and not p.username
                and not p.password and p.port in (None, 443)
                and p.path.startswith('/papermoney/') and not p.query and not p.fragment)
    except ValueError:
        return False


def exact_url(url):
    try:
        p = urlsplit(str(url or ''))
        return (p.scheme == 'https' and p.hostname in HOSTS and not p.username
                and not p.password and p.port in (None, 443)
                and bool(re.fullmatch(r'/item/[^/]+/\d+/?', p.path))
                and not p.query and not p.fragment)
    except ValueError:
        return False


def identity(title):
    """All four explicit facts are required; no catalogue/grade inference."""
    text = str(title or '')
    patterns = (r'\bfr[.#\s]*(\d+[a-z]?)\b', r'\b(1[6-9]\d{2}|20\d{2})\b',
                r'\$\s*(\d+)\b', r'\b(PMG|PCGS)\s*(\d{2})\b')
    facts = []
    for pattern in patterns:
        values = {tuple(x.lower() for x in v) if isinstance(v, tuple) else v.lower()
                  for v in re.findall(pattern, text, re.I)}
        if len(values) != 1:
            return None
        facts.append(next(iter(values)))
    facts.append(bool(re.search(r'\bEPQ\b', text, re.I)))
    facts.append(bool(re.search(r'\bPPQ\b', text, re.I)))
    return tuple(facts)


class _Links(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []
        self.current = None

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            self.current = [dict(attrs).get('href', ''), []]

    def handle_data(self, text):
        if self.current is not None:
            self.current[1].append(text)

    def handle_endtag(self, tag):
        if tag == 'a' and self.current is not None:
            self.links.append((self.current[0], ' '.join(self.current[1])))
            self.current = None


def resolve(url, title, html):
    expected = identity(title)
    if not discovery_url(url) or expected is None:
        return None
    parser = _Links()
    parser.feed(html)
    matches = set()
    for href, text in parser.links:
        try:
            target = urljoin(url, href)
        except ValueError:
            continue
        if exact_url(target) and identity(text) == expected:
            matches.add(target)
    return next(iter(matches)) if len(matches) == 1 else None
