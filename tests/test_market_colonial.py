import os,sys,tempfile,unittest,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ['DATA_DIR']=tempfile.mkdtemp(prefix='market-colonial-')
os.environ.pop('ANTHROPIC_API_KEY',None)
import market_colonial as policy
import banknote_catalog as catalog
import app as stuff

def note(country,year,**kw):
    return dict(country=country,date_1=year,empire='British',**kw)

class ColonialTests(unittest.TestCase):
    def test_bahrain_authorization_and_first_issues_share_collection_boundary(self):
        for year in (1964, 1965, 1967):
            for theme in ('colonial-worldwide', 'wantlist-british', 'entity-gap-british'):
                with self.subTest(year=year, theme=theme):
                    item = note('Bahrain', year, issuer='Bahrain Currency Board',
                                title='Bahrain 1 Dinar PMG 65', pick_number='P-4a',
                                theme=theme, entity_key='british-bahrain')
                    before = json.dumps(item, sort_keys=True)
                    self.assertEqual(policy.problem(item), '')
                    self.assertEqual(policy.administration_label(item),
                                     catalog.bahrain_issue('Bahrain', year, item['issuer'])['period'])
                    self.assertEqual(json.dumps(item, sort_keys=True), before)

    def test_bahrain_rejects_incompatible_issuer_unknown_and_late_issues(self):
        base = note('Bahrain', 1964, issuer='Bahrain Currency Board',
                    title='Bahrain 1 Dinar PMG 65', pick_number='P-4a',
                    theme='colonial-worldwide')
        for change in (
                dict(issuer='Bahrain Monetary Agency', pick_number='P-8a'),
                dict(issuer='Central Bank of Bahrain'), dict(issuer='BMA'),
                dict(issuer='Unknown bank'), dict(issuer=''), dict(date_1=1900),
                dict(date_1=None), dict(date_1='ND'), dict(date_1='1965–1967'),
                dict(date_1=1964.5), dict(date_1=True), dict(date_1=1971),
                dict(date_1=1972), dict(date_1=1973),
                dict(series='BMA issue'), dict(series='1971 issue'),
                dict(title='Bahrain 1972 1 Dinar PMG 65'),
                dict(title='Bahrain Monetary Agency 1 Dinar PMG 65'),
                dict(title='Bahrain BMA 1 Dinar PMG 65'),
                dict(title='Bahrain CBB 1 Dinar PMG 65')):
            with self.subTest(change=change):
                item = dict(base, **change)
                self.assertTrue(policy.problem(item))
                self.assertEqual(policy.administration_label(item), '')
        # A title can contradict an early date, but cannot provide a missing one.
        self.assertTrue(policy.problem(dict(base, date_1=None, title='Bahrain 1965 1 Dinar')))
        self.assertEqual(policy.administration_label(dict(base, empire='', theme='denominations',
                                                         title='Bahrain BMA 1 Dinar')), '')

    def test_bahrain_administration_cannot_widen_period_or_relabel_colony(self):
        admin = dict(kind='protectorate', name='British protected state', territory='Bahrain',
                     year_start=1861, year_end=1971, source='https://history.example/bahrain',
                     evidence='Synthetic source attribution for a Currency Board issue')
        base = note('Bahrain', 1964, issuer='Bahrain Currency Board',
                    title='Bahrain 1 Dinar PMG 65', pick_number='P-4a',
                    theme='colonial-worldwide', issue_year_start=1965, issue_year_end=1967,
                    issue_date_source='https://catalogue.example/bahrain-p4a', administration=admin)
        self.assertEqual(policy.problem(base), '')
        self.assertEqual(policy.administration_label(base),
                         'British administrative control — protected state')
        # Even supported additional-administration evidence cannot override
        # Bahrain's issuer and independence boundary (including broad searches).
        for change in (
                dict(date_1=1973, issuer='Bahrain Monetary Agency', pick_number='P-8a',
                     issue_year_start=1973, issue_year_end=1973,
                     administration=dict(admin, year_end=1975)),
                dict(administration=dict(admin, year_end=1975)),
                dict(issue_year_end=1971), dict(issue_year_start=1972, issue_year_end=1972),
                dict(issue_year_end=None), dict(issue_date_source=''),
                dict(title='Bahrain 1973 1 Dinar PMG 65')):
            with self.subTest(change=change):
                self.assertTrue(policy.problem(dict(base, **change)))
        mislabeled = dict(base, administration=dict(admin, kind='colony', name='British colony'))
        self.assertEqual(policy.problem(mislabeled), '')
        self.assertEqual(policy.administration_label(mislabeled),
                         'British administrative control — protected state')
        self.assertTrue(policy.problem(dict(base, issue_year_end=None, administration=None)))

    def test_bahrain_casing_cannot_bypass_independence_or_label_rule(self):
        for country in ('bahrain', 'BAHRAIN', 'Bahrain'):
            with self.subTest(country=country):
                admin = dict(kind='colony', name='British colony', territory=country,
                             year_start=1861, year_end=1971,
                             source='https://history.example/bahrain', evidence='Synthetic evidence')
                item = note(country, 1964, issuer='Bahrain Currency Board', pick_number='P-4a',
                            theme='colonial-worldwide', issue_year_start=1965, issue_year_end=1965,
                            issue_date_source='https://catalogue.example/bahrain-p4a', administration=admin)
                self.assertEqual(policy.problem(item), '')
                self.assertEqual(policy.administration_label(item),
                                 'British administrative control — protected state')
                late = dict(item, date_1=1973, issuer='Bahrain Monetary Agency',
                            issue_year_start=1973, issue_year_end=1973,
                            administration=dict(admin, year_end=1975))
                self.assertTrue(policy.problem(late))
                self.assertEqual(policy.administration_label(late), '')

    def test_period_boundaries_and_independent_issuers(self):
        for country,valid,end in [('Portuguese Guinea',1964,1973),('Angola',1972,1975),('Mozambique',1961,1975),('Algeria',1959,1962),('Tunisia',1950,1956),('India',1937,1947),('Canada',1860,1867),('Australia',1890,1901),('Ceylon',1940,1948)]:
            self.assertFalse(policy.problem(note(country,valid)),country)
            for year in (end,end+1,end+50,None):
                self.assertTrue(policy.problem(note(country,year)),(country,year))
        self.assertTrue(policy.problem(note('Ceylon',1940,issuer='Central Bank of Ceylon')))
        self.assertTrue(policy.problem(note('Australia',1890,series='Commonwealth of Australia')))
        self.assertTrue(policy.problem(note('Portuguese Guinea',1964,series='Reissue 1975')))
        self.assertTrue(policy.problem(note('Unknown Territory',1930)))
        self.assertTrue(policy.problem(note('West African States (Senegal)',1960,issuer='BCEAO')))

    def test_issue_range_and_victory_exception(self):
        data=note('Philippines',1944,title='500 pesos ND Victory',pick_number='P-101c')
        self.assertFalse(policy.problem(data))
        self.assertEqual(policy.victory_label(data),'Philippine Victory issue')
        cbp=dict(data,issuer='Central Bank of the Philippines',title='Victory overprint 1949',pick_number='P-121')
        self.assertFalse(policy.problem(cbp))
        self.assertIn('post-independence',policy.victory_label(cbp))
        missing=dict(cbp,pick_number='',series='Victory Series 66')
        self.assertFalse(policy.problem(missing))
        self.assertIn('post-independence',policy.victory_label(missing))
        self.assertFalse(policy.victory_label(dict(missing,issuer='Unknown bank')))
        self.assertFalse(policy.victory_label(dict(missing,pick_number='P-200')))
        for bad in (dict(data,pick_number='P-200',date_1=1960),dict(data,country='India',date_1=1960),dict(data,title='Victory replica',date_1=1960)):
            self.assertFalse(policy.victory_label(bad))
            self.assertTrue(policy.problem(bad))
        self.assertTrue(policy.problem(note('Philippines',1947,title='Republic of the Philippines')))
        self.assertTrue(policy.problem(note('Philippines',1944,title='Japanese occupation 500 pesos')))
        uncertain=note('Angola',1972,title='ND 100 escudos')
        self.assertTrue(policy.problem(uncertain))
        self.assertFalse(policy.problem(dict(uncertain,issue_year_start=1972,issue_year_end=1973,issue_date_source='https://catalogue.example/variety')))
        self.assertTrue(policy.problem(dict(uncertain,issue_year_start=1972,issue_year_end=1975,issue_date_source='https://catalogue.example/variety')))

    def test_domestic_and_collection_grouping_remain_separate(self):
        self.assertFalse(policy.problem(note('United States',1886,title='Martha Washington',theme='us-large-treasury')))
        self.assertTrue(policy.problem(note('United States',1886,theme='colonial-british')))
        self.assertFalse(policy.problem({'country':'Japan','date_1':1960,'empire':'','theme':'denominations'}))
        self.assertEqual(catalog.classify('Canada',1960)['key'],'british')
        self.assertEqual(catalog.classify('Australia',1960)['key'],'british')
        self.assertEqual(catalog.classify('Philippines',1960)['key'],'us')

    def test_entity_gap_hard_bounds_cannot_be_widened_by_administration(self):
        base = note('India', 1937, theme='entity-gap-british', entity_key='british-india',
                    issuer='Government of India', pick_number='P-18')
        self.assertFalse(policy.problem(base))
        for year in (1947, 1950, None):
            self.assertTrue(policy.problem(dict(base, date_1=year)), year)
        admin = dict(kind='colony', name='British India', territory='India',
                     year_start=1858, year_end=2000,
                     source='https://museum.example/india', evidence='Fixture issue attribution')
        widened = dict(base, administration=admin, issue_year_start=1937, issue_year_end=1937,
                       issue_date_source='https://museum.example/issue')
        self.assertIn('cutoff', policy.problem(widened))
        self.assertTrue(policy.problem(dict(widened, issue_year_end=1950)))
        # Honest administration history may name its transition year, but
        # actual issue-year evidence must stay strictly before that year.
        self.assertFalse(policy.problem(dict(widened, administration=dict(admin, year_end=1947))))
        self.assertTrue(policy.problem(dict(widened, issue_year_start=1947, issue_year_end=1947)))
        self.assertTrue(policy.problem(dict(base, title='Reissue 1950')))
        self.assertTrue(policy.problem(dict(base, title='ND 10 rupees')))
        self.assertTrue(policy.problem(dict(base, issue_year_start=1937)))
        self.assertTrue(policy.problem(dict(base, issue_year_start=1937, issue_year_end=1937)))

    def test_entity_gap_identity_is_primary_and_matches_requested_family(self):
        base = note('Puerto Rico', 1896, theme='entity-gap-other',
                    entity_key='spanish-puerto-rico', issuer='Banco Español de Puerto Rico')
        self.assertFalse(policy.problem(base))
        self.assertTrue(policy.problem(dict(base, date_1=1909)))
        self.assertTrue(policy.problem(dict(base, entity_key='british-india')))
        self.assertTrue(policy.problem(dict(base, entity_key='')))
        self.assertTrue(policy.problem(dict(base, theme='entity-gap-british')))
        burma = note('Burma', 1943, theme='entity-gap-british', entity_key='british-burma',
                     issuer='Japanese Government')
        self.assertTrue(policy.problem(burma))
        regional = note('Malaya and British Borneo', 1955, theme='entity-gap-british',
                        entity_key='british-british-north-borneo',
                        issuer='Board of Commissioners of Currency, Malaya and British Borneo')
        self.assertTrue(policy.problem(regional), 'regional coverage is not a territorial issue identity')
        for country, key, year in (
                ('British North Borneo', 'british-british-north-borneo', 1953),
                ('Sarawak', 'british-sarawak', 1959),
                ('Brunei', 'british-brunei', 1968),
                ('Malaya', 'british-malaya', 1955)):
            disguised = dict(regional, country=country, entity_key=key, date_1=year)
            self.assertIn('Shared Malaya', policy.problem(disguised), country)
        self.assertIn('Shared Malaya', policy.problem(dict(regional,
            country='British North Borneo', issuer='The Board of Commissioners of Currency')))
        self.assertFalse(policy.problem(note('British North Borneo', 1935,
            theme='entity-gap-british', entity_key='british-british-north-borneo',
            issuer='British North Borneo Chartered Company')))

        for country, key in (('Pitcairn Islands', 'british-pitcairn-islands'),
                             ('Nyassa Company', 'portuguese-nyassa-company'),
                             ('East Caribbean States', 'british-east-caribbean-states')):
            self.assertTrue(policy.problem(note(country, 1930, theme='entity-gap-british', entity_key=key)))

    def test_entity_gap_contract_does_not_change_legacy_or_victory_searches(self):
        legacy = note('India', 1937, theme='wantlist-british', issuer='Government of India')
        self.assertFalse(policy.problem(legacy), 'legacy saved cards have no entity_key')
        victory = note('Philippines', 1949, title='Victory CBP overprint',
                       issuer='Central Bank of the Philippines', pick_number='P-121',
                       theme='colonial-other')
        self.assertFalse(policy.problem(victory))
        self.assertTrue(policy.problem(dict(victory, theme='entity-gap-other', entity_key='us-philippines')))
        self.assertFalse(policy.problem(note('United States', 1886, theme='us-large-treasury')))
        self.assertTrue(policy.problem(note('United States', 1886, theme='entity-gap-other',
                                            entity_key='us-united-states')))

    def test_polynesian_coverage_alias_accepts_the_same_lineage_without_widening_dates(self):
        base = dict(country='French Polynesia', date_1=1973, empire='French',
                    issuer="Institut d'Émission d'Outre-Mer (IEOM)", pick_number='P-24b',
                    theme='entity-gap-french', entity_key='french-french-oceania',
                    issue_year_start=1973, issue_year_end=1973,
                    issue_date_source='https://catalogue.example/polynesia-24b',
                    administration=dict(kind='dependency', name='French Polynesia',
                        territory='French Polynesia', year_start=1957, year_end=2026,
                        source='https://history.example/polynesia',
                        evidence='Continuing French collectivity; exact issue reviewed'))
        before = json.dumps(base, sort_keys=True)
        self.assertFalse(policy.problem(base))
        self.assertEqual(json.dumps(base, sort_keys=True), before)
        # The older saved key remains accepted on its own original 1957+ scope.
        self.assertFalse(policy.problem(dict(base, entity_key='french-french-polynesia')))
        for country in ('New Caledonia', 'French Pacific Territories', 'New Hebrides'):
            self.assertIn('requested historical entity', policy.problem(dict(base, country=country)))
        for issuer in ('Unknown bank', "Banque de l'Indochine, Nouméa", 'BEAC'):
            self.assertIn('requested historical entity', policy.problem(dict(base, issuer=issuer)))
        # Even model-supplied broad administration dates cannot widen the
        # primary French Polynesia period down to the shared lineage's 1905.
        broad_admin = dict(base['administration'], year_start=1905)
        for year in (1904, 1950, 1956):
            for key in ('french-french-oceania', 'french-french-polynesia'):
                self.assertIn('reviewed pre-independence period', policy.problem(dict(
                    base, date_1=year, issue_year_start=year, issue_year_end=year,
                    entity_key=key, administration=broad_admin)))
        self.assertTrue(policy.problem(dict(base, issue_year_start=1956, issue_year_end=1973)))
        self.assertTrue(policy.problem(dict(base, issue_date_source='')))
        self.assertTrue(policy.problem(dict(base, theme='entity-gap-british')))

    def test_saved_legacy_wantlist_cards_remain_visible_without_new_entity_key(self):
        with stuff.app.app_context():
            db = stuff.get_db()
            db.execute("INSERT INTO market_scans(id,category,status,started_at) "
                       "VALUES('entity-compat','banknotes','done',datetime('now'))")
            base = note('India', 1937, title='India 10 rupees 1937', issuer='Government of India',
                        pick_number='P-18', listing_url='https://dealer.example/item/legacy')
            fixtures = (
                ('entity-legacy-card', dict(base, theme='wantlist-british')),
                ('entity-new-card', dict(base, theme='entity-gap-british', entity_key='british-india',
                                         listing_url='https://dealer.example/item/new')),
                ('entity-wrong-card', dict(base, theme='entity-gap-british', entity_key='spanish-cuba',
                                           listing_url='https://dealer.example/item/wrong')),
            )
            try:
                for ident, payload in fixtures:
                    db.execute("INSERT INTO market_scan_items(id,scan_id,category,status,payload,created_at) "
                               "VALUES(?,'entity-compat','banknotes','new',?,datetime('now'))",
                               (ident, json.dumps(payload)))
                db.commit()
                visible = {item['id'] for item in stuff._market_items(db, 'banknotes')}
                self.assertIn('entity-legacy-card', visible)
                self.assertIn('entity-new-card', visible)
                self.assertNotIn('entity-wrong-card', visible)
                self.assertEqual(db.execute("SELECT status FROM market_scan_items WHERE id='entity-legacy-card'").fetchone()[0], 'new')
            finally:
                db.execute("DELETE FROM market_scan_items WHERE scan_id='entity-compat'")
                db.execute("DELETE FROM market_scans WHERE id='entity-compat'")
                db.commit()

    def test_entity_gap_normalization_preserves_identity_and_rejects_late_offers(self):
        with stuff.app.app_context():
            db = stuff.get_db()
            raw = dict(country='India', year=1937, title='India 10 rupees 1937 PMG64',
                       issuer='Government of India', pick_number='P-18', empire='British',
                       entity_key='british-india', theme='entity-gap-british',
                       grade_numeric=64, grading_authority='PMG', price='$100',
                       listing_url='https://dealer.example/item/entity-gap')
            accepted = stuff._market_normalize_item(db, 'banknotes', raw)
            self.assertIsNotNone(accepted)
            self.assertEqual(accepted['entity_key'], 'british-india')
            self.assertIsNone(stuff._market_normalize_item(db, 'banknotes', dict(raw, year=1950)))
            self.assertIsNone(stuff._market_normalize_item(db, 'banknotes', dict(raw, entity_key='spanish-cuba')))
            self.assertIsNone(stuff._market_normalize_item(db, 'banknotes', dict(raw, title='India specimen PMG64')))
            prompt = stuff._market_scan_prompt('banknotes', 'entity-gap-british', 'Fixture scope', '', '')
            self.assertIn('"entity_key"', prompt)

    def test_normalization_and_saved_candidates_use_same_gate(self):
        with stuff.app.app_context():
            db=stuff.get_db()
            raw={'title':'Angola 100 escudos 1980 PMG64','country':'Angola','year':1980,'empire':'Portuguese','grade_numeric':64,'grading_authority':'PMG','price':'$100','listing_url':'https://dealer.example/item/123'}
            self.assertIsNone(stuff._market_normalize_item(db,'banknotes',raw))
            db.execute("INSERT INTO market_scans(id,category,status,started_at) VALUES('colonial','banknotes','done',datetime('now'))")
            for ident,year in [('valid',1964),('independent',1980),('uncertain',1973)]:
                payload=note('Portuguese Guinea',year,title='BNU 1000 escudos',listing_url='https://dealer.example/item/'+ident)
                db.execute("INSERT INTO market_scan_items(id,scan_id,category,status,payload,created_at) VALUES(?,'colonial','banknotes','new',?,datetime('now'))",(ident,json.dumps(payload)))
            db.commit()
            self.assertEqual([x['id'] for x in stuff._market_items(db,'banknotes')],['valid'])
            self.assertEqual(db.execute("SELECT status FROM market_scan_items WHERE id='independent'").fetchone()[0],'unavailable')

if __name__=='__main__':unittest.main()
