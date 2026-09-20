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
