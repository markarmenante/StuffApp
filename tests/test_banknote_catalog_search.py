"""Native search excerpts and bounded failure behavior; no live requests."""
import copy
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import banknote_catalog_search as search

NOTE = dict(country='Maldives', pick_number='P-5b', denomination='10 Rufiyaa',
            date_1=1960, serial_number='PRIVATE-SERIAL', price='PRIVATE-PRICE',
            order_number='PRIVATE-ORDER', image_1='PRIVATE-PHOTO')
URL = 'https://en.numista.com/223321'
SNIPPET = 'Maldives 10 Rupees P-5b. Printer: Bradbury Wilkinson. Size: 156 × 103 mm.'


def payload(url=URL, snippet=SNIPPET):
    return dict(results=[dict(url=url, title='Maldives 10 Rupees P-5b', snippet=snippet)])


class SearchTests(unittest.TestCase):
    def test_query_minimal_complete_reference_and_no_private_fields(self):
        original = copy.deepcopy(NOTE)
        self.assertEqual(search.queries(NOTE), ['Maldives "P5b"', 'Maldives "Pick 5b"'])
        self.assertEqual(NOTE, original)
        self.assertNotIn('PRIVATE-', json.dumps(search.queries(NOTE)))

    def test_namespaces_suffixes_and_all_references_are_preserved(self):
        q = search.queries(dict(country='Germany', pick_number='Grabowski Bi.7.5'))
        self.assertIn('"Grabowski bi.7.5"', q[0])
        q = search.queries(dict(country='Maldives', pick_number='P-5b*', other_catalog='TBB B105b'))
        self.assertIn('"P5b*"', q[0]); self.assertIn('"TBB b105b"', q[0])
        for value in ('P-5b, P-5a', '64', 'P-5b or P-5c', 'P-5b, unsupported'):
            self.assertEqual(search.queries(dict(country='Maldives', pick_number=value)), [])

    def test_native_snippet_is_literal_and_model_answer_is_not_evidence(self):
        out = search.sources(payload())
        self.assertEqual(out[URL], dict(title='Maldives 10 Rupees P-5b',
                                      quotes=[SNIPPET], document_text=SNIPPET))
        self.assertEqual(search.sources(dict(choices=[{'message':{'content':SNIPPET}}],
                                            citations=[URL])), {})
        self.assertEqual(search.sources(payload(snippet='')), {})

    def test_unsafe_and_wrong_domain_urls_are_discarded(self):
        for url in ('http://en.numista.com/223321', 'https://numista.com.evil.test/223321',
                    'https://evil.test/en.numista.com/223321', 'https://127.0.0.1/223321',
                    'https://user:pass@en.numista.com/223321', 'https://en.numista.com:444/223321',
                    'https://en.numista.com/account/private', 'https://en.numista.com/\\bad',
                    'https://en.numista.com/\n223321', 'https://[bad'):
            with self.subTest(url=url):
                self.assertEqual(search.sources(payload(url=url)), {})

    def test_malformed_oversized_and_duplicate_results(self):
        for bad in (None, [], {'results':None}, {'results':{}}, {'results':[None]},
                    {'results':[dict(url=URL,title='x',snippet={})]},
                    payload(snippet='x'*(search.MAX_SNIPPET+1))):
            self.assertEqual(search.sources(bad), {})
        data = payload(); data['results'].append(dict(url=URL,title='duplicate',snippet='replacement'))
        self.assertEqual(search.sources(data)[URL]['document_text'], SNIPPET)
        data = dict(results=[dict(url=f'https://en.numista.com/{i}',title='t',snippet='s') for i in range(9)])
        self.assertEqual(len(search.sources(data)), 5)

    def test_request_budget_schema_and_no_retry(self):
        before = copy.deepcopy(NOTE)
        with patch.object(search, 'build_opener') as factory:
            opener = factory.return_value
            opener.open.return_value = io.BytesIO(json.dumps(payload()).encode())
            out = search.search(NOTE, 'synthetic-key', timeout=80)
            self.assertEqual(out[URL]['document_text'], SNIPPET)
            args, kwargs = opener.open.call_args
            self.assertEqual(kwargs['timeout'], 15)
            request = args[0]
            self.assertEqual(request.full_url, 'https://api.perplexity.ai/search')
            body = json.loads(request.data)
            self.assertEqual(body['query'], ['Maldives "P5b"', 'Maldives "Pick 5b"'])
            self.assertEqual((body['max_results'],body['max_tokens'],body['max_tokens_per_page']), (5,12000,4000))
            self.assertLessEqual(len(body['search_domain_filter']), 20)
            self.assertNotIn('PRIVATE-', request.data.decode())
            self.assertEqual(opener.open.call_count, 1)
            self.assertIsInstance(factory.call_args.args[0], search._NoRedirect)
        self.assertEqual(NOTE, before)

    def test_caller_remaining_deadline_is_respected(self):
        with patch.object(search, 'build_opener') as factory:
            factory.return_value.open.return_value = io.BytesIO(b'{"results":[]}')
            search.search(NOTE, 'synthetic-key', timeout=2.25)
            self.assertEqual(factory.return_value.open.call_args.kwargs['timeout'], 2.25)
        for timeout in (0, -1, float('nan'), 'invalid', None):
            with self.subTest(timeout=timeout), patch.object(search, 'build_opener') as factory:
                self.assertEqual(search.search(NOTE, 'synthetic-key', timeout=timeout), {})
                factory.assert_not_called()

    def test_failed_truncated_and_oversized_responses_are_empty_without_retry(self):
        errors = [URLError('failure'), HTTPError(search.ENDPOINT,429,'rate limited',{},None),
                  HTTPError(search.ENDPOINT,401,'unauthorized',{},None)]
        for error in errors:
            with self.subTest(error=type(error).__name__), patch.object(search, 'build_opener') as factory:
                factory.return_value.open.side_effect = error
                self.assertEqual(search.search(NOTE, 'synthetic-key'), {})
                self.assertEqual(factory.return_value.open.call_count, 1)
        for raw in (b'{"results":[', b'not JSON', b'\xff', b'x'*(search.MAX_BYTES+1)):
            with patch.object(search, 'build_opener') as factory:
                factory.return_value.open.return_value = io.BytesIO(raw)
                self.assertEqual(search.search(NOTE, 'synthetic-key'), {})
                self.assertEqual(factory.return_value.open.call_count, 1)

    def test_missing_key_or_identity_does_not_contact_provider(self):
        for note, key in ((NOTE,None),(NOTE,''),({},'synthetic-key'),
                          ({'country':'Maldives'},'synthetic-key'),([], 'synthetic-key')):
            with patch.object(search, 'build_opener') as factory:
                self.assertEqual(search.search(note,key), {})
                factory.assert_not_called()

    def test_redirects_never_forward_provider_credentials(self):
        self.assertIsNone(search._NoRedirect().redirect_request(None,None,302,'',{},'https://other.test'))


if __name__ == '__main__':
    unittest.main()
