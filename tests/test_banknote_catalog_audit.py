"""Standalone catalogue audit: no production imports, network or source image edits."""
import copy
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import banknote_catalog_audit as audit

URL = 'https://example.org/catalogue/exact-note'
QUOTE = 'Tonga 1 Pound 1966 Pick P-7, TBB B301. Printed by De La Rue. Size 150 by 80 mm.'


def raw_response(result=None, quote=QUOTE):
    return {'id': 'fixture-message', 'stop_reason': 'end_turn', 'usage': {'input_tokens': 100, 'output_tokens': 50},
            'content': [{'type': 'server_tool_use', 'name': 'web_search', 'id': 'search-1', 'input': {'query': 'fixture'}},
                        {'type': 'web_search_tool_result', 'content': [{'type': 'web_search_result', 'url': URL, 'title': 'Exact note', 'encrypted_content': 'fixture'}]},
                        {'type': 'text', 'text': json.dumps(result or {}), 'citations': [{'type': 'web_search_result_location', 'url': URL, 'cited_text': quote, 'title': 'Exact note'}]}]}


def proof(**values):
    return {'confidence': 'high', 'source_urls': [URL], 'reason': 'Exact catalogue issue, issuer and variety established in the cited source.', **values}


def result_for(row):
    return {'identity': proof(record_id=row['id'], match='exact', confirmed={k: row.get(k) for k in ('country','denomination','issuer','date_1','date_1_text') if row.get(k) not in (None, '')}, variety_basis='The image and exact Pick variety agree on the signature combination.'),
            'catalogue_refs': [proof(catalogue='Pick', reference='P-7'), proof(catalogue='TBB', reference='TBB B301')],
            'corrections': [], 'type_fields': {'printer': proof(value='De La Rue')}, 'unresolved': ''}


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='catalogue-audit-test-')
        self.root = Path(self.temp.name)
        self.run = self.root/'audit-run'
        self.database = self.root/'stuffapp.db'
        self.env = patch.dict(os.environ, {'RAILWAY_SERVICE_NAME': 'web', 'STUFFAPP_OWNER_EMAIL': 'owner@example.test'})
        self.env.start()
        columns = set(audit.ALLOWED) | set(audit.IDENTITY_FIELDS) | {audit.SOURCE_NOTES,'id','cat_id','updated_at','status','price','serial_number','grade','slab_number','owner','image_1','image_2','description','note_references','notes'}
        db = sqlite3.connect(self.database)
        db.execute('CREATE TABLE users(email TEXT,role TEXT)')
        db.execute("INSERT INTO users VALUES ('owner@example.test','owner')")
        db.execute('CREATE TABLE banknotes (' + ','.join('"'+c+'" '+('REAL' if c in {'size_width','size_height'} else 'INTEGER' if c in {'date_1','date_2'} else 'TEXT') for c in sorted(columns)) + ')')
        values = {'id':'note-1','cat_id':'B001','country':'Tonga','denomination':'1 Pound','issuer':'Government of Tonga',
                  'date_1':1966,'date_1_text':'1966','pick_number':'P-7','updated_at':'2026-10-15T00:00:00',
                  'status':'Ordered','price':'$400','serial_number':'ABC123','grade':'65','slab_number':'CERT123',
                  'owner':'Owner','notes':'Personal inspection note','condition':'Personal history note'}
        db.execute('INSERT INTO banknotes ('+','.join(values)+') VALUES ('+','.join('?' for _ in values)+')', list(values.values()))
        db.commit(); db.close()
        audit.initialize(self.database,self.run,'owner@example.test')
        self.manifest,self.baseline=audit.checked_run(self.run,'owner@example.test')
        self.row=self.baseline['rows'][0]

    def tearDown(self):
        self.env.stop(); self.temp.cleanup()

    def proposal(self,result=None,quote=QUOTE):
        proposed=audit.validate_proposal(self.row,result or result_for(self.row),[raw_response(quote=quote)])
        entry={'record_id':self.row['id'],'baseline_record_sha256':audit.digest(self.row),**proposed}
        entry['proposal_sha256']=audit.digest(entry)
        audit.save_json(self.run/'notes'/'note-1.json',entry)
        return entry

    def approval(self,proposal,updates=None):
        updates=updates or proposal['updates']
        return {'run_id':self.manifest['run_id'],'baseline_sha256':self.manifest['baseline_sha256'],'approved':True,
                'records':[{'record_id':'note-1','proposal_sha256':proposal['proposal_sha256'],'updates':updates,
                            'identity_review':{'verified':True,'reason':'Read exact note source and compared the matching issuer, denomination and variety.'},
                            'research_review':{f:{'value':v,'source_url':URL,'supporting_quote':QUOTE,'identity_verified':True,
                                                'reason':'Independently reviewed exact source and confirmed this proposed field.'} for f,v in updates.items()}}]}

    def current(self):
        db=audit.connect(self.database)
        try:return dict(db.execute('SELECT * FROM banknotes').fetchone())
        finally:db.close()

    def test_import_has_no_app_initialization_and_backup_is_private(self):
        self.assertNotIn('app',sys.modules)
        self.assertEqual(self.current(),self.row)
        self.assertEqual((self.run/'backup.sqlite').stat().st_mode & 0o777,0o600)
        self.assertEqual(self.run.stat().st_mode & 0o777,0o700)
        with self.assertRaises(ValueError):audit.initialize(self.database,self.run,'owner@example.test')

    def test_wrong_tenant_and_tampered_baseline_rejected(self):
        with self.assertRaises(ValueError):audit.checked_run(self.run,'other@example.test')
        with patch.dict(os.environ,{'RAILWAY_SERVICE_NAME':'gerri'}):
            with self.assertRaises(ValueError):audit.checked_run(self.run,'owner@example.test')
        baseline=copy.deepcopy(self.baseline);baseline['rows'][0]['price']='$1'
        audit.save_json(self.run/'baseline.json',baseline)
        with self.assertRaises(ValueError):audit.checked_run(self.run,'owner@example.test')

    def test_catalogue_append_preserves_existing_specialist_exact_text(self):
        row=dict(self.row,pick_number='P-111a*, SB2229r, RH16')
        result=result_for(row);result['catalogue_refs']=[proof(catalogue='TBB',reference='TBB B301')]
        proposed=audit.validate_proposal(row,result,[raw_response()])
        self.assertEqual(proposed['updates']['pick_number'],'P-111a*, SB2229r, RH16, TBB B301')

    def test_namespace_variety_and_marker_guards(self):
        self.assertEqual(audit.reference_key('Fr#1361'),audit.reference_key('Fr1361'))
        self.assertEqual(audit.reference_key('Pick P-110x'),audit.reference_key('P-110x'))
        self.assertNotEqual(audit.reference_key('P-110x'),audit.reference_key('P-110'))
        self.assertNotEqual(audit.reference_key('P-111a*'),audit.reference_key('P-111a'))
        self.assertIsNone(audit.reference_namespace('PA-170'))
        self.assertIsNone(audit.reference_namespace('PMG65'))
        with self.assertRaises(ValueError):audit.reference_key('PMG65','Pick')
        self.assertEqual(audit.reference_key('P-S123a'),'pick:s123a')
        self.assertEqual(audit.reference_key('P-50r1'),'pick:50r1')
        self.assertEqual(audit.reference_key('PA-170','Friedberg'),'friedberg:pa170')
        row=dict(self.row,pick_number='TBB B305a');result=result_for(row)
        result['catalogue_refs']=[proof(catalogue='TBB',reference='B305b')]
        proposed=audit.validate_proposal(row,result,[raw_response()])
        self.assertNotIn('pick_number',proposed['updates']);self.assertTrue(proposed['held'])
        result['catalogue_refs']=[proof(catalogue='Pick',reference='Fr1361')]
        proposed=audit.validate_proposal(row,result,[raw_response()])
        self.assertNotIn('pick_number',proposed['updates']);self.assertTrue(proposed['held'])

    def test_actual_search_required_and_fabricated_urls_rejected(self):
        result=result_for(self.row)
        with self.assertRaises(ValueError):audit.validate_proposal(self.row,result,[{'content':[{'type':'text','text':json.dumps(result)}]}])
        result['type_fields']['printer']['source_urls']=['https://invented.test/item']
        proposed=audit.validate_proposal(self.row,result,[raw_response()])
        self.assertNotIn('printer',proposed['allowed_values']);self.assertTrue(any(h.get('field')=='printer' for h in proposed['held']))
        result['identity']['source_urls']=['https://invented.test/identity']
        with self.assertRaises(ValueError):audit.validate_proposal(self.row,result,[raw_response()])

    def test_unrelated_quote_requires_explicit_review(self):
        proposal=self.proposal(quote='This page discusses a different paper item.')
        self.assertTrue(all(p['support']=='review_required' for p in proposal['field_evidence']['printer']))
        approval=self.approval(proposal);approval['records'][0].pop('research_review')
        with self.assertRaises(ValueError):audit.apply(self.run,'owner@example.test',approval)
        self.assertEqual(self.current(),self.row)

    def test_null_does_not_clear_and_unknown_does_not_mean_verified(self):
        result=result_for(self.row);result['type_fields']={'printer':None};result['catalogue_refs']=[]
        proposal=audit.validate_proposal(self.row,result,[raw_response()])
        self.assertEqual(proposal['updates'],{});self.assertEqual(proposal['state'],'unresolved')
        result['catalogue_refs']=[proof(catalogue='Pick',reference='P-7')]
        proposal=audit.validate_proposal(self.row,result,[raw_response()])
        self.assertEqual(proposal['state'],'verified_unchanged')

    def test_unsafe_fields_and_nonfinite_dimensions_rejected(self):
        for field,value in [('status','Own'),('grade','70'),('price','$1'),('serial_number','OTHER'),('image_1','new.jpg')]:
            result=result_for(self.row);result['type_fields']={field:proof(value=value)}
            with self.assertRaises(ValueError):audit.validate_proposal(self.row,result,[raw_response()])
        for value in [True,float('nan'),float('inf'),-1,0,1000]:
            result=result_for(self.row);result['type_fields']={'size_width':proof(value=value)}
            proposed=audit.validate_proposal(self.row,result,[raw_response()])
            self.assertNotIn('size_width',proposed['allowed_values']);self.assertTrue(any(h.get('field')=='size_width' for h in proposed['held']))

    def test_identity_conflict_is_reviewable_not_lost(self):
        result=result_for(self.row);result['identity']['confirmed']['date_1']=1967
        result['type_fields']={'date_1':proof(value=1967)}
        proposal=self.proposal(result)
        self.assertTrue(proposal['identity_review_required'])
        self.assertEqual(proposal['updates']['date_1_text'],'1967')
        approval=self.approval(proposal,{'date_1':1967})
        with self.assertRaises(ValueError):audit.apply(self.run,'owner@example.test',approval)
        approval=self.approval(proposal,{'date_1':1967,'date_1_text':'1967'})
        self.assertEqual(audit.apply(self.run,'owner@example.test',approval)['outcomes'][0]['state'],'applied')

    def test_explicit_undated_correction_pairs_numeric_clear_and_text(self):
        result=result_for(self.row);result['type_fields']={'date_1':proof(value=None,action='clear'),'date_1_text':proof(value='ND (1960-1968)')}
        proposal=self.proposal(result)
        self.assertIn(None,proposal['allowed_values']['date_1'])
        approval=self.approval(proposal,{'date_1':None,'date_1_text':'ND (1960-1968)'})
        self.assertEqual(audit.apply(self.run,'owner@example.test',approval)['outcomes'][0]['state'],'applied')
        self.assertIsNone(self.current()['date_1'])

    def test_apply_only_approved_values_and_preserves_every_other_column(self):
        proposal=self.proposal();approval=self.approval(proposal)
        result=audit.apply(self.run,'owner@example.test',approval)
        self.assertEqual(result['outcomes'][0]['state'],'applied')
        current=self.current()
        for key in self.row:
            if key not in proposal['updates'] and key!='updated_at':self.assertEqual(current[key],self.row[key],key)
        self.assertEqual(audit.apply(self.run,'owner@example.test',approval)['outcomes'][0]['state'],'already_applied')

    def test_approval_tamper_and_missing_identity_review_rejected(self):
        proposal=self.proposal();approval=self.approval(proposal)
        approval['records'][0]['updates']['price']='$1'
        with self.assertRaises(ValueError):audit.apply(self.run,'owner@example.test',approval)
        approval=self.approval(proposal);approval['records'][0].pop('identity_review')
        with self.assertRaises(ValueError):audit.apply(self.run,'owner@example.test',approval)
        proposal['updates']['printer']='Tampered';audit.save_json(self.run/'notes'/'note-1.json',proposal)
        with self.assertRaises(ValueError):audit.apply(self.run,'owner@example.test',self.approval(proposal))

    def test_stale_baseline_cannot_overwrite_user_edit(self):
        proposal=self.proposal();db=sqlite3.connect(self.database)
        db.execute("UPDATE banknotes SET status='Own'");db.commit();db.close()
        result=audit.apply(self.run,'owner@example.test',self.approval(proposal))
        self.assertEqual(result['outcomes'][0]['state'],'conflict')
        self.assertEqual(self.current()['status'],'Own');self.assertIsNone(self.current()['printer'])

    def test_rollback_is_guarded_and_reusable(self):
        proposal=self.proposal();audit.apply(self.run,'owner@example.test',self.approval(proposal))
        approval={'run_id':self.manifest['run_id'],'baseline_sha256':self.manifest['baseline_sha256'],'rollback_approved':True,'record_ids':['note-1']}
        self.assertEqual(audit.rollback(self.run,'owner@example.test',approval)['outcomes'][0]['state'],'rolled_back')
        self.assertEqual(self.current()['pick_number'],self.row['pick_number'])
        self.assertEqual(audit.rollback(self.run,'owner@example.test',approval)['outcomes'][0]['state'],'already_rolled_back')

    def test_rollback_refuses_post_apply_user_edit(self):
        proposal=self.proposal();audit.apply(self.run,'owner@example.test',self.approval(proposal))
        db=sqlite3.connect(self.database);db.execute("UPDATE banknotes SET notes='Later personal note'");db.commit();db.close()
        approval={'run_id':self.manifest['run_id'],'baseline_sha256':self.manifest['baseline_sha256'],'rollback_approved':True,'record_ids':['note-1']}
        self.assertEqual(audit.rollback(self.run,'owner@example.test',approval)['outcomes'][0]['state'],'conflict')
        self.assertEqual(self.current()['notes'],'Later personal note')

    def test_collect_persists_raw_without_mutating_source(self):
        public_result=result_for(self.row);public_result['identity']['record_id']=audit.PUBLIC_QUERY_TOKEN
        raw=raw_response(public_result)
        client=types.SimpleNamespace(messages=types.SimpleNamespace(create=lambda **kwargs:types.SimpleNamespace(model_dump=lambda **kwargs:raw)))
        manifest=dict(self.manifest,model='fixture-model')
        state=audit.collect_one(self.run,manifest,self.row,client)
        self.assertEqual(state,'proposed');self.assertEqual(self.current(),self.row)
        entry=audit.load_json(self.run/'notes'/'note-1.json')
        self.assertTrue((self.run/entry['raw_path']/'1.json').exists())
        attempt=audit.load_json(self.run/entry['raw_path']/'attempt.json')
        self.assertEqual(attempt['prompt'],audit.PROMPT)
        self.assertEqual(attempt['prompt_sha256'],entry['prompt_sha256'])
        self.assertEqual(audit.report(self.run)['provider_calls_all_attempts'],1)
        self.assertEqual(audit.collect(self.run,'owner@example.test')['states'],{'proposed':1})

    def test_search_tool_error_is_incomplete(self):
        raw=raw_response();raw['content'].append({'type':'web_search_tool_result','content':{'type':'web_search_tool_result_error','error_code':'rate_limit_error'}})
        proposal=audit.validate_proposal(self.row,result_for(self.row),[raw])
        self.assertEqual(proposal['state'],'incomplete')

    def test_post_commit_mirror_failure_does_not_claim_no_write(self):
        proposal=self.proposal();original=audit.save_json
        def save(path,value):
            if Path(path).parent.name=='applied':raise OSError('fixture disk failure')
            return original(path,value)
        with patch.object(audit,'save_json',side_effect=save):
            result=audit.apply(self.run,'owner@example.test',self.approval(proposal))
        self.assertEqual(result['outcomes'][0]['state'],'applied')
        self.assertIn('warning',result['outcomes'][0]);self.assertEqual(self.current()['printer'],'De La Rue')


    def test_conflicting_new_namespace_references_are_held(self):
        result=result_for(self.row)
        result['catalogue_refs']=[proof(catalogue='TBB',reference='TBB B301'),proof(catalogue='TBB',reference='TBB B302')]
        proposal=audit.validate_proposal(self.row,result,[raw_response()])
        self.assertNotIn('pick_number',proposal['updates'])
        self.assertEqual(len(proposal['held']),2)

    def test_text_date_cannot_leave_conflicting_year(self):
        for display in ['1947','ND (1947-49)','N.D. (1947-49)','Undated (1947-49)']:
            result=result_for(self.row);result['type_fields']={'date_1_text':proof(value=display)}
            proposal=self.proposal(result)
            with self.assertRaises(ValueError):audit.apply(self.run,'owner@example.test',self.approval(proposal))
            self.assertEqual(self.current(),self.row)

    def test_date_two_pair_and_clear_provenance(self):
        result=result_for(self.row);result['type_fields']={'date_2':proof(value=1968)}
        proposal=self.proposal(result)
        self.assertEqual(proposal['updates']['date_2_text'],'1968')
        self.assertEqual(audit.apply(self.run,'owner@example.test',self.approval(proposal))['outcomes'][0]['state'],'applied')
        sources,_=audit.actual_sources([raw_response()])
        evidence=audit.supported(audit.evidence(proof(),sources),None,sources)
        self.assertEqual(evidence['support'],'review_required')
        self.assertFalse(evidence['supporting_excerpts'])

    def test_blank_metadata_can_have_reviewed_image_identity_proposal(self):
        row={**self.row,'country':None,'denomination':None,'pick_number':None,'date_1':None,'date_1_text':None,'issuer':None}
        result=result_for(row);result['identity']['confirmed']={'country':'Guernsey','denomination':'10 Shillings','date_1':1966}
        result['catalogue_refs']=[proof(catalogue='Pick',reference='P-42c')]
        result['type_fields']={'country':proof(value='Guernsey'),'denomination':proof(value='10 Shillings')}
        proposal=audit.validate_proposal(row,result,[raw_response()])
        self.assertEqual(proposal['state'],'proposed');self.assertTrue(proposal['identity_review_required'])
        self.assertEqual(proposal['updates']['pick_number'],'P-42c')

    def test_expanded_type_fields_and_aggregate_journal_failure(self):
        result=result_for(self.row);result['type_fields']={
            'official':proof(value='Portrait at right; allegorical figure at left'),
            'obv_rev':proof(value='Royal arms on the reverse'),
            'size_width':proof(value=150),'size_height':proof(value=80),
            'lettering':proof(value='ONE POUND'),'lettering_translation':proof(value='One pound'),
            'history_context':proof(value='Catalogue type historical context')}
        proposal=self.proposal(result);original=audit.save_json
        def save(path,value):
            if Path(path).parent.name=='apply-results':raise OSError('fixture disk failure')
            return original(path,value)
        with patch.object(audit,'save_json',side_effect=save):
            outcome=audit.apply(self.run,'owner@example.test',self.approval(proposal))
        self.assertEqual(outcome['outcomes'][0]['state'],'applied');self.assertIn('warning',outcome)
        self.assertEqual(self.current()['size_width'],150)
        self.assertEqual(self.current()['condition'],self.row['condition'])


    def test_personal_history_notes_are_fill_only(self):
        result=result_for(self.row);result['type_fields']={'condition':proof(value='Sourced catalogue type history')}
        proposal=self.proposal(result)
        self.assertNotIn('condition',proposal['allowed_values'])
        self.assertTrue(any(h.get('field')=='condition' for h in proposal['held']))
        approval=self.approval(proposal,{'condition':'Sourced catalogue type history'})
        with self.assertRaises(ValueError):audit.apply(self.run,'owner@example.test',approval)
        empty={**self.row,'condition':None}
        proposed=audit.validate_proposal(empty,result_for(empty)|{'type_fields':result['type_fields']},[raw_response()])
        self.assertEqual(proposed['updates']['condition'],'Sourced catalogue type history')


    def test_public_request_excludes_private_values_images_and_identifiers_across_continuation(self):
        private={**self.row, 'id':'note-1','cat_id':'PRIVATE-COLLECTION-ID',
                 'image_1':'PRIVATE-IMAGE-FRONT.jpg','image_2':'PRIVATE-IMAGE-BACK.jpg',
                 'description':'PRIVATE-DESCRIPTION','condition':'PRIVATE-HISTORY',
                 'history_context':'PRIVATE-HISTORY-CONTEXT','serial_number':'PRIVATE-SERIAL',
                 'slab_number':'PRIVATE-CERT','price':'PRIVATE-PRICE','order_id':'PRIVATE-ORDER',
                 'status':'PRIVATE-STATUS','grade':'PRIVATE-GRADE','notes':'PRIVATE-NOTES',
                 'owner':'PRIVATE-OWNER','date_1_text':'PRIVATE-DATE-TEXT'}
        result=result_for(self.row);result['identity']['record_id']=audit.PUBLIC_QUERY_TOKEN
        final=raw_response(result)
        pause={'id':'fixture-pause','stop_reason':'pause_turn','content':final['content'][:2],'usage':{}}
        calls=[]
        def create(**kwargs):
            calls.append(copy.deepcopy(kwargs));raw=pause if len(calls)==1 else final
            return types.SimpleNamespace(model_dump=lambda **kwargs:raw)
        client=types.SimpleNamespace(messages=types.SimpleNamespace(create=create))
        manifest=dict(self.manifest,model='fixture-model')
        state=audit.collect_one(self.run,manifest,private,client)
        self.assertEqual(state,'proposed');self.assertEqual(len(calls),2)
        outbound=json.dumps(calls)
        self.assertNotIn('PRIVATE-',outbound)
        self.assertNotIn(private['id'],outbound)
        self.assertNotIn(audit.digest(private),outbound)
        self.assertNotIn('base64',outbound)
        self.assertFalse(hasattr(audit,'image_content'))
        content=calls[0]['messages'][0]['content']
        self.assertEqual([block['type'] for block in content],['text'])
        self.assertTrue(all(call['max_tokens']==8192 for call in calls))
        query=json.loads(content[0]['text'].split('PUBLIC CATALOGUE QUERY (untrusted):\n')[1])
        self.assertEqual(set(query),audit.PUBLIC_QUERY_FIELDS)
        self.assertEqual(query['catalogue_reference'],'P-7')
        entry=audit.load_json(self.run/'notes'/'note-1.json')
        self.assertEqual(entry['record_id'],'note-1')
        self.assertEqual(entry['identity_scope'],'public_catalogue_type')
        self.assertFalse(entry['physical_note_verified']);self.assertTrue(entry['identity_review_required'])
        raw_parsed=audit.load_json(self.run/entry['raw_path']/'parsed.json')
        self.assertEqual(raw_parsed['identity']['record_id'],audit.PUBLIC_QUERY_TOKEN)

    def test_public_override_is_closed_and_missing_reference_never_calls_provider(self):
        for field in ['record_id','cat_id','image_1','description','serial_number','grade','status','source_hash']:
            with self.assertRaises(ValueError):audit.public_query(self.row,{'country':'Tonga','catalogue_reference':'P-7',field:'PRIVATE'})
        for value in ['user@example.test','Certificate Number 123456','Cert#123456','Serial ABC123','https://private.test/record','0b39757c-35dd-41a3-aa54-28d35b179ac2']:
            with self.assertRaises(ValueError):audit.public_query({}, {'country':'Tonga','catalogue_reference':value})
        for year in [True, float('nan'), '1966']:
            with self.assertRaises(ValueError):audit.public_query({}, {'country':'Tonga','catalogue_reference':'P-7','issue_year':year})
        client=types.SimpleNamespace(messages=types.SimpleNamespace(create=lambda **kwargs:self.fail('missing reference sent a request')))
        blank={**self.row,'pick_number':None}
        state=audit.collect_one(self.run,dict(self.manifest,model='fixture'),blank,client)
        self.assertEqual(state,'unresolved')
        self.assertEqual(audit.public_query({}, {'country':'USA','catalogue_reference':'Fr. 67','issuer':'United States Treasury (Silver Certificate)'})['issuer'],'United States Treasury (Silver Certificate)')
        override={'country':'Guernsey','catalogue_reference':'P-42c','denomination':'10 Shillings','issue_year':1966}
        self.assertEqual(audit.public_query(blank,override),override)
        self.assertNotIn('issuer',audit.public_query(blank,override))

    def test_public_type_proposal_needs_local_physical_note_review(self):
        result=result_for(self.row);result['identity']['record_id']=audit.PUBLIC_QUERY_TOKEN
        client=types.SimpleNamespace(messages=types.SimpleNamespace(create=lambda **kwargs:types.SimpleNamespace(model_dump=lambda **kwargs:raw_response(result))))
        audit.collect_one(self.run,dict(self.manifest,model='fixture'),self.row,client)
        proposal=audit.load_json(self.run/'notes'/'note-1.json');approval=self.approval(proposal)
        with self.assertRaises(ValueError):audit.apply(self.run,'owner@example.test',approval)
        approval['records'][0]['identity_review'].update(review_basis='local_specimen_evidence',physical_note_verified=True)
        self.assertEqual(audit.apply(self.run,'owner@example.test',approval)['outcomes'][0]['state'],'applied')

    def test_public_query_mode_bounds_worker_count_without_provider(self):
        self.proposal()
        self.assertEqual(audit.collect(self.run,'owner@example.test',workers=4)['states'],{'proposed':1})
        with self.assertRaises(ValueError):audit.collect(self.run,'owner@example.test',workers=5)
        with self.assertRaises(ValueError):audit.collect(self.run,'owner@example.test',public_queries={'wrong-record':{'country':'Tonga','catalogue_reference':'P-7'}})


    def test_new_specialist_reference_is_selectable_only_after_explicit_review(self):
        result=result_for(self.row);result['catalogue_refs']=[proof(catalogue='Tan',reference='Tan SKR3c')]
        result['type_fields']={}
        proposal=self.proposal(result)
        candidate='P-7, Tan SKR3c'
        self.assertNotIn('pick_number',proposal['updates'])
        self.assertIn(candidate,proposal['allowed_values']['pick_number'])
        self.assertEqual(proposal['held'][0]['candidate'],candidate)
        approval=self.approval(proposal,{'pick_number':candidate})
        approval['records'][0].pop('research_review')
        with self.assertRaises(ValueError):audit.apply(self.run,'owner@example.test',approval)
        approval=self.approval(proposal,{'pick_number':candidate})
        self.assertEqual(audit.apply(self.run,'owner@example.test',approval)['outcomes'][0]['state'],'applied')


    def test_low_confidence_or_malformed_fields_do_not_discard_supported_research(self):
        result=result_for(self.row)
        result['type_fields'].update({'watermark':proof(value='Unknown',confidence='medium'),
                                     'size_width':proof(value='150–155 mm'),
                                     'size_height':proof(value='80.0'), 'date_2':proof(value='1968')})
        result['catalogue_refs'].append(proof(catalogue='Pick',reference='P-99',confidence='low'))
        result['corrections']=[proof(existing_reference='NOT-SAVED',replacement='P-10')]
        proposal=audit.validate_proposal(self.row,result,[raw_response()])
        self.assertEqual(proposal['updates']['printer'],'De La Rue')
        self.assertEqual(proposal['updates']['size_height'],80.0)
        self.assertEqual(proposal['updates']['date_2'],1968)
        self.assertNotIn('watermark',proposal['allowed_values']);self.assertNotIn('size_width',proposal['allowed_values'])
        self.assertGreaterEqual(len(proposal['held']),4)
        result['identity']['confidence']='medium'
        with self.assertRaises(ValueError):audit.validate_proposal(self.row,result,[raw_response()])

    def test_numeric_string_conversion_is_exact_and_never_infers_units_or_ranges(self):
        self.assertEqual(audit.field_value('date_1',{'value':'1918'}),1918)
        self.assertEqual(audit.field_value('size_width',{'value':'150.25'}),150.25)
        for value in ['1918-1920','1918 AD','ND (1918)','1918.0','1.918e3']:
            with self.assertRaises(ValueError):audit.field_value('date_1',{'value':value})
        for value in ['150 mm','150,5','1.5e2','150 / 80','NaN','-150','150.12345']:
            with self.assertRaises(ValueError):audit.field_value('size_width',{'value':value})

    def test_completed_raw_can_be_revalidated_without_provider_or_source_write(self):
        result=result_for(self.row);result['identity']['record_id']=audit.PUBLIC_QUERY_TOKEN
        result['type_fields']['watermark']=proof(value='Unknown',confidence='medium')
        calls=[]
        def create(**kwargs):
            calls.append(kwargs)
            return types.SimpleNamespace(model_dump=lambda **kwargs:raw_response(result))
        client=types.SimpleNamespace(messages=types.SimpleNamespace(create=create))
        audit.collect_one(self.run,dict(self.manifest,model='fixture'),self.row,client)
        path=self.run/'notes'/'note-1.json';old=audit.load_json(path)
        old.update(state='error',error='old whole-response rejection',error_type='ValueError')
        old['proposal_sha256']=audit.digest({k:v for k,v in old.items() if k!='proposal_sha256'})
        audit.save_json(path,old)
        outcome=audit.revalidate(self.run,'owner@example.test',['note-1'])
        self.assertEqual(outcome['outcomes'][0]['state'],'proposed')
        new=audit.load_json(path)
        self.assertNotIn('error',new);self.assertEqual(new['prior_proposal_sha256'],old['proposal_sha256'])
        self.assertEqual(len(calls),1);self.assertEqual(self.current(),self.row)
        self.assertTrue(list((self.run/new['raw_path']).glob('revalidated-*.json')))
        with self.assertRaises(ValueError):audit.revalidate(self.run,'owner@example.test',[])


    def public_entry(self,result=None):
        entry=self.proposal(result)
        entry.update(identity_scope='public_catalogue_type',physical_note_verified=False,identity_review_required=True)
        entry['proposal_sha256']=audit.digest({k:v for k,v in entry.items() if k!='proposal_sha256'})
        audit.save_json(self.run/'notes'/'note-1.json',entry)
        return entry

    def saved_basis(self):
        return {'verified':True,'review_basis':'saved_catalogue_identity','physical_note_verified':False,
                'saved_identity':{k:self.row[k] for k in ('country','denomination','pick_number')},
                'variety_uniquely_established':True,
                'reason':'The unchanged full saved catalogue type and exact variety match the retrieved public source.'}

    def test_saved_catalogue_basis_can_enrich_type_without_claiming_image_review(self):
        proposal=self.public_entry();approval=self.approval(proposal,{'printer':'De La Rue'})
        approval['records'][0]['identity_review']=self.saved_basis()
        self.assertEqual(audit.apply(self.run,'owner@example.test',approval)['outcomes'][0]['state'],'applied')
        self.assertEqual(self.current()['pick_number'],'P-7')

    def test_saved_catalogue_basis_rejects_missing_full_identity_uncertain_variety_or_identity_correction(self):
        result=result_for(self.row);result['type_fields']['country']=proof(value='Fiji')
        proposal=self.public_entry(result);approval=self.approval(proposal,{'country':'Fiji'})
        approval['records'][0]['identity_review']=self.saved_basis()
        with self.assertRaises(ValueError):audit.apply(self.run,'owner@example.test',approval)
        for field,value in [('saved_identity',{'country':'Tonga','denomination':'1 Pound','pick_number':'P-7a'}),
                            ('variety_uniquely_established',False),('physical_note_verified',True)]:
            approval=self.approval(proposal,{'printer':'De La Rue'})
            approval['records'][0]['identity_review']=self.saved_basis();approval['records'][0]['identity_review'][field]=value
            with self.assertRaises(ValueError):audit.apply(self.run,'owner@example.test',approval)
        approval=self.approval(proposal,{'country':'Fiji'})
        approval['records'][0]['identity_review'].update(review_basis='local_specimen_evidence',physical_note_verified=True)
        self.assertEqual(audit.apply(self.run,'owner@example.test',approval)['outcomes'][0]['state'],'applied')

    def test_additive_equivalent_reference_needs_exact_suffix_crosswalk(self):
        proposal=self.public_entry();approval=self.approval(proposal,{'pick_number':'P-7, TBB B301'})
        approval['records'][0]['identity_review']=self.saved_basis()
        with self.assertRaises(ValueError):audit.apply(self.run,'owner@example.test',approval)
        cross={'from_reference':'P-7a','to_reference':'TBB B301','verified':True,'source_url':URL,
               'supporting_quote':'Tonga P-7 = TBB B301 for this exact signature variety.',
               'reason':'Direct catalogue source explicitly cross-references the same exact issue and variety.'}
        approval['records'][0]['research_review']['pick_number']['exact_reference_crosswalk']=[cross]
        with self.assertRaises(ValueError):audit.apply(self.run,'owner@example.test',approval)
        cross['from_reference']='P-7'
        self.assertEqual(audit.apply(self.run,'owner@example.test',approval)['outcomes'][0]['state'],'applied')

    def test_pick_parenthesized_numeric_variety_is_preserved_in_crosswalk(self):
        for value in ('P340(7)', 'P-338b(4)', 'Pick P-187(5)'):
            self.assertIn('(', audit.reference_key(value))
        self.assertNotEqual(audit.reference_key('P338b(4)'), audit.reference_key('P338b'))
        self.assertNotEqual(audit.reference_key('P340(7)'), audit.reference_key('P340(6)'))
        for invalid in ('P340(specimen)', 'P340(7)(8)', 'P340(1234)', 'P340(0)'):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                audit.reference_key(invalid)
        base = {**self.row, 'pick_number': 'Fr277'}
        identity = self.saved_basis(); identity['saved_identity']['pick_number'] = 'Fr277'
        quote = 'Friedberg Fr277 corresponds exactly to Pick P340(7), not the replacement-note variety.'
        sources = {URL: {'kind': 'independent_reviewer', 'quotes': [quote]}}
        cross = {'from_reference': 'Fr277', 'to_reference': 'P340(7)', 'verified': True,
                 'source_url': URL, 'supporting_quote': quote,
                 'reason': 'The actual source explicitly preserves the numbered Pick sub-variety of this exact Friedberg issue.'}
        item = {'identity_review': identity, 'research_review': {'pick_number': {'exact_reference_crosswalk': [cross]}}}
        audit.validate_public_identity_review(base, {'pick_number': 'Fr277, P340(7)'}, {}, item, sources)
        cross['to_reference'] = 'P340'
        with self.assertRaises(ValueError):
            audit.validate_public_identity_review(base, {'pick_number': 'Fr277, P340(7)'}, {}, item, sources)

    def test_tbb_base_number_does_not_establish_saved_suffix(self):
        base={**self.row,'pick_number':'TBB B305a'}
        identity=self.saved_basis();identity['saved_identity']['pick_number']='TBB B305a'
        cross={'from_reference':'TBB B305','to_reference':'P-9a','verified':True,'source_url':URL,
               'supporting_quote':'B305a corresponds to P9a.',
               'reason':'The source crosswalk explicitly preserves the exact dated signature variety.'}
        item={'identity_review':identity,'research_review':{'pick_number':{'exact_reference_crosswalk':[cross]}}}
        with self.assertRaises(ValueError):audit.validate_public_identity_review(base,{'pick_number':'TBB B305a, P-9a'},{'sources':{URL:{}}},item)
        cross['from_reference']='TBB B305a'
        audit.validate_public_identity_review(base,{'pick_number':'TBB B305a, P-9a'},{'sources':{URL:{}}},item)
        with self.assertRaises(ValueError):audit.validate_public_identity_review(base,{'pick_number':'TBB B305b'},{'sources':{URL:{}}},item)


    def test_explicit_independent_source_supports_review_and_is_durably_audited(self):
        proposal=self.public_entry();approval=self.approval(proposal,{'pick_number':'P-7, TBB B301'})
        item=approval['records'][0];item['identity_review']=self.saved_basis()
        url='https://catalogue.example.test/exact-crosswalk'
        quote='For this exact Tonga variety, Pick P-7 corresponds to The Banknote Book TBB B301.'
        field=item['research_review']['pick_number'];field.update(source_url=url,supporting_quote=quote)
        field['exact_reference_crosswalk']=[{'from_reference':'P-7','to_reference':'TBB B301','verified':True,
          'source_url':url,'supporting_quote':quote,'reason':'Independently read the primary catalogue crosswalk for the full exact variety.'}]
        with self.assertRaises(ValueError):audit.apply(self.run,'owner@example.test',approval)
        item['independent_sources']=[{'url':url,'supporting_quote':quote,'retrieved_at':'2026-01-01',
          'reviewed':True,'reason':'Reviewer actually opened this exact public catalogue page and copied the matching excerpt.'}]
        self.assertEqual(audit.apply(self.run,'owner@example.test',approval)['outcomes'][0]['state'],'applied')
        saved=audit.load_json(next((self.run/'approvals').glob('*.json')))
        self.assertEqual(saved['records'][0]['independent_sources'],item['independent_sources'])
        self.assertNotIn(url,proposal['sources'])

    def test_independent_source_requires_actual_review_date_and_matching_excerpt(self):
        proposal=self.public_entry();approval=self.approval(proposal,{'printer':'De La Rue'})
        item=approval['records'][0];item['identity_review']=self.saved_basis()
        url='https://catalogue.example.test/printer'
        source={'url':url,'supporting_quote':'This exact catalogue type was printed by De La Rue.',
                'retrieved_at':'2026-01-01','reviewed':True,'reason':'Reviewer opened the exact page and checked the printer entry against the complete type.'}
        item['research_review']['printer'].update(source_url=url,supporting_quote=source['supporting_quote'])
        for key,value in [('reviewed',False),('retrieved_at','not-a-date'),('retrieved_at','2099-01-01'),('url','https://user:secret@example.test/item')]:
            item['independent_sources']=[{**source,key:value}]
            with self.assertRaises(ValueError):audit.apply(self.run,'owner@example.test',approval)
        item['independent_sources']=[source]
        item['research_review']['printer']['supporting_quote']='A different excerpt never retrieved from this page.'
        with self.assertRaises(ValueError):audit.apply(self.run,'owner@example.test',approval)
        self.assertEqual(self.current(),self.row)

    def test_model_cannot_promote_self_declared_independent_sources(self):
        result=result_for(self.row)
        result['independent_sources']=[{'url':'https://invented.test','reviewed':True}]
        with self.assertRaises(ValueError):audit.validate_proposal(self.row,result,[raw_response()])


    def supplement_manifest(self, proposal, updates=None):
        updates = updates or {'size_width': 150.0, 'size_height': 80.0}
        return {'run_id': self.manifest['run_id'], 'baseline_sha256': self.manifest['baseline_sha256'],
                'reviewer': 'Independent catalogue reviewer',
                'reason': 'Read the exact public catalogue entry and retained its source excerpt for local identity review.',
                'records': [{'record_id': 'note-1', 'baseline_record_sha256': audit.digest(self.row),
                             'proposal_sha256': proposal['proposal_sha256'], 'updates': updates,
                             'research_review': {f: {'value': v, 'source_url': URL, 'supporting_quote': QUOTE,
                              'identity_verified': True, 'reason': 'The exact catalogue source directly supports this type fact.'} for f, v in updates.items()},
                             'independent_sources': [{'url': URL, 'supporting_quote': QUOTE,
                              'retrieved_at': '2026-01-01', 'reviewed': True,
                              'reason': 'Independently opened the exact catalogue page and copied its relevant source text.'}]}]}

    def test_supplement_is_offline_and_preserves_raw_prior_proposal_and_source_origin(self):
        proposal = self.public_entry()
        raw = self.run / 'raw' / 'note-1' / 'original.json'
        audit.save_json(raw, {'provider': 'untouched original raw response'})
        raw_before = raw.read_bytes()
        research = self.supplement_manifest(proposal)
        with patch.object(audit, 'connect', side_effect=AssertionError('Supplement must not access a database')):
            result = audit.supplement(self.run, research)
        after = audit.load_json(self.run / 'notes' / 'note-1.json')
        self.assertEqual(result['outcomes'][0]['state'], 'independent_research')
        self.assertEqual(after['sources'], proposal['sources'])
        self.assertEqual(after['independent_sources'][URL]['kind'], 'independent_reviewer')
        self.assertEqual(after['prior_proposal_sha256'], proposal['proposal_sha256'])
        self.assertFalse(after['physical_note_verified'])
        self.assertTrue(after['identity_review_required'])
        self.assertEqual(after['allowed_values']['size_width'], [150.0])
        journal = audit.load_json(next((self.run / 'supplements' / 'note-1').glob('*.json')))
        self.assertEqual(journal['before'], proposal)
        self.assertEqual(journal['after'], after)
        self.assertEqual(journal['input'], research['records'][0])
        self.assertEqual(raw.read_bytes(), raw_before)
        self.assertEqual(self.current(), self.row)
        self.assertNotEqual(after['proposal_sha256'], proposal['proposal_sha256'])

    def test_supplement_exact_candidates_still_need_fresh_identity_and_source_approval(self):
        proposal = self.public_entry()
        audit.supplement(self.run, self.supplement_manifest(proposal))
        after = audit.load_json(self.run / 'notes' / 'note-1.json')
        approval = self.approval(after, {'size_width': 150.0, 'size_height': 80.0})
        with self.assertRaises(ValueError): audit.apply(self.run, 'owner@example.test', approval)
        approval['records'][0]['identity_review'] = self.saved_basis()
        approval['records'][0]['updates']['size_width'] = 151.0
        with self.assertRaises(ValueError): audit.apply(self.run, 'owner@example.test', approval)
        approval['records'][0]['updates']['size_width'] = 150.0
        self.assertEqual(audit.apply(self.run, 'owner@example.test', approval)['outcomes'][0]['state'], 'applied')
        self.assertEqual(self.current()['size_width'], 150.0)
        self.assertEqual(self.current()['price'], self.row['price'])

    def test_supplement_can_retain_findings_for_unresolved_identity_without_promoting_it(self):
        result = result_for(self.row); result['identity']['match'] = 'uncertain'
        proposal = self.public_entry(result)
        audit.supplement(self.run, self.supplement_manifest(proposal, {'pick_number': 'P-7a'}))
        after = audit.load_json(self.run / 'notes' / 'note-1.json')
        self.assertEqual(after['identity']['match'], 'uncertain')
        self.assertEqual(after['allowed_values']['pick_number'], ['P-7a'])
        approval = self.approval(after, {'pick_number': 'P-7a'})
        approval['records'][0]['identity_review'] = self.saved_basis()
        with self.assertRaises(ValueError): audit.apply(self.run, 'owner@example.test', approval)
        self.assertEqual(self.current(), self.row)

    def test_supplement_stale_or_tampered_hashes_and_baseline_are_rejected(self):
        proposal = self.public_entry()
        for path in ['proposal_sha256', 'baseline_record_sha256']:
            research = self.supplement_manifest(proposal); research['records'][0][path] = 'stale'
            with self.assertRaises(ValueError): audit.supplement(self.run, research)
        research = self.supplement_manifest(proposal); research['baseline_sha256'] = 'stale'
        with self.assertRaises(ValueError): audit.supplement(self.run, research)
        self.assertEqual(audit.load_json(self.run/'notes'/'note-1.json'), proposal)
        self.assertFalse((self.run/'supplements').exists())
        audit.supplement(self.run, self.supplement_manifest(proposal))
        with self.assertRaises(ValueError): audit.supplement(self.run, self.supplement_manifest(proposal))

    def test_supplement_rejects_protected_unknown_and_nonempty_personal_history_fields(self):
        proposal = self.public_entry()
        for field, value in [('price', '$1'), ('status', 'Own'), ('grade', '70'), ('serial_number', '123'),
                             ('image_1', 'new.png'), ('condition', 'Replace personal context'),
                             ('printer', None), ('material', 'Plastic'), ('issue_type', 'Mystery'),
                             ('size_width', '150 mm'), ('size_height', float('nan'))]:
            with self.subTest(field=field, value=value):
                with self.assertRaises(ValueError): audit.supplement(self.run, self.supplement_manifest(proposal, {field:value}))
        self.assertEqual(audit.load_json(self.run/'notes'/'note-1.json'), proposal)
        self.assertEqual(self.current(), self.row)

    def test_supplement_null_year_needs_explicit_clear_and_consistent_display_pair(self):
        proposal = self.public_entry()
        for updates in [{'date_1':None}, {'date_1_text':'ND (1960-1968)'}, {'date_1_text':'1967'},
                        {'date_1':1967}, {'date_1':1967,'date_1_text':'1966'}]:
            with self.assertRaises(ValueError): audit.supplement(self.run, self.supplement_manifest(proposal, updates))
        research = self.supplement_manifest(proposal, {'date_1':None,'date_1_text':'ND (1960-1968)'})
        with self.assertRaises(ValueError): audit.supplement(self.run, research)
        research['records'][0]['clear_fields'] = ['date_1']
        audit.supplement(self.run, research)
        after = audit.load_json(self.run/'notes'/'note-1.json')
        self.assertIn(None, after['allowed_values']['date_1'])
        approval = self.approval(after, research['records'][0]['updates'])
        approval['records'][0]['identity_review'] = self.saved_basis()
        with self.assertRaises(ValueError): audit.apply(self.run,'owner@example.test',approval)

    def test_supplement_requires_actual_retrieved_field_excerpt_and_reviewer_provenance(self):
        proposal = self.public_entry()
        for mutation in ['reviewer','date','source','quote','missing_field','unreviewed']:
            research = self.supplement_manifest(proposal); item = research['records'][0]
            if mutation == 'reviewer': research['reviewer'] = ''
            if mutation == 'date': item['independent_sources'][0]['retrieved_at'] = '2099-01-01'
            if mutation == 'source': item['research_review']['size_width']['source_url'] = 'https://invented.test'
            if mutation == 'quote': item['research_review']['size_width']['supporting_quote'] = 'A different sentence that was not retrieved.'
            if mutation == 'missing_field': item['research_review'].pop('size_width')
            if mutation == 'unreviewed': item['independent_sources'][0]['reviewed'] = False
            with self.assertRaises(ValueError): audit.supplement(self.run, research)
        self.assertEqual(self.current(), self.row)

    def test_supplement_chain_preserves_every_parent_and_rejects_entire_invalid_batch(self):
        proposal = self.public_entry()
        research = self.supplement_manifest(proposal)
        research['records'].append({**research['records'][0], 'record_id':'unknown'})
        with self.assertRaises(ValueError): audit.supplement(self.run, research)
        self.assertFalse((self.run/'supplements').exists())
        audit.supplement(self.run, self.supplement_manifest(proposal))
        first = audit.load_json(self.run/'notes'/'note-1.json')
        audit.supplement(self.run, self.supplement_manifest(first, {'material':'Paper'}))
        second = audit.load_json(self.run/'notes'/'note-1.json')
        self.assertEqual(len(second['supplement_history']), 2)
        self.assertEqual(second['prior_proposal_sha256'], first['proposal_sha256'])
        journals = [audit.load_json(p) for p in (self.run/'supplements'/'note-1').glob('*.json')]
        self.assertEqual(len(journals), 2)
        self.assertTrue(any(j['before']==proposal and j['after']==first for j in journals))
        self.assertTrue(any(j['before']==first and j['after']==second for j in journals))



    def start_fill_run(self, changes=None):
        if changes:
            db = sqlite3.connect(self.database)
            db.execute('UPDATE banknotes SET ' + ','.join('"'+key+'"=?' for key in changes), list(changes.values()))
            db.commit(); db.close()
        self.run = self.root / 'fill-run'
        audit.initialize(self.database, self.run, 'owner@example.test', fill_missing_only=True)
        self.manifest, self.baseline = audit.checked_run(self.run, 'owner@example.test')
        self.row = self.baseline['rows'][0]

    def fill_proposal(self, result=None, quote=QUOTE):
        proposed = audit.validate_proposal(self.row, result or result_for(self.row), [raw_response(quote=quote)], fill_missing_only=True)
        entry = {'record_id': self.row['id'], 'baseline_record_sha256': audit.digest(self.row),
                 **audit.missing_only_proposal(self.row, proposed)}
        entry['proposal_sha256'] = audit.digest(entry)
        audit.save_json(self.run/'notes'/'note-1.json', entry)
        return entry

    def test_fill_policy_persisted_and_blank_definition_preserves_manual_sentinels(self):
        self.assertFalse(self.manifest['fill_missing_only'])
        self.start_fill_run()
        self.assertTrue(audit.load_json(self.run/'manifest.json')['fill_missing_only'])
        for value in [None, '', ' \t\n']:
            self.assertTrue(audit.is_blank(value))
        for value in [0, 0.0, False, 'Unknown', 'None', 'Manual text']:
            self.assertFalse(audit.is_blank(value))
            with self.assertRaises(ValueError):
                audit.validate_missing_updates({'printer': value}, {'printer': 'De La Rue'})
        with self.assertRaises(ValueError): audit.validate_missing_updates({'printer': None}, {'printer': '  '})

    def test_fill_proposals_exclude_occupied_values_enddate_and_duplicate_history(self):
        self.start_fill_run({'printer': 'Unknown', 'watermark': '  '})
        result = result_for(self.row)
        result['type_fields'].update({'watermark': proof(value='Crown'), 'history_context': proof(value='New history'),
                                     'date_2': proof(value=1968), 'country': proof(value='Fiji')})
        proposal = self.fill_proposal(result)
        self.assertEqual(proposal['updates'], {'watermark': 'Crown'})
        self.assertEqual(set(proposal['allowed_values']), {'watermark'})
        self.assertEqual(self.current(), self.row)
        unsafe = self.proposal(result)
        for updates in [{'printer': 'De La Rue'}, {'country': 'Fiji'}, {'date_2': 1968, 'date_2_text': '1968'},
                        {'history_context': 'New history'}, {'watermark': None}]:
            with self.subTest(updates=updates), self.assertRaises(ValueError):
                audit.apply(self.run, 'owner@example.test', self.approval(unsafe, updates))
        self.assertEqual(self.current(), self.row)

    def test_fill_collection_revalidation_and_prompt_restrict_public_research(self):
        self.start_fill_run({'printer': '  ', 'notes': 'PRIVATE-NOTES'})
        result = result_for(self.row); result['identity']['record_id'] = audit.PUBLIC_QUERY_TOKEN
        result['type_fields']['history_context'] = proof(value='Duplicate history')
        calls = []
        def create(**kwargs):
            calls.append(kwargs)
            return types.SimpleNamespace(model_dump=lambda **kwargs:raw_response(result))
        client = types.SimpleNamespace(messages=types.SimpleNamespace(create=create))
        self.assertEqual(audit.collect_one(self.run, self.manifest, self.row, client), 'proposed')
        entry = audit.load_json(self.run/'notes'/'note-1.json')
        self.assertEqual(entry['updates'], {'printer': 'De La Rue'})
        prompt = audit.load_json(self.run/entry['raw_path']/'attempt.json')['prompt']
        names = json.loads(prompt.split('requested blank field names are ')[1].split('. Research')[0])
        self.assertIn('printer', names)
        self.assertFalse({'history_context', 'condition', 'date_2', 'date_2_text', 'pick_number'} & set(names))
        self.assertNotIn('PRIVATE-', json.dumps(calls))
        self.assertIn('never the whole series lifespan', prompt)
        audit.revalidate(self.run, 'owner@example.test', ['note-1'])
        self.assertEqual(audit.load_json(self.run/'notes'/'note-1.json')['updates'], {'printer': 'De La Rue'})
        self.assertEqual(len(calls), 1); self.assertEqual(self.current(), self.row)

    def test_fill_skips_only_intentional_enddate_and_history_alias_blanks_without_provider(self):
        values = {key: 'Saved value' for key in audit.ALLOWED}
        values.update(date_1=1966, date_1_text='1966', date_2=None, date_2_text=None,
                      size_width=150, size_height=80, history_context=None)
        self.start_fill_run(values)
        self.assertEqual(audit.missing_fields(self.row), set())
        with patch.dict(os.environ, {'ANTHROPIC_API_KEY': ''}):
            self.assertEqual(audit.collect(self.run, 'owner@example.test')['states'], {'no_missing_fields': 1})
        self.assertEqual(audit.report(self.run)['provider_calls_all_attempts'], 0)
        self.assertEqual(self.current(), self.row)

    def test_fill_sources_append_once_preserve_prefix_and_rollback_with_values(self):
        prior = 'Manual source note.  \nKeep this exact whitespace.\n'
        self.start_fill_run({audit.SOURCE_NOTES: prior})
        proposal = self.fill_proposal(); approval = self.approval(proposal)
        self.assertEqual(proposal['updates'], {'printer': 'De La Rue'})
        self.assertEqual(audit.apply(self.run, 'owner@example.test', approval)['outcomes'][0]['state'], 'applied')
        current = self.current()
        self.assertTrue(current[audit.SOURCE_NOTES].startswith(prior + '\n\n'))
        self.assertIn('Printer: ' + URL, current[audit.SOURCE_NOTES])
        for key in self.row:
            if key not in {'printer', audit.SOURCE_NOTES, 'updated_at'}:
                self.assertEqual(current[key], self.row[key], key)
        self.assertEqual(audit.apply(self.run, 'owner@example.test', approval)['outcomes'][0]['state'], 'already_applied')
        self.assertEqual(self.current(), current)
        rollback = {'run_id': self.manifest['run_id'], 'baseline_sha256': self.manifest['baseline_sha256'],
                    'rollback_approved': True, 'record_ids': ['note-1']}
        self.assertEqual(audit.rollback(self.run, 'owner@example.test', rollback)['outcomes'][0]['state'], 'rolled_back')
        restored = self.current()
        self.assertEqual(restored[audit.SOURCE_NOTES], prior)
        self.assertEqual(restored['printer'], self.row['printer'])

    def test_fill_transaction_rechecks_blank_policy_and_source_compare_and_set(self):
        self.start_fill_run({audit.SOURCE_NOTES: 'Existing notes'})
        proposal = self.fill_proposal(); approval = self.approval(proposal)
        prepared = [('note-1', self.row, {'country': 'Fiji', audit.SOURCE_NOTES: 'Existing notes\nsource'}, proposal['proposal_sha256'])]
        with patch.object(audit, 'validate_approval', return_value=prepared):
            result = audit.apply(self.run, 'owner@example.test', approval)
        self.assertEqual(result['outcomes'][0]['state'], 'conflict')
        self.assertEqual(self.current(), self.row)
        db = sqlite3.connect(self.database)
        db.execute('UPDATE banknotes SET note_references_research=?', ('Later user source note',)); db.commit(); db.close()
        self.assertEqual(audit.apply(self.run, 'owner@example.test', approval)['outcomes'][0]['state'], 'conflict')
        self.assertEqual(self.current()[audit.SOURCE_NOTES], 'Later user source note')
        self.assertIsNone(self.current()['printer'])

    def test_fill_whitespace_history_is_eligible_but_alias_and_double_narrative_are_not(self):
        self.start_fill_run({'condition': '  ', 'history_context': None})
        result = result_for(self.row); result['catalogue_refs'] = []
        result['type_fields'] = {'condition': proof(value='Supported historical narrative'),
                                'history_context': proof(value='Another historical narrative')}
        proposal = self.fill_proposal(result)
        self.assertEqual(proposal['updates'], {'condition': 'Supported historical narrative'})
        self.assertEqual(audit.apply(self.run, 'owner@example.test', self.approval(proposal))['outcomes'][0]['state'], 'applied')
        self.assertIsNone(self.current()['history_context'])
        with self.assertRaises(ValueError):
            audit.validate_missing_updates({'condition': None, 'history_context': 'Manual history'}, {'condition': 'New'})
        with self.assertRaises(ValueError):
            audit.validate_missing_updates({'condition': None, 'history_context': None}, {'condition': 'One', 'history_context': 'Two'})

    def test_fill_numeric_year_uses_existing_consistent_display_without_overwriting(self):
        self.start_fill_run({'date_1': None, 'date_1_text': ' 1966 '})
        result = result_for(self.row); result['catalogue_refs'] = []; result['type_fields'] = {'date_1': proof(value=1966)}
        proposal = self.fill_proposal(result)
        self.assertEqual(proposal['updates'], {'date_1': 1966})
        self.assertEqual(audit.apply(self.run, 'owner@example.test', self.approval(proposal))['outcomes'][0]['state'], 'applied')
        self.assertEqual(self.current()['date_1_text'], ' 1966 ')
        for text in ['1967', 'ND (1960-1968)', '1960-1968']:
            row = {**self.row, 'date_1_text': text}
            validated = audit.validate_proposal(row, result, [raw_response()], fill_missing_only=True)
            self.assertNotIn('date_1', audit.missing_only_proposal(row, validated)['allowed_values'])
        self.assertNotIn('date_2', audit.missing_fields(self.row))
        self.assertIn('date_2', audit.missing_fields({**self.row, 'date_1_text': '1966-1968'}))

    def test_fill_supplement_and_public_identity_still_require_exact_review(self):
        self.start_fill_run({'issuer': None})
        result = result_for(self.row); result['type_fields']['issuer'] = proof(value='Government of Tonga')
        proposal = self.public_entry(result)
        for updates in [{'country': 'Fiji'}, {'printer': None}, {'history_context': 'Duplicate history'},
                        {audit.SOURCE_NOTES: 'Arbitrary replacement'}]:
            with self.subTest(updates=updates), self.assertRaises(ValueError):
                audit.supplement(self.run, self.supplement_manifest(proposal, updates))
        approval = self.approval(proposal, {'issuer': 'Government of Tonga'})
        approval['records'][0]['identity_review'] = self.saved_basis()
        with self.assertRaises(ValueError): audit.apply(self.run, 'owner@example.test', approval)
        approval['records'][0]['identity_review'].update(review_basis='local_specimen_evidence', physical_note_verified=True)
        self.assertEqual(audit.apply(self.run, 'owner@example.test', approval)['outcomes'][0]['state'], 'applied')



    def test_fill_full_date_display_cannot_contradict_or_obscure_saved_year(self):
        self.start_fill_run({'date_2': 1966, 'date_2_text': None})
        for display in ['1 June 1967', '1966-1968', '1966–68', '1966/68', '1966-02-30', 'June 66', 'ND (1966)']:
            result = result_for(self.row); result['catalogue_refs'] = []
            result['type_fields'] = {'date_2_text': proof(value=display)}
            proposal = self.fill_proposal(result)
            self.assertNotIn('date_2_text', proposal['allowed_values'])
            unsafe = self.proposal(result)
            with self.subTest(display=display), self.assertRaises(ValueError):
                audit.apply(self.run, 'owner@example.test', self.approval(unsafe))
            self.assertEqual(self.current(), self.row)
        for display in ['1966-06-01', '1966/06/01']:
            audit.validate_date_updates(self.row, {'date_2_text': display}, fill_missing_only=True)
        result['type_fields'] = {'date_2_text': proof(value='1 June 1966')}
        proposal = self.fill_proposal(result)
        self.assertEqual(audit.apply(self.run, 'owner@example.test', self.approval(proposal))['outcomes'][0]['state'], 'applied')
        self.assertEqual(self.current()['date_2'], 1966)
        self.assertEqual(self.current()['date_2_text'], '1 June 1966')



    def test_fill_silver_material_is_supported_without_relaxing_closed_values(self):
        self.start_fill_run()
        quote = 'Exact catalogue commemorative note: material Silver, 99.9% purity, weight 5 grams.'
        result = result_for(self.row); result['type_fields'] = {'material': proof(value='Silver')}
        proposal = self.fill_proposal(result, quote)
        self.assertEqual(proposal['updates'], {'material': 'Silver'})
        approval = self.approval(proposal)
        approval['records'][0]['research_review']['material']['supporting_quote'] = quote
        self.assertEqual(audit.apply(self.run, 'owner@example.test', approval)['outcomes'][0]['state'], 'applied')
        self.assertEqual(self.current()['material'], 'Silver')
        self.assertEqual(self.current()['denomination'], self.row['denomination'])
        result['type_fields']['material'] = proof(value='Plastic')
        self.assertNotIn('material', self.fill_proposal(result)['allowed_values'])


if __name__=='__main__':unittest.main()
