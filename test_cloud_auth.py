"""Cloud auth regression tests; no live users, tokens or keychain writes."""
import time
import unittest
from unittest.mock import patch
from urllib.parse import urlparse, parse_qs
import cloud_auth as c

class CloudAuthTests(unittest.TestCase):
    def setUp(self):
        c.PENDING.clear()
    def test_provider_disabled(self):
        with patch.object(c, '_request', return_value={'external': {'google': False}}):
            with self.assertRaisesRegex(ValueError, 'Web OAuth'):
                c.start('http://127.0.0.1:1234/api/cloud/callback')
        self.assertFalse(c.PENDING)
    def test_callback_validation(self):
        for url in ['https://evil.test/api/cloud/callback', 'http://localhost/api/cloud/callback']:
            with self.assertRaises(ValueError): c.start(url)
    def test_pkce_and_one_use_state(self):
        def request(method, path, **kwargs):
            if path.endswith('settings'): return {'external': {'google': True}}
            if '/token?' in path:
                self.assertEqual(kwargs['value']['code_verifier'], verifier)
                return {'access_token': 'test-only', 'refresh_token': 'test-refresh'}
            return {'id': 'test-user', 'email': 'test@example.test'}
        with patch.object(c, '_request', side_effect=request), patch.object(c, '_save') as save:
            url = c.start('http://127.0.0.1:1234/api/cloud/callback')['url']
            query = parse_qs(urlparse(url).query)
            state = parse_qs(urlparse(query['redirect_to'][0]).query)['state'][0]
            verifier = c.PENDING[state][0]
            self.assertNotIn(verifier, url)
            self.assertEqual(query['code_challenge_method'], ['s256'])
            c.finish('auth-code', state)
            save.assert_called_once()
            with self.assertRaises(ValueError): c.finish('auth-code', state)
    def test_unknown_and_expired_state_no_network(self):
        c.PENDING['expired'] = ('verifier', time.monotonic() - 601)
        with patch.object(c, '_request') as request:
            for state in ['unknown', 'expired']:
                with self.assertRaises(ValueError): c.finish('code', state)
            request.assert_not_called()
    def test_refresh_without_exposing_tokens(self):
        with patch.object(c, '_read', return_value={'refresh_token': 'secret', 'expires_at': 0}), patch.object(c, '_save', return_value={'access_token': 'new'}), patch.object(c, '_request', side_effect=[{'access_token': 'new'}, {'id': 'uid', 'email': 'a@example.test'}]):
            result = c.status()
            self.assertTrue(result['connected'])
            self.assertNotIn('token', str(result))
    def test_logout_clears_local_even_if_offline(self):
        with patch.object(c, '_read', return_value={'access_token': 'test'}), patch.object(c, '_request', side_effect=ValueError('offline')), patch.object(c.keyring, 'delete_password') as delete:
            result = c.logout()
            delete.assert_called_once()
            self.assertFalse(result['connected'])
            self.assertTrue(result['warning'])
    def test_provider_tokens_not_stored(self):
        with patch.object(c.keyring, 'set_password') as save:
            c._save({'access_token': 'test', 'refresh_token': 'test', 'provider_token': 'never-store'})
            self.assertNotIn('never-store', save.call_args.args[2])

if __name__ == '__main__': unittest.main()
