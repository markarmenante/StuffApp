"""Catalog-led matching, ambiguity guards, migration and ownership isolation."""
from fractions import Fraction
from pathlib import Path
import sqlite3
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import ebay_matching as matching
import ebay_orders as ebay


def note(**changes):
    return dict(dict(id='n1', cat_id='B001', country='Hong Kong', denomination='1 Dollar',
                     pick_number='P-316', other_catalog='', date_1=1940, date_2=None,
                     grade_numeric=66, grading_authority='PMG', series='',
                     status='Ordered', vendor='', purchase_date=None, serial_number='', slab_number=''), **changes)


def order(**changes):
    return dict(dict(line_key='o1', item_id='123456789012', order_id='12-34567-89012',
                     title='Hong Kong 1 Dollar 1940 P-316 PMG 66 EPQ', seller='dealer', seller_key='',
                     quantity=1, delivery_status='Shipped', ordered_at=None, shipped_at='2026-09-20T12:00:00Z',
                     delivered_at=None, estimated_delivery=None, attention='', ignored=0,
                     last_seen='2026-09-22T12:00:00Z', tracking=[]), **changes)


class IdentityTests(unittest.TestCase):
    def plan(self, notes=None, orders=None, links=None, sources=None):
        return matching.plan_matches(notes or [note()], orders or [order()], links or [], sources)

    def test_catalog_without_listing_or_purchase_metadata(self):
        auto, _ = self.plan()
        self.assertEqual(auto['o1']['banknote_id'], 'n1')
        self.assertIn('Catalog number', auto['o1']['evidence'])
        # The catalogue, country and denomination suffice when other fields are absent.
        auto, _ = self.plan(orders=[order(title='Hong Kong 1 Dollar Pick 316')])
        self.assertIn('o1', auto)

    def test_country_namespace_and_suffix_are_not_interchangeable(self):
        for changes in [dict(country='Australia'), dict(pick_number='P-316a'),
                        dict(pick_number='BC-316'), dict(pick_number='P-316b')]:
            with self.subTest(changes=changes):
                title = 'Hong Kong 1 Dollar P-316a PMG 66 EPQ'
                auto, _ = self.plan(notes=[note(**changes)], orders=[order(title=title)])
                self.assertEqual(bool(auto), changes == dict(pick_number='P-316a'))

    def test_catalog_normalization_keeps_varieties_and_excludes_serial_label(self):
        for raw, expected in [('P-20-C', '20c'), ('Pick 13 c', '13c'), ('P50r1', '50r1'),
                              ('Pick# J130b', 'j130b'), ('P56 S/N 000050', '56')]:
            self.assertEqual(matching.catalogs(raw), {'p': {expected}})
        self.assertEqual(matching.catalogs('Fr.#785'), {'fr': {'785'}})
        self.assertEqual(matching.catalogs('PM0125 pick 160d'), {'p': {'160d'}})
        self.assertEqual(matching.profile('Lebanon 10 Piastres 1950 Pick-47 GEM UNC PMG 66 EPQ')['grades'], {66})
        self.assertEqual(matching.profile('Indonesia 10 Sen 1947 PMG MS 64 Choice UNC')['grades'], {64})
        self.assertEqual(matching.profile('P-50c Hong Kong 1 Dollar PMG 66')['denominations'], {(Fraction(1), 'dollar')})
        self.assertEqual(matching.denominations('1/0 Dollars'), set())

    def test_variety_omitted_requires_other_identity_evidence(self):
        auto, _ = self.plan(notes=[note(pick_number='P-316a')])
        self.assertIn('o1', auto)
        auto, suggestions = self.plan(notes=[note(pick_number='P-316a')],
                                      orders=[order(title='Hong Kong 1 Dollar P-316')])
        self.assertFalse(auto)
        self.assertTrue(suggestions)

    def test_hard_conflicts_prevent_match(self):
        for changes in [dict(grade_numeric=65), dict(grading_authority='PCGS'),
                        dict(date_1=1956), dict(denomination='5 Dollars'),
                        dict(purchase_date='2025-01-01')]:
            with self.subTest(changes=changes):
                auto, _ = self.plan(notes=[note(**changes)],
                                    orders=[order(ordered_at='2026-09-20T00:00:00Z')])
                self.assertFalse(auto)

    def test_owned_duplicate_competes_and_grade_disambiguates(self):
        auto, _ = self.plan(notes=[note(), note(id='n2', status='Own')])
        self.assertFalse(auto)
        auto, _ = self.plan(notes=[note(), note(id='n2', status='Own', grade_numeric=65)])
        self.assertEqual(auto['o1']['banknote_id'], 'n1')
        auto, _ = self.plan(notes=[note(), note(id='n2', status='Own', grade_numeric=None)])
        self.assertFalse(auto)

    def test_two_different_purchases_compete_for_one_note(self):
        auto, _ = self.plan(orders=[order(), order(line_key='o2', item_id='999999999999')])
        self.assertFalse(auto)
        auto, _ = self.plan(orders=[order(), order(line_key='o2')])
        self.assertFalse(auto)

    def test_review_exclusions_quantity_and_bundles(self):
        for changes in [dict(ignored=1), dict(quantity=2), dict(attention='Cancelled'),
                        dict(title='Lot of 2 Hong Kong 1 Dollar P-316 PMG 66'),
                        dict(title='Hong Kong 1 Dollar P-316 PMG 66 3 Consecutive Serial Banknotes Set')]:
            with self.subTest(changes=changes):
                auto, suggestions = self.plan(orders=[order(**changes)])
                self.assertFalse(auto)
                self.assertFalse(suggestions)

    def test_existing_source_and_manual_links_are_respected(self):
        auto, _ = self.plan(sources={'999999999999': {'n1'}})
        self.assertFalse(auto)
        auto, _ = self.plan(links=[{'banknote_id': 'n1', 'line_key': 'o1', 'matched_by': 'manual'}])
        self.assertFalse(auto)
        auto, _ = self.plan(notes=[note(status='Sold')])
        self.assertFalse(auto)

    def test_non_catalog_fallback_needs_all_purchase_checks(self):
        n = note(vendor='Dealer', purchase_date='2026-09-20')
        o = order(title='Hong Kong 1 Dollar 1940 PMG 66 EPQ', ordered_at='2026-09-21T01:00:00Z')
        self.assertTrue(self.plan(notes=[n], orders=[o])[0])
        n['vendor'] = ''
        self.assertFalse(self.plan(notes=[n], orders=[o])[0])

    def test_serial_conflict_and_exact_certificate(self):
        o = order(title='Hong Kong 1 Dollar P-316 S/N A123456 PMG 66')
        self.assertFalse(self.plan(notes=[note(serial_number='A654321')], orders=[o])[0])
        self.assertTrue(self.plan(notes=[note(serial_number='A123456')], orders=[o])[0])
        n = note(slab_number='1234567-001')
        o = order(title='Hong Kong 1 Dollar PMG 66 1234567-001')
        self.assertIn('Certificate number', self.plan(notes=[n], orders=[o])[0]['o1']['evidence'])

    def test_catalog_country_inference_and_year_ranges(self):
        n = note(country='Canada', pick_number='BC-25b', denomination='20 Dollars', date_1=1937)
        o = order(title='1937 $20 BC-25b PMG 66')
        self.assertTrue(self.plan(notes=[n], orders=[o])[0])
        self.assertIn('1967', matching.profile('New Zealand 1960 ~7 5 Pounds')['years'])
        self.assertEqual(matching.denominations('$0.50'), {(Fraction(1, 2), 'dollar'), (Fraction(50), 'cent')})


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:')
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.executescript((ROOT / 'schema.sql').read_text())
        ebay.init_schema(self.db)
        n = note(status='Own')
        self.db.execute('INSERT INTO banknotes (' + ','.join(n) + ') VALUES (' + ','.join('?' for _ in n) + ')', list(n.values()))
        ebay.apply_items(self.db, [order()], auto_match=False)
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def test_backfill_is_idempotent_and_never_changes_banknote_fields(self):
        before = tuple(self.db.execute('SELECT * FROM banknotes').fetchone())
        result = ebay.apply_items(self.db, [], source='Recovered eBay orders')
        self.assertEqual(result['matched'], 1)
        link = self.db.execute('SELECT * FROM banknote_ebay_links').fetchone()
        self.assertEqual(link['matched_by'], 'details')
        self.assertIn('Catalog number', link['match_evidence'])
        self.assertEqual(ebay.apply_items(self.db, [])['matched'], 0)
        self.assertEqual(tuple(self.db.execute('SELECT * FROM banknotes').fetchone()), before)
        self.assertEqual(self.db.execute('SELECT count(*) FROM ebay_status_events').fetchone()[0], 1)
        self.assertFalse(self.db.execute('PRAGMA foreign_key_check').fetchall())

    def test_old_schema_migration_preserves_links_and_overrides(self):
        self.db.execute('DROP TABLE banknote_ebay_links')
        self.db.execute("CREATE TABLE banknote_ebay_links (banknote_id TEXT PRIMARY KEY REFERENCES banknotes(id) ON DELETE CASCADE, line_key TEXT NOT NULL UNIQUE REFERENCES ebay_order_items(line_key) ON DELETE CASCADE, matched_by TEXT NOT NULL CHECK(matched_by IN ('listing','manual')), matched_at TEXT NOT NULL, manual_status TEXT CHECK(manual_status IN ('Ordered','Shipped','Delivered')))")
        self.db.execute("INSERT INTO banknote_ebay_links VALUES ('n1','o1','manual','2026-09-22','Ordered')")
        self.db.commit()
        before = tuple(self.db.execute('SELECT * FROM banknote_ebay_links').fetchone())
        ebay.init_schema(self.db)
        ebay.init_schema(self.db)
        after = tuple(self.db.execute('SELECT * FROM banknote_ebay_links').fetchone())
        self.assertEqual(after[:-1], before)
        self.assertEqual(after[-1], '')
        self.assertFalse(self.db.execute('PRAGMA foreign_key_check').fetchall())
        self.assertEqual(ebay.apply_items(self.db, [])['matched'], 0)


if __name__ == '__main__':
    unittest.main()
