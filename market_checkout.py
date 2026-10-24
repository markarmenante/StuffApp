"""Choose a seller handoff URL without making requests or starting a purchase.

On 2026-10-24, the signed-in ebay.com listings 287619084102 and 147612392914
both exposed this exact Buy It Now anchor format:
https://www.ebay.com/bin/ctb?item=ITEM&quantity=1&fromPage=4429486&rev=0&fb=1
The anchor was read without clicking it. These are item/quantity/UI parameters,
not account credentials or checkout-session tokens. Keep checkout gated by the
current exact listing probe; an auction's Place bid control is not Buy It Now.
Other seller sites retain their verified exact listing/ordering page.
"""
import re
from urllib.parse import urlsplit


def _ebay_item_id(url):
    """Only the exact US eBay item format whose checkout was observed."""
    try:
        parsed = urlsplit(str(url or ''))
        if (parsed.scheme != 'https' or parsed.username or parsed.password
                or parsed.port not in (None, 443)
                or (parsed.hostname or '').lower() not in ('ebay.com', 'www.ebay.com')):
            return None
        match = re.fullmatch(r'/itm/(?:[^/]+/)?(\d{9,15})/?', parsed.path)
        return match.group(1) if match else None
    except (TypeError, ValueError):
        return None


def checkout_url(listing_url, probe=None):
    """Prefer eBay's order page only for a currently verified Buy It Now item.

    ``listing_url`` is the caller's already validated exact item URL. ``probe``
    must come from its actual page or the authorized browser's fresh exact-page
    observation, not a model/search summary or another item. The function never
    reads or mutates a seller account, submits an order, or initiates payment.
    """
    url = str(listing_url or '')
    item_id = _ebay_item_id(url)
    if not item_id or not isinstance(probe, dict):
        return url
    if probe.get('state') != 'live' or probe.get('challenged'):
        return url
    if _ebay_item_id(probe.get('final')) != item_id:
        return url
    # identity_text is the primary exact-listing content from the existing
    # liveness probe, which excludes recommendation blocks. Do not use the
    # candidate's live_evidence, title, price or generic "live" state here.
    text = str(probe.get('identity_text') or '')
    if not re.search(r'\bbuy\s+(?:it\s+)?now\b', text, re.I):
        return url
    return ('https://www.ebay.com/bin/ctb?item=' + item_id
            + '&quantity=1&fromPage=4429486&rev=0&fb=1')
