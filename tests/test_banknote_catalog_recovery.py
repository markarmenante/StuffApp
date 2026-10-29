"""Empty/partial extraction recovery using actual public type-page structure."""
import copy
import os
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['DATA_DIR'] = tempfile.mkdtemp(prefix='stuff-catalog-recovery-')
os.environ.pop('ANTHROPIC_API_KEY', None)
import app as stuff
import banknote_catalog_lookup as lookup

# Selected literal type facts from https://en.numista.com/208240, checked
# 2026-10-29. The saved P-31 does not authorize the P-31a signature variety.
URL = 'https://en.numista.com/208240'
NOTE = dict(country='French Equatorial Africa', denomination='50 Francs',
            pick_number='P-31', date_1=1957)
ISSUER = "Emission Institute of French Equatorial Africa and Cameroon (Institut d'Emission de l'Afrique Equatoriale Française et du Cameroun)"
PAGE = f'''50 Francs - French Equatorial Africa
### Features
Location | French Equatorial Africa (Central African States)
Issuing institution | {ISSUER}
Type | Standard circulation banknotes
Year | 1957
Value | 50 Francs
Composition | Paper
Size | 115 × 75 mm
References | P# 31
### Obverse
Multicolor.
Woman picking coffee beans at left.
Script: Latin
### Reverse
Multicolor.
Men logging in river at center.
Script: Latin
### Printer
Banque de France, Paris, France
### Manage my collection
ND (No date) (1957) | P# 31a
ND (No date) (1957) | P# 31s | Specimen
'''


def sources(page=PAGE, url=URL):
    return {url: dict(title='50 Francs - French Equatorial Africa',
                     document_text=page, quotes=[page])}


def claim(field='material', value='Paper', quote='Composition | Paper', **identity):
    return dict(identity=dict(NOTE, reference='P-31', match='exact', **identity),
                fields={field:dict(value=value, scope='type', source_url=URL, quote=quote)})


class RecoveryTests(unittest.TestCase):
    def test_empty_model_result_recovers_six_sourced_cameroon_type_fields(self):
        result = lookup.validate_all(NOTE, {}, {'identity':{'match':'unresolved'},'fields':{}}, sources())
        self.assertEqual(result['state'], 'ready')
        fields = {key: proof['value'] for key, proof in result['fields'].items()}
        self.assertEqual(fields, dict(issuer=ISSUER, material='Paper', size_width=115., size_height=75.,
            printer='Banque de France, Paris, France',
            obv_rev='Obv: Multicolor. Woman picking coffee beans at left. / Rev: Multicolor. Men logging in river at center.'))
        for proof in result['fields'].values():
            self.assertEqual(proof['source_url'], URL)
            self.assertIn(proof['quote'], lookup.text(PAGE))
        for field in ('signatures','watermark','series','date_1','grade','serial_number','price','pick_number'):
            self.assertNotIn(field, fields)

    def test_actual_source_text_is_required(self):
        for evidence in ({}, {URL:dict(title='50 Francs French Equatorial Africa P-31', quotes=[])},
                         {URL:dict(title='50 Francs French Equatorial Africa', quotes=[PAGE])}):
            self.assertEqual(lookup.validate_all(NOTE, {}, None, evidence)['fields'], {})

    def test_exact_type_header_required_not_variety_or_sales_table(self):
        for change in ({'pick_number':'P-31a'}, {'pick_number':'P-31s'}, {'pick_number':'P-32'},
                       {'country':'Cameroon'}, {'denomination':'100 Francs'},
                       {'issuer':'Bank of Central African States'}):
            with self.subTest(change=change):
                self.assertEqual(lookup.validate_all(dict(NOTE, **change), {}, None, sources())['fields'], {})
        for page in (PAGE.replace('P# 31\n', 'P# 30\n'),
                     PAGE.replace('banknotes', 'coins'), PAGE.replace('Features', 'Recommendations')):
            self.assertEqual(lookup.validate_all(NOTE, {}, None, sources(page))['fields'], {})

    def test_no_guessed_page_or_lookalike_host(self):
        for url in ('https://numista.com.evil.test/208240', 'https://en.numista.com/catalogue/aef-2.html',
                    'https://user:password@en.numista.com/208240', 'https://en.numista.com:bad/208240'):
            self.assertEqual(lookup.validate_all(NOTE, {}, None, sources(url=url))['fields'], {})

    def test_missing_or_duplicate_feature_is_not_guessed(self):
        page = PAGE.replace('Composition | Paper', 'Composition | Paper\nComposition | Polymer')
        page = page.replace('Size | 115 × 75 mm', 'Size | unknown')
        fields = lookup.validate_all(NOTE, {}, None, sources(page))['fields']
        self.assertNotIn('material', fields)
        self.assertNotIn('size_width', fields)
        self.assertNotIn('size_height', fields)
        self.assertIn('issuer', fields)

    def test_occupied_fields_and_conflicting_direct_identity_are_preserved(self):
        note = dict(NOTE, material='Paper', issuer=ISSUER, printer='My printer', size_width=116,
                    size_height=76, obv_rev='My design', serial_number='Private serial', image_1='manual-crop.jpg')
        before = copy.deepcopy(note)
        self.assertEqual(lookup.validate_all(note, {}, None, sources())['fields'], {})
        self.assertEqual(note, before)
        self.assertEqual(lookup.validate_all(NOTE, {'pick_number':'P-32'}, None, sources())['fields'], {})

    def test_initial_proofs_survive_empty_or_partial_final_research(self):
        # No structured fallback: exercise independent source validation of
        # the saved first pass and the second pass, including partial success.
        evidence = {URL:dict(title='French Equatorial Africa', quotes=[PAGE])}
        first = claim('printer', 'Banque de France', 'Banque de France, Paris, France')
        for final in (None, {'identity':{'match':'unresolved'},'fields':{}}, claim()):
            result = lookup.validate_all(NOTE, {}, final, evidence, previous=first)
            self.assertEqual(result['fields']['printer']['value'], 'Banque de France')
            if final and final.get('fields'):
                self.assertEqual(result['fields']['material']['value'], 'Paper')

    def test_conflicting_or_uncited_pass_cannot_replace_supported_fact(self):
        evidence = {URL:dict(title='French Equatorial Africa', quotes=[PAGE + '\nComposition | Polymer'])}
        result = lookup.validate_all(NOTE, {}, claim(), evidence,
            previous=claim(value='Polymer', quote='Composition | Polymer'))
        self.assertNotIn('material', result['fields'])
        result = lookup.validate_all(NOTE, {}, claim(), evidence,
            previous=claim(value='Imaginary', quote='Composition | Imaginary'))
        self.assertEqual(result['fields']['material']['value'], 'Paper')

    def test_parser_fills_gaps_without_discarding_a_valid_shorter_name(self):
        result = lookup.validate_all(NOTE, {}, claim('printer', 'Banque de France',
            'Banque de France, Paris, France'), sources())
        self.assertEqual(result['fields']['printer']['value'], 'Banque de France')
        self.assertEqual(result['fields']['size_width']['value'], 115.)

    def test_new_draft_identity_can_be_recovered_from_direct_evidence(self):
        self.assertEqual(lookup.validate_all({}, NOTE, None, sources())['state'], 'ready')
        self.assertEqual(lookup.validate_all({}, {'country':NOTE['country']}, None, sources())['fields'], {})

    def test_normal_check_draft_returns_fills_with_evidence_and_guard(self):
        note = dict.fromkeys(stuff.BANKNOTE_SPEC_FILLABLE)
        note.update(NOTE, id='synthetic-check', condition='', description='', notes='', note_references='')
        prepared = dict(evidence=[], reports=[], documents=[], warnings=[], images={})
        with stuff.app.test_request_context('/banknotes/synthetic-check/lookup-specs'):
            response = stuff._banknote_check_result(note, prepared, {
                'catalogue_research':{'identity':{'match':'unresolved'},'fields':{}},
                '_catalogue_sources':sources(), '_catalogue_direct_fields':[]})
        result = response.get_json()
        self.assertEqual(result['filled']['issuer'], ISSUER)
        self.assertEqual(result['filled']['size_width'], 115.)
        self.assertEqual(result['catalogue']['guard']['identity'], lookup.identity_snapshot(note))
        self.assertEqual(set(result['catalogue']['fields']), set(result['filled']))
        self.assertNotIn('proposal_id', result['catalogue']['guard'])


if __name__ == '__main__':
    unittest.main()
