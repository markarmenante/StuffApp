"""Historical filing, alias preservation, search, migration and intake regressions."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['DATA_DIR'] = tempfile.mkdtemp(prefix='stuff-catalog-test-')
os.environ.pop('ANTHROPIC_API_KEY', None)
import banknote_catalog as catalog
import app as stuff


class CatalogueTests(unittest.TestCase):
    WATER_WORKS = 'Mayor, Aldermen, and Commonalty of the City of New-York (Water Works)'

    def test_american_colonies_precede_generic_us_classification(self):
        for year in (1774, 1775, 1776):
            for country in ('USA', 'United States of America', 'New York', 'New York Colony'):
                info = catalog.classify(country, year, self.WATER_WORKS)
                self.assertEqual(info['key'], 'british')
                self.assertEqual(info['country'], 'New York Colony')
                self.assertIn('colonial', info['period'])
        for issuer in ('Colony of Connecticut', 'Province of Connecticut'):
            info = catalog.classify('United States', 1776, issuer)
            self.assertEqual((info['key'], info['country']), ('british', 'Connecticut Colony'))
        info = catalog.classify('United States', None, self.WATER_WORKS,
                                'Water Works Issue (4th issue, March 5, 1776)')
        self.assertEqual(info['key'], 'british')

    def test_american_colonial_inference_requires_confirmed_identity(self):
        for year, issuer, series in (
                (1776, 'New York', ''), (1776, 'Continental Congress', ''),
                (1775, 'Continental Congress', ''), (1918, 'Federal Reserve Bank of New York', ''),
                (1857, 'New York Water Works', ''), (1777, 'Colony of Connecticut', ''),
                (None, self.WATER_WORKS, ''), (1920, self.WATER_WORKS, 'March 5, 1776')):
            self.assertEqual(catalog.classify('United States', year, issuer, series)['key'], 'us')
        self.assertIsNone(catalog.american_colonial_country('Canada', 1776, self.WATER_WORKS))
        self.assertIsNone(catalog.american_colonial_country('New York', 1776, 'Colony of Connecticut'))
        self.assertEqual(catalog.classify('Rhode Island and Providence Plantations', 1780,
                                         'State of Rhode Island')['key'], 'us')

    def test_colonial_migration_resorts_without_changing_ownership_or_identity(self):
        self.add('federal', 'United States of America', 1918, 'Federal Reserve Bank of New York')
        self.add('ny', 'United States of America', 1776, self.WATER_WORKS)
        self.add('ct', 'United States of America', 1776, 'Colony of Connecticut')
        self.add('pa', 'Pennsylvania Colony', 1772, 'Province of Pennsylvania')
        self.db.execute("UPDATE banknotes SET denomination='$5' WHERE id='federal'")
        self.db.execute("UPDATE banknotes SET cat_id='B373', status='Ordered', issue_type='Colonial', "
                        "denomination='8 Shillings', pick_number='Fr#NY-197', "
                        "series='Water Works Issue (4th issue, March 5, 1776)' WHERE id='ny'")
        self.db.commit()
        before = {r['id']: dict(r) for r in self.db.execute('SELECT * FROM banknotes')}
        stuff._migrate_canonicalize_us_banknotes(self.db)
        self.db.commit()
        after = {r['id']: dict(r) for r in self.db.execute('SELECT * FROM banknotes')}
        for ident, row in before.items():
            for field, value in row.items():
                if field not in ('country', 'banknote_id', 'issue_type'):
                    self.assertEqual(after[ident][field], value, (ident, field))
        self.assertEqual(after['ny']['country'], 'New York Colony')
        self.assertEqual(after['ct']['country'], 'Connecticut Colony')
        self.assertEqual(after['federal']['country'], before['federal']['country'])
        self.assertEqual(after['ny']['banknote_id'], 'P 002')
        self.assertEqual(after['federal']['banknote_id'], 'P 004')
        self.assertEqual(after['ny']['status'], 'Ordered')
        self.assertEqual(after['ct']['status'], 'Own')
        self.assertEqual(after['ct']['issue_type'], 'Colonial')
        history = self.db.execute("SELECT original_country,canonical_country FROM "
                                  "banknote_country_alias_history WHERE banknote_id='ny'").fetchall()
        self.assertEqual([tuple(r) for r in history], [('United States of America', 'New York Colony')])
        stuff._migrate_canonicalize_us_banknotes(self.db)
        self.assertEqual(after, {r['id']: dict(r) for r in self.db.execute('SELECT * FROM banknotes')})
        panel = stuff._series_panel_for_row(after['ny'])
        self.assertEqual(panel['country_key'], 'colonial-america')
        self.assertEqual(panel['title'], 'New York Colony')
        self.assertEqual(panel['now'], 'United States')
        self.assertEqual(stuff._banknote_pin('New York Colony', 1776)['city'], 'New York')
        self.assertIn('British America', stuff._banknote_state_name('New York Colony', 1776)['english'])
        client = stuff.app.test_client()
        for history in ('0', '1'):
            html = client.get('/banknotes', query_string={'filter': 'heritage_british', 'history': history}).get_data(as_text=True)
            self.assertIn('item-ny', html)
            self.assertIn('item-ct', html)
            self.assertNotIn('item-federal', html)
            self.assertIn('New York Colony', html)
            self.assertLess(html.index('item-ny'), html.index('item-pa'))
        sections = stuff._banknote_report_sections(self.db)
        self.assertIn(('New York Colony', 'colonial-america'), [(c, k) for c, k, rows in sections])

    def test_colonial_correction_survives_save_and_import(self):
        self.add('ny', 'United States of America', 1776, self.WATER_WORKS)
        self.add('federal', 'United States of America', 1918, 'Federal Reserve Bank of New York')
        client = stuff.app.test_client()
        response = client.post('/banknotes/ny/save-field', json={'field': 'grade', 'value': 'AU 58'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['banknote_id'], 'P 001')
        self.assertEqual(self.db.execute("SELECT country,status FROM banknotes WHERE id='ny'").fetchone()[:],
                         ('New York Colony', 'Own'))
        fields = {'country': 'United States', 'issue_type': 'National'}
        stuff.canonicalize_banknote_fields(fields, existing=dict(date_1=1776, issuer=self.WATER_WORKS))
        self.assertEqual(fields, {'country': 'New York Colony', 'issue_type': 'Colonial'})
        seed = stuff._finalize_sweep_seed({'country': 'USA', 'date_1': 1776, 'issuer': self.WATER_WORKS,
                                          'status': 'Own'}, 'banknotes', {'role': 'owner'}, self.db, '2026-09-25')
        self.assertEqual(seed['country'], 'New York Colony')
        self.assertEqual(seed['issue_type'], 'Colonial')
        self.assertEqual(seed['status'], 'Own')

    def test_colony_blocks_do_not_split_at_era_boundaries(self):
        notes = [
            ('pa1776', 'Pennsylvania Colony', 1776, 'Province of Pennsylvania'),
            ('ny1776', 'New York Colony', 1776, self.WATER_WORKS),
            ('pa1772', 'Pennsylvania Colony', 1772, 'Province of Pennsylvania'),
            ('ct1776', 'Connecticut Colony', 1776, 'Colony of Connecticut'),
            ('ny1774', 'New York Colony', 1774, self.WATER_WORKS),
            ('nj1776', 'New Jersey', 1776, 'Colony of New Jersey'),
            ('pa1773', 'Pennsylvania Colony', 1773, 'General Assembly of Pennsylvania'),
            ('ri1780', 'Rhode Island and Providence Plantations', 1780, 'State of Rhode Island'),
            ('us1918', 'United States of America', 1918, 'Federal Reserve Bank of New York'),
        ]
        for args in notes:
            self.add(*args)
        self.db.execute("UPDATE banknotes SET issue_type='Colonial', denomination='1 Shilling'")
        self.db.execute("UPDATE banknotes SET issue_type='National', denomination='$1' WHERE id='us1918'")
        self.db.execute("UPDATE banknotes SET status='Ordered' WHERE id IN ('pa1776','ct1776')")
        self.db.execute("UPDATE banknotes SET banknote_id='P 999'")
        self.db.execute("DELETE FROM migration_state WHERE key='banknote_display_number_v25'")
        self.db.commit()
        before = {r['id']: dict(r) for r in self.db.execute('SELECT * FROM banknotes')}
        stuff.init_db()
        expected = ['ct1776', 'nj1776', 'ny1774', 'ny1776', 'pa1772', 'pa1773', 'pa1776', 'ri1780', 'us1918']
        rows = self.db.execute('SELECT * FROM banknotes ORDER BY ' + stuff.CATEGORY_ORDER_BY['banknotes']).fetchall()
        self.assertEqual([r['id'] for r in rows], expected)
        self.assertEqual([r['banknote_id'] for r in rows], [f'P {i:03d}' for i in range(1, len(rows) + 1)])
        for row in rows:
            for field, value in before[row['id']].items():
                if field != 'banknote_id':
                    self.assertEqual(row[field], value, (row['id'], field))
        sections = stuff._banknote_report_sections(self.db)
        pennsylvania = [r for country, key, r in sections if country == 'Pennsylvania Colony']
        self.assertEqual(len(pennsylvania), 1)
        self.assertEqual([r['id'] for r in pennsylvania[0]], ['pa1772', 'pa1773', 'pa1776'])
        client = stuff.app.test_client()
        for history in ('0', '1'):
            for group in ('', 'heritage_british'):
                html = client.get('/banknotes', query_string={'history': history, 'filter': group}).get_data(as_text=True)
                visible = expected if not group else expected[:-2]
                offsets = [html.index('id="item-' + ident + '"') for ident in visible]
                self.assertEqual(offsets, sorted(offsets))
        # A newly edited date moves within Pennsylvania, never across colonies.
        response = client.post('/banknotes/pa1776/save-field', json={'field': 'date_1', 'value': '1771'})
        self.assertEqual(response.status_code, 200)
        order = [r['id'] for r in self.db.execute('SELECT id FROM banknotes ORDER BY ' + stuff.CATEGORY_ORDER_BY['banknotes'])]
        self.assertEqual(order, expected[:4] + ['pa1776', 'pa1772', 'pa1773'] + expected[7:])

    def test_puerto_rico_distribution_requires_catalogue_identity(self):
        base = {'country': 'United States', 'series': 'Series of 1928',
                'denomination': '$1', 'signatures': 'Woods-Woodin'}
        for number in ('Fr.1500', 'Fr#1500', 'Friedberg 1500', 'Fr. 1500*'):
            self.assertIsNotNone(catalog.distribution_callout(dict(base, pick_number=number)))
        for number in ('Fr.1600', 'Fr.1603', 'Fr.15000', 'Fr.1500a', ''):
            self.assertIsNone(catalog.distribution_callout(dict(base, pick_number=number)))
        self.assertIsNone(catalog.distribution_callout(dict(base, country='Puerto Rico', pick_number='Fr.1500')))
        self.assertIsNone(catalog.distribution_callout(None))

    def test_puerto_rico_callout_visible_with_history_hidden_and_on_detail(self):
        self.add('legal', 'United States', 1928, 'United States Treasury (Legal Tender Note)')
        self.db.execute("UPDATE banknotes SET denomination='$1', series='Series of 1928', pick_number='Fr.1500', signatures='Woods-Woodin' WHERE id='legal'")
        self.add('silver', 'United States', 1928, 'United States Treasury (Silver Certificate)')
        self.db.execute("UPDATE banknotes SET denomination='$1', series='Series of 1928C', pick_number='Fr.1603', signatures='Woods-Woodin' WHERE id='silver'")
        self.db.commit()
        client = stuff.app.test_client()
        label = catalog.PUERTO_RICO_1928['label']
        for path in ('/banknotes', '/banknotes?history=0', '/banknotes?filter=heritage_us&history=0'):
            response = client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.get_data(as_text=True).count(label), 1)
        detail = client.get('/banknotes/legal').get_data(as_text=True)
        self.assertIn(label, detail)
        self.assertIn('April 1949', detail)
        self.assertIn(catalog.PUERTO_RICO_1928['source'], detail)
        self.assertNotIn(label, client.get('/banknotes/silver').get_data(as_text=True))
        row = self.db.execute("SELECT * FROM banknotes WHERE id='legal'").fetchone()
        self.assertEqual(stuff._us_note_class(row)['name'], 'United States Note (Legal Tender Note)')

    def test_periods_and_issuer_precedence(self):
        cases = [
            ('Canada', 2025, 'Bank of Canada', 'british'),
            ('Australia', 2025, 'Reserve Bank of Australia', 'british'),
            ('Bermuda', 1966, '', 'british'),
            ('Rhodesia', 1966, '', 'british'),
            ('Rhodesia & Nyasaland', 1960, '', 'british'),
            ('British Honduras', 1973, '', 'british'),
            ('Belize', 2021, 'Central Bank of Belize', 'other'),
            ('Algeria', 1914, "Banque de l’Algérie", 'french'),
            ('Algeria', 1964, "Banque Centrale d’Algérie", 'other'),
            ('Cuba', 1896, 'El Banco Español de la Isla de Cuba', 'spanish'),
            ('Cuba', 1958, 'Banco Nacional de Cuba', 'other'),
            ('Angola', 1973, 'Banco de Angola', 'portuguese'),
            ('Angola', 1999, 'Banco Nacional de Angola', 'other'),
            ('Macau', 1992, 'Banco Nacional Ultramarino', 'portuguese'),
            ('Macau', 2023, 'Banco Nacional Ultramarino', 'other'),
            ('Netherlands Indies', 1939, 'De Javasche Bank', 'dutch'),
            ('Netherlands Indies', 1944, 'The Japanese Government', 'japanese'),
            ('Indonesia', 1947, 'Republik Indonesia', 'other'),
            ('Burma', 1942, 'The Japanese Government', 'japanese'),
            ('Burma', 1938, 'Reserve Bank of India', 'british'),
            ('Belgian Congo', 1949, '', 'belgian'),
            ('German East Africa', 1917, '', 'german'),
            ('Italian Somaliland', 1950, 'Cassa per la Circolazione Monetaria della Somalia', 'italian'),
            ('Faroe Islands', 2011, '', 'danish'),
            ('New Hebrides', 1980, 'IEOM', 'joint'),
            ('Yemen', 1965, 'South Arabian Currency Authority', 'british'),
            ('Yemen', 1965, 'Yemen Currency Board', 'other'),
            ('Malawi', 1964, 'Reserve Bank of Malawi', 'other'),
            ('Cyprus', 1961, 'Republic of Cyprus Currency Board', 'other'),
            ('Egypt', 1917, 'National Bank of Egypt', 'british'),
            ('Egypt', 1958, 'Egyptian Government', 'other'),
            ('Tonga', 1966, 'Government of Tonga', 'british'),
            ('Thailand', 1943, '', 'other'),
            ('Atlantis', None, '', 'other'),
        ]
        for country, year, issuer, group in cases:
            with self.subTest(country=country, year=year, issuer=issuer):
                self.assertEqual(catalog.classify(country, year, issuer)['key'], group)

    def test_philippine_exception_preserves_periods(self):
        for year, issuer, phrase in [(1880, 'Banco Español Filipino', 'Spanish'),
                (1920, 'Philippine National Bank', 'American'),
                (1937, 'Philippine Treasury', 'Commonwealth'),
                (1944, 'The Japanese Government', 'Japanese occupation'),
                (1949, 'Central Bank of the Philippines', 'Republic')]:
            result = catalog.classify('Philippines', year, issuer)
            self.assertEqual(result['key'], 'us')
            self.assertIn(phrase, result['period'])

    def test_accurate_status_and_uncertainty(self):
        self.assertIn('Crown Dependency', catalog.classify('Guernsey', 2013)['period'])
        self.assertIn('protected state', catalog.classify('Maldives', 1960)['period'])
        self.assertIn('UN Trust Territory', catalog.classify('Italian Somaliland', 1950)['period'])
        self.assertIn('independence transition', catalog.classify('British East Africa', 1964)['period'])
        self.assertIn('independent', catalog.classify('Ceylon', 1959)['period'])
        self.assertTrue(catalog.classify('New Hebrides', 1980)['uncertain'])
        self.assertTrue(catalog.classify('French Guiana', 2026, 'CCFOM (Banque de la Guyane)')['uncertain'])
        self.assertTrue(catalog.classify('Hong Kong', 1997)['uncertain'])
        self.assertEqual(catalog.classify('Algeria', None)['key'], 'other')

    def test_aliases_do_not_merge_territories(self):
        for alias in ('Indochina', 'Indo China', 'Indo-China', 'French Indochina'):
            self.assertEqual(catalog.canonical_country(alias), 'French Indo-China')
            self.assertEqual(stuff.normalize_field_value('banknotes', 'country', alias), 'French Indo-China')
        for distinct in ('French Cochin-China', 'British Honduras', 'Belize',
                'Rhodesia', 'Southern Rhodesia', 'Northern Rhodesia', 'British Caribbean Territories',
                'East Caribbean States', 'West African States (Senegal)', 'Portuguese Timor',
                'Timor', 'South Vietnam', 'North Vietnam', 'Austro-Hungary'):
            self.assertEqual(catalog.canonical_country(distinct), distinct)

    def test_pennsylvania_alias_is_specific_to_the_colony(self):
        for alias in ('United States (Colonial - Pennsylvania)',
                      'United States (Colonial – Pennsylvania)', 'Pennsylvania Colony'):
            self.assertEqual(catalog.canonical_country(alias), 'Pennsylvania Colony')
            self.assertEqual(stuff.normalize_field_value('banknotes', 'country', alias),
                             'Pennsylvania Colony')
            self.assertEqual(stuff._canonical_banknote_country(alias), 'Pennsylvania Colony')
            self.assertEqual(stuff._coerce_banknote_spec('country', alias), 'Pennsylvania Colony')
            self.assertEqual(catalog.classify(alias, 1772, 'Province of Pennsylvania')['key'],
                             'british')
            self.assertEqual(stuff._country_key(alias), 'colonial-america')
        for distinct in ('Pennsylvania', 'Commonwealth of Pennsylvania', 'New Jersey',
                         'United States (Colonial - New Jersey)'):
            self.assertEqual(catalog.canonical_country(distinct), distinct)
        self.assertEqual(catalog.canonical_country('United States'), 'United States of America')
        self.assertEqual(catalog.classify('United States', 1928)['key'], 'us')

    def test_pennsylvania_migration_combines_panels_and_preserves_note_data(self):
        legacy = 'United States (Colonial - Pennsylvania)'
        self.add('pa1772', legacy, 1772, 'Province of Pennsylvania')
        self.add('pa1773', 'Pennsylvania Colony', 1773, 'General Assembly of Pennsylvania')
        self.add('modern', 'United States of America', 1928, 'United States Treasury')
        self.db.execute("UPDATE banknotes SET denomination='2 Shillings', pick_number='Fr#PA-156', "
                        "grade='Choice UNCEPQ 64', image_1='original-front.jpg' WHERE id='pa1772'")
        self.db.commit()
        before = dict(self.db.execute("SELECT * FROM banknotes WHERE id='pa1772'").fetchone())
        stuff._migrate_banknote_country_aliases(self.db)
        stuff._migrate_banknote_country_aliases(self.db)
        self.db.commit()
        after = dict(self.db.execute("SELECT * FROM banknotes WHERE id='pa1772'").fetchone())
        for field, value in before.items():
            if field not in ('country', 'updated_at'):
                self.assertEqual(after[field], value, field)
        self.assertEqual(after['country'], 'Pennsylvania Colony')
        history = self.db.execute("SELECT original_country,canonical_country FROM "
                                  "banknote_country_alias_history WHERE banknote_id='pa1772'").fetchall()
        self.assertEqual([tuple(row) for row in history], [(legacy, 'Pennsylvania Colony')])
        rows = self.db.execute("SELECT * FROM banknotes WHERE id LIKE 'pa%' ORDER BY date_1").fetchall()
        panels = stuff.series_panels(rows)
        self.assertEqual(panels['pa1772']['panel']['title'], 'Pennsylvania Colony')
        self.assertEqual(panels['pa1772']['panel']['now'], 'United States')
        self.assertEqual(panels['pa1772']['panel']['series_list'], ['1772', '1773'])
        self.assertNotIn('panel', panels.get('pa1773', {}))
        client = stuff.app.test_client()
        for path in ('/banknotes', '/banknotes?history=0', '/banknotes/pa1772'):
            response = client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertIn('Pennsylvania Colony', response.get_data(as_text=True))
            self.assertNotIn(legacy, response.get_data(as_text=True))
        for query in (legacy, 'Pennsylvania Colony'):
            html = client.get('/banknotes', query_string={'q': query}).get_data(as_text=True)
            self.assertIn('item-pa1772', html)
            self.assertIn('item-pa1773', html)
            self.assertNotIn('item-modern', html)
        response = client.post('/banknotes/pa1772/save-field',
                               json={'field': 'country', 'value': legacy})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.db.execute("SELECT country FROM banknotes WHERE id='pa1772'").fetchone()[0],
                         'Pennsylvania Colony')
        seed = stuff._finalize_sweep_seed({'country': legacy}, 'banknotes',
                                         {'role': 'owner'}, self.db, '2026-09-21')
        self.assertEqual(seed['country'], 'Pennsylvania Colony')
        self.assertEqual(self.db.execute("SELECT country FROM banknotes WHERE id='modern'").fetchone()[0],
                         'United States of America')

    def setUp(self):
        self.ctx = stuff.app.app_context(); self.ctx.push()
        self.db = stuff.get_db()
        self.db.execute('DELETE FROM banknotes'); self.db.commit()

    def tearDown(self):
        self.ctx.pop()

    def add(self, ident, country, year=1940, issuer=''):
        self.db.execute('INSERT INTO banknotes(id, country, date_1, issuer, denomination, status) VALUES(?,?,?,?,?,?)',
                        (ident, country, year, issuer, '5 Dollars', 'Own'))
        self.db.commit()

    def test_migration_is_idempotent_and_keeps_original(self):
        self.add('original', 'Indo China', 1940, 'Banque de l’Indochine')
        stuff._migrate_banknote_country_aliases(self.db)
        stuff._migrate_banknote_country_aliases(self.db)
        row = self.db.execute('SELECT * FROM banknotes').fetchone()
        self.assertEqual(row['country'], 'French Indo-China')
        self.assertEqual(row['issuer'], 'Banque de l’Indochine')
        history = self.db.execute('SELECT * FROM banknote_country_alias_history').fetchall()
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]['original_country'], 'Indo China')
        self.db.execute('DELETE FROM banknotes')
        self.assertEqual(self.db.execute('SELECT count(*) FROM banknote_country_alias_history').fetchone()[0], 0)

    def test_group_order_search_and_history_off(self):
        for ident, country, year, issuer in [
            ('a', 'Austria', 1922, ''), ('p', 'Philippines', 1944, 'The Japanese Government'),
            ('f', 'French Indo-China', 1940, 'Banque de l’Indochine'),
            ('b', 'Australia', 2025, 'Reserve Bank of Australia'),
            ('s', 'Cuba', 1896, 'Banco Español'), ('t', 'Angola', 1973, 'Banco de Angola')]:
            self.add(ident, country, year, issuer)
        with stuff.app.test_request_context('/banknotes'):
            stuff.g.current_user = {'role': 'owner'}
            sql, params = stuff.build_search_query('banknotes', '')
            self.assertEqual([r['id'] for r in self.db.execute(sql, params)], ['b', 'f', 's', 't', 'p', 'a'])
        client = stuff.app.test_client()
        for query in ('Indochina', 'Indo-China', 'Indo China', 'French Indochina'):
            response = client.get('/banknotes', query_string={'q': query, 'history': '0'})
            self.assertEqual(response.status_code, 200)
            text = response.get_data(as_text=True)
            self.assertIn('French Indo-China', text)
            self.assertIn('item-f', text)
            self.assertNotIn('item-a"', text)
        text = client.get('/banknotes?history=0').get_data(as_text=True)
        self.assertIn('data-banknote-group="british"', text)
        self.assertIn('data-banknote-group="other"', text)
        self.assertIn('Japanese occupation issue', text)
        text = client.get('/banknotes?filter=heritage_us&history=0').get_data(as_text=True)
        self.assertIn('item-p', text)
        self.assertNotIn('item-b"', text)
        self.assertIn('value="heritage_us" selected', text)

    def test_shared_helpers_keep_aliases_and_qualifiers(self):
        self.assertEqual(stuff._bn_country_label('Indochina'), 'French Indo-China')
        self.assertEqual(stuff._bn_country_label('West African States (Senegal)'), 'West African States (Senegal)')
        self.assertEqual(stuff._banknote_empire('Philippines', 1880), 'American')
        self.assertEqual(stuff._banknote_empire('Netherlands Indies', 1944, 'The Japanese Government'), 'Japanese')
        for alias in ('Indo China', 'Indochina', 'French Indo-China'):
            self.assertEqual(stuff._banknote_pin(alias, 1936)['city'], 'Hanoi')
            self.assertEqual(stuff._banknote_state_name(alias, 1936)['native'], 'Indochine française')

    def test_startup_migration_reseeds_and_preserves_alias(self):
        self.add('french', 'Indochina', 1940, 'Banque de l’Indochine')
        self.add('british', 'Australia', 2025)
        self.add('colonial', 'United States (Colonial - Pennsylvania)', 1772,
                 'Province of Pennsylvania')
        self.add('ny', 'United States of America', 1776, self.WATER_WORKS)
        self.db.execute("DELETE FROM migration_state WHERE key='banknote_display_number_v25'")
        self.db.commit()
        stuff.init_db()
        row = self.db.execute("SELECT country,banknote_id FROM banknotes WHERE id='french'").fetchone()
        self.assertEqual(tuple(row), ('French Indo-China', 'P 004'))
        self.assertEqual(self.db.execute("SELECT original_country FROM banknote_country_alias_history WHERE banknote_id='french'").fetchone()[0], 'Indochina')
        row = self.db.execute("SELECT country,banknote_id FROM banknotes WHERE id='colonial'").fetchone()
        self.assertEqual(tuple(row), ('Pennsylvania Colony', 'P 002'))
        row = self.db.execute("SELECT country,banknote_id,status FROM banknotes WHERE id='ny'").fetchone()
        self.assertEqual(tuple(row), ('New York Colony', 'P 001', 'Own'))

    def test_save_and_import_canonicalization_and_renumber(self):
        self.add('edit', 'Netherlands Indies', 1944, 'Netherlands Indies Government')
        self.add('british', 'Canada', 2025)
        client = stuff.app.test_client()
        response = client.post('/banknotes/edit/save-field', json={'field': 'country', 'value': 'Indo China'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.db.execute("SELECT country FROM banknotes WHERE id='edit'").fetchone()[0], 'French Indo-China')
        response = client.post('/banknotes/edit/save-field', json={'field': 'issuer', 'value': 'The Japanese Government'})
        self.assertEqual(response.status_code, 200)
        self.assertIn('issuer', stuff.BANKNOTE_SORT_FIELDS)
        self.assertEqual(self.db.execute("SELECT banknote_id FROM banknotes WHERE id='british'").fetchone()[0], 'P 001')
        seed = stuff._finalize_sweep_seed({'country': 'Indochina'}, 'banknotes', {'role': 'owner'}, self.db, '2026-09-20')
        self.assertEqual(seed['country'], 'French Indo-China')


if __name__ == '__main__':
    unittest.main()
