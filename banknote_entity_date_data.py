"""Reviewed dates for colony pill captions only; never collection or scan rules.

Verified 30 October 2026 against the linked primary sources. Existing exact
independence dates in banknote_entities remain the first source of date evidence.
Territories and regional issuers without a reviewed common transition year
retain an undated caption and an explanatory tooltip.
"""
PILL_DATES = {'belgian-belgian-congo': {'note': 'Independence in 1960.',
                           'source': 'https://history.state.gov/countries/congo-democratic-republic',
                           'year': '1960'},
 'belgian-ruanda-urundi': {'note': 'Rwanda and Burundi both became independent on 1 July 1962.',
                           'source': 'https://history.state.gov/countries/rwanda; '
                                     'https://history.state.gov/countries/burundi',
                           'year': '1962'},
 'british-bahrain': {'note': 'Independence in 1971.',
                     'source': 'https://history.state.gov/countries/bahrain',
                     'year': '1971'},
 'british-british-guiana': {'note': 'Independence of Guyana in 1966.',
                            'source': 'https://history.state.gov/countries/guyana',
                            'year': '1966'},
 'british-british-somaliland': {'note': 'Independence in 1960.',
                                'source': 'https://history.state.gov/countries/somalia',
                                'year': '1960'},
 'british-burma': {'note': 'Independence of Burma (Myanmar) in 1948.',
                   'source': 'https://history.state.gov/countries/burma',
                   'year': '1948'},
 'british-ceylon': {'note': 'Independence of Sri Lanka in 1948.',
                    'source': 'https://history.state.gov/countries/sri-lanka',
                    'year': '1948'},
 'british-cyprus': {'note': 'Independence in 1960.',
                    'source': 'https://history.state.gov/countries/cyprus',
                    'year': '1960'},
 'british-egypt': {'note': 'Independence in 1922.',
                   'source': 'https://history.state.gov/countries/egypt',
                   'year': '1922'},
 'british-fiji': {'note': 'Independence in 1970.',
                  'source': 'https://history.state.gov/countries/fiji',
                  'year': '1970'},
 'british-gambia': {'note': 'Independence in 1965.',
                    'source': 'https://history.state.gov/countries/gambia',
                    'year': '1965'},
 'british-gold-coast': {'note': 'Independence of Ghana in 1957.',
                        'source': 'https://history.state.gov/countries/ghana',
                        'year': '1957'},
 'british-grenada': {'note': 'Independence in 1974.',
                     'source': 'https://history.state.gov/countries/grenada',
                     'year': '1974'},
 'british-hong-kong': {'note': 'Handover to China on 1 July 1997.',
                       'source': 'https://www.basiclaw.gov.hk/en/basiclaw/preamble.html',
                       'year': '1997'},
 'british-jamaica': {'note': 'Independence in 1962.',
                     'source': 'https://history.state.gov/countries/jamaica',
                     'year': '1962'},
 'british-kenya': {'note': 'Independence in 1963.',
                   'source': 'https://history.state.gov/countries/kenya',
                   'year': '1963'},
 'british-kuwait': {'note': 'Independence in 1961.',
                    'source': 'https://history.state.gov/countries/kuwait',
                    'year': '1961'},
 'british-malawi': {'note': 'Independence in 1964.',
                    'source': 'https://history.state.gov/countries/malawi',
                    'year': '1964'},
 'british-maldives': {'note': 'Independence in 1965.',
                      'source': 'https://history.state.gov/countries/maldives',
                      'year': '1965'},
 'british-malta': {'note': 'Independence in 1964.',
                   'source': 'https://history.state.gov/countries/malta',
                   'year': '1964'},
 'british-mauritius': {'note': 'Independence in 1968.',
                       'source': 'https://history.state.gov/countries/mauritius',
                       'year': '1968'},
 'british-nigeria': {'note': 'Independence in 1960.',
                     'source': 'https://history.state.gov/countries/nigeria',
                     'year': '1960'},
 'british-northern-rhodesia': {'note': 'Independence of Zambia in 1964.',
                               'source': 'https://history.state.gov/countries/zambia',
                               'year': '1964'},
 'british-nyasaland': {'note': 'Independence of Malawi in 1964.',
                       'source': 'https://history.state.gov/countries/malawi',
                       'year': '1964'},
 'british-qatar-and-dubai': {'note': 'Qatar independence and Dubai joining independent UAE both '
                                     'occurred in 1971; not a common sovereign Qatar-and-Dubai state.',
                             'source': 'https://history.state.gov/countries/qatar; '
                                       'https://history.state.gov/countries/united-arab-emirates',
                             'year': '1971'},
 'british-rhodesia': {'note': 'Recognized independence as Zimbabwe in 1980; 1965 unilateral declaration '
                              'was not recognized.',
                      'source': 'https://history.state.gov/countries/zimbabwe',
                      'year': '1980'},
 'british-saint-kitts': {'note': 'Independence in 1983.',
                         'source': 'https://history.state.gov/countries/saint-kitts-nevis',
                         'year': '1983'},
 'british-seychelles': {'note': 'Independence in 1976.',
                        'source': 'https://history.state.gov/countries/seychelles',
                        'year': '1976'},
 'british-sierra-leone': {'note': 'Independence in 1961.',
                          'source': 'https://history.state.gov/countries/sierra-leone',
                          'year': '1961'},
 'british-south-africa': {'note': 'Independence under the Statute of Westminster in 1931; 1910 was '
                                  'Union, 1961 republic status.',
                          'source': 'https://thecommonwealth.org/our-member-countries/south-africa',
                          'year': '1931'},
 'british-south-arabia': {'note': 'Independence of South Yemen in 1967.',
                          'source': 'https://history.state.gov/countries/yemen',
                          'year': '1967'},
 'british-southern-rhodesia': {'note': 'Recognized independence as Zimbabwe in 1980; 1965 unilateral '
                                       'declaration was not recognized.',
                               'source': 'https://history.state.gov/countries/zimbabwe',
                               'year': '1980'},
 'british-tanganyika': {'note': 'Independence in 1961.',
                        'source': 'https://history.state.gov/countries/tanzania',
                        'year': '1961'},
 'british-tonga': {'note': 'Full external independence following withdrawal from British protection in '
                           '1970; Tonga retained its monarchy throughout.',
                   'source': 'https://thecommonwealth.org/our-member-countries/tonga',
                   'year': '1970'},
 'british-trinidad-and-tobago': {'note': 'Independence in 1962.',
                                 'source': 'https://history.state.gov/countries/trinidad-and-tobago',
                                 'year': '1962'},
 'british-uganda': {'note': 'Independence in 1962.',
                    'source': 'https://history.state.gov/countries/uganda',
                    'year': '1962'},
 'british-western-samoa': {'note': 'Independence in 1962.',
                           'source': 'https://history.state.gov/countries/samoa',
                           'year': '1962'},
 'british-zanzibar': {'note': 'Independent state from 10 December 1963 under section 1(1) of Zanzibar '
                              'Act 1963; union with Tanganyika followed in 1964.',
                      'source': 'https://www.legislation.gov.uk/ukpga/1963/55/pdfs/ukpga_19630055_en.pdf',
                      'year': '1963'},
 'danish-iceland': {'note': 'Independent republic established in 1944; sovereignty in personal union '
                            'with Denmark began in 1918.',
                    'source': 'https://history.state.gov/countries/iceland',
                    'year': '1944'},
 'dutch-netherlands-indies': {'note': 'Indonesian independence declared in 1945; recognized by the '
                                      'United States in 1949.',
                              'source': 'https://timor-leste.gov.tl/?p=29&lang=en; '
                                        'https://history.state.gov/countries/indonesia',
                              'year': '1945'},
 'dutch-suriname': {'note': 'Independence in 1975.',
                    'source': 'https://history.state.gov/countries/suriname',
                    'year': '1975'},
 'french-algeria': {'note': 'Independence in 1962.',
                    'source': 'https://history.state.gov/countries/algeria',
                    'year': '1962'},
 'french-cameroon': {'note': 'French-administered Cameroon became independent January 1, 1960.',
                     'source': 'https://history.state.gov/countries/cameroon',
                     'year': '1960'},
 'french-chad': {'note': 'Independence in 1960.',
                 'source': 'https://history.state.gov/countries/chad',
                 'year': '1960'},
 'french-comoros': {'note': 'Independence on 6 July 1975; Mayotte remains separately administered by '
                            'France.',
                    'source': 'https://auunmission.au.int/en/member-states?order=field_independence_population&sort=desc',
                    'year': '1975'},
 'french-french-guinea': {'note': 'Independence in 1958.',
                          'source': 'https://history.state.gov/countries/guinea',
                          'year': '1958'},
 'french-french-somaliland': {'note': 'Independence as Djibouti in 1977.',
                              'source': 'https://history.state.gov/countries/djibouti',
                              'year': '1977'},
 'french-gabon': {'note': 'Independence in 1960.',
                  'source': 'https://history.state.gov/countries/gabon',
                  'year': '1960'},
 'french-ivory-coast': {'note': 'Independence in 1960.',
                        'source': 'https://history.state.gov/countries/cote-divoire',
                        'year': '1960'},
 'french-laos': {'note': 'Full independence on 22 October 1953, following earlier status within the '
                         'French Union.',
                 'source': 'https://www.mofa.go.jp/mofaj/area/laos/data.html; '
                           'https://www.loc.gov/resource/gdcmassbookdig.laoscountrystudy00sava_0/?q=laos&sp=21&st=text',
                 'year': '1953'},
 'french-lebanon': {'note': 'Independence on 22 November 1943.',
                    'source': 'https://www.lebanonembassyus.org/the-country-of-lebanon/',
                    'year': '1943'},
 'french-madagascar': {'note': 'Independence in 1960.',
                       'source': 'https://history.state.gov/countries/madagascar',
                       'year': '1960'},
 'french-middle-congo': {'note': 'Independence as the Republic of the Congo in 1960.',
                         'source': 'https://history.state.gov/countries/congo-republic',
                         'year': '1960'},
 'french-morocco': {'note': 'Independence in 1956.',
                    'source': 'https://history.state.gov/countries/morocco',
                    'year': '1956'},
 'french-niger': {'note': 'Independence on 3 August 1960.',
                  'source': 'https://history.state.gov/historicaldocuments/frus1958-60v14/d64; '
                            'https://treaties.un.org/doc/source/docs/niger.pdf',
                  'year': '1960'},
 'french-senegal': {'note': 'Independence in 1960.',
                    'source': 'https://history.state.gov/countries/senegal',
                    'year': '1960'},
 'french-syria': {'note': 'French withdrawal and full independence on 17 April 1946.',
                  'source': 'https://sana.sy/en/international/2311061/; '
                            'https://tile.loc.gov/storage-services/master/frd/frdcstdy/sy/syriacountrystud00coll_0/syriacountrystud00coll_0.pdf',
                  'year': '1946'},
 'french-togo': {'note': 'Independence in 1960.',
                 'source': 'https://history.state.gov/countries/togo',
                 'year': '1960'},
 'french-tunisia': {'note': 'Independence in 1956.',
                    'source': 'https://history.state.gov/countries/tunisia',
                    'year': '1956'},
 'french-ubangi-shari': {'note': 'Independence as the Central African Republic in 1960.',
                         'source': 'https://history.state.gov/countries/central-african-republic',
                         'year': '1960'},
 'french-upper-volta': {'note': 'Independence as Upper Volta on 5 August 1960; later renamed Burkina '
                                'Faso.',
                        'source': 'https://history.state.gov/historicaldocuments/frus1958-60v14/d66',
                        'year': '1960'},
 'german-german-caroline-islands': {'note': 'Germany renounced its colonial rights under Article 119 of the Treaty '
                               'of Versailles, signed 28 June 1919; the treaty entered into force '
                               'on 10 January 1920. This dates the postwar settlement, not later '
                               'national independence.',
                       'source': 'https://history.state.gov/historicaldocuments/frus1919Parisv13/ch13subch1; '
                                 'https://researchbriefings.files.parliament.uk/documents/LLN-2019-0079/LLN-2019-0079.pdf',
                       'year': '1919'},
 'german-german-east-africa': {'note': 'Germany renounced its colonial rights under Article 119 of the Treaty '
                               'of Versailles, signed 28 June 1919; the treaty entered into force '
                               'on 10 January 1920. This dates the postwar settlement, not later '
                               'national independence.',
                       'source': 'https://history.state.gov/historicaldocuments/frus1919Parisv13/ch13subch1; '
                                 'https://researchbriefings.files.parliament.uk/documents/LLN-2019-0079/LLN-2019-0079.pdf',
                       'year': '1919'},
 'german-german-mariana-islands': {'note': 'Germany renounced its colonial rights under Article 119 of the Treaty '
                               'of Versailles, signed 28 June 1919; the treaty entered into force '
                               'on 10 January 1920. This dates the postwar settlement, not later '
                               'national independence.',
                       'source': 'https://history.state.gov/historicaldocuments/frus1919Parisv13/ch13subch1; '
                                 'https://researchbriefings.files.parliament.uk/documents/LLN-2019-0079/LLN-2019-0079.pdf',
                       'year': '1919'},
 'german-german-marshall-islands': {'note': 'Germany renounced its colonial rights under Article 119 of the Treaty '
                               'of Versailles, signed 28 June 1919; the treaty entered into force '
                               'on 10 January 1920. This dates the postwar settlement, not later '
                               'national independence.',
                       'source': 'https://history.state.gov/historicaldocuments/frus1919Parisv13/ch13subch1; '
                                 'https://researchbriefings.files.parliament.uk/documents/LLN-2019-0079/LLN-2019-0079.pdf',
                       'year': '1919'},
 'german-german-new-guinea': {'note': 'Germany renounced its colonial rights under Article 119 of the Treaty '
                               'of Versailles, signed 28 June 1919; the treaty entered into force '
                               'on 10 January 1920. This dates the postwar settlement, not later '
                               'national independence.',
                       'source': 'https://history.state.gov/historicaldocuments/frus1919Parisv13/ch13subch1; '
                                 'https://researchbriefings.files.parliament.uk/documents/LLN-2019-0079/LLN-2019-0079.pdf',
                       'year': '1919'},
 'german-german-samoa': {'note': 'Germany renounced its colonial rights under Article 119 of the Treaty '
                               'of Versailles, signed 28 June 1919; the treaty entered into force '
                               'on 10 January 1920. This dates the postwar settlement, not later '
                               'national independence.',
                       'source': 'https://history.state.gov/historicaldocuments/frus1919Parisv13/ch13subch1; '
                                 'https://researchbriefings.files.parliament.uk/documents/LLN-2019-0079/LLN-2019-0079.pdf',
                       'year': '1919'},
 'german-german-south-west-africa': {'note': 'Germany renounced its colonial rights under Article 119 of the Treaty '
                               'of Versailles, signed 28 June 1919; the treaty entered into force '
                               'on 10 January 1920. This dates the postwar settlement, not later '
                               'national independence.',
                       'source': 'https://history.state.gov/historicaldocuments/frus1919Parisv13/ch13subch1; '
                                 'https://researchbriefings.files.parliament.uk/documents/LLN-2019-0079/LLN-2019-0079.pdf',
                       'year': '1919'},
 'german-kamerun': {'note': 'Germany renounced its colonial rights under Article 119 of the Treaty '
                               'of Versailles, signed 28 June 1919; the treaty entered into force '
                               'on 10 January 1920. This dates the postwar settlement, not later '
                               'national independence.',
                       'source': 'https://history.state.gov/historicaldocuments/frus1919Parisv13/ch13subch1; '
                                 'https://researchbriefings.files.parliament.uk/documents/LLN-2019-0079/LLN-2019-0079.pdf',
                       'year': '1919'},
 'german-kiautschou': {'note': 'German leased-territory rights in Kiautschou transferred to Japan under '
                               'Articles 156–158 of the Treaty of Versailles, signed 28 June 1919; '
                               'the treaty entered into force on 10 January 1920. This dates the '
                               'postwar settlement, not later national independence.',
                       'source': 'https://avalon.law.yale.edu/imt/partiv.asp; '
                                 'https://researchbriefings.files.parliament.uk/documents/LLN-2019-0079/LLN-2019-0079.pdf',
                       'year': '1919'},
 'german-togoland': {'note': 'Germany renounced its colonial rights under Article 119 of the Treaty '
                               'of Versailles, signed 28 June 1919; the treaty entered into force '
                               'on 10 January 1920. This dates the postwar settlement, not later '
                               'national independence.',
                       'source': 'https://history.state.gov/historicaldocuments/frus1919Parisv13/ch13subch1; '
                                 'https://researchbriefings.files.parliament.uk/documents/LLN-2019-0079/LLN-2019-0079.pdf',
                       'year': '1919'},
 'italian-italian-dodecanese': {'note': 'Italy ceded the Dodecanese to Greece under Article 14 of the Treaty '
                                      'of Peace with Italy, signed 10 February 1947 and effective '
                                      '15 September 1947. This marks the formal postwar settlement, '
                                      'not an independence date.',
                              'source': 'https://treaties.un.org/Pages/showDetails.aspx?objid=080000028028c6f9',
                              'year': '1947'},
 'italian-italian-east-africa': {'note': 'Italian East African colonial administration ended after Allied '
                                       'conquest in 1941. This dates the end of that administration, '
                                       'not the later formal peace settlement or successor independence.',
                               'source': 'https://researchcentre.army.gov.au/library/australian-army-journal-aaj/number-1-july-1948/ex-italian-colonies-africa; '
                                         'https://collection.nam.ac.uk/detail.php?acc=1996-08-388&acc=1996-08-388-25',
                               'year': '1941'},
 'italian-italian-eritrea': {'note': 'Italy renounced its colonial rights under Article 23 of the Treaty '
                                   'of Peace with Italy, signed 10 February 1947 and effective '
                                   '15 September 1947. Wartime control had ended earlier; this dates '
                                   'the formal postwar settlement, not later independence.',
                           'source': 'https://treaties.un.org/Pages/showDetails.aspx?objid=080000028028c6f9',
                           'year': '1947'},
 'italian-italian-libya': {'note': 'Italy renounced its colonial rights under Article 23 of the Treaty '
                                 'of Peace with Italy, signed 10 February 1947 and effective '
                                 '15 September 1947. Wartime control had ended earlier; this dates '
                                 'the formal postwar settlement, not later independence.',
                         'source': 'https://treaties.un.org/Pages/showDetails.aspx?objid=080000028028c6f9',
                         'year': '1947'},
 'italian-italian-somaliland': {'note': 'Italy renounced its colonial rights under Article 23 of the Treaty '
                                      'of Peace with Italy, signed 10 February 1947 and effective '
                                      '15 September 1947. The later 1950–1960 Italian administration '
                                      'was a UN trusteeship, not restored colonial sovereignty; this '
                                      'dates the formal postwar settlement, not later independence.',
                              'source': 'https://treaties.un.org/Pages/showDetails.aspx?objid=080000028028c6f9; '
                                        'https://research.un.org/en/docs/tc/somaliland',
                              'year': '1947'},
 'japanese-burma': {'note': 'Japanese rule or occupation ended in 1945, the year of Japan\'s '
                               'surrender signed on 2 September 1945. This marks the end of '
                               'Japanese control, not a later independence date.',
                       'source': 'https://www.archives.gov/milestone-documents/surrender-of-japan',
                       'year': '1945'},
 'japanese-china': {'note': 'Japanese rule or occupation ended in 1945, the year of Japan\'s '
                               'surrender signed on 2 September 1945. This marks the end of '
                               'Japanese control, not a later independence date.',
                       'source': 'https://www.archives.gov/milestone-documents/surrender-of-japan',
                       'year': '1945'},
 'japanese-french-indo-china': {'note': 'Japanese rule or occupation ended in 1945, the year of Japan\'s '
                               'surrender signed on 2 September 1945. This marks the end of '
                               'Japanese control, not a later independence date.',
                       'source': 'https://www.archives.gov/milestone-documents/surrender-of-japan',
                       'year': '1945'},
 'japanese-hong-kong': {'note': 'Japanese rule or occupation ended in 1945, the year of Japan\'s '
                               'surrender signed on 2 September 1945. This marks the end of '
                               'Japanese control, not a later independence date.',
                       'source': 'https://www.archives.gov/milestone-documents/surrender-of-japan',
                       'year': '1945'},
 'japanese-korea': {'note': 'Japanese rule or occupation ended in 1945, the year of Japan\'s '
                               'surrender signed on 2 September 1945. This marks the end of '
                               'Japanese control, not a later independence date.',
                       'source': 'https://www.archives.gov/milestone-documents/surrender-of-japan',
                       'year': '1945'},
 'japanese-malaya': {'note': 'Japanese rule or occupation ended in 1945, the year of Japan\'s '
                               'surrender signed on 2 September 1945. This marks the end of '
                               'Japanese control, not a later independence date.',
                       'source': 'https://www.archives.gov/milestone-documents/surrender-of-japan',
                       'year': '1945'},
 'japanese-manchukuo': {'note': 'Japanese rule or occupation ended in 1945, the year of Japan\'s '
                               'surrender signed on 2 September 1945. This marks the end of '
                               'Japanese control, not a later independence date.',
                       'source': 'https://www.archives.gov/milestone-documents/surrender-of-japan',
                       'year': '1945'},
 'japanese-netherlands-indies': {'note': 'Japanese rule or occupation ended in 1945, the year of Japan\'s '
                               'surrender signed on 2 September 1945. This marks the end of '
                               'Japanese control, not a later independence date.',
                       'source': 'https://www.archives.gov/milestone-documents/surrender-of-japan',
                       'year': '1945'},
 'japanese-oceania': {'note': 'Japanese rule or occupation ended in 1945, the year of Japan\'s '
                               'surrender signed on 2 September 1945. This marks the end of '
                               'Japanese control, not a later independence date.',
                       'source': 'https://www.archives.gov/milestone-documents/surrender-of-japan',
                       'year': '1945'},
 'japanese-taiwan': {'note': 'Japanese rule or occupation ended in 1945, the year of Japan\'s '
                               'surrender signed on 2 September 1945. This marks the end of '
                               'Japanese control, not a later independence date.',
                       'source': 'https://www.archives.gov/milestone-documents/surrender-of-japan',
                       'year': '1945'},
 'joint-new-hebrides': {'note': 'Independence as Vanuatu in 1980.',
                        'source': 'https://history.state.gov/countries/vanuatu',
                        'year': '1980'},
 'portuguese-angola': {'note': 'Independence on 11 November 1975.',
                       'source': 'https://history.state.gov/countries/angola',
                       'year': '1975'},
 'portuguese-cape-verde': {'note': 'Independence in 1975.',
                           'source': 'https://www.worldbank.org/en/country/caboverde/overview',
                           'year': '1975'},
 'portuguese-macau': {'note': 'Handover to China on 20 December 1999.',
                      'source': 'https://www.fmprc.gov.cn/eng/zy/wjls/3604_665547/202405/t20240531_11367581.html; '
                                'https://yearbook.gcs.gov.mo/yearbook_pdf/2024/myb2024ePA01CH23.pdf',
                      'year': '1999'},
 'portuguese-mozambique': {'note': 'Independence on 25 June 1975.',
                           'source': 'https://portaldogoverno.gov.mz/informacao-geral/; '
                                     'https://minec.gov.mz/historia/',
                           'year': '1975'},
 'portuguese-portuguese-guinea': {'note': 'Independence declared on 24 September 1973; recognized by '
                                          'Portugal on 10 September 1974.',
                                  'source': 'https://uniogbis.unmissions.org/en/chronology-events-3',
                                  'year': '1973'},
 'portuguese-portuguese-india': {'note': 'Portuguese rule in Goa ended in 1961, followed by integration '
                                         'into India.',
                                 'source': 'https://www.goa.gov.in/',
                                 'year': '1961'},
 'portuguese-portuguese-timor': {'note': 'Independence declared on 28 November 1975; sovereignty '
                                         'restored on 20 May 2002.',
                                 'source': 'https://timor-leste.gov.tl/?p=29&lang=en',
                                 'year': '1975'},
 'portuguese-sao-tome-and-principe': {'note': 'Independence in 1975.',
                                      'source': 'https://bcstp.st/Bcstp/rm/dinheiro.pdf',
                                      'year': '1975'},
 'spanish-cuba': {'note': 'Independence as the Republic of Cuba in 1902.',
                  'source': 'https://history.state.gov/countries/cuba',
                  'year': '1902'},
 'spanish-equatorial-guinea': {'note': 'Independence in 1968.',
                               'source': 'https://history.state.gov/countries/equatorial-guinea',
                               'year': '1968'}}

PILL_DATE_EXCLUSIONS = {'british-alderney': {'note': 'Continuing Crown Dependency; no independence year.',
                      'source': 'https://commonslibrary.parliament.uk/research-briefings/cbp-9706/'},
 'british-anguilla': {'note': 'Continuing British Overseas Territory; no independence year.',
                      'source': 'https://commonslibrary.parliament.uk/research-briefings/cbp-9706/'},
 'british-australia': {'note': 'Independence developed through several constitutional stages; no single '
                               'year is shown.',
                       'source': 'https://history.state.gov/countries/australia'},
 'british-bermuda': {'note': 'Continuing British Overseas Territory; no independence year.',
                     'source': 'https://commonslibrary.parliament.uk/research-briefings/cbp-9706/'},
 'british-british-east-africa': {'note': 'Regional currency area with different independence dates: '
                                         'Tanganyika in 1961, Uganda in 1962 and Kenya in 1963.',
                                 'source': 'https://history.state.gov/countries/kenya; '
                                           'https://history.state.gov/countries/uganda; '
                                           'https://history.state.gov/countries/tanzania'},
 'british-british-north-borneo': {'note': 'Joined Malaysia in 1963; this was a federation milestone.',
                                  'source': 'https://history.state.gov/countries/malaysia'},
 'british-british-west-africa': {'note': 'Regional currency area with different independence dates: '
                                         'Ghana in 1957, Nigeria in 1960, Sierra Leone in 1961 and '
                                         'Gambia in 1965.',
                                 'source': 'https://history.state.gov/countries/ghana; '
                                           'https://history.state.gov/countries/nigeria; '
                                           'https://history.state.gov/countries/sierra-leone; '
                                           'https://history.state.gov/countries/gambia'},
 'british-canada': {'note': 'Independence developed through several constitutional stages; no single '
                            'year is shown.',
                    'source': 'https://history.state.gov/countries/canada'},
 'british-cayman-islands': {'note': 'Continuing British Overseas Territory; no independence year.',
                            'source': 'https://commonslibrary.parliament.uk/research-briefings/cbp-9706/'},
 'british-falkland-islands': {'note': 'Continuing British Overseas Territory; no independence year.',
                              'source': 'https://commonslibrary.parliament.uk/research-briefings/cbp-9706/'},
 'british-gibraltar': {'note': 'Continuing British Overseas Territory; no independence year.',
                       'source': 'https://commonslibrary.parliament.uk/research-briefings/cbp-9706/'},
 'british-gilbert-and-ellice-islands': {'note': 'Successors became independent in different years: '
                                                'Tuvalu in 1978 and Kiribati in 1979.',
                                        'source': 'https://history.state.gov/countries/kiribati; '
                                                  'https://history.state.gov/countries/tuvalu'},
 'british-guernsey': {'note': 'Continuing Crown Dependency; no independence year.',
                      'source': 'https://commonslibrary.parliament.uk/research-briefings/cbp-9706/'},
 'british-isle-of-man': {'note': 'Continuing Crown Dependency; no independence year.',
                         'source': 'https://commonslibrary.parliament.uk/research-briefings/cbp-9706/'},
 'british-jersey': {'note': 'Continuing Crown Dependency; no independence year.',
                    'source': 'https://commonslibrary.parliament.uk/research-briefings/cbp-9706/'},
 'british-malaya-and-british-borneo': {'note': 'Shared currency area with territories that became '
                                               'independent in different years.',
                                       'source': 'https://history.state.gov/countries/malaysia; '
                                                 'https://history.state.gov/countries/brunei; '
                                                 'https://www.mfa.gov.sg/about-mfa/histories-and-milestones/'},
 'british-montserrat': {'note': 'Continuing British Overseas Territory; no independence year.',
                        'source': 'https://commonslibrary.parliament.uk/research-briefings/cbp-9706/'},
 'british-new-zealand': {'note': 'Independence developed through several constitutional stages; no '
                                 'single year is shown.',
                         'source': 'https://history.state.gov/countries/new-zealand'},
 'british-pitcairn-islands': {'note': 'Continuing British Overseas Territory; no independence year.',
                              'source': 'https://commonslibrary.parliament.uk/research-briefings/cbp-9706/'},
 'british-rhodesia-and-nyasaland': {'note': 'Successors became independent in different years: Zambia '
                                            'and Malawi in 1964, Zimbabwe in 1980.',
                                    'source': 'https://history.state.gov/countries/zimbabwe; '
                                              'https://history.state.gov/countries/zambia; '
                                              'https://history.state.gov/countries/malawi'},
 'british-saint-helena': {'note': 'Continuing British Overseas Territory; no independence year.',
                          'source': 'https://commonslibrary.parliament.uk/research-briefings/cbp-9706/'},
 'british-sarawak': {'note': 'Joined Malaysia in 1963; this was a federation milestone.',
                     'source': 'https://history.state.gov/countries/malaysia'},
 'british-turks-and-caicos-islands': {'note': 'Continuing British Overseas Territory; no independence '
                                              'year.',
                                      'source': 'https://commonslibrary.parliament.uk/research-briefings/cbp-9706/'}}
