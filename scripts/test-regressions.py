"""Each suite owns its own temporary SQLite database and provider mocks."""
from pathlib import Path
import os
import subprocess
import sys
suites = [
    'test_monitoring.py', 'test_ebay_orders.py', 'test_ebay_mail.py', 'test_ebay_purchase_lookup.py',
    'test_ebay_matching.py', 'test_banknote_imports.py', 'test_banknote_import_consistency.py', 'test_banknote_review_currency.py', 'test_banknote_photo_sides.py',
    'test_banknote_import_coordinator.py', 'test_banknote_import_lifecycle.py',
    'test_banknote_import_crop_timeout.py', 'test_banknote_import_crop_retry.py',
    'test_purchase_lifecycle.py', 'test_banknote_check_sources.py',
    'test_banknote_price_currency.py', 'test_banknote_catalog_recovery.py',
    'test_market_purchase_capture.py', 'test_banknote_crop_responses.py',
    'test_banknote_image_quality.py', 'test_banknote_vision_source.py', 'test_banknote_check_preserves_images.py',
]
env = dict(os.environ, EBAY_SYNC_WORKER='0', BANKNOTE_IMPORT_WORKER='0', ORIGINAL_LISTING_WORKER='0')
for key in ('ANTHROPIC_API_KEY', 'PERPLEXITY_API_KEY', 'OPENAI_API_KEY'):
    env.pop(key, None)
for suite in suites:
    subprocess.run([sys.executable, str(Path('tests') / suite)], env=env, check=True, timeout=180)
