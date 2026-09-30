# Gennemgang: program vs. Brugervejledning og Teknisk dokumentation

**Dato:** 2026-09-30 (kode til og med commit `cdf9e7f`)
**Metode:** Brugervejledning.docx og Teknisk dokumentation.docx er udtrukket og sammenholdt afsnit for afsnit med koden (routers, calculators, parser, models, session.py, app.js, index.html, deploy/, backup/). Henvisninger "BV" = Brugervejledning, "TEK" = Teknisk dokumentation. Kodelinjer er omtrentlige.

Ingen filer er ændret – dette er kun en rapport.

> **Status (opdateret samme dag):** Rettet: A1.1 afvist af bruger (ikke et problem), A2.8 (rettigheder genindsættes ikke), A2.9 + alle se-rettigheder (håndhæves nu i backend, ny rettighed "Redigér aktiviteter"), A2.12 (helligdage synlige for alle), A2.13 (Stamdata-menu), A3.14-17 (låst periode), A4.18 (split), A4.19 (tømte felter), A1.3 (Lønkørsel "I alt" = Lønafregning; PDF bevidst uændret). Dokumentationen (build_docs.py → de to .docx, CODEREF.md, DATA_MODEL.md) er opdateret med dagens ændringer (afsnit B1). Dokumentationsfejlene i B2-B6 og de udokumenterede funktioner i C er også rettet i build_docs.py (anden runde samme dag). Øvrige KODEFEJL i afsnit A er IKKE rettet – nogle af dem er nu beskrevet som kendt adfærd i dokumentationen (fx overnatning tæller som fravær i Dagsplan, sletning af vogn tjekker kun aktiviteter).

---

## A. Fejl i selve programmet (prioriteret)

### A1. Løn / penge

1. **Sent importerede vagter bliver aldrig lønnet.** DDD-import i en låst periode rulles via `get_billing_period()` over i næste periode (`import_ddd.py:551`), men `_calculate_employee()` og pending-tjekket i `export_csv` vælger aktiviteter på **dato**, ikke `pay_period_id` (`payroll_router.py:308-318`, `1166-1176`). Vagten kommer derfor hverken med i næste periodes Danløn-CSV eller blokerer "Kør løn" hvis den er afventende. *Bekræftet.*
2. **`get_billing_period()` går kun én periode frem** (`pay_period.py:36-42`) – er næste periode også låst, lander vagten alligevel i en låst periode.
3. **Tre forskellige "I alt"-beløb for samme medarbejder:** Lønkørsel-fanen medregner hverken Ferie eller Afspadsering (`app.js:4145-4154`), PDF-timesedlen medregner Afspadsering (`timeseddel_router.py:240`), Lønafregning medregner både Ferie og Afspadsering, Danløn-CSV har Afspadsering men ikke Ferie.
4. **PDF-timeseddel på søn-/helligdage:** LØNOPSUMMERING-rækkerne bruger `ot_13/ot_extra` uden `sh_kode8/9` og har ingen række for SH-betaling (kode 4/63) – men "I alt" indeholder dem. Rækkerne summerer ikke til "I alt". I dagsoversigten trækkes SH-timerne fra "Timer arbejdet" uden at blive vist i OT-kolonnerne (`timeseddel_router.py:108-115, 229-234, 371-373`).
5. **Lønafregningens topsum og Excel-prøvekørsel:** SH-betaling indgår i totalen uden egen linje (Lønafregning), og i Excel står SH både i TOTAL-rækken og igen i "Søgnehelligdag"-rækken (dobbelttælling hvis man summerer). Ingen række for springertillæg/afspadsering. Etiketten "Barn 1.sygedag" dækker reelt "Barn 1.sygedag u. 8 uger".
6. **Danløn-koder med samme kode slås sammen med satsen fra første nøgle** (`payroll_router.py:1131-1135`) – med placeholder-kode "1" bliver både sats og total forkerte, ikke kun koden.
7. **Tilbagedateret medarbejdertillæg** valideres ikke mod låste perioder (`employee_supplements.py:22-46`) og vinder for hele den gamle periode → genberegning af gammel periode ændres bagudrettet.

### A2. Rettigheder og sikkerhed

8. **Rettigheder genindsættes ved hver serverstart.** `_ensure_activity_permissions`, `_ensure_vagtplan_permissions` og `_ensure_toggle_springer_permission` (`session.py:832ff`) tilføjer `approve_activities`, `view_calendar`, `vagtplan_view`, `vagtplan_edit_all` og `toggle_springer` til **alle** roller ved hver opstart (produktion genstarter hver nat). Fjerner man dem fra en rolle, kommer de igen. *Bekræftet.*
9. **Flere rettigheder håndhæves kun i frontend.** approve, deactivate, DELETE (permanent sletning), split, correct-segment og auto-approve-pending kræver kun login (`activities.py:878, 907, 957, 992, 1214`). `view_employees`/`view_vehicles`/`vagtplan_view` tjekkes ikke i backend. `vagtplan_edit_own` begrænser kun når `source='vagtplan'`. *Bekræftet for approve/deactivate.*
10. **Man kan låse sig selv ude:** backend tillader at deaktivere egen konto/fjerne egen admin-rolle, uden tjek for mindst én aktiv admin; rolle valideres ikke mod roles-tabellen; ingen minimumslængde på adgangskode (`users.py update_user`).
11. `POST /api/employees/{id}/dismiss-anciennitet` har intet rettighedstjek (`employees.py:241`).
12. **Helligdage vises kun for brugere med `stamdata`-rettighed:** `GET /api/stamdata/holidays` kræver `stamdata` (`stamdata.py:23, 886`), og frontend sluger 403 → Lønbogholder/Disponent ser ingen helligdagsmarkering i aktivitetskalenderen. Samme for CVR-dropdown i medarbejder-modalen (`GET /cvr-numbers`). *Bekræftet.*
13. **Stamdata-menupunktet** ligger i "System"-sektionen med `data-perm-require="user_management"` (`index.html:121-128`) – en rolle med `stamdata` men uden `user_management` ser aldrig Stamdata.

### A3. Låst periode – huller efter 30/9-ændringerne

14. `/deactivate` og `DELETE` tjekker kun **fravær** (`activities.py:334-341`) – en normal aktivitet i låst periode kan deaktiveres via API, og en manuel normal aktivitet kan slettes permanent. Detaljevisningen viser stadig "✗ Deaktiver" på en afventende normal aktivitet i låst periode. *Bekræftet.*
15. `approve`, `bulk_auto_approve` og `hide-from-vagtplan` har intet låsetjek.
16. `DELETE /api/vagtplan-comments/{id}` tjekker ikke låst periode (`vagtplan_comments.py:81-94`) – commit e7abdf7 dækker kun opret/ret.
17. **"Fortryd tidsændring"** (`undo_edit`, `activities.py:838`) bruger `get_or_create_period_for_date` uden låsetjek → kan flytte en aktivitet ind i en låst periode.

### A4. Funktionsfejl

18. **Split giver 500-fejl efter "Ret til andet arbejde".** Et rettet segment har 4 elementer, men split pakker ud som 3 (`activities.py:1245`). *Bekræftet.*
19. **Felter kan ikke tømmes.** `update_employee` og `update_activity` bruger `model_dump(exclude_none=True)` (`employees.py:349`, `activities.py:794`). Tømmer man adresse, e-mail, telefon, initialer, førerkortnr. på medarbejder, eller vognnr./KM på aktivitet, bevares den gamle værdi uden besked. *Bekræftet for medarbejder.*
20. **CVR:** (a) ved ≥2 CVR bindes medarbejderen fast til det aktuelle standard-CVR ved gem (følger ikke med hvis standard skiftes); (b) omdøbes et CVR-nummer opdateres `Employee.cvr_number` (streng, ikke FK) ikke → gammelt nummer i CSV/PDF.
21. **JS-fejl ved oprettelse af Funktionær:** `onAgreementKindChange` slår `#emp-dispatcher-groups` op, som ikke findes mere (`app.js:3496-3503`) → TypeError, forvalg af Kontor-gruppe virker aldrig.
22. **Slettede auto-helligdage genopstår** ved hver serverstart (`session.py:504-516`), selvom UI'et tilbyder sletning.
23. **Overnatning tælles som fravær** i Dagsplan (rød + fraværsadvarsel) og i Fraværsoversigten (filter `activity_type != "normal"`, `dagsplan_router.py:125,159`, `absence_overview_router.py:99`).
24. **Flere biler pr. vagt:** Dagsplan-⚠️ sammenligner kun `vehicle_number` og ignorerer `vehicle_uses` (falsk mismatch); to ukendte biler på samme vagt slås sammen til én Lønafregningslinje uden vognnr. (`payroll_settlement_router.py:95`).
25. **Sletning af vogn** tjekker kun `Activity.vehicle_registration` (`vehicles.py:82`) – ikke fast bil, fravær-vogn, dagsplan, materielt fravær.
26. **"Kør løn"-knappen kan være aktiv mens serveren afviser:** frontend-tjekket tæller kun synlige disponentgrupper, server tæller alle.
27. **Bulk-autogodkendelse** skriver `auto_approval_flags` på manuelle/fravær → misvisende "Afvigelser registreret" i detaljevisningen.
28. **Kommentar-badge vises for ofte:** split-dele får altid kommentaren "Split: første/anden del", og auto-godkendelse af korte manuelle aktiviteter sætter kommentaren til brugerens initialer.
29. **Overlap-tjek ved flerdags-fravær** ser kun den indlæste periode (`state.activities`).
30. **§56 "udløbet"-advarsel** har intet tidsfilter/`active`-filter – vises også for fratrådte og gamle udløb.
31. **Timefordeling:** fra/til-tider gemmes ikke (kun timeantal) – felterne er tomme ved genåbning.
32. **Deploy:** `pull_update.ps1` kører som SYSTEM og kalder `py` (som kommentaren i setup-scriptet selv siger ikke virker under SYSTEM); fejler backup, fortsætter `git reset --hard` alligevel. Python-ændringer slår først igennem ved natlig genstart, mens JS/HTML slår igennem efter få minutter → frontend/backend kan være ude af trit i op til et døgn.
33. Masseudsendelse af timesedler (`send-all`) ignorerer disponentgruppe-synlighed (`timeseddel_router.py:500`).

---

## B. Dokumentation der er forkert eller forældet

### B1. Ændringerne fra 30/9 mangler helt
Hverken `build_docs.py` eller de to .docx nævner:
- **Låst periode spærrer alt** (ret, fortryd, split, genåbn, segment-/pauseret, fjern fravær, kommentarer). BV 78 og TEK 151 siger stadig at registrering/rettelse i lukket periode lægges i næste periode – det gælder nu kun DDD-import efter bekræftelse.
- **Vognnummer ved fravær på medarbejderen** (`Employee.absence_vehicle_id`, påkrævet i modal). TEK 136 og 626 (samt DATA_MODEL.md:115/132) beskriver stadig disponentgruppens standardvogn og en funktion `applyDispatcherGroupVehicleDefault()` der ikke findes. Stamdata → Disponentgrupper viser stadig en "standardvogn"-kolonne uden effekt.
- **Flere biler pr. vagt** (`vehicle_uses`, "Biler på vagten", vognnr. kan ikke rettes manuelt, Lønafregning én linje pr. bil pr. dag, nærmeste-bil-reglen).
- **Pause i tooltip og kommentar-badge** i aktivitetstabellen.

### B2. Import (BV 3, TEK 4)
- BV 41-42: knapperne "Vælg filer"/"Vælg mappe" og Windows-fildialog findes ikke – kun "Tjek ddd_input-mappe". TEK 30: tkinter bruges ikke.
- BV 45 / TEK 163: godkendte/deaktiverede aktiviteter udvides **ikke** og genåbnes ikke – der oprettes en ny afventende linje (TEK 170 er korrekt → TEK modsiger sig selv).
- BV 44: dublet afgøres ved tidsoverlap mod originale tider, ikke medarbejder+starttid. BV 50: "ingen fejlmelding" er forkert – ukendte kortnumre vises.
- Kun filer ændret inden for 7 dage scannes – ikke nævnt i BV.
- TEK 158 bitlayout forkert (bit 15 slot, 14 driverStatus, 13 cardPresent, 12-11 aktivitet). TEK 160 mangler cardPresent-reglen for dagsstart. TEK 164 mangler `skipped_declined`, `skipped_conflict`, `pending_closed_period`.

### B3. Aktiviteter (BV 4-6, TEK 8-9)
- BV 67: "(K)" = manuel aktivitet, ikke barn af split (modsiger BV 61).
- BV 105: initialer angives ikke – tages fra login. BV 92: tidspunkt for godkendelse vises ikke.
- Knapnavne: "💾 Gem ændringer", "↩ Fortryd tidsændring", "✂️ Split" (ikke "Gem rettelse"/"Fortryd rettelse"/"Opdel aktivitet"). "Fortryd split" og "Al pause til andet arbejde" er ikke nævnt.
- BV 101 / TEK 397: pauser/segmenter klippes ved splitpunktet (ikke fordeles); original deaktiveres, begge dele "Afventer".
- BV 118: intet turnummer-felt i opret-modalen; KM start/slut og Salttillæg er udokumenterede.
- BV 159 / TEK 428: 0-timers-dage springes kun over for afspadsering; feriefri får altid 7,4 t.
- BV 65: ❗ "under 4 timer" tæller andre godkendte aktiviteter samme dag med.
- BV 4.1: auto-godkendte har egen farve. Pauseforslagsknapper (12:00-12:30/12:45) ikke nævnt.

### B4. Lønkørsel og Lønafregning (BV 9, 12; TEK 5, 7, 13)
- **BV 276:** Normal løn = timesats × **alle** arbejdede timer (tillæg lægges oveni) – ikke "× normaltimer".
- **BV 280-281 / TEK 315:** Pålæsning/aflæsning beregnes **ingen steder** – felterne gemmes kun.
- BV 239: prøvekørsel-modalen har intet medarbejderfelt (enkelt medarbejder vælges fra medarbejderkortet).
- BV 261/268, TEK 349-351: CSV-tal skrives som hundrededele uden decimaler (7,50 t → "750"); kolonne 5/6 skrives altid men tomme; Antal-type påvirker kun FERIEFRI/brugeroprettede typer.
- TEK 313: Ferie kan ikke "slås til" i CSV – den tælles slet ikke.
- **TEK 196:** eksemplet fredag 20:30 → lørdag 08:02 "bruger fredagens loft" er forkert for hourly_fixed – loftet skifter ved midnat (`next_day_normal_hours`); modsiger TEK 199.
- TEK 197-198: split sker også når en lørdags-/hverdagsvagt krydser **ind i** søndag/helligdag (BV 292 er korrekt).
- BV 290: 1. maj/Grundlovsdag før 12 = kun kode 1, uden tidstillæg.
- BV 285 / TEK 385: "samme typer som i Lønafregningen" – forkert, Lønafregning medtager også Ferie/Afspadsering.
- Lønafregning: har egne Fra/Til-, disponentgruppe- og medarbejderfiltre (BV 385/TEK 579 siger nej); rækker pr. (dato, vognnr.); ingen "Total løn for [navn]"-række i CSV; Ferie/Afspadsering nulstilles i CSV; filen har BOM; låsekrav gælder kun når intervallet præcist er en lønperiode; kun medarbejdere med aktiviteter vises.
- TEK 179 signatur forkert. Knapnavne: "Prøvekørsel (Excel)", "PDF-timesedler", "Kør løn (Danløn CSV)".

### B5. Medarbejdere, Stamdata, Helligdage (BV 1-2, 7-8, 10; TEK 2, 6)
- BV 28 Stamdata kræver reelt også `user_management` (se A13). BV 22 Dagsplan-ikon er 📋.
- BV 201/213: admin-rollen har altid alle rettigheder og kan ikke slås fra.
- BV 174/190: Overenskomsttype-feltet skjules helt (ikke kun stjernen). BV 179: der er intet tomt CVR-valg. BV 211: tillægsfeltet vises kun for brugere med `manage_employee_supplements`.
- Timefordeling: UI siger "Lige/Ulige uger" (ikke A/B); standard 7,5/7/0 kun i frontend.
- BV 201: anciennitet tjekker kun om navnet "{type}. 9 mdr anciennitet" findes, ikke en højere sats.
- BV 221 / TEK 130: helligdage og `half_day_from` **bruges allerede** i SH-beregningen – ikke "fremtidig".
- BV 229: halvdagstid kun "12:00". BV 230: slettede auto-helligdage kommer igen.
- BV 316 / TEK 113: Tillæg indeholder også Springertillæg og DOB.
- TEK 252: helligdags-ændringer kræver kun `manage_holidays`. BV 310: kræver `stamdata`, ikke "administrator-login".
- TEK 6.1: `load_supplement_rates_from_db`/`load_pay_types_from_db` findes ikke; `seniority_variant_exists` hedder `seniority_variant_exists_from_db(db, type)`; ikke alle har Excel-fallback.
- TEK 2.5: syv tabeller (mangler `master_cvr_numbers`), manglende kolonner.
- TEK 6.4 (277): "historisk korrekt" holder ikke (se A7).

### B6. Brugere, Vagtplan, Dagsplan, Vognpark, Auto-godkendelse (BV 11, 13-17; TEK 1, 14-18)
- BV 340-343/375: rolletabellen passer ikke – se A8 (alle roller får reelt approve/kalender/vagtplan-redigér-alle/springer).
- BV 365: genopbyg baselines kræver `manage_baselines`, ikke `manage_auto_approval`.
- BV 335: "egen konto kan ikke deaktiveres" gælder kun UI.
- BV 377: hændelsesloggen indeholder langt mere (login, godkend, deaktiver, slet, split, import, lønkørsel, genåbn, vagtplan/dagsplan) – men medarbejder- og vognændringer logges ikke.
- BV 398: Vagtplan viser 21 dage (3 uger), ikke 4 uger. TEK 634/638/641: feltet hedder `text`, parametre `date_from/date_to`, endpoints kræver kun login.
- BV 390 / TEK 623: kommentar har forrang for fravær (gul), ikke nævnt i BV; TEK selvmodsigende.
- BV 382: Dagsplans sideliste viser kun medarbejdere i synlige disponentgrupper.
- BV 423 / TEK 669: "Fast bil"-listen viser alle vogne (BV 425 er korrekt → selvmodsigelse).
- TEK 39: app.js er 6590 linjer (ikke ~5540). TEK 26-38 mangler 11 routere.
- BV 8 / TEK 17: SSO-knappen vises kun når `ENTRA_CLIENT_ID` er sat – i produktion er den tom.
- TEK 534-560 (backup): `installer.ps1` findes ikke; opgaven hedder `LonsystemBackup` og oprettes af `setup_scheduled_task.ps1`; arkivet ligger i `LONSYSTEM_BACKUP_DIR`; "20 backups" passer ikke pga. deploy-backups.
- TEK 500-512 (drift): produktion kører som planlagt opgave `Lonsystem` – stop/start via Scheduled Task, ikke Ctrl+C; auto-deploy og natlig genstart er ikke beskrevet. TEK 564/569 host/firewall-detaljer forældede.
- TEK 522-531: tom database opretter automatisk `admin`/`admin` – bør nævnes (skift adgangskode!).

---

## C. Funktioner i koden der ikke er dokumenteret (udvalg)
- Kodelåsning/`GET /api/activities/locked-dates` og klientside-tjek `_rejectIfLockedDates`.
- Activity-felter: `created_by`, `original_pause_intervals`, `vehicle_registration`, `vehicle_number`, `vehicle_uses`, `km_start/km_end`, `salt_supplement`, `is_likely_incomplete`, baseline-felter. Employee: `initials`, `absence_vehicle_id`, `mobile`.
- Tabeller uden feltbeskrivelse: `dispatcher_groups`, `vagtplan_comments`, `employee_springer_flags`, `paragraf_56_alert_dismissals`, `roles`, `app_users`, `audit_logs`, `declined_imports`, `employee_baselines`, `system_settings`.
- Endpoints: `DELETE /api/users/{id}` (ingen knap), `GET /api/auto-approval/baseline-summary`, `GET /api/auto-approval/settings`, `POST /api/activities/auto-approve-pending`.
- Fraværsoversigten tæller kun godkendt fravær for aktive medarbejdere.
- `restart_server.ps1` sundhedstjek/tilbagerulning, `deploy.ps1` hastedeploy.
- Hardkodet `funktionaer`-aftaletype skjuler førerkortnummer.
