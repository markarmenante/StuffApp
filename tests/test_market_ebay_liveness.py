"""Market Scan liveness for eBay. eBay walls the scan's fetches (a
redirect to /splashui/captcha) and keeps ended item pages up with the
title, photos and price, so 'unknown' — which never drops — let months-
old ended lots through as candidates (2026-09-11). Now: the captcha
bounce is a challenge; a readable eBay page with no buy/bid control is
ended; an unreadable eBay page keeps its item only on the model's own
live evidence; other venues are unchanged.

Run: .venv/bin/python tests/test_market_ebay_liveness.py
"""
import os, sys, tempfile
from datetime import date, timedelta

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)
sys.path.insert(0, REPO)
os.environ['DATA_DIR'] = tempfile.mkdtemp(prefix='stuffapp-ebay-')
os.environ.pop('ANTHROPIC_API_KEY', None)

import app as stuffapp

stuffapp.time.sleep = lambda s: None  # no retry pause in tests

PAGES = {}
def fake_fetch(url, limit=400_000):
    status, html, final = PAGES.get(url, (None, '', url))
    stuffapp._MARKET_LAST_URL.final = final
    return status, html
stuffapp._market_fetch_page = fake_fetch

def page(body):
    return '<html><head><title>x</title></head><body>' + body + ' ' * 100 + '</body></html>'

ENDED_SELLER = page('<h1>Curacao 2 1/2 Gulden 1920 PMG 64 EPQ</h1><div>ENDED</div><p>This listing was ended by the seller on Sat, Aug 29 at 1:11 AM because the item is no longer available.</p><span>US $375.00</span>')
ENDED_BADGE = page('<h1>French Guinea 5 Francs SPECIMEN PMG 67 EPQ Top Pop</h1><span class="badge">ENDED</span><span>US $299.99</span><span>Wed, Dec 25, 02:25 AM</span><a>Seller\'s other items</a><h2>Similar Items</h2><span>Sponsored</span>')
LIVE_BIN = page('<h1>Danish West Indies 2 Daler 1898 PMG 63</h1><span>US $599.99</span><button>Buy It Now</button><button>Add to cart</button><span>Ships from</span>')
LIVE_AUCTION = page('<h1>Sarawak One Dollar 1935</h1><span>Current bid: US $210.00</span><button>Place bid</button><span>Time left 2d 4h</span>')
CAPTCHA = '<html><head><title>Security Measure | eBay</title></head><body>Please verify yourself to continue captcha</body></html>'
DEALER_PLAIN = page('<h1>Italian Somaliland 10 Somali 1950</h1><p>Price on request. Contact us.</p>')

PAGES.update({
    'https://www.ebay.com/itm/1': (200, ENDED_SELLER, 'https://www.ebay.com/itm/1'),
    'https://www.ebay.com/itm/2': (200, ENDED_BADGE, 'https://www.ebay.com/itm/2'),
    'https://www.ebay.com/itm/3': (200, LIVE_BIN, 'https://www.ebay.com/itm/3'),
    'https://www.ebay.de/itm/4': (200, LIVE_AUCTION, 'https://www.ebay.de/itm/4'),
    'https://www.ebay.com/itm/5': (200, CAPTCHA, 'https://www.ebay.com/splashui/captcha?ap=1&ru=https%3A%2F%2Fwww.ebay.com%2Fitm%2F5'),
    'https://www.ebay.com/itm/6': (None, '', 'https://www.ebay.com/itm/6'),
    'https://www.ebay.com/itm/7': (None, '', 'https://www.ebay.com/itm/7'),
    'https://www.ebay.com/itm/8': (None, '', 'https://www.ebay.com/itm/8'),
    'https://dealer.example/notes/9': (200, DEALER_PLAIN, 'https://dealer.example/notes/9'),
    'https://www.ebay.co.uk/itm/10': (200, LIVE_BIN, 'https://www.ebay.co.uk/itm/10'),
})

assert stuffapp._market_is_ebay('https://www.ebay.com/itm/1')
assert stuffapp._market_is_ebay('https://www.ebay.de/itm/4') and stuffapp._market_is_ebay('https://www.ebay.co.uk/itm/10')
assert not stuffapp._market_is_ebay('https://dealer.example/notes/9')
assert not stuffapp._market_is_ebay('https://notebay.com/x')

st = stuffapp._market_listing_state
assert st('https://www.ebay.com/itm/1') == 'ended', 'ended by the seller'
assert st('https://www.ebay.com/itm/2') == 'ended', 'badge-only ended page (no buy control)'
assert st('https://www.ebay.com/itm/3') == 'live'
assert st('https://www.ebay.de/itm/4') == 'live'
assert st('https://www.ebay.com/itm/5') == 'unknown', 'captcha bounce is a challenge, not a verdict'
assert st('https://www.ebay.com/itm/6') == 'unknown'
assert st('https://dealer.example/notes/9') == 'unknown', 'a plain dealer page decides nothing'
print('STATES OK')

tomorrow = (date.today() + timedelta(days=1)).isoformat()
yesterday = (date.today() - timedelta(days=1)).isoformat()
items = [
    {'title': 'ended-seller', 'listing_url': 'https://www.ebay.com/itm/1', 'live_evidence': 'Buy It Now $375'},
    {'title': 'ended-badge', 'listing_url': 'https://www.ebay.com/itm/2', 'live_evidence': 'Buy It Now'},
    {'title': 'live-bin', 'listing_url': 'https://www.ebay.com/itm/3', 'live_evidence': ''},
    {'title': 'live-auction', 'listing_url': 'https://www.ebay.de/itm/4', 'live_evidence': ''},
    {'title': 'captcha-with-evidence', 'listing_url': 'https://www.ebay.com/itm/5', 'live_evidence': 'Buy It Now, 1 available'},
    {'title': 'dead-no-evidence', 'listing_url': 'https://www.ebay.com/itm/6', 'live_evidence': 'listed at $349.99'},
    {'title': 'dead-future-close', 'listing_url': 'https://www.ebay.com/itm/7', 'live_evidence': '', 'closes': tomorrow},
    {'title': 'dead-past-close', 'listing_url': 'https://www.ebay.com/itm/8', 'live_evidence': '', 'closes': yesterday},
    {'title': 'dealer-unknown', 'listing_url': 'https://dealer.example/notes/9', 'live_evidence': ''},
    {'title': 'live-uk', 'listing_url': 'https://www.ebay.co.uk/itm/10', 'live_evidence': ''},
]
kept = stuffapp._market_verify_live(items)
names = [i['title'] for i in kept]
assert names == ['live-bin', 'live-auction', 'captcha-with-evidence', 'dead-future-close', 'dealer-unknown', 'live-uk'], names
by = {i['title']: i for i in kept}
assert by['live-bin']['verified'] and by['live-uk']['verified'] and not by['captcha-with-evidence']['verified']
assert not by['dealer-unknown']['verified']
print('VERIFY OK')

ok = stuffapp._market_unreadable_ebay_ok
assert ok({'live_evidence': '3 bids · time left 1d'}) and ok({'live_evidence': 'Add to cart'}) and ok({'closes': tomorrow})
assert not ok({'live_evidence': '$299.99'}) and not ok({'closes': yesterday}) and not ok({})
print('EVIDENCE OK')
print('ALL MARKET-EBAY-LIVENESS ASSERTIONS PASSED')
