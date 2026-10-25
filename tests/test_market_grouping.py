"""Issuer-first market grouping preserves listing identity, policy and source labels."""
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import types
import unittest
from datetime import datetime
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['DATA_DIR'] = tempfile.mkdtemp(prefix='market-grouping-')
os.environ.pop('ANTHROPIC_API_KEY', None)
sys.modules['dotenv'] = types.SimpleNamespace(load_dotenv=lambda **kwargs: None)
import app as stuff
import market_grouping as grouping
import market_ebay_feed as feed


def note(ident, **fields):
    return dict(id=ident, title='Silver Certificate', country='USA', series='1934A',
                listing_url='https://example.test/item/' + ident, **fields)


class GroupingTests(unittest.TestCase):
    def test_gathers_interleaved_peers_retaining_first_group_and_listing_rank(self):
        rows=[note('a'), dict(note('b'), country='French Indochina', series='1939'),
              note('c'), dict(note('d'), country='French Indo-China', series='1939')]
        before=copy.deepcopy(rows)
        result=stuff._market_group_rows('banknotes',rows)
        self.assertEqual([r['id'] for r in result],['a','c','b','d'])
        self.assertEqual([r['_market_group']['heading'] for r in result],[True,False,True,False])
        self.assertEqual([r['_market_group']['count'] for r in result],[2,2,2,2])
        self.assertEqual(rows,before)
        self.assertTrue(all(r is not rows[i] for i,r in enumerate(result)))
        self.assertEqual(result[0]['_market_group']['key'],stuff._market_group_rows('banknotes',[rows[2]])[0]['_market_group']['key'])

    def test_series_suffix_and_us_note_type_stay_distinct(self):
        rows=[note('a'), dict(note('b'),series='Series of 1934 A'),
              dict(note('c'),series='1934'), dict(note('d'),series='1934B'),
              dict(note('e'),title='Gold Certificate')]
        result=stuff._market_group_rows('banknotes',rows)
        groups={r['id']:r['_market_group'] for r in result}
        self.assertEqual(groups['a']['key'],groups['b']['key'])
        self.assertEqual(len({g['key'] for g in groups.values()}),4)
        self.assertIn('Silver Certificate',groups['a']['title'])
        self.assertIn('Gold Certificate',groups['e']['title'])
        self.assertIn('1934A',groups['a']['title'])

    def test_aliases_do_not_merge_historical_successor_countries_or_references(self):
        rows=[dict(note('a'),country='British Honduras',series='1960',pick_number='P-1'),
              dict(note('b'),country='Belize',series='1960',pick_number='P-1'),
              dict(note('c'),country='British Honduras',series='1960',pick_number='P-2a')]
        result=stuff._market_group_rows('banknotes',rows)
        self.assertEqual([r['id'] for r in result],['a','c','b'])
        self.assertEqual([r['pick_number'] for r in result],['P-1','P-2a','P-1'])
        self.assertEqual(len(result),3)

    def test_coin_regions_use_catalogue_rules_without_mutating_fields(self):
        rows=[dict(id='a',region='Attica',mint='Aegina'),dict(id='b',region='Attica',mint='Athens'),
              dict(id='c',region='Islands off Attica',authority='Aegina'),dict(id='d',region=''),
              dict(id='e',region='Corinth')]
        before=copy.deepcopy(rows)
        result=stuff._market_group_rows('coins',rows)
        self.assertEqual([r['id'] for r in result],['a','c','b','d','e'])
        self.assertEqual(result[0]['_market_group']['title'],'Islands off Attica')
        self.assertEqual(result[2]['_market_group']['title'],'Attica')
        self.assertEqual(result[3]['_market_group']['title'],'Region not specified')
        self.assertEqual(result[4]['_market_group']['title'],'Corinthia')
        self.assertEqual(rows,before)
        self.assertEqual(result[0]['region'],'Attica')

    def test_unknown_series_is_explicit_and_does_not_guess_from_year(self):
        result=stuff._market_group_rows('banknotes',[dict(id='a',country='France',date_1=1934),dict(id='b')])
        self.assertEqual(result[0]['_market_issuer']['title'],'Unknown issuer · France')
        self.assertEqual(result[1]['_market_issuer']['title'],'Unknown issuer · Country not specified')
        self.assertEqual(result[0]['_market_group']['title'],'Issued 1934 · Series not specified · Catalogue not specified')
        self.assertEqual(result[1]['_market_group']['title'],'Series not specified · Catalogue not specified')
        self.assertEqual(grouping.observed_series('France 1934 100 Francs PMG 65'),'')
        self.assertEqual(grouping.observed_series('Series of 1934 A Silver Certificate PMG 65'),'1934A')
        self.assertEqual(grouping.observed_series('Philippines Victory Series P-96'),'Victory')
        self.assertEqual(grouping.observed_series('Series 1934-1935 date range'),'')

    def test_explicit_named_series_number_is_retained_without_borrowing_grade_or_date(self):
        self.assertEqual(grouping.observed_series('Philippines 1944 Victory Series 66 PMG 65 EPQ'),'Victory Series 66')
        self.assertEqual(grouping.observed_series('Philippines Victory Series No. 66A PMG 65'),'Victory Series 66A')
        self.assertEqual(grouping.observed_series('Philippines 1944 Victory Series PMG 66 EPQ'),'Victory')
        rows=[dict(id=str(i),country='Philippines',title=title) for i,title in enumerate((
            'Victory Series 66 PMG 65','Victory Series 67 PMG 65','Victory Series PMG 66'))]
        result=stuff._market_group_rows('banknotes',rows,observed=True)
        self.assertEqual(len({row['_market_group']['key'] for row in result}),3)

    def test_issuer_leads_across_series_with_country_and_unknown_boundaries(self):
        rows=[dict(note('a'),issuer='Government',country='France',series='1935'),
              dict(note('b'),issuer='Another Bank',country='France',series='1934'),
              dict(note('c'),issuer='  GOVERNMENT  ',country='France',series='1934'),
              dict(note('d'),issuer='Government',country='French Indochina',series='1934'),
              dict(note('e'),issuer='',country='France'),
              dict(note('f'),issuer='Unknown issuer',country='France')]
        before=copy.deepcopy(rows)
        result=stuff._market_group_rows('banknotes',rows)
        self.assertEqual([row['id'] for row in result],['c','a','b','d','e','f'])
        groups={row['id']:row['_market_issuer'] for row in result}
        self.assertEqual(groups['a']['key'],groups['c']['key'])
        self.assertNotEqual(groups['a']['key'],groups['d']['key'])
        self.assertNotEqual(groups['a']['key'],groups['e']['key'])
        self.assertEqual(groups['e']['key'],groups['f']['key'])
        self.assertEqual([r['_market_issuer']['heading'] for r in result],[True,False,True,True,True,False])
        self.assertEqual(groups['a']['count'],2)
        self.assertEqual(rows,before)

    def test_live_legal_tender_issuer_alias_shares_treasury_heading_only(self):
        rows=[dict(note('legacy'),issuer='United States (Legal Tender Note)',
                   title='1917 United States $1 Legal Tender Note',series='1917',pick_number='Fr.39'),
              dict(note('treasury'),issuer='United States Treasury',
                   title='1907 United States $5 Legal Tender Note',series='1907',pick_number='Fr.91')]
        before=copy.deepcopy(rows)
        result=stuff._market_group_rows('banknotes',rows)
        self.assertEqual([r['id'] for r in result],['treasury','legacy'])
        self.assertEqual(len({r['_market_issuer']['key'] for r in result}),1)
        self.assertEqual(result[0]['_market_issuer']['title'],
                         'United States Treasury · United States of America')
        self.assertEqual(result[0]['_market_issuer']['count'],2)
        self.assertEqual(len({r['_market_group']['key'] for r in result}),2)
        self.assertTrue(all('United States Note (Legal Tender Note)' in r['_market_group']['title'] for r in result))
        self.assertEqual(rows,before)
        self.assertEqual({r['id']:r['issuer'] for r in result},{r['id']:r['issuer'] for r in before})

    def test_treasury_aliases_require_us_country_and_preserve_bank_issuers(self):
        aliases=('US Treasury','U.S. Treasury','United States Treasury',
                 'Treasury of United States','Treasury of the United States')
        rows=[dict(note(str(i)),issuer=issuer) for i,issuer in enumerate(aliases)]
        rows.extend([
            dict(note('federal'),issuer='Federal Reserve Bank of New York',title='Federal Reserve Bank Note'),
            dict(note('national'),issuer='First National Bank of Boston',title='National Bank Note'),
            dict(note('generic'),issuer='United States'),
            dict(note('unknown'),issuer=''),
            dict(note('foreign'),country='Philippines',issuer='US Treasury'),
            dict(note('contradiction'),issuer='United States (Legal Tender Note)',title='National Bank Note'),
        ])
        before=copy.deepcopy(rows)
        result=stuff._market_group_rows('banknotes',rows)
        groups={r['id']:r['_market_issuer'] for r in result}
        treasury=groups['0']['key']
        self.assertTrue(all(groups[str(i)]['key']==treasury for i in range(len(aliases))))
        self.assertEqual(groups['0']['count'],len(aliases))
        self.assertTrue(all(groups[name]['key']!=treasury for name in
                            ('federal','national','generic','unknown','foreign','contradiction')))
        self.assertNotEqual(groups['federal']['key'],groups['national']['key'])
        self.assertEqual(groups['generic']['title'],'United States · United States of America')
        self.assertEqual(rows,before)
        # Without a classified note type, the legacy label stays literal.
        raw=[dict(note('unclassified'),issuer='United States (Legal Tender Note)')]
        self.assertTrue(grouping.group_rows(raw,'banknotes')[0]['_market_issuer']['title'].startswith(
            'United States (Legal Tender Note) ·'))

    def test_catalogue_types_separate_but_equivalent_references_and_grades_gather(self):
        base=dict(country='British Honduras',issuer='Government of British Honduras',series='1960')
        rows=[dict(note('a'),**base,pick_number='P-1a',denomination='1 Dollar',grade='65',serial_number='AAA'),
              dict(note('b'),**base,pick_number='P-1b',denomination='1 Dollar'),
              dict(note('c'),**base,pick_number='Pick 1a',other_catalog='B101',denomination='$1',grade='67',serial_number='BBB'),
              dict(note('d'),**base,pick_number='',denomination='1 Dollar')]
        result=stuff._market_group_rows('banknotes',rows)
        groups={r['id']:r['_market_group'] for r in result}
        self.assertEqual(groups['a']['key'],groups['c']['key'])
        self.assertEqual(groups['a']['count'],2)
        self.assertNotEqual(groups['a']['key'],groups['b']['key'])
        self.assertNotEqual(groups['a']['key'],groups['d']['key'])
        self.assertEqual(len({r['_market_issuer']['key'] for r in result}),1)
        self.assertIn('Catalogue not specified',groups['d']['title'])

    def test_year_and_numeric_denomination_sort_without_rewriting_values(self):
        rows=[]
        for ident,year,denom in [('ten',1935,'$10'),('pound',1935,'1 Pound'),
                                ('one',1935,'1 Dollar'),('cents',1935,'50 Cents'),
                                ('old',1934,'100 Dollars'),('blank',1935,'')]:
            rows.append(dict(note(ident),country='British Honduras',issuer='Government',
                             series='Currency Board issues',date_1=year,denomination=denom))
        before=copy.deepcopy(rows)
        result=stuff._market_group_rows('banknotes',rows)
        self.assertEqual([r['id'] for r in result],['old','cents','one','ten','pound','blank'])
        self.assertEqual(rows,before)

    def test_mixed_sources_share_explicit_issuer_and_type_without_changing_actions(self):
        candidate=dict(note('scan'),issuer='US Treasury',pick_number='Fr.1604',
                       _market_card_kind='candidate',status='new')
        observed=dict(note('card'),issuer='US Treasury',title='Series of 1934 A Silver Certificate',
                      pick_number='Friedberg1604',series='untrusted field',_market_card_kind='observed',
                      item_id='123456789012',sources=['watched','sponsored'],availability_label='Availability unverified')
        unknown=dict(observed,id='unknown',item_id='123456789013',issuer='')
        before=copy.deepcopy([candidate,observed,unknown])
        result=stuff._market_group_rows('banknotes',[candidate,unknown,observed])
        self.assertEqual([r['id'] for r in result],['scan','card','unknown'])
        self.assertEqual(result[0]['_market_group']['key'],result[1]['_market_group']['key'])
        self.assertEqual(result[0]['_market_issuer']['count'],2)
        self.assertNotEqual(result[1]['_market_issuer']['key'],result[2]['_market_issuer']['key'])
        self.assertEqual(result[1]['sources'],['watched','sponsored'])
        self.assertEqual(result[1]['item_id'],'123456789012')
        self.assertEqual(result[1]['availability_label'],'Availability unverified')
        self.assertEqual([candidate,observed,unknown],before)

    def test_unknown_series_uses_explicit_date_without_fabricating_series(self):
        rows=[dict(note('old'),issuer='Government',series='',date_1=1900),
              dict(note('new'),issuer='Government',series='',date_1=1960)]
        result=stuff._market_group_rows('banknotes',rows)
        self.assertNotEqual(result[0]['_market_group']['key'],result[1]['_market_group']['key'])
        self.assertTrue(all('Series not specified' in r['_market_group']['title'] for r in result))
        self.assertEqual([r['series'] for r in result],['',''])


class MarketRouteTests(unittest.TestCase):
    def setUp(self):
        self.ctx=stuff.app.app_context();self.ctx.push()
        self.db=stuff.get_db();self.client=stuff.app.test_client()
        for table in ('ebay_market_card_sources','ebay_market_cards','ebay_market_requests',
                      'market_scan_items','market_scans','market_dismissals','ebay_purchase_account'):
            self.db.execute('DELETE FROM '+table)
        self.db.commit()

    def tearDown(self):
        self.ctx.pop()

    def test_current_and_earlier_market_routes_group_without_changing_storage(self):
        now=datetime.utcnow().isoformat()
        for cat in ('coins','banknotes'):
            self.db.execute('INSERT INTO market_scans(id,category,started_at,finished_at,status) VALUES(?,?,?,?,?)',(cat,cat,now,now,'done'))
            for status in ('new','superseded'):
                for rank,region in enumerate(('Attica','Ionia','Attica')):
                    ident=cat+status+str(rank)
                    payload=dict(note(ident),region=region,series='1934A' if rank!=1 else '1935',grade_numeric=65)
                    self.db.execute('INSERT INTO market_scan_items(id,scan_id,category,rank,status,payload,created_at) VALUES(?,?,?,?,?,?,?)',
                                    (ident,cat,cat,rank,status,json.dumps(payload),now))
        self.db.commit()
        before=[tuple(r) for r in self.db.execute('SELECT id,rank,payload FROM market_scan_items ORDER BY id')]
        for cat in ('coins','banknotes'):
            for suffix,status in (('','new'),('?earlier=1','superseded')):
                with patch.object(stuff,'render_template',return_value='fixture') as render:
                    response=self.client.get('/'+cat+'/market'+suffix)
                self.assertEqual(response.status_code,200)
                rows=render.call_args.kwargs['rows']
                self.assertEqual([r['id'] for r in rows],[cat+status+str(n) for n in (0,2,1)])
                self.assertEqual([r['_market_group']['count'] for r in rows],[2,2,1])
        after=[tuple(r) for r in self.db.execute('SELECT id,rank,payload FROM market_scan_items ORDER BY id')]
        self.assertEqual(before,after)

    def test_observed_feed_grouping_preserves_unverified_state_sources_and_warnings(self):
        with patch.dict(os.environ,STUFFAPP_TODAY_TOKEN='fixture-'+'x'*32,RAILWAY_SERVICE_NAME='web'):
            self.db.execute("INSERT INTO ebay_purchase_account VALUES(1,'fixture-owner')");self.db.commit()
            ident=feed.queue(self.db)
            self.db.execute("UPDATE ebay_market_requests SET status='reading' WHERE id=?",(ident,));self.db.commit()
            cards=[]
            for i,title in enumerate(('Fr.1604 Series 1934 A Silver Certificate','Fr.2300 Series 1934 Gold Certificate',
                                      'Fr.1605 Series of 1934A Silver Certificate')):
                cards.append(dict(item_id=str(123456789012+i),title=title,listing_url='https://www.ebay.com/itm/'+str(123456789012+i),
                                  price='$100',image_url='',sources=['watched','sponsored'],source_label='Observed fixture',
                                  live_state='unknown',listing_text='',listing_checked_at=None))
            feed.complete(self.db,dict(request_id=ident,account='fixture-owner',observed_at=feed.utc(time.time()),
                                      sources={k:dict(status='ok',message='') for k in feed.KINDS},items=cards));self.db.commit()
            before=[tuple(r) for r in self.db.execute('SELECT * FROM ebay_market_cards ORDER BY item_id')]
            result=stuff._market_personal_feed(self.db,[])['cards']
            self.assertEqual([r['item_id'] for r in result],[str(123456789012+i) for i in (1,0,2)])
            self.assertEqual([r['_market_group']['count'] for r in result],[1,1,1])
            self.assertTrue(all(r['_market_issuer']['count']==3 for r in result))
            self.assertTrue(all(r['availability_label']=='Availability unverified' for r in result))
            self.assertTrue(all(set(r['sources'])=={'watched','sponsored'} for r in result))
            self.assertTrue(all('collection_matches' in r and 'collection_check_incomplete' in r for r in result))
            self.assertEqual(before,[tuple(r) for r in self.db.execute('SELECT * FROM ebay_market_cards ORDER BY item_id')])

    def test_collection_routes_never_use_market_grouping(self):
        with patch.object(stuff,'_market_group_rows',side_effect=AssertionError('collection must not group')), \
             patch.object(stuff,'render_template',return_value='fixture'):
            for cat in ('coins','banknotes'):
                self.assertEqual(self.client.get('/'+cat+'?history=0').status_code,200)

    def test_route_unifies_sources_under_one_issuer_and_preserves_distinct_actions(self):
        candidate=dict(note('candidate-one'),issuer='US Treasury',pick_number='Fr.1604',
                       title='Candidate Silver Certificate',canonical_url='https://example.test/item/candidate-one',
                       grade_numeric=65,price='$100',status='new')
        other=dict(note('candidate-two'),issuer='Another Bank',pick_number='Fr.1604',
                   title='Another issuer Silver Certificate',price='$110',status='new')
        card=dict(item_id='123456789012',issuer='US Treasury',country='USA',pick_number='Fr.1604',
                  title='Watched Series of 1934 A Silver Certificate',
                  listing_url='https://www.ebay.com/itm/123456789012',
                  canonical_url='https://www.ebay.com/itm/123456789012',price='$105',
                  sources=['watched','sponsored'],collection_matches=[],collection_check_incomplete=False,
                  availability_label='Availability unverified',image_url='')
        personal=dict(cards=[card],observed_date='2026-10-25',excluded_count=0,
                      sources={k:dict(status='ok',message='') for k in feed.KINDS})
        before=copy.deepcopy([candidate,other,personal])
        with patch.object(stuff,'_market_items',return_value=[candidate,other]), \
             patch.object(stuff,'_market_personal_feed',return_value=personal), \
             patch.object(stuff,'render_template',return_value='fixture') as render:
            self.assertEqual(self.client.get('/banknotes/market').status_code,200)
            rows=render.call_args.kwargs['rows']
        self.assertEqual([r.get('id') or r['item_id'] for r in rows],
                         ['candidate-one','123456789012','candidate-two'])
        self.assertEqual(rows[0]['_market_group']['key'],rows[1]['_market_group']['key'])
        self.assertEqual(rows[0]['_market_issuer']['count'],2)
        self.assertEqual(rows[1]['_market_card_kind'],'observed')
        with patch.object(stuff,'_market_items',return_value=[candidate,other]), \
             patch.object(stuff,'_market_personal_feed',return_value=personal):
            response=self.client.get('/banknotes/market')
        self.assertEqual(response.status_code,200)
        body=response.get_data(as_text=True)
        self.assertLess(body.index('Candidate Silver Certificate'),body.index(card['title']))
        self.assertLess(body.index(card['title']),body.index('Another issuer Silver Certificate'))
        self.assertEqual(body.count('data-market-issuer-heading='),2)
        self.assertNotIn('Availability unverified',body)
        self.assertIn('eBay Watched',body)
        self.assertIn('eBay Sponsored · similar to watched',body)
        self.assertIn('data-id="candidate-one"',body)
        self.assertIn('data-buy-url="/banknotes/market/ebay-feed/123456789012/buy"',body)
        self.assertIn('data-dismiss-url="/banknotes/market/ebay-feed/123456789012/dismiss"',body)
        self.assertIn('data-bought="1"',body)
        self.assertEqual([candidate,other,personal],before)


if __name__=='__main__': unittest.main()
