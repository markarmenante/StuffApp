"""Run the StuffApp test suite: python tests/run_all.py"""
import os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
TESTS = ['test_helpers.py', 'test_smoke.py', 'test_ebay_orders.py', 'test_banknote_sort.py', 'test_banknote_catalog.py',
         'test_person_medications.py', 'test_note_trim.py',
         'test_trim_quad.py', 'test_sale_plans.py',
         'test_banknote_similar.py',
         'test_banknote_price_currency.py',
         'test_banknote_serial_scan.py',
         'test_country_history_placeholder.py',
         'test_banknote_vision_source.py',
         'test_banknote_check_preserves_images.py',
         'test_banknote_image_quality.py',
         'test_market_bought.py',
         'test_market_presentation.py',
         'test_market_exact_listing.py',
         'test_market_colonial.py',
         'test_market_ebay_liveness.py',
         'test_market_ebay_verification.py',
         'test_market_images.py',
         'test_market_wantlist.py',
         'test_market_grade_word.py',
         'test_banknote_report.py',
         'test_pedigree.py',
         'test_market_interrupted.py',
         'test_market_runtime.py',
         'test_market_progressive.py',
         'test_market_scan.py']

failed = []
for t in TESTS:
    print(f'\n=== {t} ===')
    r = subprocess.run([sys.executable, os.path.join(HERE, t)])
    if r.returncode != 0:
        failed.append(t)

if failed:
    print(f'\nFAILED: {", ".join(failed)}')
    sys.exit(1)
print('\nALL SUITES PASSED')
