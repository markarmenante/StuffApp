"""Interrupted import jobs resume without losing drafts or trusting stale tokens."""
import json
from pathlib import Path
import sqlite3
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import banknote_imports as imports


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(':memory:')
        self.db.row_factory=sqlite3.Row
        self.addCleanup(self.db.close)
        imports.init_schema(self.db)
        self.db.execute('CREATE TABLE ebay_purchase_account(id INTEGER PRIMARY KEY,account_name TEXT)')
        self.db.execute("INSERT INTO ebay_purchase_account VALUES(1,'buyer')")
        self.batch('batch')
        self.batch('other-batch',account='other')
        self.clock=patch.object(imports.time,'time',return_value=1000)
        self.clock.start();self.addCleanup(self.clock.stop)
        self.context=patch.object(imports,'_check_context',return_value=('draft','capture','price'))
        self.context.start();self.addCleanup(self.context.stop)
        self.db.commit()

    def batch(self,ident,account='buyer'):
        self.db.execute('''INSERT INTO banknote_import_batches
            (id,account_name,order_id,state,created_at,updated_at) VALUES(?,?,?,'review',1,1)''',
            (ident,account,ident+'-order'))

    def item(self,ident,*,batch='batch',account='buyer',state='draft',check='checking',expires=1300):
        self.db.execute('''INSERT INTO banknote_import_items
            (id,batch_id,account_name,line_key,item_id,source_json,source_digest,fields_json,
             state,revision,manual_photos_json,retry_photos,check_state,check_token,check_expires,created_at,updated_at)
            VALUES(?,?,?,?,?,'{}','source',?,?,7,?,1,?,?,?,1,1)''',
            (ident,batch,account,ident+'-line',ident+'-ebay',json.dumps({'country':'Nigeria','image_1':'original.jpg'}),
             state,json.dumps({'image_2':'manual.jpg'}),check,ident+'-old-token',expires))
        self.db.commit()

    def row(self,ident):
        return dict(self.db.execute('SELECT * FROM banknote_import_items WHERE id=?',(ident,)).fetchone())

    def preview(self,ident,*,expires=1300,revision=7,digest='capture'):
        self.db.execute('''INSERT INTO banknote_import_preview_jobs
            (item_id,source_digest,capture_digest,revision,state,token,expires,updated_at)
            VALUES(?,'source',?,?,'checking',?,?,1)''',
            (ident,digest,revision,ident+'-preview-old',expires))
        self.db.commit()

    def test_startup_requeues_abandoned_checks_and_fences_late_writers(self):
        self.item('draft')
        self.item('inspection',state='blocked')
        for ident,check in (('finished','done'),('partial','partial'),('failed','failed'),('idle','idle')):
            self.item(ident,check=check)
        self.item('released',state='released')
        self.item('other',batch='other-batch',account='other')
        before={row['id']:dict(row) for row in self.db.execute('SELECT * FROM banknote_import_items')}
        result=imports.recover_interrupted_work(self.db,abandoned=True)
        self.assertEqual(result,{'checks':['batch'],'previews':[]})
        for ident in ('draft','inspection'):
            row=self.row(ident)
            self.assertEqual(row['check_state'],'queued')
            self.assertIsNone(row['check_token'])
            self.assertEqual(row['check_expires'],0)
            for field in ('fields_json','revision','manual_photos_json','retry_photos','source_json','source_digest'):
                self.assertEqual(row[field],before[ident][field])
            cursor=self.db.execute("UPDATE banknote_import_items SET fields_json='{}' WHERE id=? AND check_token=?",
                                   (ident,before[ident]['check_token']))
            self.assertEqual(cursor.rowcount,0)
        self.db.commit()
        for ident in ('finished','partial','failed','idle','released','other'):
            self.assertEqual(self.row(ident),before[ident])
        self.assertEqual(imports.recover_interrupted_work(self.db,abandoned=True),{'checks':[],'previews':[]})
        token=imports.claim_check(self.db,'batch','draft',7)
        self.assertTrue(token)
        self.assertNotEqual(token,before['draft']['check_token'])

    def test_periodic_recovery_leaves_current_worker_leases_untouched(self):
        self.item('expired',expires=999)
        self.item('boundary',expires=1000)
        self.item('active',expires=1001)
        active=self.row('active')
        self.assertEqual(imports.recover_interrupted_work(self.db)['checks'],['batch'])
        self.assertEqual(self.row('expired')['check_state'],'queued')
        self.assertEqual(self.row('boundary')['check_state'],'queued')
        self.assertEqual(self.row('active'),active)

    def test_changed_purchase_fails_clearly_instead_of_restarting_invalid_work(self):
        self.item('changed',expires=999)
        before=self.row('changed')
        with patch.object(imports,'_check_context',side_effect=imports.ImportProblem('Purchase identity changed.')):
            self.assertEqual(imports.recover_interrupted_work(self.db),{'checks':[],'previews':[]})
        row=self.row('changed')
        self.assertEqual(row['check_state'],'failed')
        self.assertEqual(row['check_message'],'Purchase identity changed.')
        self.assertIsNone(row['check_token'])
        self.assertEqual(row['fields_json'],before['fields_json'])
        self.assertEqual(imports.recover_interrupted_work(self.db),{'checks':[],'previews':[]})

    def test_preview_restart_rotates_token_and_keeps_saved_originals_and_crops(self):
        self.item('preview',state='blocked',check='idle')
        self.preview('preview')
        self.db.execute('''INSERT INTO banknote_import_photo_previews
            VALUES('preview','https://example.test/front','source','capture','original.jpg','original-hash',
                   'crop.jpg','crop-hash','[]',0)''')
        self.db.commit()
        before=dict(self.db.execute('SELECT * FROM banknote_import_photo_previews').fetchone())
        with patch.object(imports,'_preview_context',return_value=([{'source_url':'https://example.test/front'}],'capture')):
            self.assertEqual(imports.recover_interrupted_work(self.db,abandoned=True),{'checks':[],'previews':['batch']})
            job=dict(self.db.execute('SELECT * FROM banknote_import_preview_jobs').fetchone())
            self.assertEqual(job['state'],'queued')
            self.assertNotEqual(job['token'],'preview-preview-old')
            self.assertGreater(job['expires'],1000)
            self.assertEqual(imports.pending_preview_batches(self.db),['batch'])
            self.assertEqual(imports.claim_previews(self.db,'batch','preview'),job['token'])
            with self.assertRaises(imports.ImportProblem):
                imports._validate_preview_job(self.db,'batch','preview','preview-preview-old')
            imports._validate_preview_job(self.db,'batch','preview',job['token'])
        self.assertEqual(dict(self.db.execute('SELECT * FROM banknote_import_photo_previews').fetchone()),before)

    def test_preview_recovery_rejects_a_changed_capture_or_revision(self):
        self.item('old-capture',state='blocked',check='idle')
        self.item('old-revision',state='blocked',check='idle')
        self.preview('old-capture',expires=999,digest='old-capture')
        self.preview('old-revision',expires=999,revision=6)
        with patch.object(imports,'_preview_context',return_value=([{'source_url':'current'}],'capture')):
            self.assertEqual(imports.recover_interrupted_work(self.db),{'checks':[],'previews':[]})
        for job in self.db.execute('SELECT * FROM banknote_import_preview_jobs'):
            self.assertEqual(job['state'],'failed')
            self.assertIsNone(job['token'])
            self.assertIn('listing photos changed',job['message'])


if __name__=='__main__':
    unittest.main()
