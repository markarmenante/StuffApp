# Reviewed African currency families

Verified 26 October 2026. This is display and report filing, not a database
migration, catalogue correction, or bulk backfill. Full territorial names,
Pick suffixes, series, photographs and purchase facts stay on each record.

## Scope of the live audit

The reviewed collection has five BAO notes filed as French West Africa, and six
BCEAO notes filed as West African States, West African States (Senegal), or Togo.
They now share **West African franc area**, with distinct BAO and BCEAO sections.
The intermediate AOF/Togo issuing institute is described in the history but is
not silently treated as either authority.

Three Central African notes form a second lineage: CCFOM (French Equatorial
Africa, 1944), the AEF/Cameroon Institut d'Émission (1957), and BEAC (Cameroon,
1983). **Central African franc area** keeps three distinct issuer sections.
BEAC notes are explicitly identified as issues for independent states.

The British audit found five East African Currency Board notes already filed
under British East Africa, two West African Currency Board notes already filed
under British West Africa, and separate Rhodesian and federal Rhodesia/Nyasaland
issuers. These have no equivalent country split needing consolidation, so this
change leaves them alone. Independent Kenya, Uganda and Gambia issues remain
separate, as do German East African notes.

## Exact matching and boundaries

`banknote_africa.regional_issue(country, date, issuer, series)` returns fresh,
derived metadata. It uses full issuer aliases after accent/punctuation folding,
not substring matches or inferred date-to-issuer assignments.

- BCEAO's French name, English name and acronym resolve only with a bounded
  regional/member attribution, a blank country, or that exact authority used
  as the saved country. The Senegal/Togo country text and catalogue suffixes
  remain visible; `P-702Kn`, `P-803Tn` and `P-808Tm` remain distinct references.
- BAO and CCFOM also served other territories. Their names alone cannot identify
  the relevant African catalogue scope: blank countries and unrelated countries
  do not resolve. BAO Cameroon issues are not pulled into West Africa; CCFOM
  Antilles, Réunion and Somaliland issues are not pulled into Central Africa.
- Cameroon/Cameroun spellings can join an explicitly named Central African
  issuer. German Kamerun, Belgian Congo and ambiguous bare Congo cannot.
- An independent national bank is never replaced with the regional bank.
  BCEAO and BEAC are separate authorities/currency areas, and neither is the
  British West African Currency Board or Rhodesia's Central African Currency Board.
- `catalogue_scope` preserves the saved attribution. Family keys are unsuitable
  as duplicate identity keys; this module does not change duplicate checking.
- BCEAO contributes to the existing West African States entity only. BEAC
  contributes to a separately labelled Central African States successor entity;
  owning a BEAC note does not establish colonial Cameroon coverage. Regional
  circulation does not credit every member territory.

Dates remain untouched. A BCEAO note saved as 1958 gets a short review note
because BCEAO was created in 1959. A Togo BCEAO note saved before 1963 also
gets a territorial-date review note. These are prompts to distinguish a catalogue
family date from the actual issue date, not automatic corrections. The same
principle covers BEAC design dates before operations began and Equatorial Guinea
attributions before its membership. Unknown and ranged dates are not guessed.

## Primary evidence and denomination scopes

The header lists describe documented denominations across each authority's
issues, including values absent from this collection; they do not mean every
denomination existed concurrently or in every territorial variety.

| Authority | Header denominations in francs | Evidence and scope |
| --- | --- | --- |
| BAO, West African issues | 5, 10, 25, 50, 100, 500, 1,000, 5,000 | BCEAO's 2003 annual report describes the BAO range; the contemporary UN Togo report explicitly includes 10 francs. |
| BCEAO | 50, 100, 500, 1,000, 2,000, 2,500, 5,000, 10,000 | BCEAO museum history plus the official 2,000-franc issue notice. Includes withdrawn values. |
| CCFOM, Central African issues | 5, 10, 20, 50, 100, 500, 1,000, 5,000 | BEAC's 30th-anniversary catalogue, printed pages 25–27, Biang/Bifra illustrations, visually checked. |
| AEF/Cameroon Institut d'Émission | 5, 10, 20, 50, 100, 500, 1,000 | Same catalogue, printed page 28: includes the low values modified to IEAEFC in 1957 and the four larger denominations. |
| BEAC | 500, 1,000, 2,000, 5,000, 10,000 | Same catalogue, printed pages 36–37 and 53; 2,000 francs introduced in 1993. |

Sources:

- [BCEAO official chronology](https://www.bceao.int/sites/default/files/inline-files/chronologie_des_evenements_marquants_de_l_histoire_de_la_bceao_et_de_l_umoa.pdf): BAO 1901–1955, AOF/Togo institute 1955–1959, BCEAO from 1959.
- [BCEAO key dates](https://www.bceao.int/fr/content/dates-cles): 4 April 1959 institutional change; 1962 monetary union; Togo membership effective 17 December 1963.
- [BCEAO 2003 annual report, printed page 60](https://www.bceao.int/sites/default/files/2017-12/rapport_annuel_de_la_bceao_2003.pdf): BAO history and denominations.
- [UN Togo report T/1300](https://digitallibrary.un.org/record/1639506/files/T_1300-EN.pdf): contemporary list of BAO notes circulating in Togo.
- [BCEAO museum](https://www.bceao.int/fr/content/presentation-du-musee-de-la-monnaie) and [2,000-franc issue notice](https://www.bceao.int/fr/content/billet-de-2000-fcfa): historical range and 2003 addition.
- [BEAC monetary history](https://www.beac.int/billets-pieces/histoire-franc-cfa/histoire-de-lemission-monetaire-afrique-centrale/): distinct Central African successor authorities, BEAC operations from 1973, and Equatorial Guinea's 1985 accession.
- [BEAC 30th-anniversary catalogue](https://www.beac.int/wp-content/uploads/2016/11/billets-et-pieces-brochure-du-30eme-anniversaire.pdf): illustrated issuer/denomination evidence and chronological boundaries.
- [Central Bank of Kenya currency history](https://www.centralbank.go.ke/currency-history/), [Central Bank of Nigeria currency gallery](https://www.cbn.gov.ng/currency/gallery.html), and [Reserve Bank of Zimbabwe history](https://www.rbz.co.zw/index.php/about-us/about-us/history): British regional boards and later national/federal authorities are distinct.

Regression coverage is in `tests/test_banknote_africa.py`; integrated list,
History-on/off, responsive and PDF acceptance is exercised by the regional
collection suites. All inputs remain read-only.
