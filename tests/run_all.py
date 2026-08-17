"""Run the StuffApp test suite: python tests/run_all.py"""
import os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
TESTS = ['test_helpers.py', 'test_smoke.py', 'test_banknote_sort.py',
         'test_person_medications.py', 'test_note_trim.py',
         'test_sale_plans.py']

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
