# Design: Gentagelse i Vagtplan

**Dato:** 2026-10-07
**Status:** Godkendt i brainstorming – afventer brugerens gennemlæsning af spec

## Baggrund

I Vagtplan kan man i dag oprette fravær (én dag eller en periode) og fritekst-kommentarer
på én dag ad gangen. Gentagne registreringer (fx "fri hver tirsdag", "kursus 2. tirsdag i
måneden", "ringer ind kl. 10 hver mandag") skal i dag oprettes dag for dag.

Ønsket: et felt **"Gentagelse"** i opret-modalen i Vagtplan. Afkrydses det, vælger man et
mønster (ugentligt på valgte ugedage eller månedligt) og en afslutning (antal gange eller
slutdato). Slutdato/antal skal kunne ændres senere ved at åbne en af forekomsterne – på
samme måde som en fraværsperiodes start-/slutdato kan rettes i dag
(`PATCH /api/activities/absence-group/{id}`).

## Beslutninger (afklaret med bruger 2026-10-07)

1. **Forekomst = altid én dag.** En gentagelse kan ikke bestå af perioder (fx man–ons hver
   uge). "Til dato" skjules når Gentagelse er afkrydset.
2. **Mønster:** to valg – *Ugentligt* (afkrydsning af én eller flere ugedage man–søn;
   startdatoens ugedag er forvalgt; "Hver [N]. uge", N = 1–4, talt fra startdatoens uge –
   tilføjet 2026-10-07 efter brugerønske) eller *Månedligt*.
3. **Månedligt = samme ugedag i måneden**, udledt af startdatoen ("N. <ugedag> i
   måneden", fx 2. tirsdag). Er startdatoen den 5. forekomst af ugedagen, betyder mønstret
   "sidste <ugedag> i måneden".
4. **Helligdage springes over for fravær** (tabellen `holidays`); kommentarer oprettes
   også på helligdage.
5. **Antal = antal faktisk oprettede dage.** Springes en helligdag over, tages næste dag i
   mønstret, så antallet nås.
6. **Grænser:** maks. 1 år fra startdatoen og maks. 100 forekomster.
7. **Redigering af en forekomst:** slutdato/antal kan rettes for hele serien; man kan slette
   kun denne forekomst eller hele serien. Øvrigt indhold (type, tider, tekst) rettes dag for
   dag som i dag.
8. **"Slet hele serien"** sletter alle forekomster undtagen dem i låste lønperioder; de
   bevares, og brugeren får besked om antallet.
9. **Kun i Vagtplan.** Gentagelse-feltet vises kun i opret-modalen i vagtplan-kontekst
   (`_manualActivityContext.vagtplan`). Serie-sektionen i aktivitetsdetaljen vises dog
   også når fraværet åbnes fra Aktivitetsoversigten (samme modal).

## Funktionel beskrivelse

### Oprettelse

Opret-modalen (`modal-manual-activity`) i vagtplan-kontekst får en afkrydsning
**"Gentagelse"**. Når den er afkrydset:

- "Til dato" og start-/sluttidsfelterne skjules (fraværstider beregnes som ved perioder,
  se nedenfor).
- **Gentag:** radioknapper *Ugentligt* / *Månedligt*.
  - *Ugentligt:* 7 afkrydsningsfelter man–søn; startdatoens ugedag er forvalgt. Mindst én
    skal være valgt.
  - *Månedligt:* skrivebeskyttet tekst, fx "Hver 2. tirsdag i måneden" / "Sidste fredag i
    måneden", der opdateres når startdatoen ændres.
- **Slutter:** radioknapper *Efter [antal] gange* / *Den [dato]*. Antal 1–100; dato på/efter
  startdatoen og højst 1 år efter.

Gælder både rigtige fraværstyper og "Ingen (kun kommentar)". Udfyldes både fraværstype og
Vagtplan-kommentar, får hver forekomst begge dele (én aktivitet + én kommentar pr. dag, i
samme serie).

**Datoberegning:**
- Serien starter på startdatoen; startdatoen er kun en forekomst hvis den passer i mønstret.
- Dage kandideres i kronologisk rækkefølge efter mønstret. For fravær springes helligdage
  over. Beregningen stopper ved antal nået, slutdato passeret, 100 forekomster eller 1 år
  efter startdatoen – hvad der kommer først.

**Fraværstider pr. dag** følger samme regler som oprettelse af en fraværsperiode i dag
(`_range_day_defaults` i backend): kl. 06:00 + medarbejderens arbejdstid for ugedagen (lige/
ulige uge), fallback 7,4 t; afspadsering/skole_kursus springes over på dage uden
garanterede timer; tælle-baserede typer (`_COUNT_BASED_RANGE_TYPES`) oprettes som i dag.

**Konflikter – vises i en bekræftelse før oprettelse (preview):**
- Dage i en **låst lønperiode** → oprettelsen afvises helt, ingen dage oprettes; beskeden
  nævner datoerne.
- Dage hvor medarbejderen **allerede har en Vagtplan-kommentar** → kommentaren for den dag
  springes over (overskrives ikke); brugeren får besked. Fraværet oprettes stadig.
- Dage med **registreret kørsel** (ikke-deaktiveret `normal`) → samme advarsel som i dag
  ("Vil du alligevel registrere fraværet?").
- Dage **uden garanterede timer** (afspadsering/skole_kursus) → springes over; vises som i dag.

### Redigering og sletning

Når en forekomst åbnes – aktivitetsdetaljen (`openActivityDetail`) for fravær eller
kommentarboksen (`modal-vagtplan-comment`) for en kommentar – og den har et `series_id`,
vises en serie-sektion:

- Beskrivelse af mønstret, fx "Gentagelse: hver tirsdag og torsdag" / "hver 2. tirsdag i
  måneden".
- **Slutter:** *Efter [antal] gange* / *Den [dato]*, forudfyldt med de nuværende værdier
  (antal = nuværende antal forekomster), med knappen **"Gem for serien"**.
- Knapperne **"Slet denne forekomst"** og **"Slet hele serien"** (med bekræftelse).

**Ret slutdato/antal – serien ændres kun i enden:**
- Forlængelse: nye dage beregnes fra dagen efter den nuværende sidste forekomst, efter
  samme regler som ved oprettelse. Dage midt i serien røres aldrig – en forekomst der er
  slettet enkeltvis, genopstår derfor ikke.
- Antal sammenlignes med det nuværende antal forekomster (fx 7 tilbage efter én slettet,
  nyt antal 10 → 3 tilføjes efter den sidste).
- Forkortelse: forekomster efter den nye slutdato / ud over det nye antal slettes
  permanent, uanset status (samme regel som ved forkortelse af fraværsperiode).
- Rammer en dag der skal fjernes eller tilføjes en låst lønperiode, afvises hele
  ændringen (alt-eller-intet), og beskeden nævner datoen. En splittet aktivitet der skal
  fjernes afviser også ændringen ("fortryd splittet først"), som ved fraværsperioder.
- Grænsen (1 år fra seriens startdato, 100 forekomster) gælder også ved forlængelse.

**Slet denne forekomst:** som i dag – "Slet aktiviteten helt" i deaktiver-modalen for
fravær, "Slet" i kommentarboksen for en kommentar. Rækken forsvinder fra serien.

**Slet hele serien:** sletter permanent alle aktiviteter og kommentarer med serie-id'et,
uanset status, undtagen dem på datoer i låste lønperioder. Toast fx "12 forekomster
slettet – 3 i låste lønperioder er bevaret". Serierækken slettes når ingen forekomster er
tilbage; ellers bevares den.

**Øvrigt:**
- En deaktiveret forekomst forbliver i serien (vises gråtonet som i dag).
- En enkelt forekomst kan rettes (type, tider, tekst) uden at påvirke resten; den bevarer
  sit `series_id`.
- Serieaktiviteter får IKKE `absence_group_id` (hver forekomst er én dag).

### Rettigheder

Alle serie-endpoints kræver redigeringsret til medarbejderens linje i Vagtplan
(`_has_vagtplan_edit_access`: `vagtplan_edit_all`, eller `vagtplan_edit_own` med matchende
initialer). Serieaktiviteter har `source=vagtplan`, så den eksisterende undtagelse i
`_require_activity_permission` gælder for enkeltforekomster. Frontend skjuler
Gentagelse-feltet/serie-knapperne når `_hasVagtplanEditAccess(emp)` er falsk.

### Hændelseslog

`log_action` for: oprettelse af serie (`create_vagtplan_series`), ændring af slutning
(`update_vagtplan_series`), sletning af serie (`delete_vagtplan_series`) – med medarbejder,
mønster og antal tilføjede/fjernede/bevarede forekomster.

## Arkitektur

### Datamodel (`models.py` + migration i `session.py`)

Ny tabel `vagtplan_series` (model `VagtplanSeries`):

| Felt | Type | Bemærk |
|---|---|---|
| id | Int PK | |
| employee_id | Int FK → employees | |
| activity_type | String, nullable | Fraværstype; null = kun kommentar |
| comment_text | String(1000), nullable | Vagtplan-kommentar pr. forekomst; null = ingen |
| vehicle_number | String, nullable | Vognnummer til fraværsaktiviteterne |
| terminsdato | Date, nullable | Kun relevant for barsel |
| freq | String | `weekly` / `monthly` |
| weekdays | String, nullable | Kommasepareret 0–6 (0 = mandag), kun `weekly` |
| start_date | Date | |
| end_mode | String | `count` / `date` |
| end_count | Int, nullable | |
| end_date | Date, nullable | |
| created_by | String(10) | Initialer |
| created_at | DateTime | server_default now |

Mindst én af `activity_type`/`comment_text` skal være udfyldt. Månedligt mønster udledes
af `start_date` (ugedag + N. forekomst i måneden) og gemmes ikke separat.

Nyt felt `series_id` (Int, nullable, FK → vagtplan_series, indekseret) på `activities` og
`vagtplan_comments`. Migration: idempotent `ALTER TABLE ADD COLUMN` + `CREATE INDEX IF NOT
EXISTS`, samme mønster som øvrige kolonner. `ActivityResponse` og
`VagtplanCommentResponse` udvides med `series_id`.

### Beregning (`calculators/recurrence.py`, ny, ingen DB-afhængighed)

`occurrence_dates(freq, weekdays, start_date, end_mode, end_count, end_date, holidays,
skip_holidays, after=None, existing_count=0) -> list[date]`

- `after`: start kandidat-søgningen dagen efter denne dato (bruges ved forlængelse).
- `existing_count`: antal forekomster der allerede findes (tæller med i antal og i
  100-grænsen).
- Håndhæver 1 år fra `start_date` og 100 forekomster i alt.
- Hjælper `monthly_label(start_date) -> str` ("Hver 2. tirsdag i måneden" / "Sidste
  fredag i måneden") til frontend-visning via API.

### API (ny router `routers/vagtplan_series.py`, prefix `/api/vagtplan-series`)

| Endpoint | Metode | Beskrivelse |
|---|---|---|
| `/preview` | POST | Body = samme som oprettelse. Returnerer `dates`, `locked_dates`, `comment_conflicts`, `driving_conflicts`, `skipped_no_hours`. Gemmer intet. |
| `` | POST | Opretter serien + alle forekomster i én transaktion. 400 ved låste datoer, ingen ugedage, ingen forekomster eller overskredne grænser. Returnerer serien + antal oprettede/oversprungne. |
| `/{id}` | GET | Reglen, mønsterbeskrivelse, nuværende antal forekomster og sidste dato. |
| `/{id}` | PATCH | Body `{end_mode, end_count?, end_date?}`. Forlænger/forkorter i enden (se ovenfor). |
| `/{id}` | DELETE | Sletter alle forekomster uden for låste perioder; returnerer `{deleted, kept_locked}`. |

Oprettelse af hver fraværsforekomst skal gå gennem samme regler som
`create_manual_activity` (bl.a. omklassificering ved lav anciennitet, status/auto-
godkendelse, `get_billing_period`, `_forbid_date_in_closed_period`). Den fælles
oprettelseslogik trækkes ud i en hjælpefunktion i `activities.py`, som både
`create_manual_activity` og serie-routeren kalder – i stedet for at duplikere den.
Tiderne beregnes med `_range_day_defaults`.

Routeren registreres i `main.py`.

### Frontend (`index.html` + `app.js`)

- Opret-modalen: `manual-repeat-group` (afkrydsning + mønster- og slut-felter), kun synlig
  i vagtplan-kontekst. `updateManualTypeVisibility()` skjuler "Til dato"/tider når
  Gentagelse er afkrydset.
- `confirmManualActivity()`: når Gentagelse er afkrydset → `POST /preview` → bekræftelse
  med evt. advarsler → `POST /api/vagtplan-series` → `loadVagtplan()`.
- `openActivityDetail()` og `openVagtplanCommentModal()`: serie-sektion når `series_id` er
  sat (henter `GET /api/vagtplan-series/{id}`), med "Gem for serien", "Slet denne
  forekomst" og "Slet hele serien".
- Efter ændringer: `loadVagtplan()` i Vagtplan, `refreshActivities()` i
  Aktivitetsoversigten.

## Tests (pytest)

- `tests/test_recurrence.py`: ugentligt én/flere dage; startdato uden for mønstret;
  månedligt N. ugedag inkl. 5. → sidste; helligdag springes over og erstattes ved antal;
  kommentarer på helligdage; slutdato; grænser (1 år, 100); `after`/`existing_count`.
- `tests/test_vagtplan_series.py`: preview-indhold; oprettelse af fravær, kun kommentar og
  begge; eksisterende kommentar springes over; låst dato afviser alt; forlæng (slettet
  forekomst genopstår ikke); forkort sletter godkendte; låst dag i ændring afviser alt;
  slet hele serien bevarer låste; rettigheder (egen linje / alle linjer / ingen).

## Ikke i scope

- Forekomster der er perioder over flere dage.
- Ændring af mønster, fraværstype eller kommentartekst for hele serien på én gang.
- Gentagelse i Aktivitetsoversigtens opret-modal.
- Gentagelse af "Normal tid" (kan ikke oprettes fra Vagtplan).
