// Ancient-coin geography: shared between the coin detail origin map and the
// coins-list distribution map. Coordinates are [lat, lng].
window.COIN_CITIES = {
  'Athens':[37.97,23.72], 'Sparta':[37.08,22.43], 'Corinth':[37.93,22.93],
  'Thebes':[38.32,23.32], 'Delphi':[38.48,22.50], 'Olympia':[37.64,21.63],
  'Argos':[37.63,22.73], 'Mycenae':[37.73,22.75], 'Marathon':[38.15,23.97],
  'Eretria':[38.40,23.79], 'Chalcis':[38.46,23.60], 'Aegina':[37.74,23.43],
  'Megara':[37.99,23.34], 'Pella':[40.76,22.52], 'Thessaloniki':[40.64,22.94],
  'Amphipolis':[40.82,23.85], 'Olynthus':[40.29,23.37], 'Larissa':[39.64,22.42],
  'Pharsalus':[39.29,22.38], 'Dodona':[39.55,20.79],
  'Troy':[39.96,26.24], 'Byzantium':[41.01,28.97], 'Cyzicus':[40.39,27.89],
  'Thasos':[40.78,24.71],
  'Pergamon':[39.13,27.18], 'Sardis':[38.49,28.04], 'Smyrna':[38.42,27.14],
  'Phocaea':[38.67,26.75], 'Clazomenae':[38.36,26.78], 'Colophon':[38.10,27.16],
  'Ephesus':[37.94,27.34], 'Miletus':[37.53,27.28], 'Halicarnassus':[37.04,27.43],
  'Knidos':[36.69,27.37], 'Aspendos':[36.94,31.17], 'Side':[36.77,31.39],
  'Tarsus':[36.92,34.90],
  'Rhodes':[36.45,28.22], 'Kos':[36.89,27.29], 'Samos':[37.75,26.97],
  'Chios':[38.37,26.13], 'Mytilene':[39.10,26.55], 'Lesbos':[39.20,26.30],
  'Delos':[37.40,25.27], 'Naxos':[37.11,25.38], 'Paros':[37.08,25.15],
  'Knossos':[35.30,25.17], 'Gortyn':[35.06,24.95], 'Kydonia':[35.51,24.02],
  'Sinope':[42.03,35.16], 'Trebizond':[41.00,39.73], 'Heraclea Pontica':[41.28,31.42],
  'Olbia':[46.69,31.91], 'Panticapaeum':[45.35,36.47],
  'Antioch':[36.20,36.16], 'Tyre':[33.27,35.20], 'Sidon':[33.55,35.37],
  'Alexandria':[31.20,29.92], 'Cyrene':[32.82,21.86], 'Carthage':[36.85,10.32],
  'Rome':[41.90,12.49],
  'Syracuse':[37.07,15.29], 'Akragas':[37.31,13.59], 'Selinunte':[37.58,12.83],
  'Himera':[37.97,13.81], 'Naxos (Sicily)':[37.83,15.27], 'Messana':[38.19,15.55],
  'Gela':[37.07,14.25], 'Catana':[37.50,15.09], 'Leontini':[37.29,14.99],
  'Tarentum':[40.47,17.24], 'Croton':[39.08,17.13], 'Sybaris':[39.72,16.50],
  'Locri':[38.23,16.26], 'Metapontum':[40.34,16.82], 'Thurii':[39.71,16.50],
  'Neapolis':[40.84,14.25], 'Cumae':[40.85,14.06],
  'Massalia':[43.30,5.37], 'Emporion':[42.13,3.12],
  // ── Hellenistic east (Seleucid, Parthian, Bactrian, Indo-Greek) ──
  'Antiochia ad Orontem':[36.20,36.16], 'Orontes':[36.20,36.16],
  'Apamea':[35.42,36.40], 'Laodikeia ad Mare':[35.52,35.78],
  'Damaskos':[33.51,36.30], 'Damascus':[33.51,36.30],
  'Ake-Ptolemais':[32.92,35.08], 'Akko':[32.92,35.08],
  'Seleucia':[33.09,44.52], 'Seleukeia':[33.09,44.52],
  'Seleucia-on-the-Tigris':[33.09,44.52],
  'Babylon':[32.54,44.42], 'Dura-Europos':[34.75,40.73],
  'Nisibis':[37.06,41.21], 'Edessa':[37.15,38.79],
  'Samosata':[37.51,38.62], 'Cyrrhus':[36.75,36.97],
  'Susa':[32.19,48.26], 'Ecbatana':[34.80,48.52],
  'Persepolis':[29.94,52.89], 'Istakhr':[29.98,52.92],
  'Nisa':[38.00,58.20], 'Hekatompylos':[36.00,54.00],
  'Baktra':[36.76,66.90], 'Balkh':[36.76,66.90],
  'Ai-Khanoum':[37.17,69.41], 'Ai Khanoum':[37.17,69.41],
  'Ai‑Khanoum':[37.17,69.41],
  'Alexandria Eschate':[40.28,69.62], 'Khujand':[40.28,69.62],
  'Taxila':[33.74,72.82], 'Pushkalavati':[34.16,71.73],
  'Sagala':[32.50,74.53],
  'Istros':[44.55,28.78], 'Histria':[44.55,28.78],
  'Nikaia':[40.43,29.72], 'Nicomedia':[40.77,29.95],
  'Amastris':[41.75,32.39],
  // ── Illyria & Adriatic coast ──
  'Apollonia':[40.72,19.47], 'Apollonia (Illyria)':[40.72,19.47],
  'Dyrrhachium':[41.32,19.45], 'Dyrrachium':[41.32,19.45],
  'Epidamnus':[41.32,19.45], 'Durrës':[41.32,19.45],
  'Lissus':[41.95,19.65], 'Scodra':[42.07,19.51],
  'Pharos':[43.17,16.45], 'Issa':[43.05,16.17],
  'Byllis':[40.53,19.74],
  // ── Principal cities the region fallback lands on ──
  'Ctesiphon':[33.09,44.58], 'Xanthos':[36.36,29.32],
  'Maroneia':[40.87,25.52], 'Abdera':[40.94,24.98],
  'Chersonesos':[40.40,26.60], 'Entella':[37.79,13.03],
  'Aegae':[40.48,22.32], 'Sicyon':[37.98,22.72],
  'Lampsacus':[40.35,26.70], 'Carystus':[38.02,24.42],
  'Stobi':[41.55,21.98], 'Segesta':[37.94,12.83],
};

window.COIN_REGIONS = {
  'Attica':[38.00,23.72], 'Boeotia':[38.32,23.32], 'Argolis':[37.63,22.73],
  'Laconia':[37.08,22.43], 'Messenia':[37.10,21.93], 'Arcadia':[37.50,22.20],
  'Achaia':[38.10,21.95], 'Elis':[37.64,21.63], 'Phocis':[38.48,22.50],
  'Locris':[38.50,22.70], 'Euboea':[38.50,23.80],
  'Macedonia':[40.76,22.52], 'Macedon':[40.76,22.52],
  'Thessaly':[39.64,22.42], 'Epirus':[39.70,20.85], 'Thrace':[40.87,25.52],
  'Aetolia':[38.50,21.50], 'Acarnania':[38.85,20.90],
  'Mysia':[39.13,27.18], 'Lydia':[38.49,28.04], 'Ionia':[37.94,27.34],
  'Caria':[37.04,27.43], 'Lycia':[36.36,29.32], 'Pamphylia':[36.94,31.17],
  'Cilicia':[36.92,34.90], 'Bithynia':[40.40,30.00], 'Pontus':[42.03,35.16],
  'Cappadocia':[38.70,35.50], 'Phrygia':[39.30,30.50],
  'Troas':[39.80,26.30], 'Aeolis':[39.00,26.80],
  'Phoenicia':[33.27,35.20], 'Syria':[36.20,36.16],
  'Judaea':[31.78,35.22], 'Arabia':[30.32,35.44],
  'Egypt':[31.20,29.92], 'Cyrenaica':[32.82,21.86],
  'Sicily':[37.07,15.29], 'Magna Graecia':[40.47,17.24],
  'Crete':[35.30,25.17], 'Cyclades':[37.00,25.00], 'Cyprus':[35.00,33.20],
  'Italy':[41.90,12.49], 'Etruria':[42.50,11.50], 'Latium':[41.90,12.49],
  'Campania':[40.85,14.26], 'Apulia':[41.10,16.50], 'Lucania':[40.21,16.66],
  'Bruttium':[38.23,16.26],
  'Seleucid Empire':[36.20,36.16], 'Seleucid':[36.20,36.16],
  'Ptolemaic Kingdom':[31.20,29.92], 'Ptolemaic':[31.20,29.92],
  'Roman Republic':[41.90,12.49], 'Roman Empire':[41.90,12.49],
  'Roman Provincial':[41.90,12.49],
  'Byzantine Empire':[41.01,28.97], 'Byzantine':[41.01,28.97],
  'Parthian Empire':[33.09,44.58], 'Parthian':[33.09,44.58],
  'Sasanian Empire':[32.60,51.70], 'Sasanian':[32.60,51.70],
  'Achaemenid Empire':[29.95,52.89], 'Achaemenid':[29.95,52.89],
  'Kingdom of Macedon':[40.76,22.52],
  'Kingdom of Pergamon':[39.13,27.18], 'Attalid':[39.13,27.18],
  'Kingdom of Bactria':[36.76,66.90], 'Bactria':[36.76,66.90],
  'Bactrian Kingdom':[36.76,66.90], 'Greco-Bactrian Kingdom':[36.76,66.90],
  'Indo-Greek Kingdom':[33.74,72.82], 'Indo-Greek':[33.74,72.82],
  'Indo-Skythian':[33.74,72.82], 'Indo-Scythian':[33.74,72.82],
  'Gandhara':[33.74,72.82], 'Arachosia':[32.10,65.50],
  'Sogdiana':[39.50,67.00], 'Margiana':[37.80,62.30],
  'Parthia':[33.09,44.58], 'Persia':[32.00,53.00],
  'Persis':[29.98,52.92], 'Elymais':[32.19,48.26],
  'Characene':[30.50,47.80], 'Media':[35.70,49.00],
  'Mesopotamia':[33.09,44.52], 'Commagene':[37.50,38.00],
  'Osrhoene':[37.15,38.79],
  'Persia, Achamaenid Empire':[29.95,52.89],
  'Pontos':[42.03,35.16],
  'Kingdom of Pontus':[42.03,35.16],
  'Kingdom of Bithynia':[40.40,30.00],
  'Kingdom of Cappadocia':[38.70,35.50],
  'Illyria':[41.50,20.00], 'Illyricum':[41.50,20.00],
  'Dalmatia':[43.50,16.60],
  'Macedon (Roman Province)':[40.64,22.94], 'Roman Macedonia':[40.64,22.94],
  'Macedonia (Roman Province)':[40.64,22.94],
  'Thraco-Macedonian':[40.78,24.71], 'Thraco-Macedonian Region':[40.78,24.71],
  'Paeonia':[41.55,21.98], 'Paionia':[41.55,21.98],
  'Baktrian Kingdom':[36.76,66.90], 'Baktria':[36.76,66.90],
  'Seleukid Empire':[36.20,36.16], 'Seleukid':[36.20,36.16],
  'Celtic Gaul':[46.93,4.04], 'Gaul':[46.93,4.04], 'Celtic':[46.93,4.04],
  'Carpathian Region':[47.00,25.00], 'Dacia':[45.62,23.31],
  'Siculo-Punic':[37.79,13.03],
};

// Region -> principal city, for regions whose pin sits on a city that
// COIN_CITIES doesn't also list under those exact coordinates. (Where
// the coordinates match a city, resolveCoinOrigin finds it itself.)
window.COIN_REGION_PRINCIPAL = {
  'Celtic Gaul': 'Bibracte', 'Gaul': 'Bibracte', 'Celtic': 'Bibracte',
  'Dacia': 'Sarmizegetusa',
};

// Greek transliteration → canonical Latinized city name in COIN_CITIES.
// Add new entries as you encounter mismatches; they all resolve via byCity.
window.COIN_CITY_ALIASES = {
  'phokaia':       'Phocaea',
  'phokaea':       'Phocaea',
  'kyzikos':       'Cyzicus',
  'kyme':          'Pergamon',     // approximate — Kyme is just north of Pergamon
  'korinth':       'Corinth',
  'korinthos':     'Corinth',
  'thebai':        'Thebes',
  'athenai':       'Athens',
  'syrakousai':    'Syracuse',
  'kroton':        'Croton',
  'taras':         'Tarentum',
  'metapontion':   'Metapontum',
  'massalia':      'Massalia',
  'panticapaion':  'Panticapaeum',
  'pantikapaion':  'Panticapaeum',
  'olbia pontike': 'Olbia',
  'sikyon':        'Sicyon',
  'aigai':         'Aegae',
  'klazomenai':    'Clazomenae',
  'kos':           'Kos',
  'karystos':      'Carystus',
  'kameiros':      'Camirus',
  'lampsakos':     'Lampsacus',
  'kebren':        'Cebren',
  'kerasos':       'Cerasus',
  'mytilini':      'Mytilene',
  'mytilene':      'Mytilene',
  'knidos':        'Knidos',
  'thasos':        'Thasos',
  'thassos':       'Thasos',
  'thasos island': 'Thasos',
  'island of thasos': 'Thasos',
};

// Modern/world origin fallback. For modern coins, prefer mint city when
// available; otherwise fall back to the country/region capital.
window.COIN_WORLD_PLACES = {
  // North America
  'Philadelphia':[39.95,-75.16], 'Denver':[39.74,-104.99],
  'San Francisco':[37.77,-122.42], 'West Point':[41.39,-73.96],
  'New Orleans':[29.95,-90.07], 'Carson City':[39.16,-119.77],
  'Charlotte':[35.23,-80.84], 'Dahlonega':[34.53,-83.98],
  'Washington DC':[38.90,-77.04], 'Washington, DC':[38.90,-77.04],
  'United States':[38.90,-77.04], 'USA':[38.90,-77.04],
  'U.S.A.':[38.90,-77.04], 'US':[38.90,-77.04],
  'Ottawa':[45.42,-75.70], 'Canada':[45.42,-75.70],
  'Mexico City':[19.43,-99.13], 'Mexico':[19.43,-99.13],

  // Europe
  'London':[51.51,-0.13], 'Llantrisant':[51.54,-3.37],
  'United Kingdom':[51.51,-0.13],
  'Great Britain':[51.51,-0.13], 'England':[51.51,-0.13],
  'Birmingham':[52.49,-1.89], 'Soho':[52.50,-1.93],
  'Bristol':[51.45,-2.59], 'Canterbury':[51.28,1.08],
  'Chester':[53.19,-2.89], 'Durham':[54.78,-1.58],
  'Edinburgh':[55.95,-3.19], 'Exeter':[50.72,-3.53],
  'Glasgow':[55.86,-4.25], 'Norwich':[52.63,1.30],
  'Oxford':[51.75,-1.26], 'Shrewsbury':[52.71,-2.75],
  'York':[53.96,-1.08],
  'Paris':[48.86,2.35], 'France':[48.86,2.35],
  'Berlin':[52.52,13.41], 'Germany':[52.52,13.41],
  'Munich':[48.14,11.58], 'Hamburg':[53.55,10.00],
  'Vienna':[48.21,16.37], 'Austria':[48.21,16.37],
  'Bern':[46.95,7.45], 'Switzerland':[46.95,7.45],
  'Rome':[41.90,12.49], 'Italy':[41.90,12.49],
  'Milan':[45.46,9.19], 'Florence':[43.77,11.26],
  'Venice':[45.44,12.33], 'Genoa':[44.41,8.93],
  'Turin':[45.07,7.69], 'Naples':[40.85,14.27],
  'Palermo':[38.12,13.36], 'Messina':[38.19,15.55],
  'Bologna':[44.49,11.34], 'Ferrara':[44.84,11.62],
  'Mantua':[45.16,10.79], 'Modena':[44.65,10.93],
  'Parma':[44.80,10.33], 'Lucca':[43.84,10.50],
  'Pisa':[43.72,10.40], 'Siena':[43.32,11.33],
  'Ancona':[43.62,13.52], 'Ravenna':[44.42,12.20],
  'Urbino':[43.73,12.64], 'Verona':[45.44,10.99],
  'Cagliari':[39.22,9.12],
  'Madrid':[40.42,-3.70], 'Spain':[40.42,-3.70],
  'Lisbon':[38.72,-9.14], 'Portugal':[38.72,-9.14],
  'Brussels':[50.85,4.35], 'Belgium':[50.85,4.35],
  'Amsterdam':[52.37,4.90], 'Netherlands':[52.37,4.90],
  'Utrecht':[52.09,5.12], 'Stockholm':[59.33,18.07],
  'Sweden':[59.33,18.07], 'Oslo':[59.91,10.75], 'Norway':[59.91,10.75],
  'Copenhagen':[55.68,12.57], 'Denmark':[55.68,12.57],
  'Helsinki':[60.17,24.94], 'Finland':[60.17,24.94],
  'Warsaw':[52.23,21.01], 'Poland':[52.23,21.01],
  'Prague':[50.08,14.44], 'Czech Republic':[50.08,14.44],
  'Czechia':[50.08,14.44], 'Budapest':[47.50,19.04],
  'Hungary':[47.50,19.04], 'Athens':[37.98,23.73],
  'Greece':[37.98,23.73], 'Moscow':[55.76,37.62],
  'Russia':[55.76,37.62], 'St Petersburg':[59.93,30.34],

  // Asia-Pacific
  'Tokyo':[35.68,139.76], 'Japan':[35.68,139.76],
  'Osaka':[34.69,135.50], 'Kyoto':[35.01,135.77],
  'Beijing':[39.90,116.41], 'China':[39.90,116.41],
  'Tianjin':[39.12,117.20], 'Tientsin':[39.12,117.20],
  'Nanjing':[32.06,118.80], 'Nanking':[32.06,118.80],
  'Shanghai':[31.23,121.47], 'Guangzhou':[23.13,113.26],
  'Canton':[23.13,113.26], 'Wuhan':[30.59,114.31],
  'Wuchang':[30.55,114.32], 'Chengdu':[30.66,104.06],
  'Kunming':[25.04,102.71], 'Shenyang':[41.80,123.43],
  'Mukden':[41.80,123.43], 'Harbin':[45.76,126.64],
  'Urumqi':[43.83,87.62], 'Dihua':[43.83,87.62],
  'Hong Kong':[22.32,114.17], 'Seoul':[37.57,126.98],
  'South Korea':[37.57,126.98], 'India':[28.61,77.21],
  'New Delhi':[28.61,77.21], 'Mumbai':[19.08,72.88],
  'Kolkata':[22.57,88.36], 'Calcutta':[22.57,88.36],
  'Canberra':[-35.28,149.13], 'Australia':[-35.28,149.13],
  'Melbourne':[-37.81,144.96], 'Perth':[-31.95,115.86], 'Sydney':[-33.87,151.21],

  // Africa, Middle East, South America
  'Pretoria':[-25.75,28.19], 'South Africa':[-25.75,28.19],
  'Cairo':[30.04,31.24], 'Egypt':[30.04,31.24],
  'Jerusalem':[31.78,35.22], 'Israel':[31.78,35.22],
  'Ankara':[39.93,32.86], 'Turkey':[39.93,32.86],
  'Tehran':[35.69,51.39], 'Iran':[35.69,51.39],
  'Brasilia':[-15.79,-47.88], 'Brazil':[-15.79,-47.88],
  'Buenos Aires':[-34.60,-58.38], 'Argentina':[-34.60,-58.38],
  'Santiago':[-33.45,-70.66], 'Chile':[-33.45,-70.66],
  'Lima':[-12.05,-77.04], 'Peru':[-12.05,-77.04],

  // Historical states, mapped to a reasonable capital or mint center.
  'Bohemia':[50.08,14.44], 'Kingdom of Bohemia':[50.08,14.44],
  'Czechoslovakia':[50.08,14.44],
  'Prussia':[52.52,13.41], 'German Empire':[52.52,13.41],
  'Weimar Republic':[52.52,13.41], 'Bavaria':[48.14,11.58],
  'Austria-Hungary':[48.21,16.37], 'Austrian Empire':[48.21,16.37],
  'Holy Roman Empire':[48.21,16.37],
  'Ottoman Empire':[41.01,28.97], 'Constantinople':[41.01,28.97],
  'Russian Empire':[59.93,30.34],
  'Republic of Venice':[45.44,12.33], 'Venetian Republic':[45.44,12.33],
  'Duchy of Milan':[45.46,9.19], 'Milanese':[45.46,9.19],
  'Grand Duchy of Tuscany':[43.77,11.26], 'Duchy of Florence':[43.77,11.26],
  'Florentine Republic':[43.77,11.26], 'Republic of Florence':[43.77,11.26],
  'Duchy of Savoy':[45.07,7.69], 'Kingdom of Sardinia':[45.07,7.69],
  'Republic of Genoa':[44.41,8.93],
  'Kingdom of Naples':[40.85,14.27], 'Kingdom of the Two Sicilies':[40.85,14.27],
  'Kingdom of Sicily':[38.12,13.36], 'Papal States':[41.90,12.49],
  'Duchy of Parma':[44.80,10.33], 'Duchy of Modena':[44.65,10.93],
  'Duchy of Mantua':[45.16,10.79], 'Duchy of Ferrara':[44.84,11.62],
  'Duchy of Urbino':[43.73,12.64],
};

window.COIN_WORLD_PLACE_ALIASES = {
  'u s': 'United States',
  'u.s.': 'United States',
  'u.s': 'United States',
  'united states of america': 'United States',
  'america': 'United States',
  'american': 'United States',
  'canadian': 'Canada',
  'commonwealth australia': 'Australia',
  'commonwealth of australia': 'Australia',
  'australian': 'Canberra',
  'royal australian': 'Canberra',
  'britain': 'Great Britain',
  'british': 'United Kingdom',
  'uk': 'United Kingdom',
  'u.k.': 'United Kingdom',
  'royal mint': 'Llantrisant',
  'royal mint llantrisant': 'Llantrisant',
  'llantrisant royal mint': 'Llantrisant',
  'tower mint': 'London',
  'tower london': 'London',
  'london mint': 'London',
  'birmingham uk': 'Birmingham',
  'birmingham united kingdom': 'Birmingham',
  'heaton': 'Birmingham',
  'heaton mint': 'Birmingham',
  'ralph heaton': 'Birmingham',
  'ralph heaton sons': 'Birmingham',
  'kings norton': 'Birmingham',
  'king s norton': 'Birmingham',
  'king norton': 'Birmingham',
  'kings norton metal company': 'Birmingham',
  'king s norton metal company': 'Birmingham',
  'the mint birmingham': 'Birmingham',
  'soho mint': 'Soho',
  'soho birmingham': 'Soho',
  'england': 'England',
  'french': 'France',
  'german': 'Germany',
  'austrian': 'Austria',
  'swiss': 'Switzerland',
  'italian': 'Italy',
  'republic venice': 'Republic of Venice',
  'venetian': 'Republic of Venice',
  'venice republic': 'Republic of Venice',
  'duchy milan': 'Duchy of Milan',
  'milan duchy': 'Duchy of Milan',
  'grand duchy tuscany': 'Grand Duchy of Tuscany',
  'duchy tuscany': 'Grand Duchy of Tuscany',
  'tuscany': 'Grand Duchy of Tuscany',
  'florentine': 'Florence',
  'florence republic': 'Republic of Florence',
  'republic florence': 'Republic of Florence',
  'duchy savoy': 'Duchy of Savoy',
  'savoy': 'Duchy of Savoy',
  'kingdom sardinia': 'Kingdom of Sardinia',
  'sardinia': 'Kingdom of Sardinia',
  'republic genoa': 'Republic of Genoa',
  'genoese': 'Republic of Genoa',
  'kingdom naples': 'Kingdom of Naples',
  'two sicilies': 'Kingdom of the Two Sicilies',
  'kingdom two sicilies': 'Kingdom of the Two Sicilies',
  'kingdom sicily': 'Kingdom of Sicily',
  'sicily': 'Kingdom of Sicily',
  'papal': 'Papal States',
  'papal states': 'Papal States',
  'pontifical': 'Papal States',
  'duchy parma': 'Duchy of Parma',
  'duchy modena': 'Duchy of Modena',
  'duchy mantua': 'Duchy of Mantua',
  'duchy ferrara': 'Duchy of Ferrara',
  'duchy urbino': 'Duchy of Urbino',
  'spanish': 'Spain',
  'portuguese': 'Portugal',
  'dutch': 'Netherlands',
  'belgian': 'Belgium',
  'japanese': 'Japan',
  'people republic of china': 'China',
  'peoples republic of china': 'China',
  'republic china': 'China',
  'republic of china': 'China',
  'china republic': 'China',
  'chinese': 'China',
  'prc': 'China',
  'tianjin mint': 'Tianjin',
  'tientsin mint': 'Tianjin',
  'nanking mint': 'Nanjing',
  'nanjing mint': 'Nanjing',
  'canton mint': 'Guangzhou',
  'kwangtung mint': 'Guangzhou',
  'guangdong mint': 'Guangzhou',
  'wuchang mint': 'Wuchang',
  'mukden mint': 'Mukden',
  'sinkiang mint': 'Urumqi',
  'republic of korea': 'South Korea',
  'korea': 'South Korea',
  'korean': 'South Korea',
  'ussr': 'Russia',
  'soviet union': 'Russia',
  'russian': 'Russia',
  'bohemian': 'Bohemia',
  'kingdom bohemia': 'Kingdom of Bohemia',
  'austro hungarian': 'Austria-Hungary',
  'ottoman': 'Ottoman Empire',
};

window.COIN_WORLD_PLACE_LABELS = {
  'United States': 'Washington, DC',
  'Canada': 'Ottawa',
  'Mexico': 'Mexico City',
  'United Kingdom': 'London',
  'Llantrisant': 'Llantrisant',
  'Great Britain': 'London',
  'England': 'London',
  'France': 'Paris',
  'Germany': 'Berlin',
  'Austria': 'Vienna',
  'Switzerland': 'Bern',
  'Italy': 'Rome',
  'Republic of Venice': 'Venice',
  'Venetian Republic': 'Venice',
  'Duchy of Milan': 'Milan',
  'Grand Duchy of Tuscany': 'Florence',
  'Duchy of Florence': 'Florence',
  'Florentine Republic': 'Florence',
  'Republic of Florence': 'Florence',
  'Duchy of Savoy': 'Turin',
  'Kingdom of Sardinia': 'Turin',
  'Republic of Genoa': 'Genoa',
  'Kingdom of Sicily': 'Palermo',
  'Duchy of Parma': 'Parma',
  'Duchy of Modena': 'Modena',
  'Duchy of Mantua': 'Mantua',
  'Duchy of Ferrara': 'Ferrara',
  'Duchy of Urbino': 'Urbino',
  'Spain': 'Madrid',
  'Portugal': 'Lisbon',
  'Belgium': 'Brussels',
  'Netherlands': 'Amsterdam',
  'Sweden': 'Stockholm',
  'Norway': 'Oslo',
  'Denmark': 'Copenhagen',
  'Finland': 'Helsinki',
  'Poland': 'Warsaw',
  'Czech Republic': 'Prague',
  'Czechia': 'Prague',
  'Hungary': 'Budapest',
  'Greece': 'Athens',
  'Russia': 'Moscow',
  'Japan': 'Tokyo',
  'China': 'Beijing',
  'Tientsin': 'Tianjin',
  'Nanking': 'Nanjing',
  'Canton': 'Guangzhou',
  'Mukden': 'Shenyang',
  'Dihua': 'Urumqi',
  'South Korea': 'Seoul',
  'India': 'New Delhi',
  'Australia': 'Canberra',
  'South Africa': 'Pretoria',
  'Egypt': 'Cairo',
  'Israel': 'Jerusalem',
  'Turkey': 'Ankara',
  'Iran': 'Tehran',
  'Brazil': 'Brasilia',
  'Argentina': 'Buenos Aires',
  'Chile': 'Santiago',
  'Peru': 'Lima',
  'Bohemia': 'Prague',
  'Kingdom of Bohemia': 'Prague',
  'Czechoslovakia': 'Prague',
  'Prussia': 'Berlin',
  'German Empire': 'Berlin',
  'Weimar Republic': 'Berlin',
  'Bavaria': 'Munich',
  'Austria-Hungary': 'Vienna',
  'Austrian Empire': 'Vienna',
  'Holy Roman Empire': 'Vienna',
  'Ottoman Empire': 'Constantinople',
  'Russian Empire': 'St Petersburg',
  'Kingdom of Naples': 'Naples',
  'Kingdom of the Two Sicilies': 'Naples',
  'Papal States': 'Rome',
};

// Given a coin's {mint, region, authority}, return the best {name, latlng}
// match or null. Exposed so the detail and list maps share identical logic.
window.resolveCoinOrigin = function(coin) {
  const cities = window.COIN_CITIES, regions = window.COIN_REGIONS;
  const aliases = window.COIN_CITY_ALIASES || {};
  const world = window.COIN_WORLD_PLACES || {};
  const worldAliases = window.COIN_WORLD_PLACE_ALIASES || {};
  const worldLabels = window.COIN_WORLD_PLACE_LABELS || {};
  const mint = (coin.mint || '').trim();
  const region = (coin.region || '').trim();
  const authority = (coin.authority || '').trim();

  const norm = (s) => (s || '')
    .toLowerCase()
    .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
    .replace(/\b(royal|national|central|federal|state|the|mint|mints|coinage|republic|kingdom|empire|duchy|grand|principality|county|commune|of|bank)\b/g, ' ')
    .replace(/[^a-z0-9]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
  const rawNorm = (s) => (s || '')
    .toLowerCase()
    .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-z0-9]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
  const isPlaceholderMint = (s) => {
    const clean = rawNorm(s);
    return !clean || [
      'uncertain',
      'unknown',
      'undetermined',
      'unattributed',
      'not specified',
      'not known',
      'various',
      'multiple',
      'miscellaneous',
      'n a',
      'na',
      'none',
    ].includes(clean);
  };
  const effectiveMint = isPlaceholderMint(mint) ? '' : mint;

  const byCity = (s) => {
    if (!s) return null;
    const lc = s.toLowerCase();
    let key = Object.keys(cities).find(k => k.toLowerCase() === lc);
    if (!key && aliases[lc]) key = aliases[lc];
    return key && cities[key] ? {name: key, latlng: cities[key]} : null;
  };
  const byWorldPlace = (s) => {
    if (!s) return null;
    const rawClean = rawNorm(s);
    const rawAliasKey = worldAliases[rawClean];
    if (rawAliasKey && world[rawAliasKey]) {
      return {name: worldLabels[rawAliasKey] || rawAliasKey, latlng: world[rawAliasKey]};
    }
    const clean = norm(s);
    if (!clean) return null;
    const cleanTokens = new Set(clean.split(' '));
    const aliasKey = worldAliases[clean];
    let key = aliasKey && world[aliasKey] ? aliasKey : null;
    if (!key) {
      key = Object.keys(world).find(k => norm(k) === clean);
    }
    if (!key) {
      const candidates = Object.keys(world).filter(k => {
        const kk = norm(k);
        if (kk.length < 4 && clean !== kk) return false;
        const keyTokens = kk.split(' ').filter(Boolean);
        return keyTokens.length > 0 && keyTokens.every(t => cleanTokens.has(t));
      });
      candidates.sort((a, b) => {
        const aFallback = worldLabels[a] && worldLabels[a] !== a ? 1 : 0;
        const bFallback = worldLabels[b] && worldLabels[b] !== b ? 1 : 0;
        if (aFallback !== bFallback) return aFallback - bFallback;
        return norm(b).length - norm(a).length;
      });
      key = candidates[0] || null;
    }
    return key && world[key]
      ? {name: worldLabels[key] || key, latlng: world[key]}
      : null;
  };
  const byRegion = (s) => {
    if (!s) return null;
    const key = Object.keys(regions).find(k => k.toLowerCase() === s.toLowerCase());
    if (!key) return null;
    const latlng = regions[key];
    // A region pin is a principal city: name it, keep the region.
    const principal = (window.COIN_REGION_PRINCIPAL || {})[key]
      || Object.keys(cities).find(c =>
           cities[c][0] === latlng[0] && cities[c][1] === latlng[1]);
    if (principal && principal !== key) {
      return {name: principal, latlng, region: key, principal: true};
    }
    return {name: key, latlng, region: key};
  };
  const byFuzzyCity = (s) => {
    if (!s) return null;
    const lc = s.toLowerCase();
    const first = lc.split(/[,\s]/)[0];
    const hit = Object.keys(cities).find(k => {
      const kl = k.toLowerCase();
      return lc.includes(kl) || kl.includes(first);
    });
    return hit ? {name: hit, latlng: cities[hit]} : null;
  };
  if (coin.ancientOnly) {
    // Ancient/medieval tables only — no modern capitals standing in
    // for a Hellenistic kingdom.
    return byCity(effectiveMint)
        || byCity(region) || byCity(authority)
        || byRegion(region) || byRegion(authority)
        || byFuzzyCity(effectiveMint) || byFuzzyCity(region) || byFuzzyCity(authority);
  }
  return byCity(effectiveMint) || byWorldPlace(effectiveMint)
      || byCity(region) || byCity(authority)
      || byRegion(region) || byRegion(authority)
      || byWorldPlace(region) || byWorldPlace(authority)
      || byFuzzyCity(effectiveMint) || byFuzzyCity(region) || byFuzzyCity(authority);
};

window.resolveCoinOriginAsync = async function(coin) {
  const rawNorm = (s) => (s || '')
    .toLowerCase()
    .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-z0-9]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
  const isPlaceholderMint = (s) => {
    const clean = rawNorm(s);
    return !clean || [
      'uncertain',
      'unknown',
      'undetermined',
      'unattributed',
      'not specified',
      'not known',
      'various',
      'multiple',
      'miscellaneous',
      'n a',
      'na',
      'none',
    ].includes(clean);
  };
  const mint = isPlaceholderMint(coin && coin.mint) ? '' : (coin && coin.mint || '').trim();
  const mintLocal = mint
    ? window.resolveCoinOrigin({mint, region: '', authority: '', ancient: coin && coin.ancient})
    : null;
  if (mintLocal) return mintLocal;

  if (coin && coin.ancient) return null;

  const local = window.resolveCoinOrigin(coin);
  if (!mint) return local;

  const queries = [
    [mint, coin.region].filter(Boolean).join(', '),
    [mint, coin.authority].filter(Boolean).join(', '),
    mint,
  ].filter(Boolean).filter((q, idx, arr) => arr.indexOf(q) === idx);

  const fetchGeocode = async (query) => {
    const cacheKey = 'coin-origin-geocode:' + query.toLowerCase();
    try {
      const cached = window.localStorage && window.localStorage.getItem(cacheKey);
      if (cached) return JSON.parse(cached);
    } catch (_) {}

    const url = '/api/geocode-city?q=' + encodeURIComponent(query);
    const res = await fetch(url, {headers: {'Accept': 'application/json'}});
    if (!res.ok) return null;
    const hit = await res.json();
    if (!hit || !hit.latlng || !Number.isFinite(Number(hit.latlng[0])) || !Number.isFinite(Number(hit.latlng[1]))) {
      return null;
    }
    hit.latlng = [Number(hit.latlng[0]), Number(hit.latlng[1])];
    try {
      if (window.localStorage) window.localStorage.setItem(cacheKey, JSON.stringify(hit));
    } catch (_) {}
    return hit;
  };

  try {
    for (const query of queries) {
      const hit = await fetchGeocode(query);
      if (hit) return hit;
    }
    return local || null;
  } catch (_) {
    return local || null;
  }
};

// ── Era borders: the world as it stood in the coin's or note's year ──
// Snapshot years available in aourednik/historical-basemaps (served via
// jsDelivr, open CORS); negative = BC. The latest snapshot at or before
// the year is drawn, the polity containing the pin is filled and named.
window.ERA_BORDER_YEARS = [
  -1000, -700, -500, -400, -323, -300, -200, -100, -1,
  100, 200, 300, 400, 500, 600, 700, 800, 900,
  1000, 1100, 1200, 1279, 1300, 1400, 1492, 1500, 1530, 1600, 1650,
  1700, 1715, 1783, 1800, 1815, 1880, 1900, 1914, 1920, 1930, 1938,
  1945, 1960, 1994, 2000, 2010,
];
window.eraBorderSnapshot = function(year) {
  const y = Number(year);
  if (!Number.isFinite(y)) return null;
  let best = null;
  for (const s of window.ERA_BORDER_YEARS) if (s <= y) best = s;
  return best;
};
window.eraYearLabel = function(y) {
  return y < 0 ? Math.abs(y) + ' BC' : String(y);
};
// Ray-casting point-in-polygon over a GeoJSON Polygon/MultiPolygon.
window.geoJsonContains = function(geometry, latlng) {
  const [lat, lng] = latlng;
  const inRing = (ring) => {
    let inside = false;
    for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      const [xi, yi] = ring[i], [xj, yj] = ring[j];
      const hit = ((yi > lat) !== (yj > lat))
        && (lng < (xj - xi) * (lat - yi) / ((yj - yi) || 1e-12) + xi);
      if (hit) inside = !inside;
    }
    return inside;
  };
  const inPolygon = (poly) => poly.length > 0 && inRing(poly[0])
    && !poly.slice(1).some(inRing);
  if (!geometry) return false;
  if (geometry.type === 'Polygon') return inPolygon(geometry.coordinates);
  if (geometry.type === 'MultiPolygon') return geometry.coordinates.some(inPolygon);
  return false;
};
// Rough centre of a Polygon/MultiPolygon: the vertex mean of its
// largest outer ring (plenty for "is this polity inside that one").
window.geoJsonCentroid = function(geometry) {
  if (!geometry) return null;
  let rings = [];
  if (geometry.type === 'Polygon') rings = [geometry.coordinates[0]];
  else if (geometry.type === 'MultiPolygon') rings = geometry.coordinates.map(p => p[0]);
  rings = rings.filter(r => r && r.length);
  if (!rings.length) return null;
  const ring = rings.reduce((a, b) => (b.length > a.length ? b : a));
  let sx = 0, sy = 0;
  ring.forEach(([x, y]) => { sx += x; sy += y; });
  return [sy / ring.length, sx / ring.length];
};
// Draw the era's borders on `map`; fill the polity at `latlng` (when
// given). Resolves to {year, name} or null. Fails silently — the pin is
// the point of the map.
// Supplements for spans the world snapshots serve badly — hand-drawn
// files shipped with the app (British America 1763–1775) and maps
// Claude draws on demand when a record's nearest snapshot is decades
// stale. /api/era-supplements says which apply to this pin and year
// (and commissions a drawing when none does); their polities are drawn
// over the snapshot, whose own polities they cover are dropped.
window.loadEraBorders = function(map, year, latlng, meta) {
  const snap = window.eraBorderSnapshot(year);
  if (snap === null) return Promise.resolve(null);
  const file = snap < 0 ? 'bc' + Math.abs(snap) : String(snap);
  const y = Number(year);
  const getJson = (url) => fetch(url).then(res => res.ok ? res.json() : null).catch(() => null);
  const suppList = latlng
    ? getJson('/api/era-supplements?year=' + encodeURIComponent(y)
              + '&lat=' + encodeURIComponent(latlng[0]) + '&lng=' + encodeURIComponent(latlng[1])
              + '&polity=' + encodeURIComponent((meta && meta.polity) || '')
              + '&place=' + encodeURIComponent((meta && meta.place) || ''))
        .then(r => (r && r.supplements) || [])
    : Promise.resolve([]);
  return Promise.all([
    getJson('https://cdn.jsdelivr.net/gh/aourednik/historical-basemaps@master/geojson/world_'
            + file + '.geojson'),
    suppList.then(list => Promise.all(list.map(sp =>
      getJson(sp.url).then(gj => gj && gj.features ? Object.assign({}, sp, {gj}) : null)))),
  ])
    .then(([world, supps]) => {
      supps = (supps || []).filter(Boolean);
      let gj = world;
      const fromSupplement = new Set();
      let suppFrom = null, generated = false, note = null;
      if (supps.length) {
        const extraFeatures = [];
        const drop = new Set();
        supps.forEach(sp => {
          (sp.replaces || []).forEach(n => drop.add(String(n).toLowerCase()));
          sp.gj.features.forEach(f => { extraFeatures.push(f); fromSupplement.add(f); });
          suppFrom = suppFrom === null ? sp.from : Math.max(suppFrom, sp.from);
          if (sp.generated) { generated = true; note = sp.note || note; }
        });
        // A snapshot polity whose centre falls inside a supplement
        // polygon is what the drawing supersedes.
        const covered = (f) => {
          const c = window.geoJsonCentroid(f.geometry);
          return c && extraFeatures.some(e => !(e.properties && e.properties.LINE)
                                             && window.geoJsonContains(e.geometry, c));
        };
        const kept = (world && world.features || []).filter(f =>
          !drop.has(((f.properties || {}).NAME || '').trim().toLowerCase()) && !covered(f));
        gj = {type: 'FeatureCollection', features: extraFeatures.concat(kept)};
      }
      if (!gj) return null;
      let home = null;
      if (latlng) {
        home = (gj.features || []).find(f => !(f.properties && f.properties.LINE)
                                              && window.geoJsonContains(f.geometry, latlng)) || null;
        // Coastal seats (Williamsburg, Tabora's Dar es Salaam neighbours)
        // fall just outside a coarsely drawn shoreline: take the nearest
        // polity within ~120 km instead of leaving the pin stateless.
        if (!home) {
          const pin = L.latLng(latlng[0], latlng[1]);
          let best = null, bestD = 120000;
          (gj.features || []).forEach(f => {
            const g = f.geometry;
            if (!g || !f.properties || !(f.properties.NAME || '').trim() || f.properties.LINE) return;
            const polys = g.type === 'Polygon' ? [g.coordinates]
              : g.type === 'MultiPolygon' ? g.coordinates : [];
            polys.forEach(poly => (poly[0] || []).forEach(([x, y]) => {
              if (Math.abs(y - pin.lat) > 2 || Math.abs(x - pin.lng) > 2) return;
              const d = pin.distanceTo(L.latLng(y, x));
              if (d < bestD) { bestD = d; best = f; }
            }));
          });
          home = best;
        }
      }
      const layer = L.geoJSON(gj, {
        style: (f) => (f.properties && f.properties.LINE)
          ? {color: '#c0392b', weight: 1.4, opacity: 0.7, dashArray: '5 4', fill: false}
          : f === home
            ? {color: '#8a6d3b', weight: 1.6, opacity: 0.85, fillColor: '#8a6d3b', fillOpacity: 0.14}
            : {color: '#8a6d3b', weight: 1, opacity: 0.6, fill: false},
        interactive: false,
      }).addTo(map);
      // Name the neighbours: the polities nearest the pin get a label
      // at their centre, so an Alexander tetradrachm shows Macedon
      // beside Thrace, Epirus and the Persian satrapies of its day.
      if (latlng) {
        const pin = L.latLng(latlng[0], latlng[1]);
        const near = [];
        layer.eachLayer(l => {
          const f = l.feature;
          const nm = f && f.properties && (f.properties.NAME || '').trim();
          if (!nm || f === home || !l.getBounds || (f.properties && f.properties.LINE)) return;
          const b = l.getBounds();
          if (!b.isValid()) return;
          let c;
          const at = f.properties.LABEL_AT;
          if (at && at.length === 2) c = L.latLng(at[0], at[1]);
          else { try { c = l.getCenter(); } catch (_) { c = b.getCenter(); } }
          if (!c) return;
          if (Math.abs(c.lat - pin.lat) > 14 || Math.abs(c.lng - pin.lng) > 22) return;
          // Archaeological-culture and hunter-gatherer areas aren't
          // neighbouring states; skip them.
          if (/culture|hunter|gatherer|nomad|peoples|uninhabited|unclaimed/i.test(nm)) return;
          // Hand-drawn supplement polities label ahead of the snapshot's.
          near.push({name: nm, center: c,
                     d: pin.distanceTo(c) - (fromSupplement.has(f) ? 1e8 : 0)});
        });
        near.sort((a, b) => a.d - b.d);
        // One label per name, nearest first, and none closer than
        // ~110 km to a label already placed — the New England colonies
        // would otherwise print on top of each other.
        const seen = new Set(), placed = [];
        near.filter(n => {
          if (seen.has(n.name)) return false;
          if (placed.some(c => c.distanceTo(n.center) < 110000)) return false;
          seen.add(n.name); placed.push(n.center); return true;
        }).slice(0, 12).forEach(n => {
          L.tooltip({
            permanent: true, direction: 'center', className: 'coin-era-label',
            interactive: false, opacity: 1,
          }).setLatLng(n.center).setContent(n.name).addTo(map);
        });
      }
      const name = home && home.properties && (home.properties.NAME || '').trim();
      let bounds = null;
      if (home) {
        layer.eachLayer(l => { if (l.feature === home && l.getBounds) bounds = l.getBounds(); });
      }
      // A supplement is drawn for its own span: report its start year,
      // not the older world snapshot underneath it.
      const shownYear = suppFrom !== null ? Math.max(snap, suppFrom) : snap;
      return {year: shownYear, name: name || null, generated, note,
              bounds: bounds && bounds.isValid() ? bounds : null};
    })
    .catch(() => null);
};
