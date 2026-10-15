"""One purchase phase across evidence, manual inspection, filtering and holdings."""
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['DATA_DIR'] = tempfile.mkdtemp(prefix='stuff-lifecycle-')
os.environ['EBAY_SYNC_WORKER'] = '0'
os.environ['ORIGINAL_LISTING_WORKER'] = '0'
os.environ.pop('ANTHROPIC_API_KEY', None)
sys.modules['dotenv'] = types.SimpleNamespace(load_dotenv=lambda **kwargs: None)
import app as stuff
import ebay_orders
import purchase_lifecycle as lifecycle


class PurchaseLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.ctx = stuff.app.app_context(); self.ctx.push()
        self.db = stuff.get_db()
        for category in lifecycle.SUPPORTED_CATEGORIES:
            self.db.execute('DELETE FROM ' + category)
        self.db.execute('DELETE FROM ebay_order_items')
        self.db.execute('DELETE FROM ebay_status_events')
        self.db.commit()
        self.client = stuff.app.test_client()

    def tearDown(self):
        self.db.rollback(); self.ctx.pop()

    def note(self, ident='note', status='Ordered', delivery=None, manual=None, attention=''):
        self.db.execute('INSERT INTO banknotes (id,country,denomination,pick_number,status,updated_at) VALUES (?,?,?,?,?,?)',
                        (ident, 'Canada', '20 Dollars', 'P-1', status, 'unchanged'))
        if delivery:
            self.db.execute('INSERT INTO ebay_order_items (line_key,order_id,item_id,title,quantity,delivery_status,attention,last_seen) VALUES (?,?,?,?,1,?,?,?)',
                            (ident, '12-12345-12345', '123456789012', 'Canada banknote P-1', delivery, attention, '2026-10-15T12:00:00Z'))
            self.db.execute('INSERT INTO banknote_ebay_links (banknote_id,line_key,matched_by,matched_at,manual_status) VALUES (?,?,?,?,?)',
                            (ident, ident, 'manual', '2026-10-15T12:00:00Z', manual))
        self.db.commit()
        return self.row(ident)

    def row(self, ident='note', category='banknotes'):
        return self.db.execute('SELECT * FROM '+category+' WHERE id=?', (ident,)).fetchone()

    def state(self, ident='note', category='banknotes'):
        return lifecycle.for_record(self.db, category, self.row(ident, category))

    def post(self, target, expected='Ordered', category='banknotes', ident='note', **extra):
        return self.client.post('/'+category+'/'+ident+'/purchase-status', json=dict(status=target, expected_status=expected, **extra))

    def filtered(self, phase):
        with stuff.app.test_request_context('/banknotes'):
            sql, args = stuff.build_search_query('banknotes', '', coin_filter=phase)
            return [r['id'] for r in self.db.execute(sql,args)]

    def test_delivery_projected_and_owned_never_automatic(self):
        for phase in lifecycle.PENDING:
            self.note(phase, delivery=phase)
            state=self.state(phase)
            self.assertEqual(state['status'],phase)
            self.assertEqual(state['next'], {'Ordered':'Shipped','Shipped':'Delivered','Delivered':'Own'}[phase])
            self.assertEqual(state['source'],'eBay')
            self.assertTrue(state['inspection_required'])
            self.assertEqual(self.row(phase)['status'],'Ordered')
            self.assertEqual(self.filtered(phase.lower()),[phase])

    def test_owned_alias_blank_and_dispositions_override_shipping(self):
        for i,raw in enumerate(('Own','Owned','',None,'Sold','Gifted','Loaned','Consigned','Lost')):
            ident=str(i);self.note(ident,raw,'Delivered')
            state=self.state(ident)
            expected=lifecycle.canonical(raw)
            self.assertEqual(state['status'],expected)
            self.assertEqual(state['label'],'Owned' if expected=='Own' else expected)
            self.assertIsNone(state['next'])
            self.assertFalse(state['inspection_required'])
            self.assertIn(ident,self.filtered(expected.lower()))

    def test_authoritative_correction_and_manual_override(self):
        self.note(status='Shipped',delivery='Delivered')
        item=dict(self.db.execute('SELECT * FROM ebay_order_items').fetchone(),tracking=[])
        item['delivery_status']='Ordered'
        ebay_orders.apply_items(self.db,[item],auto_match=False,authoritative=True);self.db.commit()
        self.assertEqual(self.state()['status'],'Ordered')
        self.assertEqual(self.filtered('ordered'),['note'])
        self.assertEqual(self.row()['status'],'Shipped')
        result=self.post('Delivered')
        self.assertEqual(result.status_code,200,result.json)
        self.assertEqual(result.json['lifecycle']['source'],'manual')
        ebay_orders.apply_items(self.db,[item],auto_match=False,authoritative=True);self.db.commit()
        self.assertEqual(self.state()['status'],'Delivered')
        self.assertEqual(self.filtered('delivered'),['note'])

    def test_unverified_email_and_refund_do_not_advance_or_demote_owned(self):
        self.note(delivery='Delivered')
        self.db.execute("INSERT INTO ebay_mail_receipts VALUES ('m','note','Delivered','email evidence','2026-10-15T12:00:00Z')")
        self.db.commit()
        self.assertEqual(self.state()['status'],'Ordered')
        self.assertTrue(self.state()['attention'])
        self.assertIn('Email alone', self.state()['review_reason'])
        self.assertEqual(self.filtered('ordered'),['note'])
        self.db.execute("INSERT INTO ebay_purchase_observations VALUES ('note','2026-10-15T12:01:00Z','Refunded','')")
        self.db.execute("UPDATE ebay_order_items SET delivery_status='Shipped'")
        self.db.commit()
        self.assertEqual(self.state()['status'],'Ordered')
        self.assertIn('Refunded',self.state()['review_reason'])
        self.assertEqual(self.filtered('ordered'),['note'])
        self.db.execute("UPDATE banknotes SET status='Own'");self.db.commit()
        self.assertEqual(self.state()['status'],'Own')
        self.assertTrue(self.state()['attention'])
        self.assertIn('Refunded',self.state()['review_reason'])

    def test_manual_phase_wins_over_unverified_source(self):
        self.note(delivery='Shipped', manual='Delivered')
        self.db.execute("INSERT INTO ebay_mail_receipts VALUES ('m','note','Shipped','email','2026-10-15T12:00:00Z')");self.db.commit()
        self.assertEqual(self.state()['status'],'Delivered')
        self.assertTrue(self.state()['attention'])
        self.assertEqual(self.filtered('delivered'),['note'])

    def test_multiple_purchase_alert_never_counts_as_delivered(self):
        self.note(delivery='Delivered', attention='Multiple purchase rows match this listing')
        self.assertEqual(self.state()['status'],'Ordered')
        self.assertTrue(self.state()['attention'])
        self.assertEqual(self.filtered('ordered'),['note'])

    def test_inspection_required_and_exactly_one_feedback_handoff(self):
        self.note(delivery='Delivered')
        before=dict(self.row())
        with patch.object(stuff.banknote_feedback,'handoff',return_value={'state':'ready','url':'/banknotes/note/feedback'}) as handoff:
            for inspected in (None,False,'true',1):
                result=self.post('Own','Delivered',inspected=inspected)
                self.assertEqual(result.status_code,409,result.json)
                self.assertEqual(result.json['code'],'inspection_required')
                self.assertEqual(dict(self.row()),before)
            result=self.post('Own','Delivered',inspected=True)
            self.assertEqual(result.status_code,200,result.json)
            self.assertEqual(result.json['lifecycle']['label'],'Owned')
            self.assertEqual(result.json['feedback']['state'],'ready')
            self.assertEqual(self.row()['status'],'Own')
            saved=dict(self.row())
            result=self.post('Own','Own',inspected=True)
            self.assertEqual(result.status_code,200)
            self.assertNotIn('feedback',result.json)
            self.assertEqual(dict(self.row()),saved)
            self.assertEqual(handoff.call_count,1)
            self.assertEqual(self.post('Own','Delivered',inspected=True).status_code,409)
            self.assertEqual(handoff.call_count,1)

    def test_noop_effective_phase_does_not_pin_manual_override(self):
        self.note(delivery='Delivered')
        before=dict(self.row())
        result=self.post('Delivered','Delivered')
        self.assertEqual(result.status_code,200,result.json)
        self.assertEqual(dict(self.row()),before)
        self.assertIsNone(self.db.execute('SELECT manual_status FROM banknote_ebay_links').fetchone()[0])
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM ebay_status_events').fetchone()[0],0)

    def test_stale_effective_phase_rejects_without_mutation(self):
        self.note(delivery='Delivered')
        before=dict(self.row())
        self.assertEqual(self.post('Shipped','Ordered').status_code,409)
        self.assertEqual(dict(self.row()),before)
        self.assertEqual(self.client.post('/banknotes/note/purchase-status',json={'status':'Shipped'}).status_code,400)
        self.assertEqual(self.post('invented','Delivered').status_code,400)

    def test_all_supported_categories_can_manually_progress(self):
        for category in lifecycle.SUPPORTED_CATEGORIES-{'banknotes'}:
            self.db.execute('INSERT INTO '+category+" (id,status,updated_at) VALUES ('r','Ordered','old')")
            self.db.commit()
            for previous,target in zip(lifecycle.VALUES,lifecycle.VALUES[1:]):
                result=self.post(target,previous,category,'r',inspected=target=='Own')
                self.assertEqual(result.status_code,200,(category,result.json))
                self.assertEqual(result.json['lifecycle']['value'],target)
            self.assertEqual(self.row('r',category)['status'],'Own')
        for category in ('watches','properties'):
            self.assertEqual(self.post('Shipped',category=category).status_code,400)
            self.assertIsNone(lifecycle.resolve(category,{'status':'Ordered'}))

    def test_owner_row_and_cross_site_guards(self):
        self.note(delivery='Delivered')
        self.db.execute("INSERT OR REPLACE INTO users(id,email,role,categories) VALUES ('member','lifecycle-member@example.com','member','banknotes')");self.db.commit()
        result=self.client.post('/banknotes/note/purchase-status',json={'status':'Own','expected_status':'Delivered','inspected':True},headers={'Cf-Access-Authenticated-User-Email':'lifecycle-member@example.com'})
        self.assertEqual(result.status_code,403)
        with patch.object(stuff,'_user_can_see_row',return_value=False):
            self.assertEqual(self.post('Own','Delivered',inspected=True).status_code,403)
        result=self.client.post('/banknotes/note/purchase-status',json={'status':'Own','expected_status':'Delivered','inspected':True},headers={'Origin':'https://other.example'})
        self.assertEqual(result.status_code,403)
        self.assertEqual(self.post('Own',ident='missing').status_code,404)
        self.assertEqual(self.row()['status'],'Ordered')

    def test_legacy_status_autosave_guard_and_manual_progression(self):
        self.note(delivery='Shipped')
        path='/banknotes/note/save-field'
        result=self.client.post(path,json={'field':'status','value':'Owned'})
        self.assertEqual(result.status_code,409,result.json)
        self.assertEqual(result.json['code'],'inspection_required')
        result=self.client.post(path,json={'field':'status','value':'Delivered'})
        self.assertEqual(result.status_code,200,result.json)
        self.assertEqual(result.json['lifecycle']['status'],'Delivered')
        self.assertEqual(self.state()['source'],'manual')
        result=self.client.post(path,json={'field':'status','value':'Owned','inspected':True})
        self.assertEqual(result.status_code,200,result.json)
        self.assertEqual(self.row()['status'],'Own')
        self.assertIn('feedback',result.json)

    def test_full_form_cannot_silently_mark_pending_owned(self):
        self.note(delivery='Delivered')
        before=dict(self.row())
        result=self.client.post('/banknotes/note',data={'status':'Own'})
        self.assertEqual(result.status_code,409,result.json)
        self.assertEqual(dict(self.row()),before)

    def test_full_form_echo_does_not_pin_or_clear_evidence(self):
        self.note(delivery='Delivered')
        for echo in ('Ordered','Delivered'):
            result=self.client.post('/banknotes/note',data={'status':echo,'country':'Canada','denomination':'20 Dollars'})
            self.assertEqual(result.status_code,302,result.get_data(as_text=True)[:200])
            self.assertEqual(self.row()['status'],'Ordered')
            self.assertIsNone(self.db.execute('SELECT manual_status FROM banknote_ebay_links').fetchone()[0])
            self.assertEqual(self.state()['status'],'Delivered')

    def test_stale_full_form_cannot_undo_inspection(self):
        self.note(delivery='Delivered')
        self.assertEqual(self.post('Own','Delivered',inspected=True).status_code,200)
        before=dict(self.row())
        for extra in ({},{'expected_status':'Delivered'},{'expected_status':''}):
            result=self.client.post('/banknotes/note',data=dict(status='Delivered',country='Canada',**extra))
            self.assertEqual(result.status_code,409,result.get_data(as_text=True)[:200])
            self.assertEqual(result.json['code'],'status_changed')
            self.assertEqual(result.json['lifecycle']['status'],'Own')
            self.assertEqual(dict(self.row()),before)
        # An explicit legacy caller can still make a deliberate non-ownership
        # correction if it has read the current effective status.
        result=self.client.post('/banknotes/note',data={'status':'Delivered','expected_status':'Own','country':'Canada'})
        self.assertEqual(result.status_code,302,result.get_data(as_text=True)[:200])
        self.assertEqual(self.row()['status'],'Delivered')
        self.assertEqual(self.state()['source'],'manual')

    def test_member_full_form_status_echo_is_not_manual_progression(self):
        self.note(delivery='Delivered')
        self.db.execute("INSERT OR REPLACE INTO users(id,email,role,categories) VALUES ('member','lifecycle-member@example.com','member','banknotes')");self.db.commit()
        headers={'Cf-Access-Authenticated-User-Email':'lifecycle-member@example.com'}
        result=self.client.post('/banknotes/note',data={'status':'Delivered','country':'Canada','denomination':'20 Dollars'},headers=headers)
        self.assertEqual(result.status_code,302,result.get_data(as_text=True)[:200])
        self.assertEqual(self.row()['status'],'Ordered')
        result=self.client.post('/banknotes/note',data={'status':'Shipped'},headers=headers)
        self.assertEqual(result.status_code,403)
        self.assertEqual(self.row()['status'],'Ordered')

    def test_owner_status_row_filter_cannot_be_escaped(self):
        self.note()
        with patch.object(stuff,'_row_filter_for_category',return_value={'status':['Ordered']}):
            self.assertEqual(self.post('Shipped').status_code,403)
        self.assertEqual(self.row()['status'],'Ordered')

    def test_market_match_warning_uses_effective_phase(self):
        self.note(delivery='Delivered')
        matches=stuff._market_collection_matches(self.db,dict(country='Canada',pick_number='P-1'))
        self.assertEqual(matches[0]['status'],'Delivered')
        self.assertEqual(self.row()['status'],'Ordered')

    def test_pending_holdings_reports_and_matching_remain_included(self):
        for phase in lifecycle.PENDING:
            self.note(phase,status=phase)
            self.db.execute("UPDATE banknotes SET description=? WHERE id=?",('Listing: https://www.ebay.com/itm/12345678901'+str(lifecycle.PENDING.index(phase)),phase))
        self.db.commit()
        self.assertEqual(len(stuff._market_owned_banknote_rows(self.db)),3)
        self.assertEqual(len(stuff._analysis_active_rows(self.db,'banknotes')),3)
        self.assertEqual(sum(len(s[2]) for s in stuff._banknote_report_sections(self.db)),3)
        self.assertEqual(set.union(*ebay_orders.listing_candidates(self.db).values()),set(lifecycle.PENDING))
        matches=stuff._market_collection_matches(self.db,dict(country='Canada',pick_number='P-1'))
        self.assertEqual({m['status'] for m in matches},set(lifecycle.PENDING))
        self.assertIn('Canada (3)',stuff._market_holdings_summary(self.db,'banknotes'))
        self.assertIn('20 Dollars',stuff._market_denomination_coverage(self.db,'banknotes'))

    def test_options_and_watches_remain_distinct(self):
        with stuff.app.test_request_context('/'):
            for category in lifecycle.SUPPORTED_CATEGORIES:
                field=next(f for f in stuff.visible_fields(category) if f['name']=='status')
                self.assertTrue(set(lifecycle.VALUES).issubset(field['options']))
            self.assertNotIn('Shipped',stuff.current_vlists('watches')['status'])
            self.assertNotIn('Delivered',stuff.CATEGORY_FILTERS['watches'])

    def test_original_listing_refresh_includes_same_state(self):
        self.note(delivery='Delivered')
        result=stuff._original_listing_service.lookup('banknotes',self.row())
        self.assertEqual(result['lifecycle'],self.state())
        self.assertEqual(self.row()['status'],'Ordered')


if __name__=='__main__':
    unittest.main()
