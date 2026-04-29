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
};

window.COIN_REGIONS = {
  'Attica':[38.00,23.72], 'Boeotia':[38.32,23.32], 'Argolis':[37.63,22.73],
  'Laconia':[37.08,22.43], 'Messenia':[37.10,21.93], 'Arcadia':[37.50,22.20],
  'Achaia':[38.10,21.95], 'Elis':[37.64,21.63], 'Phocis':[38.48,22.50],
  'Locris':[38.50,22.70], 'Euboea':[38.50,23.80],
  'Macedonia':[40.76,22.52], 'Macedon':[40.76,22.52],
  'Thessaly':[39.50,22.30], 'Epirus':[39.70,20.85], 'Thrace':[41.50,26.00],
  'Aetolia':[38.50,21.50], 'Acarnania':[38.85,20.90],
  'Mysia':[39.13,27.18], 'Lydia':[38.49,28.04], 'Ionia':[37.94,27.34],
  'Caria':[37.04,27.43], 'Lycia':[36.30,29.80], 'Pamphylia':[36.94,31.17],
  'Cilicia':[37.00,35.30], 'Bithynia':[40.40,30.00], 'Pontus':[42.03,35.16],
  'Cappadocia':[38.70,35.50], 'Phrygia':[39.30,30.50],
  'Troas':[39.80,26.30], 'Aeolis':[39.00,26.80],
  'Phoenicia':[33.27,35.20], 'Syria':[36.20,36.16],
  'Judaea':[31.78,35.22], 'Arabia':[30.32,35.44],
  'Egypt':[31.20,29.92], 'Cyrenaica':[32.82,21.86],
  'Sicily':[37.60,14.00], 'Magna Graecia':[40.47,17.24],
  'Crete':[35.30,25.17], 'Cyclades':[37.00,25.00], 'Cyprus':[35.00,33.20],
  'Italy':[41.90,12.49], 'Etruria':[42.50,11.50], 'Latium':[41.90,12.49],
  'Campania':[40.85,14.26], 'Apulia':[41.10,16.50], 'Lucania':[40.21,16.66],
  'Bruttium':[38.23,16.26],
  'Seleucid Empire':[36.20,36.16], 'Seleucid':[36.20,36.16],
  'Ptolemaic Kingdom':[31.20,29.92], 'Ptolemaic':[31.20,29.92],
  'Roman Republic':[41.90,12.49], 'Roman Empire':[41.90,12.49],
  'Roman Provincial':[41.90,12.49],
  'Byzantine Empire':[41.01,28.97], 'Byzantine':[41.01,28.97],
  'Parthian Empire':[33.10,44.40], 'Parthian':[33.10,44.40],
  'Sasanian Empire':[32.60,51.70], 'Sasanian':[32.60,51.70],
  'Achaemenid Empire':[29.95,52.89], 'Achaemenid':[29.95,52.89],
  'Kingdom of Macedon':[40.76,22.52],
  'Kingdom of Pergamon':[39.13,27.18], 'Attalid':[39.13,27.18],
  'Kingdom of Bactria':[36.76,66.90], 'Bactria':[36.76,66.90],
  'Bactrian Kingdom':[36.76,66.90], 'Greco-Bactrian Kingdom':[36.76,66.90],
  'Indo-Greek Kingdom':[34.20,71.50], 'Indo-Greek':[34.20,71.50],
  'Indo-Skythian':[34.20,71.50], 'Indo-Scythian':[34.20,71.50],
  'Gandhara':[34.20,71.50], 'Arachosia':[32.10,65.50],
  'Sogdiana':[39.50,67.00], 'Margiana':[37.80,62.30],
  'Parthia':[33.10,44.40], 'Persia':[32.00,53.00],
  'Persis':[29.98,52.92], 'Elymais':[32.19,48.26],
  'Characene':[30.50,47.80], 'Media':[35.70,49.00],
  'Mesopotamia':[33.00,44.00], 'Commagene':[37.50,38.00],
  'Osrhoene':[37.15,38.79],
  'Persia, Achamaenid Empire':[29.95,52.89],
  'Pontos':[42.03,35.16],
  'Kingdom of Pontus':[42.03,35.16],
  'Kingdom of Bithynia':[40.40,30.00],
  'Kingdom of Cappadocia':[38.70,35.50],
  'Illyria':[41.50,20.00], 'Illyricum':[41.50,20.00],
  'Dalmatia':[43.50,16.60],
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
};

// Given a coin's {mint, region, authority}, return the best {name, latlng}
// match or null. Exposed so the detail and list maps share identical logic.
window.resolveCoinOrigin = function(coin) {
  const cities = window.COIN_CITIES, regions = window.COIN_REGIONS;
  const aliases = window.COIN_CITY_ALIASES || {};
  const mint = (coin.mint || '').trim();
  const region = (coin.region || '').trim();
  const authority = (coin.authority || '').trim();

  const byCity = (s) => {
    if (!s) return null;
    const lc = s.toLowerCase();
    let key = Object.keys(cities).find(k => k.toLowerCase() === lc);
    if (!key && aliases[lc]) key = aliases[lc];
    return key && cities[key] ? {name: key, latlng: cities[key]} : null;
  };
  const byRegion = (s) => {
    if (!s) return null;
    const key = Object.keys(regions).find(k => k.toLowerCase() === s.toLowerCase());
    return key ? {name: key, latlng: regions[key]} : null;
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
  return byCity(mint) || byCity(region) || byCity(authority)
      || byRegion(region) || byRegion(authority)
      || byFuzzyCity(mint) || byFuzzyCity(region) || byFuzzyCity(authority);
};
