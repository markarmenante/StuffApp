"""Bounded catalogue page verification: synthetic provider responses only."""
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['DATA_DIR'] = tempfile.mkdtemp(prefix='stuff-catalog-fetch-')
os.environ.pop('ANTHROPIC_API_KEY', None)
import banknote_catalog_lookup as lookup
import app as stuff

NOTE = dict(country='Maldives', denomination='10 Rufiyaa', pick_number='P-5b',
            issuer='Government of the Maldives', date_1=1960)
URL = 'https://en.numista.com/223321'
INDEX = 'https://en.numista.com/catalogue/maldives-1.html'
FULL = 'Maldives. Government of the Maldives. 10 Rufiyaa. P-5b. 1960. Printer: Bradbury Wilkinson. Size: 156 × 103 mm.'


def research():
    return dict(identity=dict(NOTE, reference='P-5b', match='exact'), fields={
        'printer': dict(value='Bradbury Wilkinson', scope='type', source_url=URL,
                        quote='Printer: Bradbury Wilkinson.')})


def search_blocks(url=URL, title='Maldives 10 Rupees P-5b'):
    return [dict(type='server_tool_use', name='web_search', id='search-1', input={}),
            dict(type='web_search_tool_result', tool_use_id='search-1', content=[
                dict(type='web_search_result', url=url, title=title)])]


def fetch_blocks(url=URL, data=FULL):
    return [dict(type='server_tool_use', name='web_fetch', id='fetch-1', input={'url':url}),
            dict(type='web_fetch_tool_result', tool_use_id='fetch-1', content=dict(
                type='web_fetch_result', url=url, content=dict(type='document',
                    title='Maldives 10 Rupees', source=dict(type='text', data=data))))]


def response(raw=None, blocks=(), stop='end_turn', text=None):
    dumped = copy.deepcopy(list(blocks))
    dumped.append(dict(type='text', text=json.dumps(raw or {}) if text is None else text))
    return SimpleNamespace(stop_reason=stop,
        content=[SimpleNamespace(**block) for block in dumped],
        model_dump=lambda: {'content':copy.deepcopy(dumped)})


class CandidateTests(unittest.TestCase):
    def test_candidates_are_observed_allowed_pages_only_and_at_most_two(self):
        sources = {url:dict(title='Maldives 10 Rupees P-5b', quotes=[]) for url in (
            URL, INDEX, 'https://www.banknoteindex.com/banknote.aspx?id=22',
            'http://en.numista.com/223321', 'https://numista.com.evil.test/223321',
            'https://user:pass@en.numista.com/223321', 'https://en.numista.com:444/223321',
            'https://127.0.0.1/223321', 'https://en.numista.com/forum/223321',
            'https://en.numista.com/account/223321')}
        raw = dict(catalogue_research=research())
        raw['catalogue_research']['fields']['size_width'] = dict(source_url='https://en.numista.com/999999')
        selected = lookup.fetch_candidates(NOTE, raw, sources)
        self.assertEqual(selected, [URL, INDEX])
        self.assertNotIn('https://en.numista.com/999999', selected)

    def test_observed_country_directory_can_resolve_missing_dimensions(self):
        directory = 'https://banknoteindex.com/browse.mhtml?browseBy=Country'
        sources = {directory:dict(title='Banknote Index - Country', quotes=[]),
            'https://banknoteindex.com/browse.mhtml?browseBy=Authority':dict(title='Authority', quotes=[])}
        self.assertEqual(lookup.fetch_candidates(NOTE, {}, sources), [directory])
        self.assertEqual(lookup.fetch_candidates(dict(NOTE,size_width=156,size_height=103), {}, sources), [])
        self.assertEqual(lookup.fetch_candidates(dict(NOTE,country=''), {}, sources), [])
        self.assertEqual(lookup.fetch_candidates(NOTE, {}, {}), [directory])

    def test_numeric_discovery_does_not_require_rufiyaa_english_alias(self):
        note = copy.deepcopy(NOTE)
        selected = lookup.fetch_candidates(note, {}, {
            URL:dict(title='10 Rupees - Maldives', quotes=[]),
            'https://en.numista.com/other':dict(title='Bermuda 10 Rupees P-5b', quotes=[]),
        })
        self.assertEqual(selected, [URL, lookup.BNI_COUNTRY_DIRECTORY])
        self.assertEqual(note, NOTE)

    def test_discovery_rejects_neighboring_type_currency_and_coin(self):
        for title in ('Maldives 10 Laari P-5b', 'Maldives 5 Rufiyaa P-5b',
                      'Maldives 10 Rufiyaa P-5a', 'Maldives 10 Rufiyaa coin P-5b'):
            with self.subTest(title=title):
                self.assertEqual(lookup.fetch_candidates(NOTE, {}, {
                    URL:dict(title=title, quotes=[])}), [lookup.BNI_COUNTRY_DIRECTORY])

    def test_observed_legacy_numista_note_url_keeps_same_numeric_identity(self):
        old = 'https://en.numista.com/catalogue/note223321.html'
        self.assertEqual(lookup.fetch_candidates(NOTE, {}, {
            old:dict(title='Maldives 10 Rufiyaa P-5b', quotes=[])}), [URL, lookup.BNI_COUNTRY_DIRECTORY])

    def test_configured_directory_requires_explicit_unambiguous_country_and_reference(self):
        for change in ({'country':''}, {'pick_number':''}, {'pick_number':'64'},
                       {'pick_number':'P-5b, possibly P-5c'}, {'pick_number':'P-5b, P-5a'},
                       {'pick_number':'Fr-652'}, {'size_width':156,'size_height':103}):
            with self.subTest(change=change):
                self.assertEqual(lookup.fetch_candidates(dict(NOTE, **change), {}, {}), [])
        for country, ref in (('Seychelles','P-14a'), ('Bermuda','TBB B101a'),
                             ('French Somaliland','P-12b')):
            self.assertEqual(lookup.fetch_candidates(dict(NOTE,country=country,pick_number=ref), {}, {}),
                             [lookup.BNI_COUNTRY_DIRECTORY])
        # A model's invented identity does not create a configured navigation intent.
        self.assertEqual(lookup.fetch_candidates({}, {'catalogue_research':research()}, {}), [])

    def test_configured_navigation_is_separate_from_observed_sources_and_proof(self):
        source = {}
        urls = lookup.fetch_candidates(NOTE, {}, source)
        self.assertEqual(source, {})
        prompt = lookup.fetch_prompt(NOTE, urls)
        self.assertIn('Configured public directory (navigation only, not evidence)', prompt)
        self.assertIn('Observed URLs: []', prompt)
        self.assertIn('actual exact country or historical-territory link', prompt)
        self.assertIn('do not stop while requested dimensions remain unverified', prompt)
        fake = research()
        fake['fields']['printer']['source_url'] = lookup.BNI_COUNTRY_DIRECTORY
        self.assertEqual(lookup.validate(NOTE, {}, fake, source)['fields'], {})

    def test_chinese_compound_reference_keeps_directory_and_exact_pcgs_source(self):
        note = dict(country='China', pick_number='P-M30, S/M#T32-6',
                    denomination='100 Yen', date_1=1945)
        url = 'https://www.pcgs.com/notefacts/detail/china/pick-m30/707203'
        src = dict(title='China Pick M30 100 Yen Japanese Imperial Government',
                   quotes=['China Pick M30 S/M T32-6 100 Yen ND (1945)'])
        self.assertEqual(lookup.fetch_candidates(note, {}, {url:src}),
                         [url, lookup.BNI_COUNTRY_DIRECTORY])
        self.assertEqual(lookup.fetch_candidates(note, {}, {
            'https://pcgs.com.evil.test/notefacts/707203':src}), [lookup.BNI_COUNTRY_DIRECTORY])

    def test_failed_server_calls_spend_budget_but_text_claims_do_not(self):
        calls = [dict(content=[dict(type='server_tool_use', name='web_fetch'),
            dict(type='web_fetch_tool_result', content=dict(type='web_fetch_tool_result_error')),
            dict(type='tool_use', name='web_fetch'), dict(type='text', text='web_fetch used 99 times')]),
            dict(content=[dict(type='server_tool_use', name='web_fetch'),
                          dict(type='server_tool_use', name='web_search')])]
        self.assertEqual(lookup.tool_uses(calls, 'web_fetch'), 2)
        self.assertEqual(lookup.tool_uses(calls, 'web_search'), 1)

    def test_fetch_prompt_omits_protected_record_and_photo_fields(self):
        note = dict(NOTE, serial_number='PRIVATE-SERIAL', slab_number='PRIVATE-CERT',
                    price='PRIVATE-PRICE', order_number='PRIVATE-ORDER',
                    image_1='PRIVATE-PHOTO', grade='PRIVATE-GRADE', printer='Known printer')
        prompt = lookup.fetch_prompt(note, [URL])
        self.assertIn(URL, prompt)
        self.assertIn('P-5b', prompt)
        self.assertNotIn('PRIVATE-', prompt)
        missing = prompt.split('Research only these missing type fields: ', 1)[1].split('.', 1)[0]
        self.assertNotIn('printer', missing)


class ProviderBudgetTests(unittest.TestCase):
    def call(self, replies, ticks=(100, 101, 110), note=None, native=None,
             search_key='', native_calls=None, native_error=None):
        with patch('anthropic.Anthropic') as factory, \
                patch.dict(os.environ, {'PERPLEXITY_API_KEY':search_key}), \
                patch.object(stuff.banknote_catalog_search, 'search',
                    return_value=native or {}, side_effect=native_error) as native_search, \
                patch.object(stuff, '_require_anthropic_key', return_value='synthetic-key'), \
                patch.object(stuff, 'anthropic_lookup_model', return_value='configured-model'), \
                patch.object(stuff, 'anthropic_web_search_tool', return_value=dict(
                    type='web_search_20250305', name='web_search', max_uses=4)), \
                patch.object(stuff, '_load_vision_images', return_value=[]), \
                patch.object(stuff.time, 'monotonic', side_effect=ticks):
            factory.return_value.messages.create.side_effect = replies
            result = stuff.fetch_banknote_specs(copy.deepcopy(NOTE if note is None else note))
            calls = [call.kwargs for call in factory.return_value.messages.create.call_args_list]
            if native_calls is not None:
                native_calls.extend(native_search.call_args_list)
            self.assertEqual(factory.call_args.kwargs['max_retries'], 0)
        return result, calls

    def test_empty_followup_retains_first_pass_proofs_without_trusting_private_model_keys(self):
        first = dict(catalogue_research=research(), _catalogue_previous_research={'invented':True})
        result, calls = self.call([response(first, search_blocks()), response(
            {'catalogue_research':{'identity':{'match':'unresolved'},'fields':{}},
             '_catalogue_previous_research':{'also_invented':True}}, fetch_blocks())])
        self.assertEqual(result['_catalogue_previous_research'], research())
        valid = lookup.validate_all(NOTE, {}, result['catalogue_research'], result['_catalogue_sources'],
                                    previous=result['_catalogue_previous_research'])
        self.assertEqual(valid['fields']['printer']['value'], 'Bradbury Wilkinson')
        self.assertEqual(len(calls), 2)
        prompt = calls[0]['messages'][0]['content'][-1]['text']
        template = prompt.split('Reply with a JSON object, without code fences.', 1)[1].split('EXECUTE THESE', 1)[0]
        self.assertIn('"direct_evidence": {}', template)
        self.assertIn('"catalogue_research":', template)

    def test_empty_cameroon_extraction_recovers_native_page_without_extra_provider_calls(self):
        from test_banknote_catalog_recovery import NOTE as cameroon, sources as cameroon_sources
        result, calls = self.call([response(), response({'catalogue_research':{'fields':{}}})],
            note=cameroon, native=cameroon_sources(), search_key='synthetic-key', ticks=(100,101,110,112))
        valid = lookup.validate_all(cameroon, {}, result['catalogue_research'], result['_catalogue_sources'])
        self.assertEqual(set(valid['fields']), {'issuer','printer','material','size_width','size_height','obv_rev'})
        self.assertEqual(len(calls), 2)
        self.assertLessEqual(calls[1]['timeout'], 75)
        self.assertIn('most promising observed exact type page FIRST', calls[1]['messages'][0]['content'])

    def test_check_prompt_preserves_established_hong_kong_occupation_filing(self):
        note = dict(country='Hong Kong', issuer='Japanese Imperial Government',
                    issue_type='Military / Occupation', denomination='100 Yen',
                    date_1=1945, pick_number='P-M30, S/M#T32-6')
        _, calls = self.call([response({}), response({})], note=note)
        prompt = calls[0]['messages'][0]['content'][-1]['text']
        self.assertIn('Preserve an established Hong Kong filing for a Japanese occupation issue', prompt)
        self.assertIn('a grading label saying China alone does not change it to China', prompt)
        self.assertIn('Federal Reserve Bank of China, Central Reserve Bank, Mengchiang Bank, Hua Hsing', prompt)
        self.assertIn('Never infer Hong Kong from Japanese military yen or a China label alone', prompt)

    def test_followup_fetch_only_preserves_direct_facts_and_ignores_top_level_changes(self):
        first = dict(serial_number='C136027', price='$199.99', printer='Direct Print',
                     direct_evidence={'printer':dict(source='dealer', quote='Printer: Direct Print')},
                     catalogue_research={'identity':{'match':'unresolved'},'fields':{}})
        second = dict(catalogue_research=research(), serial_number='REPLACED', price='$1',
                      printer='REPLACED', _catalogue_direct_fields=['watermark'])
        result, calls = self.call([response(first, search_blocks()), response(second, fetch_blocks())],
                                 note=dict(NOTE, description='Printer: Direct Print'))
        self.assertEqual(len(calls), 2)
        self.assertEqual([t['name'] for t in calls[0]['tools']], ['web_search'])
        self.assertEqual([t['name'] for t in calls[1]['tools']], ['web_fetch'])
        self.assertEqual(calls[1]['tools'][0]['max_uses'], lookup.MAX_FETCHES)
        self.assertEqual(calls[1]['timeout'], 65)
        self.assertEqual(result['serial_number'], 'C136027')
        self.assertEqual(result['price'], '$199.99')
        self.assertEqual(result['printer'], 'Direct Print')
        self.assertEqual(result['_catalogue_direct_fields'], ['printer'])
        self.assertEqual(result['catalogue_research'], research())
        self.assertEqual(result['_catalogue_sources'][URL]['document_text'], FULL)

    def test_followup_failure_is_not_retried_and_retains_first_result(self):
        first = dict(serial_number='C136027', catalogue_research=research())
        for failure in (RuntimeError('provider failed'), response(text='not json'),
                        response({'catalogue_research':{}}, stop='pause_turn'),
                        response({'catalogue_research':{}}, stop='max_tokens')):
            with self.subTest(failure=type(failure).__name__, stop=getattr(failure,'stop_reason',None)):
                result, calls = self.call([response(first, search_blocks()), failure])
                self.assertEqual(len(calls), 2)
                self.assertEqual(result['serial_number'], 'C136027')
                self.assertEqual(result['catalogue_research'], first['catalogue_research'])

    def test_pause_continuation_and_followup_share_tool_budgets(self):
        used = search_blocks() + [dict(type='server_tool_use',name='web_search',id='s2',input={})]
        used += [dict(type='server_tool_use',name='web_fetch',id='f1',input={'url':URL}),
                 dict(type='web_fetch_tool_result',content=dict(type='web_fetch_tool_result_error'))]
        first = response({}, used, stop='pause_turn')
        second = response(dict(catalogue_research=research()), [
            dict(type='server_tool_use',name='web_fetch',id='f2',input={'url':URL}),
            dict(type='web_fetch_tool_result',content=dict(type='web_fetch_tool_result_error'))])
        result, calls = self.call([first, second, response(dict(catalogue_research=research()), fetch_blocks())],
                                 ticks=(100,101,120,140))
        self.assertEqual(len(calls), 3)
        limits = {t['name']:t['max_uses'] for t in calls[1]['tools']}
        self.assertEqual(limits, {'web_search':2})
        self.assertEqual(calls[2]['tools'][0]['max_uses'], lookup.MAX_FETCHES-2)
        self.assertEqual([call['timeout'] for call in calls], [74,55,35])
        self.assertIn('document_text', result['_catalogue_sources'][URL])

    def test_no_followup_when_deadline_near_or_fetch_budget_exhausted(self):
        for blocks, ticks in [(search_blocks(), (100,101,168)),
                (search_blocks()+[dict(type='server_tool_use',name='web_fetch',id=str(i),input={})
                                  for i in range(lookup.MAX_FETCHES)], (100,101,110))]:
            with self.subTest(ticks=ticks):
                result, calls = self.call([response(dict(catalogue_research=research()), blocks)], ticks=ticks)
                self.assertEqual(len(calls), 1)
                self.assertEqual(result['catalogue_research'], research())

    def test_model_url_and_document_claim_cannot_trigger_fetch(self):
        first = dict(catalogue_research=research(), _catalogue_sources={URL:{'document_text':FULL}})
        result, calls = self.call([response(first)], note=dict(NOTE,size_width=156,size_height=103))
        self.assertEqual(len(calls), 1)
        self.assertEqual(result['_catalogue_sources'], {})

    def test_malformed_optional_research_does_not_discard_direct_result(self):
        for research_value in (['unexpected'], {'fields':['unexpected']},
                               {'identity':['unexpected']}):
            with self.subTest(research=research_value):
                first = dict(serial_number='C136027', catalogue_research=research_value)
                result, calls = self.call([response(first)], note=dict(NOTE,size_width=156,size_height=103))
                self.assertEqual(result['serial_number'], 'C136027')
                self.assertEqual(len(calls), 1)

    def test_existing_full_source_does_not_fetch_same_page_again(self):
        result, calls = self.call([response(dict(catalogue_research=research()), search_blocks()+fetch_blocks())])
        self.assertEqual(len(calls), 1)
        self.assertEqual(result['_catalogue_sources'][URL]['document_text'], FULL)

    def test_native_source_proof_authorizes_only_cited_type_fact(self):
        native = {URL:dict(title='Maldives 10 Rufiyaa P-5b', quotes=[FULL], document_text=FULL)}
        first = dict(serial_number='C136027', price='$199.99',
                     _catalogue_sources={'https://invented.example':dict(document_text='Invented')})
        second = dict(catalogue_research=research(), serial_number='REPLACED',
                      _catalogue_sources={'https://invented.example':dict(document_text='Invented')},
                      _catalogue_direct_fields=['printer'])
        native_calls = []
        result, calls = self.call([response(first), response(second)], ticks=(100,101,110,112),
            native=native, search_key='synthetic-existing-key', native_calls=native_calls)
        self.assertEqual(len(calls), 2)
        self.assertEqual(len(native_calls), 1)
        self.assertEqual(native_calls[0].args, (NOTE, 'synthetic-existing-key'))
        self.assertEqual(native_calls[0].kwargs['timeout'], 15)
        self.assertEqual(calls[1]['timeout'], 63)
        self.assertEqual(result['serial_number'], 'C136027')
        self.assertEqual(result['price'], '$199.99')
        self.assertEqual(result['_catalogue_direct_fields'], [])
        self.assertEqual(set(result['_catalogue_sources']), {URL})
        validated = lookup.validate(NOTE, {}, result['catalogue_research'], result['_catalogue_sources'])
        self.assertEqual(validated['fields']['printer']['value'], 'Bradbury Wilkinson')
        self.assertIn(json.dumps(FULL)[1:-1], calls[1]['messages'][0]['content'])
        self.assertNotIn('synthetic-existing-key', json.dumps(calls))

    def test_native_source_cannot_authorize_uncited_changed_value(self):
        native = {URL:dict(title='Maldives 10 Rufiyaa P-5b', quotes=[FULL], document_text=FULL)}
        wrong = research()
        wrong['fields']['printer']['value'] = 'Invented Printer'
        wrong['fields']['printer']['quote'] = 'Printer: Invented Printer.'
        result, _ = self.call([response(), response(dict(catalogue_research=wrong,
            _catalogue_sources={URL:dict(document_text='Printer: Invented Printer.')}))],
            ticks=(100,101,110,112), native=native, search_key='synthetic-key')
        self.assertEqual(lookup.validate(NOTE, {}, result['catalogue_research'],
            result['_catalogue_sources'])['fields'], {})
        self.assertEqual(result['_catalogue_sources'][URL]['document_text'], FULL)

    def test_native_source_and_actual_fetch_evidence_merge_without_losing_either(self):
        native = {URL:dict(title='Maldives 10 Rufiyaa P-5b', quotes=[FULL], document_text=FULL)}
        extra = 'Maldives P-5b. Material: Paper.'
        result, _ = self.call([response({}, search_blocks()), response(dict(catalogue_research=research()),
            fetch_blocks(data=extra))], ticks=(100,101,110,112), native=native, search_key='synthetic-key')
        self.assertIn(FULL, result['_catalogue_sources'][URL]['quotes'])
        self.assertIn(extra, result['_catalogue_sources'][URL]['quotes'])
        self.assertIn('printer', lookup.validate(NOTE, {}, result['catalogue_research'],
            result['_catalogue_sources'])['fields'])

    def test_native_search_uses_remaining_budget_and_preserves_time_for_extraction(self):
        native = {URL:dict(title='Maldives 10 Rufiyaa P-5b', quotes=[FULL], document_text=FULL)}
        native_calls = []
        result, calls = self.call([response(), response(dict(catalogue_research=research()))],
            ticks=(100,101,160,165), native=native, search_key='synthetic-key', native_calls=native_calls)
        self.assertEqual(native_calls[0].kwargs['timeout'], 5)
        self.assertEqual(calls[1]['timeout'], 10)
        self.assertEqual(len(native_calls), 1)
        self.assertEqual(len(calls), 2)

    def test_native_search_near_deadline_cannot_trigger_extra_provider_call(self):
        native_calls = []
        result, calls = self.call([response(dict(serial_number='C136027'))],
            ticks=(100,101,172,174), search_key='synthetic-key', native_calls=native_calls)
        self.assertEqual(native_calls[0].kwargs['timeout'], 0)
        self.assertEqual(len(calls), 1)
        self.assertEqual(result['serial_number'], 'C136027')

    def test_native_search_no_key_does_not_contact_or_create_an_integration(self):
        native_calls = []
        result, calls = self.call([response(dict(serial_number='C136027'))],
            search_key='', native_calls=native_calls, note=dict(NOTE,size_width=156,size_height=103))
        self.assertEqual(native_calls, [])
        self.assertEqual(len(calls), 1)
        self.assertEqual(result['serial_number'], 'C136027')

    def test_native_unavailable_or_failed_extraction_does_not_retry_or_lose_direct_facts(self):
        native_calls = []
        result, calls = self.call([response(dict(serial_number='C136027'))],
            ticks=(100,101,110,112), search_key='synthetic-key', native_calls=native_calls,
            note=dict(NOTE,size_width=156,size_height=103))
        self.assertEqual(len(native_calls), 1)
        self.assertEqual(len(calls), 1)
        self.assertEqual(result['serial_number'], 'C136027')
        native = {URL:dict(title='Maldives 10 Rufiyaa P-5b', quotes=[FULL], document_text=FULL)}
        result, calls = self.call([response(dict(serial_number='C136027')), RuntimeError('extract unavailable')],
            ticks=(100,101,110,112), native=native, search_key='synthetic-key')
        self.assertEqual(len(calls), 2)
        self.assertEqual(result['serial_number'], 'C136027')
        self.assertEqual(result['_catalogue_sources'][URL]['document_text'], FULL)

    def test_unexpected_native_search_failure_preserves_first_direct_result(self):
        result, calls = self.call([response(dict(serial_number='C136027'))],
            ticks=(100,101,110,112), search_key='synthetic-key',
            native_error=RuntimeError('unexpected adapter failure'), note=dict(NOTE,size_width=156,size_height=103))
        self.assertEqual(len(calls), 1)
        self.assertEqual(result['serial_number'], 'C136027')

    def test_native_markdown_excerpt_has_same_literal_proof_rules_as_provider_fetch(self):
        document = FULL.replace('Printer: Bradbury Wilkinson.', '**Printer:** Bradbury Wilkinson.')
        native = {URL:dict(title='Maldives 10 Rufiyaa P-5b', quotes=[document], document_text=document)}
        result, _ = self.call([response(), response(dict(catalogue_research=research()))],
            ticks=(100,101,110,112), native=native, search_key='synthetic-key')
        self.assertIn('printer', lookup.validate(NOTE, {}, result['catalogue_research'],
            result['_catalogue_sources'])['fields'])

    def test_no_search_sources_uses_existing_fetch_phase_without_creating_proof(self):
        second = dict(catalogue_research=research(), _catalogue_sources={URL:dict(document_text=FULL)})
        result, calls = self.call([response(), response(second)])
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[1]['tools'][0]['max_uses'], 4)
        self.assertEqual(calls[1]['timeout'], 65)
        prompt = calls[1]['messages'][0]['content']
        self.assertIn(lookup.BNI_COUNTRY_DIRECTORY, prompt)
        self.assertNotIn(URL, prompt)
        self.assertEqual(result['_catalogue_sources'], {})
        self.assertEqual(lookup.validate(NOTE, {}, result['catalogue_research'], {})['fields'], {})

    def test_configured_directory_accepts_only_actual_fetched_entry_proof(self):
        note_url = 'https://banknoteindex.com/browse.mhtml?browseBy=Id&browse=53893'
        claimed = dict(identity=dict(NOTE, reference='P-5b', match='exact'), fields={
            'size_width':dict(value=156,scope='type',source_url=note_url,quote='Width in mm | 156'),
            'size_height':dict(value=103,scope='type',source_url=note_url,quote='Height in mm | 103')})
        full = 'Maldives Government of the Maldives 10 Rufiyaa P-5b 1960. Width in mm | 156\nHeight in mm | 103'
        result, calls = self.call([response(), response(dict(catalogue_research=claimed), fetch_blocks(note_url,full))])
        validated = lookup.validate(NOTE, {}, result['catalogue_research'], result['_catalogue_sources'])
        self.assertEqual({k:p['value'] for k,p in validated['fields'].items()}, {'size_width':156,'size_height':103})
        self.assertNotIn(lookup.BNI_COUNTRY_DIRECTORY, result['_catalogue_sources'])
        self.assertEqual(len(calls), 2)

    def test_retrieval_diagnostics_have_counts_and_field_names_only(self):
        secret = 'PRIVATE-DIAGNOSTIC-MARKER'
        result = dict(catalogue_research={'identity':{'country':secret}, 'fields':{
            'printer':dict(value=secret,source_url='https://'+secret,quote=secret), secret:{}}})
        with self.assertLogs(stuff.app.logger, level='INFO') as captured:
            self.call([response(), response(result)], note=dict(NOTE,serial_number=secret,order_number=secret))
        summary = '\n'.join(captured.output)
        self.assertIn('native_sources=0 sources=0 candidates=1', summary)
        self.assertIn('fetch_attempted=True fetch_stop=end_turn fetch_failed=False claimed_fields=printer', summary)
        for forbidden in (secret, NOTE['country'], NOTE['pick_number'], 'https://', 'synthetic-key'):
            self.assertNotIn(forbidden, summary)


if __name__ == '__main__':
    unittest.main()
