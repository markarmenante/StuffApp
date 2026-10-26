"""Catalogue-assisted Check: exact cited variety, blank-only and concurrent edits."""
import copy
import os
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['DATA_DIR'] = tempfile.mkdtemp(prefix='stuff-catalog-check-')
os.environ.pop('ANTHROPIC_API_KEY', None)
import banknote_catalog_lookup as lookup
import banknote_catalog_proposals as proposals
import app as stuff

URL = 'https://en.numista.com/catalogue/note-example.html'
NOTE = dict(country='Maldives', pick_number='P-5b', denomination='10 Rufiyaa',
            issuer='Maldivian State (Government of the Maldives)', date_1=1960)
QUOTE = 'Maldives. Government of the Maldives. 10 Rufiyaa. P-5b. 1960. Printer: Bradbury Wilkinson. Size: 156 × 103 mm. Material: Paper.'


def research(note=None, quote=QUOTE):
    note = dict(NOTE if note is None else note)
    identity = {field: note.get(field) for field in lookup.IDENTITY_FIELDS}
    identity.update(match='exact', reference=note.get('pick_number'), variety_dates=[1960])
    return dict(identity=identity, fields={
        'printer': dict(value='Bradbury Wilkinson', scope='type', source_url=URL, quote=quote),
        'size_width': dict(value=156, scope='type', source_url=URL, quote=quote),
        'size_height': dict(value=103, scope='type', source_url=URL, quote=quote),
        'material': dict(value='Paper', scope='type', source_url=URL, quote=quote),
    })


def sources(*quotes):
    return {URL: dict(title='Catalogue', quotes=list(quotes or (QUOTE,)))}


class ValidationTests(unittest.TestCase):
    def test_saved_maldives_parenthetical_issuer_and_numeric_dimensions(self):
        result = lookup.validate(NOTE, {}, research(), sources())
        self.assertEqual(result['state'], 'ready')
        self.assertEqual({key: p['value'] for key, p in result['fields'].items()},
                         dict(printer='Bradbury Wilkinson', size_width=156., size_height=103., material='Paper'))

    def test_recovered_label_identity_works_for_blank_draft(self):
        self.assertEqual(lookup.validate({}, NOTE, research(), sources())['state'], 'ready')
        self.assertEqual(lookup.validate({}, {'country':'Maldives'}, research(), sources())['fields'], {})

    def test_all_countries_and_catalogue_namespaces_use_same_path(self):
        for country, number, issuer in [('Bermuda', 'P-14a', 'Bermuda Monetary Authority'),
                                       ('United States', 'Fr#652', 'City National Bank'),
                                       ('Seychelles', 'TBB B103b', 'Government of Seychelles')]:
            note = dict(NOTE, country=country, pick_number=number, issuer=issuer)
            quote = f'{country} {number} {issuer} 10 Rufiyaa 1960 Printer: Bradbury Wilkinson Size: 156 × 103 mm Material: Paper.'
            self.assertEqual(lookup.validate(note, {}, research(note, quote), sources(quote))['state'], 'ready')

    def test_exact_suffix_namespace_and_historical_country(self):
        for key, value in [('reference','P-5a'), ('reference','P-5'), ('reference','TBB B5b'), ('country','India')]:
            result = research(); result['identity'][key] = value
            self.assertEqual(lookup.validate(NOTE, {}, result, sources())['fields'], {})
        note = dict(NOTE, country='India')
        quote = QUOTE.replace('Maldives.', 'British India.', 1)
        self.assertEqual(lookup.validate(note, {}, research(note, quote), sources(quote))['fields'], {})

    def test_ref_parser_never_grades_serials_or_loses_specialist_hierarchy(self):
        for value in ('PMG64', 'PCGS 65', '64', 'S/N P12345', 'Certificate 12345'):
            self.assertIsNone(lookup.reference(value), value)
        self.assertEqual(lookup.reference('Pick#5b'), lookup.reference('P-5b'))
        self.assertNotEqual(lookup.reference('Grabowski Bi.7.5'), lookup.reference('Grabowski Bi.75'))
        self.assertNotEqual(lookup.reference('P-5b*'), lookup.reference('P-5b'))

    def test_actual_citations_and_literal_quotes_required(self):
        for src in ({}, {URL:dict(quotes=[])}, sources('Unrelated actual excerpt')):
            self.assertEqual(lookup.validate(NOTE, {}, research(), src)['fields'], {})
        result = research(); result['fields']['printer']['source_url'] = 'https://invented.example/no'
        self.assertNotIn('printer', lookup.validate(NOTE, {}, result, sources())['fields'])

    def test_variety_field_requires_own_exact_reference_date_context(self):
        identity = QUOTE
        for quote in ('P-5a 1947. Watermark: repeating patterns.', 'Watermark: repeating patterns.',
                      'P-5b 1947–1960. Watermark: repeating patterns.'):
            result = research(); result['fields'] = dict(watermark=dict(value='repeating patterns', scope='variety', source_url=URL, quote=quote))
            self.assertEqual(lookup.validate(NOTE, {}, result, sources(identity, quote))['fields'], {})
        quote = 'Maldives P-5b 1960. Watermark: repeating patterns.'
        result['fields']['watermark']['quote'] = quote
        self.assertIn('watermark', lookup.validate(NOTE, {}, result, sources(identity, quote))['fields'])

    def test_type_fact_cannot_borrow_identity_from_other_variety_paragraph(self):
        wrong = 'P-5a Printer: Bradbury Wilkinson.'
        result = research(); result['fields']['printer']['quote'] = wrong
        self.assertNotIn('printer', lookup.validate(NOTE, {}, result, sources(QUOTE, wrong))['fields'])

    def test_full_signer_names_must_occur_in_dated_variety_quote(self):
        quote = 'Maldives P-5b 1960. Signature: A. Didi.'
        result = research(); result['fields'] = dict(signatures=dict(value='Ahmed Didi', scope='variety', source_url=URL, quote=quote))
        self.assertEqual(lookup.validate(NOTE, {}, result, sources(QUOTE, quote))['fields'], {})
        result['fields']['signatures']['value'] = 'A. Didi'
        self.assertIn('signatures', lookup.validate(NOTE, {}, result, sources(QUOTE, quote))['fields'])
        result['fields']['signatures']['scope'] = 'type'
        self.assertEqual(lookup.validate(NOTE, {}, result, sources(QUOTE, quote))['fields'], {})

    def test_conflicting_saved_or_recovered_identity_never_researches_a_choice(self):
        for recovered in ({'pick_number':'P-5a'}, {'country':'Bermuda'}, {'date_1':1947}, {'issuer':'Other Bank'}):
            self.assertEqual(lookup.validate(NOTE, recovered, research(), sources())['fields'], {})
        for refs in ('P-5b, P-5a', 'P-5b, TBB B103a'):
            note = dict(NOTE, pick_number=refs)
            self.assertEqual(lookup.validate(note, {}, research(), sources())['fields'], {})

    def test_multiple_namespaces_require_cited_cross_reference(self):
        note = dict(NOTE, other_catalog='TBB B103b')
        quote = QUOTE + ' Cross reference TBB B103b.'
        result = research(note); result['identity']['reference'] = 'P-5b'
        self.assertEqual(lookup.validate(note, {}, result, sources(quote))['state'], 'ready')

    def test_occupied_direct_fields_and_protected_facts_never_catalogue_filled(self):
        result = research()
        for key in ('grade', 'grade_numeric', 'serial_number', 'slab_number', 'price', 'vendor', 'purchase_date', 'image_1', 'status', 'pick_number'):
            result['fields'][key] = dict(value='Paper', scope='type', source_url=URL, quote=QUOTE)
        note = dict(NOTE, printer='My printer', material='Unknown')
        fields = lookup.validate(note, {'size_width':155}, result, sources())['fields']
        self.assertEqual(set(fields), {'size_height'})

    def test_criswell_requires_exact_state_context(self):
        note = dict(NOTE, country='United States', issuer='Commonwealth of Virginia', pick_number='Cr-6')
        quote = 'United States Commonwealth of Virginia Cr-6 10 Rufiyaa 1960 Printer: Bradbury Wilkinson. Size:156 ×103mm. Paper.'
        result = research(note, quote)
        self.assertEqual(lookup.validate(note, {}, result, sources(quote))['fields'], {})
        result['identity']['state'] = 'Virginia'
        self.assertEqual(lookup.validate(note, {}, result, sources(quote))['state'], 'ready')
        result['identity']['state'] = 'Georgia'
        self.assertEqual(lookup.validate(note, {}, result, sources(quote))['fields'], {})

    def test_identity_date_text_is_not_ignored(self):
        note = dict(NOTE, date_1=None, date_1_text='1947')
        self.assertEqual(lookup.validate(note, {}, research(), sources())['fields'], {})

    def test_country_only_publisher_issuer_can_support_stable_pick_type(self):
        quote = QUOTE.replace('Government of the Maldives.', 'Issuer: Maldives.')
        self.assertEqual(lookup.validate(NOTE, {}, research(quote=quote), sources(quote))['state'], 'ready')
        quote = QUOTE.replace('Government of the Maldives.', 'Issuer: Central Bank of Maldives.')
        self.assertEqual(lookup.validate(NOTE, {}, research(quote=quote), sources(quote))['fields'], {})

    def test_uncertain_reference_and_alternative_signatures_remain_blank(self):
        note = dict(NOTE, pick_number='P-5b, possibly P-5c')
        self.assertEqual(lookup.validate(note, {}, research(), sources())['fields'], {})
        quote = 'Maldives P-5b 1960. Two signature combinations: Signer A or Signer B.'
        result = research(); result['fields'] = dict(signatures=dict(value='Signer A', scope='variety', source_url=URL, quote=quote))
        self.assertEqual(lookup.validate(NOTE, {}, result, sources(QUOTE, quote))['fields'], {})

    def test_sourced_history_uses_existing_condition_field_and_preserves_notes(self):
        quote = QUOTE + ' This denomination was issued in paper.'
        result = research(); result['fields'] = dict(history_context=dict(value='This denomination was issued in paper.', scope='type', source_url=URL, quote=quote))
        self.assertIn('condition', lookup.validate(NOTE, {}, result, sources(quote))['fields'])
        self.assertEqual(lookup.validate(dict(NOTE, condition='My existing history'), {}, result, sources(quote))['fields'], {})

    def test_direct_origin_flags_are_bound_to_actual_inputs(self):
        result = dict(printer='Direct Print', direct_evidence={'printer':{'source':'dealer', 'quote':'Printer: Direct Print'}})
        self.assertEqual(lookup.direct_fields(result, 'Printer: Direct Print', False), ['printer'])
        self.assertEqual(lookup.direct_fields(result, 'Different actual text', False), [])
        result['direct_evidence']['printer']['source'] = 'image'
        self.assertEqual(lookup.direct_fields(result, '', False), [])
        self.assertEqual(lookup.direct_fields(result, '', True), ['printer'])

    def test_provider_urls_without_native_cited_excerpts_are_not_field_proof(self):
        raw = {'content':[{'type':'web_search_tool_result','content':[{'type':'web_search_result','url':URL,'title':'Catalogue'}]},
                          {'type':'text','text':'invented quote','citations':[]}]}
        source, _ = lookup.actual_sources([raw])
        self.assertEqual(lookup.validate(NOTE, {}, research(), source)['fields'], {})
        raw['content'][1]['citations'] = [{'type':'web_search_result_location','url':URL,'cited_text':QUOTE}]
        source, _ = lookup.actual_sources([raw])
        self.assertEqual(lookup.validate(NOTE, {}, research(), source)['state'], 'ready')

    def test_dimension_evidence_preserves_decimal_precision(self):
        quote = QUOTE.replace('156 × 103', '156.5 × 103.2')
        result = research(quote=quote)
        self.assertNotIn('size_width', lookup.validate(NOTE, {}, result, sources(quote))['fields'])
        result['fields']['size_width']['value'] = 156.5
        self.assertEqual(lookup.validate(NOTE, {}, result, sources(quote))['fields']['size_width']['value'], 156.5)

    def test_search_plan_is_generic_exact_and_does_not_restrict_old_url_layout(self):
        prompt = lookup.prompt(NOTE)
        self.assertIn('site:numista.com Maldives 10 1960 banknote', prompt)
        self.assertIn('Maldives Pick 5b banknote', prompt)
        self.assertIn('site:banknoteindex.com Maldives P5b', prompt)
        self.assertNotIn('site:numista.com/catalogue', prompt)
        self.assertIn('Bermuda Pick 14a banknote',
                      lookup.prompt(dict(NOTE, country='Bermuda', pick_number='P-14a')))

    def test_banknote_index_zero_padded_pick_and_labelled_dimensions(self):
        self.assertEqual(lookup.reference('P-0005b'), lookup.reference('P5b'))
        self.assertNotEqual(lookup.reference('P-0005a'), lookup.reference('P5b'))
        quote = QUOTE.replace('P-5b', 'P-0005b').replace('Size: 156 × 103 mm', 'Width in mm | 156. Height in mm | 103')
        result = lookup.validate(NOTE, {}, research(quote=quote), sources(quote))
        self.assertEqual(result['fields']['size_width']['value'], 156)
        self.assertEqual(result['fields']['size_height']['value'], 103)

    def test_fetch_prefers_real_country_catalogue_over_similarly_numbered_coin(self):
        index = 'https://www.atsnotes.com/catalog/banknotes/seychelles.html'
        candidates = {
            'https://en.numista.com/catalogue/pieces20575.html': dict(title='5 Cents - Seychelles', quotes=[]),
            'https://en.numista.com/20575': dict(title='5 Cents - Seychelles', quotes=[]),
            index: dict(title='Seychelles banknotes - paper money catalog', quotes=[]),
        }
        note = dict(country='Seychelles', denomination='5 Rupees', pick_number='P-14a')
        self.assertEqual(lookup.fetch_candidates(note, {}, candidates), [index])

    def test_fetched_document_overcomes_truncated_search_citations(self):
        note = dict(country='Seychelles', pick_number='P-14a', denomination='5 Rupees',
                    issuer='Government of Seychelles', date_1=1968)
        full = '# 5 Rupees - Seychelles\n**Issuer**: Seychelles Seychelles\n**Size**: 134 × 70 mm\nDate | References\n1968 | P#14a\n'
        source, _ = lookup.actual_sources([{'content':[
            {'type':'web_fetch_tool_result','content':{'type':'web_fetch_result','url':URL,
              'content':{'type':'document','title':'5 Rupees - Seychelles','source':{'type':'text','data':full}}}},
        ]}])
        result = research(note); result['fields'] = {
            field:dict(value=value,scope='type',source_url=URL,quote='Size: 134 × 70 mm')
            for field,value in [('size_width',134),('size_height',70)]}
        self.assertEqual(set(lookup.validate(note, {}, result, source)['fields']), {'size_width','size_height'})
        result['fields']['size_width']['quote'] = 'Size: 135 × 70 mm'
        self.assertNotIn('size_width', lookup.validate(note, {}, result, source)['fields'])

    def test_fetch_error_and_model_document_claim_are_not_actual_source(self):
        fake = {'content':[{'type':'text','text':json.dumps({'document_text':QUOTE,'url':URL})},
            {'type':'web_fetch_tool_result','content':{'type':'web_fetch_tool_result_error','error_code':'url_not_accessible'}}]}
        self.assertEqual(lookup.actual_sources([fake])[0], {})

    def test_provider_request_is_one_bounded_search_fetch_budget(self):
        raw = dict(catalogue_research=research(), printer='Uncited model guess', _catalogue_direct_fields=['printer'])
        response = SimpleNamespace(stop_reason='end_turn',
            content=[SimpleNamespace(type='text',text=json.dumps(raw))],
            model_dump=lambda: {'content':[{'type':'text','text':json.dumps(raw)}]})
        with patch('anthropic.Anthropic') as factory, \
                patch.object(stuff, '_require_anthropic_key', return_value='test-not-a-secret'), \
                patch.object(stuff, 'anthropic_lookup_model', return_value='configured-model'), \
                patch.object(stuff, 'anthropic_web_search_tool', return_value={'type':'web_search_20250305','name':'web_search','max_uses':4}), \
                patch.object(stuff, '_load_vision_images', return_value=[]):
            factory.return_value.messages.create.return_value = response
            result = stuff.fetch_banknote_specs(NOTE)
            self.assertEqual(result['_catalogue_direct_fields'], [])
            self.assertEqual(result['_catalogue_sources'], {})
            self.assertEqual(factory.return_value.messages.create.call_count, 1)
            args = factory.return_value.messages.create.call_args.kwargs
            self.assertLessEqual(args['timeout'], 75)
            self.assertNotIn('web_fetch', [tool['name'] for tool in args['tools']])
            fetch = lookup.web_fetch_tool()
            self.assertEqual(fetch['max_uses'], lookup.MAX_FETCHES)
            self.assertEqual(fetch['max_content_tokens'], 12000)
            self.assertEqual(factory.call_args.kwargs['max_retries'], 0)

    def test_catalogue_dimensions_cannot_swap_axes(self):
        result = research()
        result['fields']['size_width']['value'] = 103
        result['fields']['size_height']['value'] = 156
        self.assertEqual(set(lookup.validate(NOTE, {}, result, sources())['fields']), {'printer','material'})

    def test_presentation_prefixes_do_not_require_invented_source_words(self):
        quote = QUOTE + ' Queen Elizabeth II at right. FIVE RUPEES.'
        result = research(); result['fields'] = {
            'obv_rev':dict(value='Obv: Queen Elizabeth II at right',scope='type',source_url=URL,quote=quote),
            'lettering':dict(value='Front: FIVE RUPEES',scope='type',source_url=URL,quote=quote)}
        self.assertEqual(set(lookup.validate(NOTE, {}, result, sources(quote))['fields']), {'obv_rev','lettering'})


class RouteTests(unittest.TestCase):
    def setUp(self):
        self.ctx = stuff.app.app_context(); self.ctx.push()
        self.db = stuff.get_db(); self.client = stuff.app.test_client()
        self.db.execute('DELETE FROM banknotes')
        self.db.execute('INSERT INTO banknotes(id,country,pick_number,denomination,issuer,date_1,price,serial_number,image_1) VALUES(?,?,?,?,?,?,?,?,?)',
            ('check', NOTE['country'], NOTE['pick_number'], NOTE['denomination'], NOTE['issuer'], NOTE['date_1'], '$199.99', 'C136027', 'manual-crop.jpg'))
        self.db.commit()

    def tearDown(self):
        self.ctx.pop()

    def row(self):
        return dict(self.db.execute("SELECT * FROM banknotes WHERE id='check'").fetchone())

    def check(self, result=None, error=None):
        result = result if result is not None else dict(catalogue_research=research(), _catalogue_sources=sources())
        prepared = dict(evidence=[], reports=[], documents=[], warnings=[], images={})
        with patch.object(stuff.ebay_purchase_lookup, 'ensure', return_value=None), \
                patch.object(stuff.banknote_check_sources, 'prepare', return_value=prepared), \
                patch.object(stuff, 'ensure_country_history'), \
                patch.object(stuff, 'fetch_banknote_specs', return_value=result, side_effect=error):
            return self.client.post('/banknotes/check/lookup-specs')

    def test_lookup_returns_separate_evidence_guard_and_never_updates_type_fields(self):
        before = self.row()
        data = self.check().get_json()
        self.assertEqual(data['catalogue']['state'], 'ready')
        self.assertEqual(data['filled']['size_width'], 156)
        self.assertEqual(data['catalogue']['guard']['identity'], lookup.identity_snapshot(before))
        self.assertIsNone(data['expected_values']['printer'])
        after = self.row()
        self.assertEqual({k:v for k,v in before.items() if k != 'specs_searched_at'},
                         {k:v for k,v in after.items() if k != 'specs_searched_at'})

    def test_apply_catalogue_fills_with_guard_and_preserves_item_facts(self):
        data = self.check().get_json(); before = self.row()
        response = self.client.post('/banknotes/check/apply-lookup-specs', json=dict(updates=data['filled'],
            catalogue_guard=data['catalogue']['guard'], expected_values=data['expected_values']))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['accepted_values']['printer'], 'Bradbury Wilkinson')
        after = self.row()
        for key in ('price','serial_number','image_1','country','pick_number','issuer','date_1'):
            self.assertEqual(after[key], before[key], key)

    def test_apply_skips_concurrent_target_edit(self):
        data = self.check().get_json()
        self.db.execute("UPDATE banknotes SET printer='My edit' WHERE id='check'"); self.db.commit()
        result = self.client.post('/banknotes/check/apply-lookup-specs', json=dict(updates=data['filled'],
            catalogue_guard=data['catalogue']['guard'], expected_values=data['expected_values'])).get_json()
        self.assertIn('printer', result['skipped_fields'])
        self.assertEqual(self.row()['printer'], 'My edit')
        self.assertEqual(self.row()['size_width'], 156)

    def test_apply_skips_all_catalogue_fields_on_identity_change(self):
        data = self.check().get_json()
        self.db.execute("UPDATE banknotes SET pick_number='P-5a' WHERE id='check'"); self.db.commit()
        result = self.client.post('/banknotes/check/apply-lookup-specs', json=dict(updates=data['filled'],
            catalogue_guard=data['catalogue']['guard'], expected_values=data['expected_values'])).get_json()
        self.assertEqual(result['accepted_values'], {})
        self.assertIsNone(self.row()['printer'])

    def test_empty_draft_identity_and_direct_fills_share_atomic_apply(self):
        self.db.execute("UPDATE banknotes SET country=NULL,pick_number=NULL,issuer=NULL,date_1=NULL,denomination=NULL WHERE id='check'"); self.db.commit()
        before = self.row()
        guard = dict(identity=lookup.identity_snapshot(before), fields=['printer'])
        guard['proposal_id'] = proposals.create(self.db, 'check', guard['identity'],
            {'printer':research()['fields']['printer']}, recovered=NOTE)
        self.db.commit()
        updates = dict(NOTE, printer='Bradbury Wilkinson')
        result = self.client.post('/banknotes/check/apply-lookup-specs', json=dict(updates=updates,
            catalogue_guard=guard, expected_values={key: before.get(key) for key in updates})).get_json()
        self.assertEqual(result['accepted_values']['printer'], 'Bradbury Wilkinson')
        self.assertEqual(self.row()['pick_number'], 'P-5b')

    def test_draft_recovered_identity_cannot_be_omitted_or_changed_at_apply(self):
        self.db.execute("UPDATE banknotes SET country=NULL,pick_number=NULL,issuer=NULL,date_1=NULL,denomination=NULL WHERE id='check'"); self.db.commit()
        before = self.row()
        guard = dict(identity=lookup.identity_snapshot(before), fields=['printer'])
        guard['proposal_id'] = proposals.create(self.db, 'check', guard['identity'],
            {'printer':research()['fields']['printer']}, recovered=NOTE)
        self.db.commit()
        for identity in ({}, dict(NOTE, country='Bermuda')):
            updates = dict(identity, printer='Bradbury Wilkinson')
            with patch.object(stuff, 'ensure_country_history'):
                result = self.client.post('/banknotes/check/apply-lookup-specs', json=dict(updates=updates,
                    catalogue_guard=guard, expected_values={key:before.get(key) for key in updates})).get_json()
            self.assertNotIn('printer', result['accepted_values'])
            self.assertIsNone(self.row()['printer'])

    def test_accepted_sources_append_latest_reference_notes_and_survive_reload(self):
        self.db.execute("UPDATE banknotes SET note_references_research='My original research' WHERE id='check'"); self.db.commit()
        data = self.check().get_json()
        # A manual note saved while research was pending must be preserved.
        self.db.execute("UPDATE banknotes SET note_references_research='My original research\nA newer manual note' WHERE id='check'"); self.db.commit()
        response = self.client.post('/banknotes/check/apply-lookup-specs', json=dict(updates=data['filled'],
            catalogue_guard=data['catalogue']['guard'], expected_values=data['expected_values'])).get_json()
        notes = self.row()['note_references_research']
        self.assertTrue(notes.startswith('My original research\nA newer manual note\n\nCatalogue Check type evidence'))
        self.assertIn('Maldives · P-5b', notes)
        self.assertIn(URL, notes)
        self.assertIn(QUOTE, notes)
        self.assertEqual(response['accepted_values']['note_references_research'], notes)
        proofs = self.db.execute('SELECT field,quote,source_url,accepted_value_json FROM banknote_catalog_proposal_fields WHERE accepted_at IS NOT NULL').fetchall()
        self.assertEqual({r['field'] for r in proofs}, set(data['catalogue']['fields']))
        self.assertTrue(all(r['quote'] == QUOTE and r['source_url'] == URL for r in proofs))
        with patch.object(stuff, 'ensure_country_history'):
            rendered = self.client.get('/banknotes/check').get_data(as_text=True)
        self.assertIn('Catalogue Check type evidence', rendered)
        self.assertIn('My original research', rendered)

    def test_skipped_field_never_gets_an_accepted_source_claim(self):
        data = self.check().get_json()
        self.db.execute("UPDATE banknotes SET printer='My printer' WHERE id='check'"); self.db.commit()
        self.client.post('/banknotes/check/apply-lookup-specs', json=dict(updates=data['filled'],
            catalogue_guard=data['catalogue']['guard'], expected_values=data['expected_values']))
        self.assertNotIn('- Printer:', self.row()['note_references_research'])
        proof = self.db.execute("SELECT accepted_at FROM banknote_catalog_proposal_fields WHERE field='printer'").fetchone()
        self.assertIsNone(proof[0])

    def test_missing_fabricated_expired_or_altered_proposal_never_fills(self):
        data = self.check().get_json()
        for mode in ('missing', 'fabricated', 'expired', 'altered'):
            guard = copy.deepcopy(data['catalogue']['guard'])
            updates = dict(data['filled'])
            if mode == 'missing':
                guard.pop('proposal_id')
            elif mode == 'fabricated':
                guard['proposal_id'] = 'not-issued-by-server'
            elif mode == 'expired':
                self.db.execute('UPDATE banknote_catalog_proposals SET expires_at=0'); self.db.commit()
            else:
                self.db.execute('UPDATE banknote_catalog_proposals SET expires_at=9999999999'); self.db.commit()
                updates = {'printer':'Unverified changed printer'}
            result = self.client.post('/banknotes/check/apply-lookup-specs', json=dict(updates=updates,
                catalogue_guard=guard, expected_values=data['expected_values'])).get_json()
            self.assertEqual(result['accepted_values'], {}, mode)
            self.assertIsNone(self.row()['printer'])
            self.assertFalse(self.row()['note_references_research'])

    def test_repeated_apply_does_not_duplicate_evidence_and_cleanup_retains_acceptance(self):
        data = self.check().get_json()
        payload = dict(updates=data['filled'], catalogue_guard=data['catalogue']['guard'], expected_values=data['expected_values'])
        self.client.post('/banknotes/check/apply-lookup-specs', json=payload)
        notes = self.row()['note_references_research']
        result = self.client.post('/banknotes/check/apply-lookup-specs', json=payload).get_json()
        self.assertEqual(result['accepted_values'], {})
        self.assertEqual(self.row()['note_references_research'], notes)
        self.db.execute('UPDATE banknote_catalog_proposals SET expires_at=0'); self.db.commit()
        proposals.create(self.db, 'check', lookup.identity_snapshot(self.row()), {})
        self.db.commit()
        self.assertEqual(self.db.execute('SELECT count(*) FROM banknote_catalog_proposal_fields WHERE accepted_at IS NOT NULL').fetchone()[0], len(data['filled']))

    def test_failed_research_keeps_purchase_description_path(self):
        self.db.execute("UPDATE banknotes SET description='My Cost: $199.99; Printer: Direct Print' WHERE id='check'"); self.db.commit()
        data = self.check(error=RuntimeError('Search unavailable')).get_json()
        self.assertEqual(data.get('catalogue', {}).get('state'), 'unavailable')
        self.assertEqual(self.row()['price'], '$199.99')
        self.assertEqual(self.row()['image_1'], 'manual-crop.jpg')

    def test_no_uncited_dimension_provider_fallback(self):
        with patch.object(stuff, '_require_anthropic_key', side_effect=AssertionError('No secondary provider call')):
            self.assertIsNone(stuff._banknote_dims_scan_or_lookup(NOTE, ''))
            self.assertEqual(stuff._banknote_dims_scan_or_lookup(NOTE, '156 x 103 mm'), (156.,103.))

    def test_deleted_record_cannot_be_recreated_by_apply(self):
        data = self.check().get_json()
        self.db.execute("DELETE FROM banknotes WHERE id='check'"); self.db.commit()
        self.assertEqual(self.client.post('/banknotes/check/apply-lookup-specs', json=dict(updates=data['filled'],
            catalogue_guard=data['catalogue']['guard'])).status_code, 404)

    def test_top_level_web_guesses_cannot_bypass_unresolved_catalogue(self):
        result = dict(printer='Invented web printer', watermark='Arms from 1983', size_width=156, size_height=103,
                      history_context='Guessed context', catalogue_research={'identity':{'match':'unresolved'},'fields':{}},
                      _catalogue_sources={})
        data = self.check(result).get_json()
        self.assertEqual(data['filled'], {})
        self.assertEqual(data['overwritten'], {})

    def test_validated_direct_metadata_keeps_existing_photo_check(self):
        result = dict(printer='Visible Printer', _catalogue_sources={}, _catalogue_direct_fields=['printer'])
        data = self.check(result).get_json()
        self.assertEqual(data['filled']['printer'], 'Visible Printer')
        self.assertEqual(data['catalogue']['fields'], {})

    def test_ordinary_review_expected_values_protect_concurrent_edits(self):
        response = self.client.post('/banknotes/check/apply-lookup-specs', json=dict(
            updates={'price':'$200.01', 'printer':'Proposed'}, expected_values={'price':'$10', 'printer':None})).get_json()
        self.assertEqual(self.row()['price'], '$199.99')
        self.assertEqual(self.row()['printer'], 'Proposed')
        self.assertEqual(response['skipped_fields'], ['price'])


if __name__ == '__main__':
    unittest.main()
