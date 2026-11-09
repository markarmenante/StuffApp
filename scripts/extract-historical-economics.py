#!/usr/bin/env python3
"""Extract reviewed public JST CPI series (pandas is a research-only dependency).

Download JSTdatasetR6.dta from the source below and pass its path. The resulting
separate data file retains the dataset's CC BY-NC-SA 4.0 attribution/license.
No collection records are read. Exchange-rate columns are deliberately excluded:
JST expresses historical units after monetary reforms, not always printed units.
"""
import json
from pathlib import Path
import sys
import pandas as pd

SOURCE = 'https://www.macrohistory.net/database/'
DATA_URL = 'https://www.macrohistory.net/app/download/9834512469/JSTdatasetR6.dta'
# Only CPI paths with explicit currency identity rules in the calculator.
COUNTRIES = ('AUS', 'BEL', 'CAN', 'CHE', 'DNK', 'ESP', 'FRA', 'GBR', 'ITA', 'JPN', 'NLD', 'NOR', 'PRT', 'SWE')
frame = pd.read_stata(sys.argv[1])
result = dict(version=1, name='Jordà–Schularick–Taylor Macrohistory Database, release 6',
    source_url=SOURCE, data_url=DATA_URL, retrieved='2026-11-08',
    documentation_url='https://www.macrohistory.net/app/download/9834516169/JST_documentationR6.pdf',
    license='CC BY-NC-SA 4.0', license_url='https://creativecommons.org/licenses/by-nc-sa/4.0/',
    citation='Òscar Jordà, Moritz Schularick, and Alan M. Taylor (2017), Macrofinancial History and the New Business Cycle Facts, NBER Macroeconomics Annual 2016, volume 31.',
    note='CPI indices as published (1990=100); rebased at a shared 2010 observation when joining current CPI. No exchange-rate series is included.', cpi={})
for iso in COUNTRIES:
    rows = frame[frame.iso == iso]
    result['cpi'][iso] = {str(int(row.year)): float(row.cpi) for row in rows.itertuples()
                          if pd.notna(row.cpi) and row.cpi > 0 and row.year <= 2010}
target = Path(__file__).resolve().parents[1] / 'data' / 'banknote-historical-economics.json'
target.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n')
print('Wrote', len(result['cpi']), 'public CPI series')
