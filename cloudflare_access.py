"""Narrow signed-owner proof for external eBay mutations, not global app auth."""
import json
import os
import re
import threading
import time
from urllib.request import HTTPRedirectHandler, Request, build_opener
from urllib.parse import urlsplit

import jwt

_CACHE = {}
_LOCK = threading.Lock()
_CACHE_SECONDS = 300
_FAILURE_SECONDS = 30


def same_origin_write(origin, fetch_site, host):
    """Browser intent proof for new external writes; absent headers fail closed."""
    if fetch_site is not None and fetch_site != 'same-origin':
        return False
    if origin is None:
        return fetch_site == 'same-origin'
    try:
        parsed = urlsplit(origin)
        return (parsed.scheme == 'https' and parsed.netloc == host and bool(host)
                and parsed.username is None and parsed.password is None
                and not parsed.path and not parsed.query and not parsed.fragment)
    except (ValueError, TypeError):
        return False


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


def _settings():
    issuer = os.environ.get('STUFFAPP_CF_ACCESS_TEAM_DOMAIN', '').rstrip('/')
    audience = os.environ.get('STUFFAPP_CF_ACCESS_AUD', '')
    if not re.fullmatch(r'https://[a-z0-9][a-z0-9-]*\.cloudflareaccess\.com', issuer):
        return None
    if not re.fullmatch(r'[a-f0-9]{64}', audience):
        return None
    return issuer, audience


def _fetch_keys(issuer):
    """Only the configured trusted team; never token-provided URLs or redirects."""
    url = issuer + '/cdn-cgi/access/certs'
    with build_opener(_NoRedirect()).open(Request(url, headers={'Accept': 'application/json'}), timeout=3) as response:
        if response.status != 200 or response.geturl() != url:
            raise ValueError('Untrusted key response')
        data = response.read(262145)
    if len(data) > 262144:
        raise ValueError('Key response exceeds limit')
    value = json.loads(data)
    keys = value.get('keys') if isinstance(value, dict) else None
    if not isinstance(keys, list) or not 1 <= len(keys) <= 16:
        raise ValueError('Invalid key set')
    return [key for key in keys if isinstance(key, dict) and key.get('kty') == 'RSA'
            and key.get('alg') == 'RS256' and key.get('use') == 'sig'
            and isinstance(key.get('kid'), str) and len(key['kid']) <= 256]


def _keys(issuer):
    # One bounded refresh per team, with a short outage cooldown. No untrusted
    # kid can force a network refresh; Cloudflare publishes current/next keys.
    with _LOCK:
        cached = _CACHE.get(issuer)
        if cached and cached[0] > time.monotonic():
            return cached[1]
        try:
            keys = _fetch_keys(issuer)
            lifetime = _CACHE_SECONDS
        except Exception:
            keys, lifetime = [], _FAILURE_SECONDS
        _CACHE[issuer] = (time.monotonic() + lifetime, keys)
        return keys


def owner_verified(token, owner_email, user_email):
    """No email-header, service-token, dev-user, or owner-fallback substitute."""
    settings = _settings()
    owner = str(owner_email or '').strip().lower()
    if not settings or not owner or str(user_email or '').strip().lower() != owner:
        return False
    if not isinstance(token, str) or not 1 <= len(token) <= 16384:
        return False
    issuer, audience = settings
    try:
        header = jwt.get_unverified_header(token)
        if header.get('alg') != 'RS256' or not isinstance(header.get('kid'), str) or len(header['kid']) > 256:
            return False
        if any(key in header for key in ('jku', 'x5u', 'jwk')):
            return False
        matches = [key for key in _keys(issuer) if key['kid'] == header['kid']]
        if len(matches) != 1:
            return False
        claims = jwt.decode(token, jwt.PyJWK.from_dict(matches[0]).key, algorithms=['RS256'],
                            audience=audience, issuer=issuer, leeway=10,
                            options={'require': ['exp', 'iat', 'iss', 'aud', 'sub', 'email', 'type']})
        return (claims.get('type') == 'app' and isinstance(claims.get('sub'), str) and bool(claims['sub'])
                and isinstance(claims.get('email'), str) and claims['email'].strip().lower() == owner)
    except Exception:
        # Deliberately no token, claims, email, key or upstream error logging.
        return False
