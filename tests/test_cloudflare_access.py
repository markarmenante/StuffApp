"""Real RSA-signed synthetic tokens; no network, credentials or external writes."""
import json
import os
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
import cloudflare_access as access

ISSUER = 'https://fixture.cloudflareaccess.com'
AUD = 'a' * 64
OWNER = 'owner@example.test'


class AccessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.key = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(cls.private.public_key()))
        cls.key.update(kid='fixture', alg='RS256', use='sig')

    def setUp(self):
        self.env = patch.dict(os.environ, STUFFAPP_CF_ACCESS_TEAM_DOMAIN=ISSUER, STUFFAPP_CF_ACCESS_AUD=AUD)
        self.env.start()
        self.keys = patch.object(access, '_keys', return_value=[self.key]); self.keys.start()

    def tearDown(self):
        self.keys.stop(); self.env.stop()

    def token(self, changes=None, header=None, private=None, omit=None):
        now = int(time.time())
        claims = dict(iss=ISSUER, aud=[AUD], email=OWNER, sub='fixture-user', type='app', iat=now-5, exp=now+300)
        claims.update(changes or {})
        if omit:
            claims.pop(omit)
        return jwt.encode(claims, private or self.private, algorithm='RS256', headers=dict(kid='fixture', **(header or {})))

    def verify(self, token, owner=OWNER, user=OWNER):
        return access.owner_verified(token, owner, user)

    def test_real_signed_owner_token_and_both_identities_required(self):
        token = self.token()
        self.assertTrue(self.verify(token))
        self.assertFalse(self.verify(token, owner='other@example.test'))
        self.assertFalse(self.verify(token, user='other@example.test'))
        self.assertFalse(self.verify(token, user=''))
        self.assertFalse(self.verify(self.token(dict(email='other@example.test'))))

    def test_signature_algorithm_and_untrusted_key_urls_are_rejected(self):
        self.assertFalse(self.verify(self.token(private=self.other)))
        self.assertFalse(self.verify(jwt.encode(dict(email=OWNER), 'synthetic-secret-' * 3, algorithm='HS256')))
        self.assertFalse(self.verify(jwt.encode(dict(email=OWNER), '', algorithm='none')))
        for header in ({'jku': 'https://evil.test/keys'}, {'x5u': ISSUER+'/keys'}, {'jwk': self.key}):
            self.assertFalse(self.verify(self.token(header=header)))

    def test_audience_issuer_expiry_future_claims_and_service_tokens_fail_closed(self):
        now = int(time.time())
        for changes in (dict(aud=['b'*64]), dict(iss='https://evil.cloudflareaccess.com'),
                        dict(exp=now-60), dict(nbf=now+60), dict(iat=now+60),
                        dict(type='service'), dict(sub=''), dict(email=None)):
            self.assertFalse(self.verify(self.token(changes)), changes)
        for field in ('exp','iat','aud','iss','sub','email','type'):
            self.assertFalse(self.verify(self.token(omit=field)), field)

    def test_no_configuration_raw_email_or_malformed_token_substitute(self):
        for token in (None, '', OWNER, 'not.a.token', 'x'*16385):
            self.assertFalse(self.verify(token))
        for domain in ('', 'http://fixture.cloudflareaccess.com', 'https://fixture.cloudflareaccess.com.evil.test',
                       'https://fixture.cloudflareaccess.com/redirect'):
            with patch.dict(os.environ, STUFFAPP_CF_ACCESS_TEAM_DOMAIN=domain):
                self.assertFalse(self.verify(self.token()))
        with patch.dict(os.environ, STUFFAPP_CF_ACCESS_AUD=''):
            self.assertFalse(self.verify(self.token()))

    def test_unknown_or_duplicate_keys_and_key_fetch_failure_fail_closed(self):
        for keys in ([], [dict(self.key, kid='other')], [self.key,self.key]):
            with patch.object(access, '_keys', return_value=keys):
                self.assertFalse(self.verify(self.token()))
        with patch.object(access, '_keys', side_effect=RuntimeError('synthetic failure')):
            self.assertFalse(self.verify(self.token()))

    def test_key_cache_and_outage_cooldown_never_use_token_urls(self):
        self.keys.stop()
        try:
            access._CACHE.clear()
            with patch.object(access, '_fetch_keys', return_value=[self.key]) as fetch:
                self.assertTrue(self.verify(self.token()))
                self.assertTrue(self.verify(self.token()))
                fetch.assert_called_once_with(ISSUER)
            access._CACHE.clear()
            with patch.object(access, '_fetch_keys', side_effect=OSError('offline')) as fetch:
                self.assertFalse(self.verify(self.token()))
                self.assertFalse(self.verify(self.token()))
                fetch.assert_called_once_with(ISSUER)
        finally:
            access._CACHE.clear(); self.keys.start()

    def test_external_write_requires_same_origin_browser_intent(self):
        host = 'stuff.example.test'
        self.assertTrue(access.same_origin_write('https://' + host, 'same-origin', host))
        self.assertTrue(access.same_origin_write('https://' + host, None, host))
        self.assertTrue(access.same_origin_write(None, 'same-origin', host))
        for origin, site in ((None,None), ('null','same-origin'), ('null','cross-site'),
                             ('','same-origin'), ('https://evil.test','same-origin'),
                             ('https://'+host,'cross-site'), ('https://'+host,'same-site'),
                             ('https://'+host+'/path','same-origin'), ('https://name@'+host,'same-origin'),
                             ('http://'+host,'same-origin'), ('https://[','same-origin')):
            self.assertFalse(access.same_origin_write(origin, site, host), (origin,site))


if __name__ == '__main__':
    unittest.main()
