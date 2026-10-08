# Lønberegningsregler – Lønsystem

**Bemærk:** Stamdata (databasen) er den autoritative kilde til satser og løntypekoder –
denne fil er en menneskelæsbar reference, som kan komme bagud af ændringer gjort direkte i
Stamdata-UI'en. Tjek altid Stamdata → Overenskomsttyper / Løntypekoder ved tvivl. Sidst
gennemgået mod koden 2026-07-30.

## Timesatser pr. 1. marts 2026

| Medarbejdertype | Grundtimeløn | Tillæg | Samlet timeløn |
|----------------|--------------|--------|----------------|
| Chauffør under oplæring | 159,65 kr. | – | 159,65 kr. |
| Chauffør (nyansættelse) | 159,65 kr. | Chaufførtillæg 14,50 kr. | 174,15 kr. |
| Chauffør (efter 9 mdr.) | 159,65 kr. | 14,50 + anciennitet 8,15 kr. | 182,30 kr. |
| Faglært chauffør | 159,65 kr. | 14,50 + anciennitet 8,15 + faglært 4,00 kr. | 186,30 kr. |
| + Kvalifikationstillæg (hænger+kran) | +3,80 kr. | tillæg oveni | +3,80 kr. |

---

## Effektiv arbejdstid

**Effektiv tid = sluttid − starttid** (total varighed fra stempelind til stempelud)

Der sondres IKKE internt mellem rådighedstid, hvil, kørsel etc. i lønberegningen. Hele perioden tæller.

Undtagelse: Pålæsning og aflæsning (manuelt tastet fra dagssedler) medregnes i effektiv tid.

---

## Minimum 4-timer regel

Kilde: Chaufføroverenskomst §3, stk. 1 / §5 afløser

- En vagt må **ikke** aflønnes for **under 4 timer** uden særlig begrundelse
- Systemet markerer automatisk vagter under 4 timer med et ❗-ikon (aktiviteten forbliver `pending`, ikke deaktiveret)
- Kræver **manuel godkendelse** med initialer og begrundelse
- Ved godkendelse under 4 timer: den faktiske tid bruges i lønberegningen

---

## Overtid

Se `OVERTIME_RULES.md` for detaljerede regler.

**Opsummering** (tidsrumsbaseret, ikke akkumulerede timer – normaltids-loftet forbruges kun i kl. 06-18, se `OVERTIME_RULES.md`):
- Kl. 05-06: +44,54 kr./time
- Kl. 18-21, samt timer ud over normaltidsloftet i kl. 06-18 (de første 3 sådanne timer): +44,54 kr./time
- Kl. 21-05, samt overtidstimer ud over de første 3: +109,40 kr./time
- Søn- og helligdage: +109,40 kr./time (al arbejde)

---

## Ubekvem arbejdstid – UDGÅET (erstattet 10/6-2026)

De tre overtidstillæg herover **erstatter fuldstændigt** den tidligere separate
ubekvemstillæg-model (18-23, 23-06, lørdag 14+/søn-/helligdage), som er bekræftet af bruger og
fjernet fra beregningen. Denne sektion stod tidligere med de gamle satser (46,93 / 52,65 /
102,71 kr./time) – de tillæg findes IKKE i den nuværende kode og skal ikke lægges til oveni
overtidstillæggene. Se `docs/OVERTIME_RULES.md` for den fulde, aktuelle model.

---

## Medarbejdertillæg (individuelt, fra 2026-08-13)

Ud over overenskomsttypens grundsats kan en medarbejder have et individuelt kr/time-tillæg
("Ikke overenskomstmæssigt tillæg"), administreret under sidebar-punktet "Tillæg" og gemt i
tabellen `employee_supplements` med en historisk gyldighedsperiode (start-/slutdato).

**Satsopslag ved lønberegning:** for den periode der beregnes, findes det tillæg hvis
gyldighedsperiode overlapper perioden. Overlapper flere rækker (fordi et nyt tillæg er oprettet
midt i en periode), bruges rækken med nyeste startdato for HELE perioden — ingen dag-for-dag
opdeling. Findes intet overlap, bruges kun grundsatsen. Reglen gør samtidig genberegning af en
gammel, allerede afsluttet periode historisk korrekt.

**Hvor det slår igennem:** tillægget lægges til grundsatsen étsted (`hourly_rate` i
`_calculate_employee()`), og fordi den variabel allerede bruges alle steder nedstrøms, slår det
automatisk igennem i: normaltid (kode 1 i CSV'en), søgnehelligdags-betaling, afspadsering,
sygdom, barsel, skole/kursus, samt i Fraværsoversigtens viste sats (samme funktion genbruges der).
Det påvirker IKKE de tre overtidstillæg (OT_BEFORE/OT_13/OT_EXTRA) eller salt-/overnatnings-
tillæggene, som har deres egne, adskilte satser.

**Afslutning af et tillæg:** stopper ikke med øjeblikkelig virkning — det gælder stadig resten af
den lønperiode hvori afslutningsdatoen falder, og bortfalder først fra den efterfølgende periode.

Se `DATA_MODEL.md` for tabelstruktur og `CODEREF.md` for implementeringsdetaljer.

---

## Daterede satser (fra 2026-10-06)
- Fremtidige satser lægges ind i Stamdata › Overenskomsttyper › *Fremtidige satser* (type, ny timesats, gælder fra).
- Satsen for en lønperiode er satsen der gælder på periodens **sidste dag**: ligger datoen inde i perioden, får hele perioden den nye sats (fx 1/3-2027 → perioden 22/2–7/3-2027).
- Når datoen nås, bliver den nye sats typens nuværende sats; den gamle gemmes, så ældre perioder regnes uændret.
- Fremtidige satser kan rettes og slettes (logges med alle værdier); satser der er trådt i kraft er låst historik.
- Roller med *Lønkørsel* sat eksplicit får en popup X dage før lønperioden med de nye satser (samme varsel som elevløn).
- Lærlingeoverenskomstens satser (lærlinge, disponentspecialet, EGU) for 1/5-2025, 1/3-2026 og 1/3-2027 er lagt ind én gang ved opstart.

## Elevløn-trin (Lærlingeoverenskomsten 2025-2028 § 8, fra 2026-10-06)
- EUD-lærlinge lønnes efter år af lærekontrakten, regnet **baglæns** fra slutdatoen: sidste år, næstsidste år, tredjesidste år. Alt før tredjesidste år får tredjesidste-satsen (overenskomsten har ikke flere trin).
- Skifter eleven trin inde i en lønperiode, gælder den nye sats **hele lønperioden**.
- Trinnene er overenskomsttyperne `Lærling (EUD) … af lærerkontrakt`. Systemet skifter aldrig selv: lønbogholderen får en popup (30 dage før lønperioden, påmind igen 7 dage før) og godkender, ændrer, udsætter eller bevarer satsen med en bemærkning. Et godkendt skift træder i kraft fra lønperiodens start; Lønkørsel bruger typen for perioden.
- Afviger en elevs type fra trinnet i en åben periode, vises "Mulig fejl i elevløn" i Advarsler (eksporten blokeres ikke), indtil typen rettes eller bevares med en bemærkning.
- Voksenlærlinge (fyldt 25 ved aftalens indgåelse, § 8 stk. 4), EGU-elever og disponentspecialet har ingen trin.
- Popups vises kun for roller hvor rettigheden *Godkend elevlønændring* er sat eksplicit (ikke via systemrollen).
- Trykker en lønbogholder "Behandl", låses skiftet for de andre ("Behandles af …") i op til 15 minutter. Der kan kun være én åben beslutning pr. skift.
- Kun den aktuelle lønperiode og perioden der lige er slut tjekkes (den køres typisk nu). Ældre åbne perioder tjekkes ikke, da systemet kun kender medarbejderens type i dag (ikke historikken). Dialogen foreslår den første åbne lønperiode fra trinnets start. Er en periode allerede låst (eksporteret), vises beløbet der mangler ("skal efterreguleres") – regnet som forskellen i Lønafregningens "I alt" med den rigtige type – i dialogen, i Lønkørsel og i loggen. Efterreguleringen laves indtil videre manuelt i Danløn.
- Ændres en elevs datoer, voksenelev-markering eller overenskomsttype, annulleres åbne beslutninger automatisk (logges), og advarslen kommer igen med de rigtige datoer.
- Alle beslutninger logges i audit-loggen med gammel → ny værdi.

## Lønstigninger og Advarsler-oversigten (fra 2026-10-06)
- **9 måneders anciennitet** behandles som elevløn-trin: når en medarbejder når 9 måneder, foreslås skift fra
  '<type>' til '<type>. 9 mdr anciennitet' (hvis typen findes). Der tælles fra **anciennitetsdatoen**, hvis den er
  udfyldt, ellers fra ansættelsesdatoen. Ligger datoen inde i en lønperiode, gælder den nye sats hele perioden.
  Varsel før, godkend fra en lønperiode, 'Mulig fejl i løn' hvis det er glemt, efterregulering for låste perioder.
  Medarbejdere hvor den gamle anciennitetsadvarsel er afvist, springes over.
- **Advarsler-oversigten** erstatter de enkelte popups: Mulig fejl i løn · Kommende ændringer i overenskomst (elevløn + anciennitet) ·
  Øvrige (nye satser, §56, mærkedage). 🔔 i toppen viser antallet. Vinduet åbner kun af sig selv ved start, når der er
  nye advarsler.
- **Personlige indstillinger** (⚙ Indstillinger): Kommende ændringer i overenskomst – første besked (standard 30 dage før lønperioden) og
  påmind igen (7 dage, eller aldrig). Øvrige – første besked (højst 30 dage), anden besked (7 dage) og på dagen;
  "OK" skjuler kun til næste påmindelse. Man ser kun indstillinger for de advarsler rollen giver.

## Anciennitet

- Beregnes automatisk fra `hire_date`
- 0–8 måneder og 29 dage: nyansættelses-sats
- Fra og med 9 måneder: anciennitetstillæg (+8,15 kr./time)
- Pop-up ved opstart: hvis medarbejder har nået 9 måneder og er i forkert løngruppe
- Pop-up-knapper: "Luk" eller "Gå til medarbejder for at ændre timesats"

---

## Særlig opsparing og pension

| Element | Sats |
|---------|------|
| Særlig opsparing | 10% af grundlønnen |
| Særligt løntillæg (timelønnet) | 8,40% |
| Pension – arbejdsgiver | 11% |
| Pension – lønmodtager | 2% |
| Pension i alt | 13% |

---

## CSV-format til Danløn

| Kolonne | Felt | Eksempel |
|---------|------|---------|
| A | CVR-nummer | fra Stamdata → CVR-nummer (medarbejderens eget, ellers standard) |
| B | Medarbejdernummer (lønnummer) | [medarbejdernr] |
| C | Danløn-kode | 1=Normal, 7=OT før, 8=OT 1-3t, 9=Øvrig OT, 6=Salt, 14=Overnatning, 71=Afspadsering, 51=Sygdom/§56/Barsel, 15=Barn 1.sygedag, 81=Feriefri, 2=Skole/kursus, 4/63=Søgnehelligdag, 60=Ferie (default ekskluderet fra CSV) |
| D | Antal (timer eller antal, afhænger af løntypen) | 7.40 |
| E | Timesats / tillægssats (hvis konfigureret til at vises) | 174.15 |
| F | Totalbeløb (hvis konfigureret til at vises i stedet for/ud over sats) | – |

Én række pr. løntype med antal > 0 og "Medtag i CSV" slået til i Stamdata → Løntypekoder.
Koder, enhed og hvilke af E/F der vises er alt sammen konfigurérbart pr. løntype der – se
`CODEREF.md` for den fulde tabel og implementeringsdetaljer.

---

## Prøvekørsel – Excel-markering

Følgende markeres i prøvekørsels-Excel:
- 🟡 Dage med **under 4 timer** (kræver manuel godkendelse)
- 🟠 Dage med **over 12 timer** (ualmindeligt lang vagt – til kontrol)

---

## Åbne punkter

- [x] Præcis beregning af overtid: dagligt (pr. vagt/kalenderdag) – se OVERTIME_RULES.md
- [x] Ubekvem tid og overtidstillæg kombineres IKKE – ubekvem-modellen er udgået, se ovenfor
- [x] Danløn-koder – konfigureres nu pr. løntype i Stamdata → Løntypekoder (ikke længere fast "1")
- [x] Afspadsering – egen kode (71), timer summeres (periode = skemalagte timer/hverdag)
- [x] Disponentgrupper og output-mappe stier – konfigureres i Stamdata / ved eksport
- [ ] Verificér om "Øvrigt overtid" (nat/aften) altid stemmer med Danløns egen beregning for
      medarbejdere med meget tidligt/sent arbejde – mindre afvigelser observeret 2026-07-30
      ved sammenligning med det gamle Tacho-baserede system, uden en entydig fælles årsag
