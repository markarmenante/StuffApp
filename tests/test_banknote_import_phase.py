"""Review status distinguishes saved metadata from ongoing display crops."""
import time
import unittest

import test_banknote_imports as fixture_module


class CheckPhaseTests(unittest.TestCase):
    def setUp(self):
        self.fixture=fixture_module.DraftTests()
        self.fixture.setUp()

    def tearDown(self):
        self.fixture.tearDown()

    def assert_phases_through_crop(self, *, crop_fails):
        fixture=self.fixture
        batch=fixture.imported()
        item=batch['items'][0]
        observed=[]

        def current():
            response=fixture.client.get(batch['status_url'])
            self.assertEqual(response.status_code,200)
            return next(row for row in response.json['items'] if row['id']==item['id'])

        def evaluate(note,prepared):
            status=current()
            self.assertEqual(status['check_state'],'checking')
            self.assertEqual(status['check_phase'],'checking')
            observed.append('checking')
            return dict(filled=fixture.fills)

        def crop(raw,note):
            status=current()
            self.assertEqual(status['check_state'],'checking')
            self.assertEqual(status['check_phase'],'cropping')
            self.assertEqual(status['check_message'],fixture_module.imports.CHECK_CROP_MESSAGE)
            for field,value in fixture.fills.items():
                self.assertEqual(status['fields'][field],value)
            observed.append('cropping')
            if crop_fails:raise TimeoutError('Optional crop timed out')
            return fixture.preview_crop(raw,note)

        fixture.check(batch,item,evaluate,crop)
        status=current()
        expected='partial' if crop_fails else 'done'
        self.assertEqual(status['check_state'],expected)
        self.assertEqual(status['check_phase'],expected)
        self.assertEqual(observed,['checking','cropping','cropping'])

    def test_successful_crop_exposes_checkpoint_phase_until_done(self):
        self.assert_phases_through_crop(crop_fails=False)

    def test_failed_crop_stops_exposing_cropping_after_partial_result(self):
        self.assert_phases_through_crop(crop_fails=True)

    def test_expired_checkpoint_exposes_failed_phase_without_mutating_saved_state(self):
        fixture=self.fixture
        batch=fixture.imported();item=batch['items'][0]
        fixture.db.execute('''UPDATE banknote_import_items SET check_state='checking',
            check_message=?,check_expires=? WHERE id=?''',
            (fixture_module.imports.CHECK_CROP_MESSAGE,time.time()-1,item['id']))
        fixture.db.commit()
        status=next(row for row in fixture.client.get(batch['status_url']).json['items'] if row['id']==item['id'])
        self.assertEqual(status['check_state'],'failed')
        self.assertEqual(status['check_phase'],'failed')
        self.assertEqual(fixture.db.execute('SELECT check_state FROM banknote_import_items WHERE id=?',
                                           (item['id'],)).fetchone()[0],'checking')


if __name__=='__main__':
    unittest.main()
