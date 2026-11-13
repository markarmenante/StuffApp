"""A missing date extends history automatically without misfiling or changing notes."""
import copy
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['DATA_DIR'] = tempfile.mkdtemp(prefix='stuff-history-')
for name in ('ANTHROPIC_API_KEY', 'PERPLEXITY_API_KEY', 'OPENAI_API_KEY'):
    os.environ.pop(name, None)
for name in ('EBAY_SYNC_WORKER', 'BANKNOTE_IMPORT_WORKER', 'ORIGINAL_LISTING_WORKER'):
    os.environ[name] = '0'

import app as stuff
import banknote_history as history


class HistoryCoverageTests(unittest.TestCase):
    OLD = ('France', ((1800, 1913, 'Existing period', 'Keep the established history.'),))
    ADDITION = {'title': 'France', 'spellings': ['france'],
                'eras': [[1789, 1799, 'The Revolution and assignats', 'Researched revolutionary paper money.']],
                'sources': [{'title': 'Archive catalogue', 'url': 'https://www.lib.uchicago.edu/'}]}

    def setUp(self):
        self.ctx = stuff.app.app_context()
        self.ctx.push()
        self.db = stuff.get_db()
        for table in ('banknotes', 'country_eras', 'country_history_jobs', 'country_history_updates'):
            self.db.execute('DELETE FROM ' + table)
        self.db.commit()
        stuff._generated_country_eras(force=True)
        stuff._COUNTRY_HISTORY_INFLIGHT.clear()
        self.client = stuff.app.test_client()

    def tearDown(self):
        self.db.rollback()
        self.ctx.pop()

    def add(self, ident='assignat', year=1792, **changes):
        row = dict(id=ident, country='France', date_1=year, issuer='Domaines Nationaux (Assignat)',
                   denomination='10 Livres', pick_number='P-66b', cat_id='B-' + ident,
                   status='Ordered', banknote_id='P 999', price='$99', image_1='front.jpg',
                   image_2='back.jpg', order_number='12-12345-12345', notes='Keep these facts')
        row.update(changes)
        self.db.execute('INSERT INTO banknotes (' + ','.join(row) + ') VALUES (' +
                        ','.join('?' for _ in row) + ')', tuple(row.values()))
        self.db.commit()

    def records(self):
        return {r['id']: dict(r) for r in self.db.execute('SELECT * FROM banknotes')}

    def generate(self):
        with patch.dict(os.environ, {'ANTHROPIC_API_KEY': 'synthetic'}), \
                patch.object(stuff, 'ensure_state_names'), \
                patch.object(stuff, 'generate_country_eras', return_value=copy.deepcopy(self.ADDITION)) as model:
            stuff.ensure_country_history('France', synchronous=True)
        return model

    def test_assignat_and_french_period_boundaries(self):
        for year, start, label in ((1789, 1789, 'The Revolution and assignats'),
                                  (1792, 1789, 'The Revolution and assignats'),
                                  (1799, 1789, 'The Revolution and assignats'),
                                  (1800, 1800, 'Founding of the Banque de France'),
                                  (1802, 1800, 'Founding of the Banque de France'),
                                  (1803, 1803, 'The germinal franc'), (1913, 1803, 'The germinal franc'),
                                  (1944, 1929, 'Depression and occupation')):
            with self.subTest(year=year):
                panel = stuff._series_panel_for_row(dict(country='France', date_1=year))
                self.assertEqual((panel['era']['start'], panel['era']['label']), (start, label))
        self.add()
        html = self.client.get('/banknotes', query_string={'q': 'P-66b'}).get_data(as_text=True)
        self.assertIn('1789–1799', html)
        self.assertIn('The Revolution and assignats', html)
        self.assertNotIn('The germinal franc', html)

    def test_earlier_later_and_internal_gaps_never_borrow_a_nearby_era(self):
        with patch.dict(stuff.COUNTRY_ERAS, {'france': ('France', (
                (1800, 1840, 'First', 'First body'), (1850, 2001, 'Later', 'Later body')))}):
            for year in (1792, 1845, 2020):
                self.add(str(year), year)
                self.assertIsNone(stuff._country_era('france', year))
            self.assertEqual(stuff._country_history_request('France')[1], [1792, 1845, 2020])
            html = self.client.get('/banknotes').get_data(as_text=True)
            self.assertIn('History does not cover this date yet.', html)
            self.assertEqual(self.client.get('/banknotes/country-history/status?country=France').json['state'], 'missing')

    def test_success_adds_sourced_history_to_builtin_and_updates_list_and_report(self):
        with patch.dict(stuff.COUNTRY_ERAS, {'france': self.OLD}):
            self.add()
            self.add('later', 1900, issuer='Banque de France')
            before = self.records()
            model = self.generate()
            self.assertEqual(model.call_args.args[1], [1792])
            self.assertEqual(model.call_args.args[2], self.OLD[1])
            self.assertEqual(stuff._country_era('france', 1792)['start'], 1789)
            self.assertEqual(stuff._country_era('france', 1900)['body'], self.OLD[1][0][3])
            self.assertEqual(stuff._country_history_state('France'), 'ready')
            self.assertEqual(self.client.get('/banknotes/country-history/status?country=France&year=1792').json['state'], 'ready')
            html = self.client.get('/banknotes', query_string={'q': 'P-66b'}).get_data(as_text=True)
            self.assertIn('The Revolution and assignats', html)
            self.assertNotIn('History does not cover this date yet.', html)
            _, _, eras = stuff._banknote_report_history('France', 'france', [])
            self.assertEqual(eras[0][0], '1789–1799')
            saved = self.db.execute('SELECT * FROM country_history_updates').fetchone()
            self.assertEqual(json.loads(saved['sources']), self.ADDITION['sources'])
            after = self.records()
            for ident, row in before.items():
                self.assertEqual({k: v for k, v in row.items() if k != 'banknote_id'},
                                 {k: v for k, v in after[ident].items() if k != 'banknote_id'})
            self.assertEqual(self.generate().call_count, 0, 'covered notes must not regenerate')

    def test_generated_tables_are_extended_without_replacing_existing_history(self):
        self.db.execute('INSERT INTO country_eras (country_key,title,eras,spellings) VALUES (?,?,?,?)',
                        ('fixtureland', 'Fixtureland', json.dumps(self.OLD[1]), '["fixtureland"]'))
        self.db.commit()
        stuff._generated_country_eras(force=True)
        self.add(country='Fixtureland')
        with patch.dict(os.environ, {'ANTHROPIC_API_KEY': 'synthetic'}), \
                patch.object(stuff, 'ensure_state_names'), \
                patch.object(stuff, 'generate_country_eras', return_value=copy.deepcopy(self.ADDITION)):
            stuff.ensure_country_history('Fixtureland', synchronous=True)
        entry = stuff._country_eras_for('fixtureland')
        self.assertEqual(entry[0], 'Fixtureland')
        self.assertEqual(entry[1][-1], self.OLD[1][0])
        self.assertEqual(stuff._country_era('fixtureland', 1792)['start'], 1789)

    def test_response_validation_rejects_uncovered_dates_overlap_and_missing_sources(self):
        valid = {'title': 'France', 'spellings': ['France'], 'sources': self.ADDITION['sources'],
                 'eras': [{'start': 1789, 'end': 1799, 'label': 'Revolution', 'body': 'Paper money.'}]}
        self.assertEqual(history.validate(valid, [1792], self.OLD[1])['eras'][0][0], 1789)
        with self.assertRaisesRegex(RuntimeError, 'not returned by web research'):
            history.validate(valid, [1792], self.OLD[1], observed_sources={})
        self.assertTrue(history.validate(valid, [1792], self.OLD[1],
                                        observed_sources={'https://www.lib.uchicago.edu/': {}})['sources'])
        changes = [{'sources': []}, {'eras': [{'start': 1789, 'end': 1791, 'label': 'Wrong', 'body': 'Wrong years.'}]},
                   {'eras': [{'start': 1789, 'end': 1800, 'label': 'Overlap', 'body': 'Overlap.'}]},
                   {'eras': valid['eras'] * 2}, {'eras': []}]
        for change in changes:
            with self.subTest(change=change), self.assertRaises(RuntimeError):
                history.validate(dict(valid, **change), [1792], self.OLD[1])

    def test_generator_requires_sources_actually_returned_by_research(self):
        payload = dict(self.ADDITION, eras=[{'start': 1789, 'end': 1799,
                       'label': 'Revolution', 'body': 'Revolutionary paper money.'}])
        observed = {'content': []}
        response = SimpleNamespace(model_dump=lambda: observed)
        with patch.object(stuff, '_require_anthropic_key', return_value='synthetic'), \
                patch.object(stuff, 'anthropic_lookup_model', return_value='fixture-model'), \
                patch.object(stuff, '_anthropic_create', return_value=response) as call, \
                patch.object(stuff, '_message_text', return_value=json.dumps(payload)):
            with self.assertRaisesRegex(RuntimeError, 'not returned by web research'):
                stuff.generate_country_eras('France', [1792], self.OLD[1])
            observed['content'] = [{'type': 'web_search_tool_result', 'content': [
                {'type': 'web_search_result', 'url': self.ADDITION['sources'][0]['url']}]}]
            self.assertEqual(stuff.generate_country_eras('France', [1792], self.OLD[1])['eras'][0][0], 1789)
        prompt = call.call_args.kwargs['messages'][0]['content']
        self.assertIn('1792', prompt)
        self.assertIn('Keep the established history.', prompt)

    def test_durable_lease_backoff_retry_cap_and_manual_retry(self):
        token = history.claim(self.db, 'france', [1792], self.OLD[1])
        self.assertTrue(token)
        self.assertIsNone(history.claim(self.db, 'france', [1792], self.OLD[1]))
        history.fail(self.db, 'france', token, 'Temporary provider failure')
        self.assertEqual(history.state(self.db, 'france'), 'pending')
        self.assertIsNone(history.claim(self.db, 'france', [1792], self.OLD[1]))
        for attempt in (2, 3):
            self.db.execute('UPDATE country_history_jobs SET retry_after=0')
            self.db.commit()
            token = history.claim(self.db, 'france', [1792], self.OLD[1])
            self.assertTrue(token)
            history.fail(self.db, 'france', token, 'Still unavailable')
        self.assertEqual(history.state(self.db, 'france'), 'missing')
        self.assertIsNone(history.claim(self.db, 'france', [1792], self.OLD[1]))
        self.assertTrue(history.claim(self.db, 'france', [1792], self.OLD[1], force=True))

    def test_expired_worker_cannot_publish_over_replacement(self):
        with patch.dict(stuff.COUNTRY_ERAS, {'france': self.OLD}):
            self.add()
            former = history.claim(self.db, 'france', [1792], self.OLD[1])
            self.db.execute('UPDATE country_history_jobs SET lease_until=0')
            self.db.commit()
            current = history.claim(self.db, 'france', [1792], self.OLD[1])
            self.assertNotEqual(former, current)
            with patch.object(stuff, 'generate_country_eras', return_value=copy.deepcopy(self.ADDITION)):
                stuff._run_country_history_job('France', 'france', [1792], self.OLD[1], former)
            self.assertEqual(self.db.execute('SELECT count(*) FROM country_eras').fetchone()[0], 0)
            self.assertEqual(self.db.execute('SELECT token FROM country_history_jobs').fetchone()[0], current)

    def test_transient_failure_retries_from_poll_then_publishes(self):
        with patch.dict(stuff.COUNTRY_ERAS, {'france': self.OLD}):
            self.add()
            with patch.dict(os.environ, {'ANTHROPIC_API_KEY': 'synthetic'}), \
                    patch.object(stuff, 'ensure_state_names'), \
                    patch.object(stuff, 'generate_country_eras', side_effect=RuntimeError('Unavailable')):
                stuff.ensure_country_history('France', synchronous=True)
            self.assertIsNone(stuff._country_era('france', 1792))
            self.db.execute('UPDATE country_history_jobs SET retry_after=0')
            self.db.commit()
            with patch.dict(os.environ, {'ANTHROPIC_API_KEY': 'synthetic'}), \
                    patch.object(stuff, 'ensure_state_names'), \
                    patch.object(stuff, 'generate_country_eras', return_value=copy.deepcopy(self.ADDITION)), \
                    patch.object(stuff.threading, 'Thread', side_effect=lambda target, args, daemon:
                                 SimpleNamespace(start=lambda: target(*args))):
                response = self.client.get('/banknotes/country-history/status?country=France&year=1792')
            self.assertEqual(response.json['state'], 'ready')

    def test_editing_only_the_date_starts_coverage_check(self):
        self.add(year=1900)
        with patch.object(stuff, 'ensure_country_history') as ensure:
            response = self.client.post('/banknotes/assignat/save-field', json={'field': 'date_1', 'value': '1792'})
        self.assertEqual(response.status_code, 200, response.json)
        ensure.assert_called_once_with('France')

    def test_list_checks_coverage_even_with_history_hidden(self):
        self.add()
        with patch.object(stuff, 'ensure_country_history') as ensure:
            self.assertEqual(self.client.get('/banknotes?history=0').status_code, 200)
        ensure.assert_called_once_with('France')

    def test_alias_and_series_dates_are_included_without_guessing_undated_notes(self):
        with patch.dict(stuff.COUNTRY_ERAS, {'france': self.OLD}):
            self.add(country='France (Republic)')
            self.add('series', None, series='1793 issue')
            self.add('undated', None, series='Undated')
            self.assertEqual(stuff._country_history_request('France')[1], [1792, 1793])

    def test_same_label_in_two_date_bands_does_not_merge_their_headings(self):
        with patch.dict(stuff.COUNTRY_ERAS, {'france': ('France', (
                (1789, 1799, 'Paper money', 'Early period'),
                (1800, 1913, 'Paper money', 'Later period')))}):
            self.add()
            self.add('later', 1900)
            rows = self.db.execute('SELECT * FROM banknotes ORDER BY date_1').fetchall()
            panels = stuff.series_panels(rows)
            self.assertEqual(panels['assignat']['panel']['era']['span'], '1789–1799')
            self.assertEqual(panels['later']['panel']['era']['span'], '1800–1913')

    def test_invalid_future_date_does_not_regenerate_or_reload_forever(self):
        self.add(year=2992)
        self.assertIsNone(stuff._country_history_request('France'))
        html = self.client.get('/banknotes').get_data(as_text=True)
        self.assertIn('data-year="2992"', html)
        self.assertEqual(self.client.get('/banknotes/country-history/status?country=France&year=2992').json['state'], 'missing')

    def test_startup_resequences_once_and_preserves_note_facts(self):
        self.add()
        before = self.records()
        self.db.execute("DELETE FROM migration_state WHERE key='banknote_display_number_v42'")
        self.db.commit()
        stuff.init_db()
        self.assertEqual(self.records()['assignat']['banknote_id'], 'P 001')
        self.assertEqual({k: v for k, v in before['assignat'].items() if k != 'banknote_id'},
                         {k: v for k, v in self.records()['assignat'].items() if k != 'banknote_id'})
        with patch.object(stuff, '_renumber_banknotes') as renumber:
            stuff.init_db()
        renumber.assert_not_called()


if __name__ == '__main__':
    unittest.main()
