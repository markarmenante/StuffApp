#!/usr/bin/env python3
"""Refresh public annual official FX for explicitly reviewed unchanged units.

No collection records, credentials or runtime application dependencies are read.
World Bank WDI data are CC BY 4.0. These are official annual averages, not a
promise that households could exchange notes at that price.
"""
import json
from pathlib import Path
import urllib.request

CODES = 'MAC;IRN;KEN;NGA;COL;THA;BHS;BLZ;CYM;CUB;EGY;KWT;MUS;MDV;MAR;LBN;MWI;FJI;SLB;GMB;BRN;SYC;HKG;SGP;PHL;IDN;ZAF'
URL = 'https://api.worldbank.org/v2/country/' + CODES + '/indicator/PA.NUS.FCRF?format=json&per_page=20000'
with urllib.request.urlopen(URL, timeout=45) as response:
    payload = json.load(response)
if payload[0]['pages'] != 1: raise ValueError('Incomplete World Bank data')
result = dict(version=1, name='World Bank / IMF official annual exchange rates',
              source_url=URL, indicator='PA.NUS.FCRF', retrieved='2026-11-08',
              license='CC BY 4.0', license_url='https://datacatalog.worldbank.org/public-licenses',
              unit='Local currency units per US dollar, period average', rates={})
for row in payload[1]:
    value = row['value']
    if isinstance(value, (float, int)) and value > 0:
        result['rates'].setdefault(row['countryiso3code'], {})[row['date']] = value
path = Path(__file__).resolve().parents[1] / 'data' / 'banknote-historical-fx.json'
path.write_text(json.dumps(result, indent=2) + '\n')
print('Wrote', len(result['rates']), 'public official FX series')
