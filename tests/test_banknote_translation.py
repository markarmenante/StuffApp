"""Captured lettering always has a translation path, independent of catalogue citations."""
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['DATA_DIR'] = tempfile.mkdtemp(prefix='stuff-translation-')
for name in ('ANTHROPIC_API_KEY', 'PERPLEXITY_API_KEY', 'OPENAI_API_KEY'):
    os.environ.pop(name, None)
for name in ('EBAY_SYNC_WORKER', 'BANKNOTE_IMPORT_WORKER', 'ORIGINAL_LISTING_WORKER'):
    os.environ[name] = '0'
import app as stuff
import banknote_lettering as lettering
import banknote_catalog_lookup as lookup


JAVASCHE = '''Front: DE JAVASCHE BANK
Front: BETAALT AAN TOONDER
Front: VIJF GULDEN
Front: MEMBAJAR KEPADA PEMBAWA
Front: LIMA ROEPIAH
Front: SECRETARIS / PRESIDENT
Front: 1946
Front: JOH. ENSCHEDE EN ZONEN
Back: HET NAMAKEN OF VERVALSCHEN VAN BANKBILJETTEN, HET OPZETTELIJK UITGEVEN OF
IN VOORRAAD HEBBEN VAN VALSCHE OF VERVALSCHTE BANKBILJETTEN, IS STRAFBAAR.
Back: BARANGSIAPA MENIROE ATAU MEMALSOEKAN OEANG KERTAS ... AKAN DITOENTOET
DIMOEKA HAKIM
Back: Javanese-script legal panel (lower left)
Back: Chinese-script legal panel (lower right)'''
FRENCH = 'Front: CINQ FRANCS\nBack: PAYABLE AU PORTEUR'


def response(data):
    text = json.dumps(data)
    return SimpleNamespace(stop_reason='end_turn', content=[SimpleNamespace(type='text', text=text)],
        model_dump=lambda: {'content': [{'type': 'text', 'text': text}]})


def french_result():
    return {'already_english': False, 'lines': [
        {'source': 'Front: CINQ FRANCS', 'english': 'Five francs'},
        {'source': 'Back: PAYABLE AU PORTEUR', 'english': 'Payable to the bearer'}]}


class TranslationTests(unittest.TestCase):
    def setUp(self):
        self.ctx = stuff.app.app_context()
        self.ctx.push()
        self.db = stuff.get_db()
        self.db.execute('DELETE FROM banknote_import_items')
        self.db.execute('DELETE FROM banknote_import_batches')
        self.db.execute('DELETE FROM banknote_translation_repairs')
        self.db.execute('DELETE FROM banknotes')
        self.db.commit()
        self.client = stuff.app.test_client()

    def tearDown(self):
        self.db.rollback()
        self.ctx.pop()

    def add(self, ident='java', **changes):
        fields = dict(id=ident, country='Netherlands Indies', denomination='5 Gulden', date_1=1946,
                      pick_number='P-87', issuer='De Javasche Bank', lettering=JAVASCHE,
                      image_1='front.jpg', image_2='back.jpg', price='$369', cat_id='B-test',
                      order_number='20-15403-98167', serial_number='EL094595', slab_number='2587402-009')
        fields.update(changes)
        self.db.execute('INSERT INTO banknotes (' + ','.join(fields) + ') VALUES (' +
                        ','.join('?' for _ in fields) + ')', tuple(fields.values()))
        self.db.commit()
        return dict(self.db.execute('SELECT * FROM banknotes WHERE id=?', (ident,)).fetchone())

    def prepared(self):
        return dict(evidence=[], reports=[], documents=[], warnings=[], images={})

    def test_translation_inherits_verified_original_instead_of_requiring_english_on_photo(self):
        raw = dict(lettering=FRENCH, lettering_translation='Front: Five francs\nBack: Payable to the bearer',
                   direct_evidence={'lettering': {'source': 'image', 'quote': 'CINQ FRANCS'}})
        self.assertIn('lettering_translation', lookup.direct_fields(raw, '', True))
        self.assertNotIn('lettering_translation', lookup.direct_fields(raw, '', False))
        self.assertIn('lettering_translation', lookup.direct_fields(raw, '', False, FRENCH))
        self.assertNotIn('lettering_translation', lookup.direct_fields(raw, '', False, 'Unrelated text'))

    def test_translation_of_a_quoted_dealer_inscription_needs_no_literal_english_quote(self):
        raw = dict(lettering='CINQ FRANCS', lettering_translation='Five francs', direct_evidence={
            'lettering': {'source': 'dealer', 'quote': 'CINQ FRANCS'},
            'lettering_translation': {'source': 'dealer', 'quote': 'CINQ FRANCS'}})
        self.assertIn('lettering_translation', lookup.direct_fields(raw, 'Printed text: CINQ FRANCS', False))
        self.assertNotIn('lettering_translation', lookup.direct_fields(raw, 'Different purchase', False))

    def test_bounded_text_only_fallback_covers_each_line_and_keeps_sides(self):
        raw = dict(lettering=FRENCH, _catalogue_direct_fields=['lettering'])
        client = Mock()
        client.messages.create.return_value = response(french_result())
        deadline = time.monotonic() + 75
        stuff._complete_banknote_translation({}, raw, client, 'fixture-model', deadline)
        self.assertEqual(raw['lettering_translation'], 'Front: Five francs\nBack: Payable to the bearer')
        self.assertIn('lettering_translation', raw['_catalogue_direct_fields'])
        args = client.messages.create.call_args.kwargs
        self.assertLessEqual(args['timeout'], 20)
        self.assertNotIn('tools', args)
        self.assertNotIn('image', str(args['messages']))

    def test_complete_translation_and_saved_translation_do_not_call_provider(self):
        for note, raw in [({}, dict(lettering=FRENCH, lettering_translation='Complete',
                                  _catalogue_direct_fields=['lettering', 'lettering_translation'])),
                          ({'lettering_translation': 'User translation'}, dict(lettering=FRENCH))]:
            client = Mock()
            stuff._complete_banknote_translation(note, raw, client, 'fixture-model', time.monotonic() + 75)
            client.messages.create.assert_not_called()

    def test_draft_translation_matches_preserved_lettering_instead_of_rejected_rewrite(self):
        raw = dict(lettering='Front: ZEHN MARK', lettering_translation='Front: Ten marks',
                   _catalogue_direct_fields=['lettering', 'lettering_translation'])
        client = Mock()
        client.messages.create.return_value = response(french_result())
        stuff._complete_banknote_translation(dict(lettering=FRENCH, _preserve_lettering=True),
            raw, client, 'fixture-model', time.monotonic() + 75)
        self.assertEqual(raw['lettering_translation'], 'Front: Five francs\nBack: Payable to the bearer')

    def test_missing_or_reordered_lines_are_rejected(self):
        for outputs in (french_result()['lines'][:1], list(reversed(french_result()['lines']))):
            with self.assertRaises(ValueError):
                lettering.validate(FRENCH, {'already_english': False, 'lines': outputs})

    def test_english_notes_keep_front_left_and_back_right(self):
        original = 'Front: FIVE DOLLARS\nBack: IN GOD WE TRUST'
        result = lettering.validate(original, {'already_english': True, 'lines': [
            {'source': 'Front: FIVE DOLLARS', 'english': 'FIVE DOLLARS'},
            {'source': 'Back: IN GOD WE TRUST', 'english': 'IN GOD WE TRUST'}]})
        self.assertEqual(result['lettering'], 'Front: FIVE DOLLARS')
        self.assertEqual(result['lettering_translation'], 'Back: IN GOD WE TRUST')

    def test_screenshot_text_translates_without_inventing_untranscribed_panels(self):
        translated = lettering.known_translation(JAVASCHE)
        self.assertIn('Front: Five guilders', translated)
        self.assertIn('Front: Five rupiah', translated)
        self.assertIn('paper money … will be prosecuted', translated)
        self.assertIn('Javanese inscription not transcribed', translated)
        self.assertIn('Chinese inscription not transcribed', translated)
        self.assertEqual(len(lettering.lines(translated)), 12)
        self.assertIsNone(lettering.known_translation(JAVASCHE.replace('VIJF GULDEN', 'TIEN GULDEN')))

    def test_real_specs_path_repairs_omission_before_catalogue_followup(self):
        primary = dict(lettering=FRENCH, catalogue_research={'identity': {'match': 'unresolved'}},
                       direct_evidence={'lettering': {'source': 'image', 'quote': 'CINQ FRANCS'}})
        provider = Mock()
        provider.messages.create.side_effect = [response(primary), response(french_result())]
        note = dict(country='France', description='France 5 Francs', lettering=None, lettering_translation=None)
        with patch('anthropic.Anthropic', return_value=provider), \
                patch.object(stuff, '_require_anthropic_key', return_value='fixture'), \
                patch.object(stuff, 'anthropic_lookup_model', return_value='fixture-model'), \
                patch.object(stuff, '_banknote_check_vision_images', return_value=[
                    dict(label='front', data='fixture', media_type='image/jpeg')]):
            result = stuff.fetch_banknote_specs(note)
        self.assertIn('Five francs', result['lettering_translation'])
        self.assertEqual(provider.messages.create.call_count, 2)

    def test_live_check_and_import_use_shared_translation_fill(self):
        note = self.add()
        with patch.object(stuff, 'fetch_banknote_specs', return_value={}):
            draft = stuff._evaluate_import_check(note, self.prepared())
        self.assertIn('Five guilders', draft['filled']['lettering_translation'])
        with patch.object(stuff.ebay_purchase_lookup, 'ensure', return_value=None), \
                patch.object(stuff.banknote_check_sources, 'prepare', return_value=self.prepared()), \
                patch.object(stuff, 'fetch_banknote_specs', return_value={}), \
                patch.object(stuff, 'ensure_country_history'):
            result = self.client.post('/banknotes/java/lookup-specs')
        self.assertEqual(result.status_code, 200)
        self.assertIn('Five guilders', result.json['filled']['lettering_translation'])
        self.assertIsNone(self.db.execute("SELECT lettering_translation FROM banknotes WHERE id='java'").fetchone()[0])

    def test_translation_timeout_returns_partial_check_and_preserves_captured_text(self):
        note = self.add(lettering=None)
        raw = dict(lettering=FRENCH, _catalogue_direct_fields=['lettering'], _catalogue_sources={})
        client = Mock()
        stuff._complete_banknote_translation(note, raw, client, 'fixture-model', time.monotonic() - 1)
        client.messages.create.assert_not_called()
        result = stuff._banknote_check_result(note, self.prepared(), raw, db=self.db, record_id='java', source_record=note).json
        self.assertEqual(result['filled']['lettering'], FRENCH)
        self.assertIn('translation', result['lookup_error'])
        self.assertIsNone(result['specs_searched_at'])

    def test_repair_fills_only_blank_exact_note_and_preserves_photos_purchase_and_lettering(self):
        before = self.add()
        self.add('saved', lettering_translation='User translation')
        self.add('wrong-type', pick_number='P-88')
        self.add('unknown-text', lettering=JAVASCHE + '\nBack: An unreadable additional line')
        stuff._backfill_english_banknote_lettering(self.db)
        self.assertIsNone(self.db.execute("SELECT lettering_translation FROM banknotes WHERE id='java'").fetchone()[0])
        stuff._backfill_banknote_translations(self.db)
        after = dict(self.db.execute("SELECT * FROM banknotes WHERE id='java'").fetchone())
        self.assertIn('Five guilders', after['lettering_translation'])
        self.assertEqual({k: v for k, v in before.items() if k != 'lettering_translation'},
                         {k: v for k, v in after.items() if k != 'lettering_translation'})
        self.assertEqual(self.db.execute("SELECT lettering_translation FROM banknotes WHERE id='saved'").fetchone()[0], 'User translation')
        for ident in ('wrong-type', 'unknown-text'):
            self.assertIsNone(self.db.execute('SELECT lettering_translation FROM banknotes WHERE id=?', (ident,)).fetchone()[0])
        stuff._backfill_banknote_translations(self.db)
        self.assertEqual(self.db.execute('SELECT count(*) FROM banknote_translation_repairs').fetchone()[0], 1)

    def test_draft_repair_increments_revision_and_does_not_touch_active_checks(self):
        fields = self.add()
        self.db.execute("INSERT INTO banknote_import_batches(id,account_name,order_id,created_at,updated_at) VALUES('b','fixture','20-15403-98167',1,1)")
        for ident, state in (('draft', 'done'), ('active', 'checking')):
            self.db.execute('''INSERT INTO banknote_import_items
                (id,batch_id,account_name,line_key,item_id,source_json,source_digest,fields_json,check_state,created_at,updated_at)
                VALUES (?,'b','fixture',?,?,'{}','fixture',?,?,1,1)''', (ident, ident, ident, json.dumps(fields), state))
        self.db.commit()
        stuff._backfill_banknote_translations(self.db)
        draft = self.db.execute("SELECT * FROM banknote_import_items WHERE id='draft'").fetchone()
        self.assertEqual(draft['revision'], 2)
        repaired = json.loads(draft['fields_json'])
        self.assertIn('Five guilders', repaired.pop('lettering_translation'))
        self.assertEqual(repaired, {k: v for k, v in fields.items() if k != 'lettering_translation'})
        active = self.db.execute("SELECT * FROM banknote_import_items WHERE id='active'").fetchone()
        self.assertEqual(active['revision'], 1)
        self.assertIsNone(json.loads(active['fields_json'])['lettering_translation'])


if __name__ == '__main__':
    unittest.main()
