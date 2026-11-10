"""Read one product's structured asking price, never shipping or related cards."""
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
import json
import re

from market_scan import canonical_url


def _key(url):
    parts = urlsplit(url)
    # MA-Shops' Offer URL omits the display-currency selector. Keep its item ID.
    if (parts.hostname or '').removeprefix('www.') == 'ma-shops.com':
        parts = parts._replace(query=urlencode([(k, v) for k, v in parse_qsl(parts.query)
                                                if k.lower() != 'curr']))
    return canonical_url(urlunsplit(parts))


def _price(amount, currency, kind):
    if isinstance(amount, bool) or not isinstance(amount, (str, int, float, Decimal)):
        return None
    if not isinstance(currency, str) or not re.fullmatch(r'[A-Z]{3}', currency):
        return None
    try:
        value = Decimal(str(amount))
        if not value.is_finite() or not 0 < value < 10_000_000:
            return None
        if value != value.quantize(Decimal('.01')):
            return None
        return dict(amount=float(value), currency=currency, kind=kind)
    except InvalidOperation:
        return None


def _unique(values):
    values = [v for v in values if v]
    return values[0] if len({(v['currency'], v['amount']) for v in values}) == 1 else None


class _Node:
    def __init__(self, tag, attrs=(), parent=None):
        self.tag, self.attrs, self.parent = tag, dict(attrs), parent
        self.children, self.text = [], ''

    def descendants(self):
        for child in self.children:
            yield child
            yield from child.descendants()

    def scope(self):
        node = self.parent
        while node and 'itemscope' not in node.attrs:
            node = node.parent
        return node

    def value(self):
        return self.attrs.get('content', self.attrs.get('href', self.text.strip()))

    def props(self, name):
        return [n.value() for n in self.descendants()
                if name in n.attrs.get('itemprop', '').split() and n.scope() is self]


class _Page(HTMLParser):
    VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input',
            'link', 'meta', 'param', 'source', 'track', 'wbr'}

    def __init__(self, html):
        super().__init__(convert_charrefs=True)
        self.root = self.current = _Node('root')
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        node = _Node(tag, attrs, self.current)
        self.current.children.append(node)
        if tag not in self.VOID:
            self.current = node

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        node = self.current
        while node.parent:
            if node.tag == tag:
                self.current = node.parent
                return
            node = node.parent

    def handle_data(self, data):
        node = self.current
        while node:
            node.text += data
            node = node.parent


def read(url, html):
    try:
        return _read(url, html)
    except (ValueError, TypeError, RecursionError):
        # Malformed seller markup cannot break availability checks or Buy.
        return None


def _read(url, html):
    """Return amount/currency evidence only for an unambiguous primary offer.

    No currency default and no first-money-amount fallback: denominations,
    postage thresholds, installment amounts and recommendations are not asks.
    Liveness, redirects and title identity are checked separately by the caller.
    """
    page = _Page(html or '')
    nodes = list(page.root.descendants())
    heading = next((n.text for n in nodes if n.tag == 'h1'), '')
    clean = lambda s: re.sub(r'\s+', ' ', str(s or '')).strip().casefold()

    def same(value):
        return isinstance(value, str) and _key(urljoin(url, value)) == _key(url)

    def primary(products, get_url, get_name):
        exact = [p for p in products if get_url(p) and same(get_url(p))]
        if exact:
            return exact[0] if len(exact) == 1 else None
        named = [p for p in products if not get_url(p) and heading
                 and clean(get_name(p)) == clean(heading)]
        if len(named) == 1:
            return named[0]
        if len(products) == 1 and not get_url(products[0]):
            name = get_name(products[0])
            if not heading or not name or clean(name) == clean(heading):
                return products[0]
        return None

    products = []
    for node in nodes:
        if node.tag != 'script' or node.attrs.get('type', '').lower() != 'application/ld+json':
            continue
        try:
            data = json.loads(node.text)
        except (ValueError, TypeError):
            continue
        for obj in data if isinstance(data, list) else [data]:
            if not isinstance(obj, dict):
                continue
            for product in obj.get('@graph', [obj]):
                if isinstance(product, dict) and product.get('@type') == 'Product':
                    products.append(product)
    has_products = bool(products)
    product = primary(products, lambda p: p.get('url') or p.get('@id'), lambda p: p.get('name'))
    if product:
        offers = product.get('offers', [])
        offers = offers if isinstance(offers, list) else [offers]
        prices = [_price(o.get('price'), o.get('priceCurrency'), 'product-jsonld')
                  for o in offers if isinstance(o, dict) and o.get('@type') == 'Offer'
                  and (not o.get('url') or same(o['url']))]
        if any(prices):
            return _unique(prices)

    typed = lambda n, kind: any(t.rstrip('/').endswith('/' + kind)
                               for t in n.attrs.get('itemtype', '').split())
    products = [n for n in nodes if 'itemscope' in n.attrs and typed(n, 'Product')]
    product = primary(products, lambda p: p.attrs.get('itemid') or next(iter(p.props('url')), ''),
                      lambda p: next(iter(p.props('name')), ''))
    if product:
        prices = []
        for offer in product.descendants():
            if offer.scope() is not product or not typed(offer, 'Offer'):
                continue
            urls = offer.props('url')
            if urls and not all(same(u) for u in urls):
                continue
            amounts, currencies = offer.props('price'), offer.props('priceCurrency')
            if len(set(amounts)) == len(set(currencies)) == 1:
                prices.append(_price(amounts[0], currencies[0], 'product-microdata'))
        if any(prices):
            return _unique(prices)

    # Open Graph product metadata belongs to the page head, not nested cards.
    if not products and not has_products:
        head = next((n for n in nodes if n.tag == 'head'), None)
        metas = {}
        for n in head.descendants() if head else []:
            if n.tag == 'meta':
                metas.setdefault(n.attrs.get('property', '').lower(), []).append(n.value())
        if any(not same(value) for value in metas.get('og:url', [])):
            return None
        amounts = metas.get('product:price:amount', metas.get('og:price:amount', []))
        currencies = metas.get('product:price:currency', metas.get('og:price:currency', []))
        if len(set(amounts)) == len(set(currencies)) == 1:
            return _price(amounts[0], currencies[0], 'product-meta')
    return None
