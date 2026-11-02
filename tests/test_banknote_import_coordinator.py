"""An explicit order refresh must not strand earlier in-flight draft checks."""
import json
import unittest
from unittest.mock import patch

import test_banknote_imports as fixtures

stuff = fixtures.stuff
imports = fixtures.imports


class CoordinatorTests(unittest.TestCase):
    setUp = fixtures.DraftTests.setUp
    tearDown = fixtures.DraftTests.tearDown
    batch = fixtures.DraftTests.batch
    payload = fixtures.DraftTests.payload
    imported = fixtures.DraftTests.imported
    download = fixtures.DraftTests.download
    classify = fixtures.DraftTests.classify

    def coordinator(self, batch, refresh_at=None):
        checks = []
        acquisitions = []
        owner = self

        class Slots:
            def acquire(self, **_kwargs):
                acquisitions.append(True)
                if len(acquisitions) == refresh_at:
                    db = stuff.get_db()
                    saved = db.execute('SELECT * FROM banknote_import_batches WHERE id=?', (batch['id'],)).fetchone()
                    sources = [json.loads(row['source_json']) for row in db.execute(
                        'SELECT * FROM banknote_import_items WHERE batch_id=?', (batch['id'],))]
                    db.execute("UPDATE banknote_import_batches SET state='queued' WHERE id=?", (batch['id'],))
                    imports.materialize(db, 'buyer', saved['order_id'], sources, saved['request_id'])
                    db.commit()
                    # The caller has committed fresh draft revisions before it
                    # asks the still-running coordinator to resume processing.
                    stuff._start_import_checks(batch['id'])
                owner.assertLess(len(acquisitions), 10, 'Only newly eligible rows may be scheduled')
                return True

            def release(self):
                pass

        class Thread:
            def __init__(self, *, target, args=(), name='', **_kwargs):
                self.target, self.args, self.name = target, args, name

            def start(self):
                if self.name == 'banknote-import-batch':
                    self.target(*self.args)
                else:
                    owner.assertEqual(self.name, 'banknote-import-check')
                    checks.append(self.args)

        with patch.dict(stuff.os.environ, {'BANKNOTE_IMPORT_WORKER': '1'}), \
                patch.object(stuff, '_start_import_previews'), \
                patch.object(stuff.threading, 'Thread', Thread), \
                patch.object(imports, '_CHECK_SLOTS', Slots()):
            stuff._start_import_checks(batch['id'])
        self.assertNotIn(batch['id'], stuff._IMPORT_BATCH_THREADS)
        return checks

    def finish(self, checks, evaluate=None, prepare_photo=None):
        with patch.object(imports.listing_images, 'download', side_effect=self.download):
            for batch_id, item_id, revision, token in checks:
                imports.run_check(stuff.open_db_connection, batch_id, item_id, revision, token,
                    stuff.UPLOAD_FOLDER, self.classify, evaluate or (lambda *_: dict(filled=self.fills)),
                    prepare_photo=prepare_photo)

    def test_restart_recovers_checkpointed_jobs_and_fences_old_workers(self):
        batch = self.imported()
        sources = {row['id']: (row['line_key'], row['source_json'], row['source_digest']) for row in
                   self.db.execute('SELECT * FROM banknote_import_items WHERE batch_id=?', (batch['id'],))}
        old_checks = self.coordinator(batch)
        self.assertEqual(len(old_checks), 3)
        fresh_checks = []
        checkpoint = {}

        def crop_after_restart(raw, note):
            # Identification and originals have already been committed. Mimic
            # a replacement worker taking over while the old crop call returns.
            current = imports.status(self.db, batch['id'])
            checkpoint.update({item['id']: item['fields'] for item in current['items']})
            first = next(item for item in current['items'] if item['id'] == old_checks[0][1])
            self.assertEqual(first['check_phase'], 'cropping')
            self.assertEqual(first['fields']['country'], self.fills['country'])
            recovered = imports.recover_interrupted_work(self.db, abandoned=True)
            self.assertEqual(recovered, {'checks': [batch['id']], 'previews': []})
            fresh_checks.extend(self.coordinator(batch))
            return fixtures.DraftTests.preview_crop(raw, note)

        self.finish(old_checks[:1], prepare_photo=crop_after_restart)
        self.assertEqual(len(fresh_checks), 3)
        old_tokens = {item_id: token for _, item_id, _, token in old_checks}
        fresh_tokens = {item_id: token for _, item_id, _, token in fresh_checks}
        self.assertEqual(set(fresh_tokens), set(old_tokens))
        self.assertTrue(all(fresh_tokens[item_id] != old_tokens[item_id] for item_id in old_tokens))
        # The other abandoned jobs can also return after the new claims. None
        # may save stale model output or fail the replacement worker's lease.
        self.finish(old_checks[1:], lambda *_: dict(filled={'country': 'Stale result'}))
        for item in imports.status(self.db, batch['id'])['items']:
            self.assertEqual(item['check_state'], 'checking')
            self.assertEqual(item['fields'], checkpoint[item['id']])
            token = self.db.execute('SELECT check_token FROM banknote_import_items WHERE id=?',
                                    (item['id'],)).fetchone()[0]
            self.assertEqual(token, fresh_tokens[item['id']])

        self.finish(fresh_checks)
        for item in imports.status(self.db, batch['id'])['items']:
            self.assertEqual(item['check_state'], 'done', item['check_message'])
            self.assertEqual(item['fields']['country'], self.fills['country'])
            for field, value in checkpoint[item['id']].items():
                self.assertEqual(item['fields'].get(field), value)
        current_sources = {row['id']: (row['line_key'], row['source_json'], row['source_digest']) for row in
                           self.db.execute('SELECT * FROM banknote_import_items WHERE batch_id=?', (batch['id'],))}
        self.assertEqual(current_sources, sources)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM banknotes').fetchone()[0], 0)

    def test_refresh_while_third_item_waits_requeues_the_first_two_stale_checks(self):
        batch = self.imported()
        checks = self.coordinator(batch, refresh_at=3)
        # The two stale jobs may finish, but their replaced work tokens cannot
        # publish. Each refreshed draft must also receive one current job.
        self.assertEqual(len(checks), 5)
        self.assertEqual(len({job[1] for job in checks}), 3)
        self.finish(checks[:2], lambda *_: dict(filled={'country': 'Stale result'}))
        mid = imports.status(self.db, batch['id'])
        self.assertTrue(all(not item['fields'].get('country') for item in mid['items']))
        self.finish(checks[2:])
        after = imports.status(self.db, batch['id'])
        for item in after['items']:
            self.assertEqual(item['check_state'], 'done', item['check_message'])
            self.assertEqual(item['fields']['country'], self.fills['country'])
            self.assertTrue(item['fields']['image_1'])
            self.assertTrue(item['fields']['image_2'])
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM banknotes').fetchone()[0], 0)

    def test_failed_partial_and_completed_jobs_are_not_retried_by_coordinator(self):
        batch = self.imported()
        checks = self.coordinator(batch)
        self.assertEqual(len(checks), 3)
        self.finish(checks[:1], lambda *_: (_ for _ in ()).throw(RuntimeError('Provider unavailable')))
        self.finish(checks[1:2], lambda *_: dict(filled=self.fills, lookup_error='A source is unavailable'))
        self.finish(checks[2:])
        self.assertEqual({item['check_state'] for item in imports.status(self.db, batch['id'])['items']},
                         {'failed', 'partial', 'done'})
        self.assertEqual(self.coordinator(batch), [])
        with patch.object(stuff, '_start_import_checks') as start:
            self.assertEqual(self.client.get(batch['status_url']).status_code, 200)
            self.assertEqual(self.client.get(batch['url']).status_code, 200)
        start.assert_not_called()


if __name__ == '__main__':
    unittest.main()
