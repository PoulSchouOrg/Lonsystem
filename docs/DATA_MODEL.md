# Datamodel – Lønsystem

## Tabeller

---

### `employees` (Medarbejdere)

| Felt | Type | Beskrivelse |
|------|------|-------------|
| id | INTEGER PK | Intern ID |
| employee_number | TEXT UNIQUE NOT NULL | Medarbejdernummer (Danløn) |
| tachograph_card_number | TEXT UNIQUE NULL | Tachografkortnummer (fra .ddd-fil) |
| first_name | TEXT NOT NULL | Fornavn |
| last_name | TEXT NOT NULL | Efternavn (`name`-property = fornavn + efternavn, ikke en egen kolonne) |
| address, postal_code, email, phone, mobile | TEXT NULL | Kontaktoplysninger |
| initials | VARCHAR(10) NULL | Skal matche `app_users.initials` for "egen linje"-rettighed i Vagtplan |
| agreement_kind | VARCHAR(50) NOT NULL DEFAULT 'hourly_fixed' | Nøgle fra `master_agreement_kinds.key` – se typer nedenfor |
| agreement_type | TEXT NOT NULL | Overenskomsttype (fra Excel-arket "Overenskomsttyper og timesatser.xlsx") |
| fuldloennet | BOOLEAN NOT NULL DEFAULT TRUE | Fuldlønnet (relevant for feriefri-beregning) |
| active | BOOLEAN NOT NULL DEFAULT TRUE | Aktiv medarbejder |
| hire_date | DATE NOT NULL | Ansættelsesdato |
| termination_date | DATE NOT NULL DEFAULT 9999-12-31 | Fratrædelsesdato |
| work_schedule | JSON NOT NULL | Timefordeling over 14 dage: `{"even": [man..søn], "odd": [man..søn]}` i timer |
| cvr_number | VARCHAR(20) NULL | Tilknyttet CVR-nummer (NULL = standard) |
| anciennitet_dismissed_at | DATETIME NULL | Tidspunkt for afvist anciennitetsadvarsel |
| terminsdato | DATE NULL | Seneste terminsdato angivet ved oprettelse af en barsel-aktivitet |
| paragraf_56, paragraf_56_start_date, paragraf_56_end_date | BOOLEAN / DATE NULL | §56-aftale (fleksjob) |
| afloeser | BOOLEAN NOT NULL DEFAULT FALSE | Afløser |
| dispatcher_group_id | INTEGER FK NULL | Reference til disponentgruppe (én, ikke flere – se `dispatcher_groups` nedenfor) |
| fast_bil | BOOLEAN NOT NULL DEFAULT FALSE | "Fast bil" – foreslår medarbejderen som standardchauffør på `fast_bil_vehicle_id` i Dagsplan |
| fast_bil_vehicle_id | INTEGER FK NULL | Den faste vogn (kun relevant når `fast_bil=true`), ikke begrænset til egen disponentgruppe |
| absence_vehicle_id | INTEGER FK NULL | "Vognnummer ved fravær" (2026-09-30) – forudfyldes som vognnummer ved fravær. Påkrævet i medarbejder-modalen (kun frontend); ingen fallback til disponentgruppen |
| ot_extra_alle_timer | BOOLEAN NOT NULL DEFAULT FALSE | Særaftale: alle arbejdstimer giver Øvrig overtid (kode 9) oveni normal løn, uden dagligt loft – se `OVERTIME_RULES.md` |
| position_id | INTEGER FK NULL | Stilling (2026-10-01) – FK til `master_positions`. Påkrævet ved gem (server + klient), NULL tilladt i DB for eksisterende |
| seniority_date | DATE NULL | Anciennitetsdato – bruges KUN til jubilæumsadvarsel (25/40/50 år) |
| cpr_number | VARCHAR(11) NULL | CPR `ddmmåå-xxxx`. Maskeres server-side (`ddmmåå-****`) uden `view_cpr`; intet unikhedstjek |
| elev, elev_start_date, elev_end_date | BOOLEAN NOT NULL DEFAULT FALSE / DATE NULL | Elev (kun chauffører). Datoer påkrævede når `elev=true`. Bruges til elevløn-trin (se `elev_step_decisions`) |
| voksenelev | BOOLEAN NOT NULL DEFAULT FALSE | Voksenlærling (§ 8 stk. 4): almindelig overenskomstløn, ingen elevløn-trin (2026-10-06) |
| personaleforening | BOOLEAN NOT NULL | Medlem af Personaleforening – default TRUE for nye, eksisterende migreret til FALSE |
| natarbejde_tillaeg | BOOLEAN NOT NULL DEFAULT FALSE | Natarbejdetillæg (kun chauffører) – kun filter/tabel, ingen beregning |
| created_at | DATETIME | Oprettelsestidspunkt |
| updated_at | DATETIME | Sidst opdateret |

**Aftaletyper (`agreement_kind`):** de to systemnøgler overtidsberegningen kender:
- `hourly_fixed` – Timelønnet, fast arbejdstid
- `hourly_flexible` – Timelønnet, ikke fastlagt arbejdstid

Nye aftaletyper kan tilføjes via Stamdata (`master_agreement_kinds`-tabellen); timesatser kommer ikke længere fra en hårdkodet type-enum, men fra Excel-arket ("Overenskomsttyper og timesatser.xlsx") pr. `agreement_type`.

Anciennitet beregnes automatisk fra `hire_date`. Pop-up ved 9 måneder hvis `anciennitet_dismissed_at` er tom (se `anciennitet_alert`-tilladelsen).

### elev_step_decisions (2026-10-06)
Lønbogholderens beslutning om et elevløn-trinskift.

| Kolonne | Type | Beskrivelse |
|---|---|---|
| employee_id | INTEGER FK | Eleven |
| event_date | DATE | Dagen eleven går ind i det nye år af lærekontrakten |
| decision | VARCHAR(10) | `approve` (skift typen) eller `keep` (bevar typen bevidst, note påkrævet) |
| from_type, to_type | VARCHAR(200) | Overenskomsttype før / efter |
| effective_from | DATE NULL | Startdato for lønperioden skiftet gælder fra (hele perioden) |
| note, decided_by, decided_at | | Bemærkning, initialer, tidspunkt |
| applied_at | DATETIME NULL | Sat når medarbejderens `agreement_type` er skiftet |

`system_settings` har desuden `elev_alerts_enabled` (advarsler starter først efter opstartstjekket i Elevoversigten), `elev_notice_days` (varsel, default 30) og `elev_remind_days` (påmind igen dage før, default 7, NULL = aldrig).
Elevløn-popups afvises/udsættes pr. bruger i `paragraf_56_alert_dismissals` med `alert_type` `elevup_ÅÅÅÅ-MM-DD` (påmind igen), `elevno_ÅÅÅÅ-MM-DD` (påmind ikke igen) og `elevfx_<id>` (trådt i kraft, set).

Mærkedagsadvarsler (jubilæum, elev slutter, rund fødselsdag – 2026-10-01) afvises pr. bruger i `paragraf_56_alert_dismissals` med `alert_type` = begivenheden (`jubilee_25`, `birthday_40`, `elev_ÅÅÅÅ-MM-DD`).

---

### `master_positions` (Stillinger, 2026-10-01)

| Felt | Type | Beskrivelse |
|------|------|-------------|
| id | INTEGER PK | Intern ID |
| name | VARCHAR(100) UNIQUE NOT NULL | Stillingens navn. Vedligeholdes i Stamdata → Stillinger; kan ikke slettes, mens en medarbejder bruger den |

---

### `pay_periods` (Lønperioder)

| Felt | Type | Beskrivelse |
|------|------|-------------|
| id | INTEGER PK | Intern ID |
| start_date | DATE NOT NULL | Startdato for perioden |
| end_date | DATE NOT NULL | Slutdato (altid start_date + 13 dage = 14 dage) |
| status | TEXT | `open`, `preview`, `closed` |
| closed_at | DATETIME | Tidspunkt for lønkørsel |
| closed_by | TEXT | Initialer på den der lukkede |

**Regler:**
- En periode er altid præcis 14 dage, mandag-søndag
- Perioder beregnes fra et fast anker (mandag 1/6-2026) med 14-dages modulo – ikke "næste hverdag efter forrige periode"
- Systemet opretter ny periode automatisk ved behov

---

### `activities` (Aktiviteter/Bjælker)

| Felt | Type | Beskrivelse |
|------|------|-------------|
| id | INTEGER PK | Intern ID |
| employee_id | INTEGER FK | Reference til medarbejder |
| pay_period_id | INTEGER FK | Reference til lønperiode |
| trip_number | TEXT | TurNR (6 cifre, kan være NULL) |
| source | TEXT | `tachograph` eller `manual` |
| start_time | DATETIME NOT NULL | Starttidspunkt |
| end_time | DATETIME NOT NULL | Sluttidspunkt |
| availability_time_pct | DECIMAL | Rådighedstid (%) |
| rest_pause_pct | DECIMAL | Hvil/pause (%) |
| other_work_pct | DECIMAL | Andet arbejde (%) |
| driving_pct | DECIMAL | Kørsel (%) |
| loading_minutes | INTEGER | Pålæsningstid i minutter (kun manuel) |
| unloading_minutes | INTEGER | Aflæsningstid i minutter (kun manuel) |
| status | TEXT | `pending`, `approved`, `deactivated` |
| approved_by | TEXT | Initialer på godkender |
| approved_at | DATETIME | Godkendelsestidspunkt |
| deactivated_by | TEXT NULL | Initialer på den der deaktiverede |
| updated_by | TEXT NULL | Initialer på den bruger der senest gemte en rettelse via PATCH – NULL indtil første redigering, overskrives ved hver efterfølgende (ingen historik) |
| vehicle_registration, vehicle_number | TEXT NULL | Nummerplade / internt vognnummer på aktiviteten (hovedbilen = flest timer) |
| vehicle_uses | JSON NULL | `[[start_iso, slut_iso, reg], ...]` – alle biler vagten er kørt i (2026-09-30). Kun .ddd-vagter; bruges af Lønafregning (én linje pr. bil pr. dag) |
| comment | TEXT | Fri kommentar |
| parent_activity_id | INTEGER FK NULL | Hvis splittet: reference til original |
| split_part | INTEGER NULL | 1 = første del (deaktiveret), 2 = anden del (aktiv) |
| created_at | DATETIME | Oprettelsestidspunkt |

**Effektiv tid** = `end_time - start_time` (total tid fra start til slut)

**Farvestatus:**
- `deactivated` → 🔴 Rød
- `approved` → 🟢 Grøn
- `pending` → 🔵 Blå

**Manuelle aktiviteter** vises med `(K)` prefix.

**Split-logik:**
- Original aktivitet sættes til `deactivated` (regnes ikke med) og erstattes af to nye rækker med `parent_activity_id` = original
- Del 1 (`split_part = 1`) og del 2 (`split_part = 2`): begge sættes til `pending` og skal godkendes hver for sig

---

### `dispatcher_groups` (Disponentgrupper)

| Felt | Type | Beskrivelse |
|------|------|-------------|
| id | INTEGER PK | Intern ID |
| name | TEXT NOT NULL | Gruppenavn |
| description | TEXT | Beskrivelse |
| vehicle_id | INTEGER FK NULL | Gruppens "standardvogn" – bruges IKKE længere (fravær-default kommer fra `employees.absence_vehicle_id` siden 2026-09-30); kan stadig redigeres i Stamdata |

En medarbejder tilhører højst ÉN gruppe (`employees.dispatcher_group_id`, se ovenfor) – ikke en
mange-til-mange-relation. Feltet har historisk skiftet form to gange: oprindeligt en enkelt
tekststreng, dernæst (fra 27/7-2026) en mange-til-mange-relation via en nu fjernet
`employee_dispatcher_groups`-jointabel, og siden igen erstattet af den nuværende enkelte FK.

---

### `vehicles` (Køretøjer)

| Felt | Type | Beskrivelse |
|------|------|-------------|
| id | INTEGER PK | Intern ID |
| registration_number | TEXT | Nummerplade |
| vehicle_number | TEXT | Internt vognnummer |
| description | TEXT NULL | Vises som kolonne 2 i Dagsplan |
| dispatcher_group_id | INTEGER FK NULL | Mange vogne → én disponentgruppe (adskilt fra `dispatcher_groups.vehicle_id` ovenfor, som er gruppens egen "standardvogn") |

---

### `daily_plan_assignments` (Dagsplan – vogntildeling)

| Felt | Type | Beskrivelse |
|------|------|-------------|
| id | INTEGER PK | Intern ID |
| date | DATE NOT NULL | |
| vehicle_id | INTEGER FK NOT NULL | |
| employee_id | INTEGER FK NULL | Tom = vogn uden chauffør den dag |
| task | TEXT NULL | Opgave |
| informed | BOOLEAN NOT NULL DEFAULT FALSE | Chauffør informeret |
| created_at, updated_at | DATETIME | |

`UniqueConstraint(date, vehicle_id)` – én tildeling pr. vogn pr. dag (upsert via `PATCH /api/dagsplan/assignment`).

### `daily_plan_extra_assignments` (Dagsplan – EKSTRA-rækker)

Samme felter som `daily_plan_assignments`, men uden `vehicle_id` – i stedet et fast `slot`
(1-10) for de 10 EKSTRA-pladser (hjælp på pladsen/lærlinge). Indgår aldrig i vognnummer-
autoudfyldning eller lønberegning.

### `vehicle_absences` (Materielt fravær)

| Felt | Type | Beskrivelse |
|------|------|-------------|
| id | INTEGER PK | Intern ID |
| vehicle_id | INTEGER FK NOT NULL | |
| date_from | DATE NOT NULL | |
| date_to | DATE NULL | NULL = étdags-fravær (samme dag som `date_from`) |
| comment | TEXT NOT NULL | Årsag/beskrivelse |
| created_by | TEXT NULL | Initialer |
| created_at | DATETIME | |

En vogn regnes som materielt fraværende på dato `d`, hvis `date_from <= d <= (date_to ?? date_from)`.
Permissions: `dagsplan_view` (læse) / `dagsplan_edit` (redigere) for alle fire Dagsplan-tabeller.

---

### `payroll_runs` (Lønkørsler)

| Felt | Type | Beskrivelse |
|------|------|-------------|
| id | INTEGER PK | Intern ID |
| pay_period_id | INTEGER FK | Lønperiode |
| run_type | TEXT | `preview` eller `final` |
| run_at | DATETIME | Tidspunkt |
| run_by | TEXT | Initialer |
| csv_path | TEXT | Sti til genereret CSV (final) |
| excel_path | TEXT | Sti til genereret Excel (preview) |

---

### `holidays` (Helligdage)

| Felt | Type | Beskrivelse |
|------|------|-------------|
| id | INTEGER PK | Intern ID |
| date | DATE UNIQUE NOT NULL | Helligdagens dato |
| name | TEXT NOT NULL | Navn, fx "Påskedag", "1. maj" |
| half_day_from | TEXT NULL | "12:00" = fri fra middag; NULL = heldagshelligdag |
| is_auto_generated | BOOLEAN DEFAULT TRUE | TRUE = genereret af systemet, FALSE = manuel |

**Regler:**
- Tabellen seedes automatisk ved serveropstart via `_seed_holidays()` i `session.py`
- 5 løbende år genereres (indeværende år + 4)
- Seeding er idempotent — eksisterende datoer springes over
- Dato er UNIQUE: hvis en bevægelig helligdag falder samme dag som en fast (fx 2. pinsedag på Grundlovsdag i 2028), vinder den faste helligdag
- Beregning af påskedag sker via anonym Gregoriansk Computus-algoritme i `app/calculators/holidays.py`
- Store Bededag medtages ikke (afskaffet fra 2024)

**Auto-genererede helligdage:**

| Type | Helligdag | Halvdag fra |
|------|-----------|-------------|
| Fast | Nytårsdag (1/1) | — |
| Fast | 1. maj (1/5) | 12:00 |
| Fast | Grundlovsdag (5/6) | 12:00 |
| Fast | Juleaftensdag (24/12) | — |
| Fast | 1. juledag (25/12) | — |
| Fast | 2. juledag (26/12) | — |
| Fast | Nytårsaftensdag (31/12) | — |
| Bevægelig | Skærtorsdag (Påske − 3) | — |
| Bevægelig | Langfredag (Påske − 2) | — |
| Bevægelig | Påskedag | — |
| Bevægelig | 2. påskedag (Påske + 1) | — |
| Bevægelig | Kristi Himmelfartsdag (Påske + 39) | — |
| Bevægelig | Pinsedag (Påske + 49) | — |
| Bevægelig | 2. pinsedag (Påske + 50) | — |

**Permission:** `manage_holidays` — kun brugere med denne rettighed kan oprette og slette helligdage.

---

### `employee_supplements` (Medarbejdertillæg)

| Felt | Type | Beskrivelse |
|------|------|-------------|
| id | INTEGER PK | Intern ID |
| employee_id | INTEGER FK | Medarbejder |
| name | TEXT | Altid "Ikke overenskomstmæssigt tillæg" – hardkodet, ikke redigerbar |
| type | TEXT | Altid "Timebaseret" – hardkodet |
| value | NUMERIC(10,2) | kr/time, skal være > 0 |
| start_date | DATE NOT NULL | Gyldighedsperiodens start (default dags dato ved oprettelse) |
| end_date | DATE NOT NULL | Gyldighedsperiodens slut (default 9999-12-31 = åbentstående) |

**Regler:**
- Status (Aktiv/Inaktiv) er IKKE et lagret felt — beregnes ved visning ud fra om dags dato ligger i `[start_date, end_date]`
- Oprettelse af et nyt tillæg lukker automatisk medarbejderens forrige åbentstående række (`end_date = ny_start_dato − 1 dag`)
- "Afslut"-handlingen sætter `end_date` til slutdatoen for den lønperiode dags dato falder i (ikke dags dato selv) — tillægget gælder derfor stadig resten af igangværende periode
- Partielt unikt indeks `uq_employee_supplements_one_open_row` (`employee_id` WHERE `end_date='9999-12-31'`) sikrer kun én åbentstående række pr. medarbejder ad gangen
- Ved lønberegning: overlapper flere rækker den beregnede periode (nyt tillæg oprettet midt i perioden), vinder rækken med nyeste `start_date` for hele perioden
- Ingen redigering eller sletning af eksisterende rækker — kun oprettelse af nye og afslutning af den aktive
- Permission: `manage_employee_supplements`

Se `PAYROLL_RULES.md` og `CODEREF.md` for hvordan tillægget slår igennem i selve lønberegningen.

### `applied_permission_grants` (Engangstildeling af rettigheder, 2026-09-30)
| Felt | Type | Beskrivelse |
|------|------|-------------|
| key | TEXT PK | Navnet på en automatisk rettighedstildeling (fx `edit_activities`) |
| applied_at | DATETIME | Hvornår tildelingen blev kørt |

Bruges af `_grant_permissions_once()` i `session.py`, så en rettighed kun tildeles eksisterende roller én gang – ikke igen ved hver serverstart.

---

## Beregningsregler (ikke gemt i DB)

Se `PAYROLL_RULES.md` for detaljerede beregningsregler.

- **Effektiv tid**: `end_time - start_time`
- **Minimum 4 timer**: Vagter under 4 timer markeres `pending` og kræver manuel godkendelse med begrundelse
- **Overtid**: Se `OVERTIME_RULES.md`
- **Ubekvem tid**: Se `PAYROLL_RULES.md`
