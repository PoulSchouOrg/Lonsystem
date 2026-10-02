# PS Løn – Kode-referenceguide (token-optimeret)

## Stack
FastAPI + SQLite (WAL) + vanilla HTML/JS.  
**Daglig drift:** `cd app && uvicorn main:app --host 0.0.0.0 --port 8000`  
**Under udvikling:** `cd app && uvicorn main:app --host 0.0.0.0 --port 8000 --reload` (auto-genstart ved .py-ændringer)  
Ændringer i `.py`-filer kræver servergenstart. `app.js` har automatisk cache-busting (`?v={{ app_js_mtime }}`, filens mtime) – ændringer træder altid i kraft ved reload. `style.css` og `index.html` har IKKE automatisk cache-busting: `style.css?v=N` i `index.html` er et manuelt versionsnummer der SKAL bumpes for hånd, hver gang `style.css` ændres, ellers kan browsere med gammel cache blive hængende på den gamle CSS (skete 2026-07-02: ny `.btn-muted`-regel virkede ikke i browseren, selvom JS-logikken var korrekt, fordi `?v=6` ikke var bumpet).  
CVR: læses altid fra Stamdata → CVR-nummer (MasterCvrNumber). Lønperiode: faste 14-dage (start beregnet fra dato).  
Auth: SessionMiddleware (session-cookie, 1 dag). Seed-admin: initialer=`admin`, adgangskode=`admin` (skift ved første login).

---

## Filer
```
app/
  main.py                      # FastAPI app, SessionMiddleware, router-inkludering, cache-busting
  auth.py                      # hash_password, verify_password, get_current_user, require_roles, log_action
  database/
    models.py                  # SQLAlchemy-modeller inkl. AppUser, AuditLog, UserRole
    schemas.py                 # Pydantic-skemaer (ActivityApprove/Deactivate har IKKE approved_by – fra session)
    session.py                 # get_db(), init_db() (seeder ADM-admin hvis ingen brugere)
  routers/
    auth.py                    # POST /api/auth/login, /logout; GET /api/auth/me
    users.py                   # /api/users CRUD + /api/users/audit-log (admin-only)
    roles.py                   # /api/roles CRUD (admin-only); dynamisk rollestyring
    activities.py              # /api/activities (CRUD + godkend/deaktiver/split/absence-types) – alle roller
    employees.py               # /api/employees (CRUD + anciennitet-alerts + dismiss + agreement-types) – alle roller
    payroll_router.py          # /api/payroll (preview, prøvekørsel, CSV, PDF) – admin+lonbogholder
    absence_overview_router.py # /api/absence-overview (data, export-per-employee, export-per-type) – absence_overview perm
    timeseddel_router.py       # /api/timesedler – timeseddel-eksport pr. medarbejder
    stamdata.py                # /api/stamdata – CVR-numre, løntypekoder, overtidssatser, helligdage (admin)
    vehicles.py                # /api/vehicles – alle roller
    import_ddd.py              # /api/import-ddd (scanner ddd_input/) – admin+lonbogholder
    auto_approval_router.py    # POST /api/auto-approval/rebuild-baselines, GET /baseline-summary (manage_baselines perm)
    employee_supplements.py    # /api/employee-supplements – kr/time-tillæg pr. medarbejder (manage_employee_supplements perm)
    dagsplan_router.py         # /api/dagsplan + /api/vehicle-absences – daglig vogn/chauffør-fordeling (dagsplan_view/dagsplan_edit perm)
  calculators/
    overtime.py                # calculate_overtime() → OvertimeResult
    pay_period.py              # get_or_create_period_for_date(), is_even_week()
    rates_loader.py            # load_agreement_types/overtime_rates/salt_supplement_rate(); get_active_supplement_for_period()
    pay_rates.py               # DANLOEN_CODE_* konstanter (NORMAL/OT_*/SALT/AFSPADSERING/SYGDOM/PARAGRAF_56/BARN_1SYGEDAG – "1" placeholder, DB-værdier er authoritative)
    day_type.py                # Dag-klassifikation og lønberegning for lørdage, søndage og helligdage (SH-betaling)
    holidays.py                # easter_date() + danish_holidays(year) – genererer helligdage via Computus
    auto_approval.py           # should_auto_approve(activity, db) → (bool, list[str]); MIN_SAMPLES=5
    baseline_updater.py        # update_baseline_from_activity() – Welford update + downdate-dedup; rebuild_baselines_for_employee()
  parsers/ddd_parser.py        # .ddd-filparsing
  templates/index.html         # Eneste HTML-side (alle modaler herinde)
  static/
    js/app.js                  # Al frontend-logik (~3100 linjer)
    css/style.css              # Styling

# Excel-filer i app/ (læses uden genstart):
app/Fraværstyper.xlsx          # Kolonne A, række 2+ → fraværstyper
app/Overenskomsttyper og timesatser.xlsx  # Kol A=navn, B=timesats
app/Overtid satser.xlsx        # Kol A=navn, B=sats (3 rækker)
app/Salttillæg.xlsx            # Celle B1 = salttillæg pr. time
```

---

## DB-modeller (models.py)

### Employee (tabel: employees)
| Felt | Type | Bemærk |
|---|---|---|
| employee_number | String | Lønnummer, unik |
| tachograph_card_number | String nullable | Førerkortnummer |
| agreement_kind | String(50) | Nøgle fra `master_agreement_kinds.key` (se nedenfor) – IKKE længere en hård `Enum`-kolonne (fra v24) |
| agreement_type | String | Overenskomsttype fra Stamdata; tom streng `""` hvis den valgte `agreement_kind` har `requires_agreement_type=False` |
| work_schedule | JSON | `{"even":[0..6],"odd":[0..6]}` timer man-søn |
| dispatcher_group_id / dispatcher_group | Int FK nullable / relation | Én disponentgruppe (nullable) – se DispatcherGroup nedenfor og linje ~574 for migreringshistorik |
| hire_date / termination_date | Date | Ansættelses-/slutdato |
| paragraf_56 | Boolean | Krydses af i medarbejder-modalen; kræver paragraf_56_start_date/paragraf_56_end_date udfyldt (400 ellers). Ingen kobling til lønberegning eller den eksisterende "§56 syg"-fraværstype endnu |
| paragraf_56_start_date / paragraf_56_end_date | Date nullable | Se paragraf_56 – nulstilles til NULL server-side når paragraf_56 sættes til false |
| fast_bil / fast_bil_vehicle_id | Boolean / Int FK nullable | "Fast bil" – foreslår medarbejderen som default chauffør på den valgte vogn i Dagsplan (se "Dagsplan" nedenfor). Vognvalget er IKKE begrænset til egen disponentgruppe |
| absence_vehicle_id / absence_vehicle | Int FK nullable / relation | "Vognnummer ved fravær" (2026-09-30) – eneste kilde til default-vognnummer ved fraværsregistrering (`applyAbsenceVehicleDefault()` i app.js). Påkrævet i medarbejder-modalen ved opret OG redigér (kun frontend-validering; backend validerer blot at vogn-id findes). Eksisterende medarbejdere blev IKKE migreret – feltet er tomt til de redigeres. Ingen fallback til disponentgruppens vogn |
| ot_extra_alle_timer | Boolean, default false | Særaftale pr. medarbejder: alle arbejdstimer giver Øvrig overtid (kode 9) oveni normal løn, uden dagligt loft. Se `override_ot_extra_alle_timer()` i overtime.py nedenfor |

### MasterAgreementKind (tabel: master_agreement_kinds) — "Aftale"
| Felt | Type | Bemærk |
|---|---|---|
| key | String unik | Fast fra oprettelsen, kan ALDRIG ændres (heller ikke ved redigering) – `overtime.py`/`payroll_router.py` grener direkte på `"hourly_fixed"`/`"hourly_flexible"` |
| label | String | Redigerbar, også for systemtyperne |
| is_active | Boolean | Styrer om typen vises i medarbejder-modalens dropdown (`GET /api/employees/agreement-kinds`, kun aktive) |
| is_user_created | Boolean | `False` for de 2 seedede systemtyper (kan ikke slettes); `True` for nye |
| requires_agreement_type | Boolean | Om `agreement_type` er påkrævet for medarbejdere med denne `agreement_kind` (håndhævet i `routers/employees.py`) |
Seedes ved opstart (`session.py: _seed_agreement_kinds`) med `hourly_fixed`/`hourly_flexible`, IKKE fra Excel. CRUD under Stamdata → "Aftale" (kræver `stamdata`-tilladelse). Overtidsberegning: medarbejdere med en `agreement_kind` uden for de to systemnøgler springes automatisk over i `_calculate_employee()` og får `calculate_flat_hours()` i stedet (ingen tillæg/loft, kun flad normaltid) — se `docs/superpowers/specs/2026-08-24-aftale-stamdata-design.md`.

### DispatcherGroup (tabel: dispatcher_groups)
| Felt | Type | Bemærk |
|---|---|---|
| name | String unik | Fx "2 - Kran" |
| description | Text nullable | |
CRUD under Stamdata → "Disponentgrupper" (kræver `stamdata`-tilladelse). Lightweight read-only liste til dropdowns: `GET /api/employees/dispatcher-groups` (kun `get_current_user`). Medarbejder-modal bruger nu ét dropdown-felt (`Employee.dispatcher_group_id`, nullable) – ikke afkrydsningsbokse. Historik: en enkelt `employees.dispatcher_group`-streng blev frem til 2026-07-27 migreret til en many-to-many `EmployeeDispatcherGroup`-jointabel, som siden er erstattet igen af den nuværende enkelte FK – se linje ~574 for den fulde migreringshistorik.

### Activity (tabel: activities)
| Felt | Type | Bemærk |
|---|---|---|
| activity_type | String(50) | "normal" eller normaliseret fraværstype-streng |
| status | Enum(pending/approved/deactivated) | |
| approved_by | String | Initialer – kun ved godkendelse |
| approved_at | DateTime | |
| deactivated_by | String nullable | Initialer – kun ved deaktivering (legacy: falder tilbage til approved_by) |
| updated_by | String nullable | Initialer på seneste bruger der gemte en PATCH-rettelse. NULL indtil første redigering, overskrives ubetinget ved hver efterfølgende (ingen historik, samme mønster som approved_by/deactivated_by). Sat ubetinget i `update_activity()` (activities.py), vist i frontend kun når feltet er sat |
| salt_supplement | Boolean | |
| pause_intervals | JSON | `[["ISO","ISO"],...]` |
| segments | JSON | `[["ISO","ISO","type"],...]` |
| parent_activity_id / split_part | Int | Split-relation |
| vehicle_registration | String | Nummerplade (fx DF67671) |
| vehicle_number | String | Vognnummer |
| vehicle_uses | JSON nullable | Alle biler vagten er kørt i fra .ddd: `[["ISO","ISO","REG"],...]` (se "Flere biler på én vagt") |
| auto_approved | Boolean | True hvis auto-godkendt |
| auto_approval_flags | JSON | Liste over afvisningsårsager (tom = godkendt) |
| baseline_duration_minutes | Numeric nullable | Varighed (min) der sidst blev bidraget til baseline (deduplication) |
| baseline_start_hour | Numeric nullable | Starttid (decimal timer) der sidst blev bidraget til baseline |

### Øvrige
- **PayPeriod**: start_date, end_date, status(open/preview/closed)
- **Vehicle**: registration_number (nummerplade), vehicle_number (vognnr), description (Text nullable, Dagsplan kol. 2), dispatcher_group_id (Int FK nullable – mange vogne → én gruppe, adskilt fra `DispatcherGroup.vehicle_id`s "standardvogn"-relation, se linje ~586)
- **PayrollRun**: pay_period_id, run_type, csv_path, excel_path

### Dagsplan-tabeller (2026-09-09, se "Dagsplan" nedenfor)
- **DailyPlanAssignment** (`daily_plan_assignments`): date, vehicle_id, employee_id (nullable), task, informed. `UniqueConstraint(date, vehicle_id)` – upsert.
- **DailyPlanExtraAssignment** (`daily_plan_extra_assignments`): samme felter uden vehicle_id, i stedet slot 1-10 (de 10 faste "EKSTRA"-rækker). Persisteres siden 2026-09-09 (oprindeligt kun frontend-state).
- **VehicleAbsence** (`vehicle_absences`): vehicle_id, date_from, date_to (nullable = étdags), comment, created_by. Aktiv på dato `d` hvis `date_from <= d <= (date_to ?? date_from)`.

### EmployeeSupplement (tabel: employee_supplements)
| Felt | Type | Bemærk |
|---|---|---|
| employee_id | Int FK | |
| name | String | Altid `"Ikke overenskomstmæssigt tillæg"` – hardcoded server-side, ikke redigerbar |
| type | String | Altid `"Timebaseret"` – hardcoded server-side |
| value | Numeric(10,2) | kr/time, skal være > 0, afrundes til 2 decimaler før gemning |
| start_date / end_date | Date | Gyldighedsperiode – `end_date` default `9999-12-31` (åbentstående) |

Status (Aktiv/Inaktiv) er IKKE lagret – beregnes ved visning ud fra om dags dato ligger i `[start_date, end_date]`. Partielt unikt indeks `uq_employee_supplements_one_open_row` (`employee_id` WHERE `end_date='9999-12-31'`) sikrer kun én åbentstående række pr. medarbejder. Se afsnit "Medarbejdertillæg" nedenfor for livscyklus- og satsopslagsregler.

### EmployeeBaseline (tabel: employee_baselines)
| Felt | Type | Bemærk |
|---|---|---|
| employee_id | Int FK | |
| weekday | Int | 0=mandag…6=søndag |
| sample_count | Int | Antal godkendte aktiviteter |
| duration_mean_minutes | Numeric | Welford mean |
| duration_m2_minutes | Numeric | Welford M2 (til std-beregning: sqrt(M2/n)) |
| start_hour_mean | Numeric | Starttid som float-timer (7.5 = 07:30) |
| start_hour_m2 | Numeric | Welford M2 |
| salt_count | Int | Antal aktiviteter med salttillæg |

---

## API-endpoints

### /api/activities
| Method | Sti | Beskrivelse |
|---|---|---|
| GET | / | Liste (period_start?, employee_id?) |
| POST | / | Opret manuel aktivitet |
| GET | /period-info | Stats + prev/next periode |
| GET | /absence-types | Fra Fraværstyper.xlsx → [{value,label}] |
| GET | /{id} | Hent én |
| PATCH | /{id} | Rediger |
| POST | /{id}/approve | Body: {approved_by, comment?} |
| POST | /{id}/deactivate | Body: {deactivated_by, comment?} |
| POST | /{id}/reopen | Sæt pending, nulstil approved_* |
| POST | /{id}/split | Body: {split_at: ISO}; begge dele → pending |
| POST | /{id}/undo-edit | Gendan originale tider |
| POST | /{id}/undo-split | Slet children, gendan forælder |
| POST | /auto-approve-pending | Auto-godkend egnede pending-aktiviteter i periode |

### /api/employees
| Method | Sti | Beskrivelse |
|---|---|---|
| GET | / | active_only=true |
| POST | / | Opret |
| PATCH | /{id} | Rediger |
| GET | /{id} | Hent én |
| PATCH | /{id} | Rediger |
| GET | /agreement-types | [{name, hourly_rate}] fra Excel |
| GET | /dispatcher-groups | Alle disponentgrupper (kun `get_current_user`) – bruges til dropdown i medarbejder-modalen |
| GET | /anciennitet-alerts | Medarbejdere med ≥9 mdr der mangler variant |

`EmployeeCreate`/`EmployeeUpdate` bruger `dispatcher_group_id: Optional[int]` (én gruppe, ikke en liste); `EmployeeResponse.dispatcher_group` er et enkelt `{id, name, description}`-objekt eller `null`. Fuld CRUD på selve grupperne (opret/omdøb/slet) ligger under `/api/stamdata/dispatcher-groups` (kræver `stamdata`-tilladelse) – fane "Disponentgrupper" i Stamdata-viewet.

**Advarsel om mulig dublet ved oprettelse (app.js: `confirmEmployee`, kun ved `id` tom):** Før POST slås navn (for+efternavn, case-insensitive) og førerkortnummer op mod `GET /api/employees?active_only=false`. Navnesammenfald → `modal-emp-duplicate-warning` med to knapper: "Ændre" (luk advarslen, bliv i oprettelsesmodalen) og "OK, opret alligevel" (kalder `_saveEmployee` med det gemte `_pendingEmployeeBody`). Match på førerkortnummer skjuler OK-knappen (`btn-emp-duplicate-ok`) – kan kun rettes, ikke ignoreres, da kolonnen stadig er unik i DB.

### /api/dagsplan (dagsplan_view / dagsplan_edit)
| Method | Sti | Beskrivelse |
|---|---|---|
| GET | /?date=YYYY-MM-DD | Samlet svar: `vehicles` (filtrerbar på disponentgruppe/medarbejder, farvestatus+mismatch) + `employees` (altid ufiltreret, farvestatus grøn/rød/grå/gul) |
| PATCH | /assignment | Upsert på (date, vehicle_id). Body: {date, vehicle_id, employee_id?, task?, informed?} |
| PATCH | /extra-assignment | Upsert på én af de 10 faste EKSTRA-rækker (slot 1-10) |

### /api/vehicle-absences (dagsplan_view / dagsplan_edit)
| Method | Sti | Beskrivelse |
|---|---|---|
| GET | /?date=YYYY-MM-DD | Materielt fravær aktivt på angivet dato |
| POST | / | Meld materielt fravær. Body: {vehicle_id, date_from, date_to?, comment} |
| DELETE | /{id} | Fjern en materielt fravær-registrering |

### /api/auto-approval
| Method | Sti | Beskrivelse |
|---|---|---|
| POST | /rebuild-baselines | Genbyg baselines fra historik (manage_baselines) |
| GET | /baseline-summary | Oversigt over baseline-status per medarbejder |

### /api/payroll
| Method | Sti | Beskrivelse |
|---|---|---|
| GET | /preview | JSON til lønkørsel-siden |
| POST | /proevekoersel-gem | Excel-fil, browser-download (Response, se 2026-09-09) |
| POST | /export-csv | Danløn CSV, browser-download – afviser (400) hvis perioden allerede er `closed`, eller der er `pending`-aktiviteter i perioden |
| POST | /pdf-timesedler | Dan PDF'er (A4 landscape), browser-download – én PDF direkte, eller ZIP hvis flere medarbejdere har data |

---

## Schemas (schemas.py) – vigtige
```python
ActivityDeactivate: comment: Optional[str]           # deactivated_by hentes fra session (current_user.initials)
ActivityApprove:    comment: Optional[str]            # approved_by hentes fra session
ActivitySplit:      split_at: datetime
AnciennitetsAlert:  employee_id, employee_name, hire_date, months_employed, suggested_agreement_type
```
**OBS:** `ActivityCreate.activity_type`, `ActivityResponse.activity_type` og `ActivityUpdate.activity_type` er `str` (ikke `ActivityType`-enum). `ActivityType`-enum i `models.py` bevares kun for bagudkompatibilitet; bruges ikke længere til sammenligning i routers. Ændringen muliggør alle dynamiske typer fra `Fraværstyper.xlsx`.

`ActivityCreate` indeholder `pause_intervals: list = Field(default_factory=list)` – sendes fra frontend som `[["ISO","ISO"],...]`. **Alle felter i Activity-modellen skal med i `ActivityCreate`/`ActivityUpdate`**, ellers dropper Pydantic dem stiltiende fra POST-body.

---

## Fraværstyper – normalisering (activities.py:27)
```python
_LABEL_OVERRIDES = {"Kursus/Skole": "skole_kursus"}  # bagudkompatibilitet
# Ellers: lowercase, æ→ae ø→oe å→aa, mellemrum//-/→_, dobbelt__ fjernes
_BACKEND_ONLY_TYPES = {"sygdom_u_8uger", "sygdom_u_8_uger", "barn_1sygedag_u_8uger", "barsel_u_loen"}  # filtreres fra dropdown; tildeles automatisk
```
`ActivityType`-enum i models.py bevares for bagudkompatibilitet (sammenligning). `activity_type`-kolonnen er `String(50)`.

### Sygdom – anciennitetskontrol
`create_manual_activity`: hvis `activity_type == "sygdom"` og `(start_date − hire_date).days < 56` → konverteres til `"sygdom_u_8uger"` (sygdom uden løn).

### Fraværstyper.xlsx indeholder
`Sygdom`, `Sygdom u. 8 uger`, `Afspadsering`, `Ferie`, `§56 syg`, `Barn 1.sygedag`, `Barn 2-3.sygedag`, `Barsel`, `Barsel u. løn`, `Feriefri`, `Graviditetsbetinget sygdom`, `Kursus/Skole`, `Selvbetalt fridag`.
`Løn andet sted fra` (normaliseret nøgle `loen_andet_sted_fra`) er IKKE i Excel-filen – den seedes i stedet idempotent til `master_absence_types` af `_ensure_loen_andet_sted_fra_absence_type()` (session.py, kaldes fra `init_db()`), samme mønster som `_ensure_springer_pay_type()` osv. Opfører sig præcis som Selvbetalt fridag: ingen `elif`-gren i `_calculate_employee()` (payroll_router.py) → 0 kr., ingen CSV-linje, og er med i `isFerie`/`isRangeType`/`_RANGE_TYPES` i app.js (periode-oprettelse understøttet).

---

## JS – app.js nøglefunktioner

**Linjenumre nedenfor er verificeret mod app.js 2026-09-04 (filen er ~5540 linjer, ikke ~3100).
Da app.js har automatisk cache-busting og ændres ofte, kan tallene igen drive – ved tvivl, grep
efter funktionsnavnet i stedet for at stole blindt på tallet.**

### State & konstanter (linje 15-38)
```js
state = { currentView, currentPeriodStart, periodInfo, activities, employees, vehicles,
          agreementTypes, agreementKinds, absenceTypes, selectedActivityId, currentUser,
          roles, usersAdminTab, holidays, dispatcherGroups, autoApprovalEnabled, vagtplan }
// Væsentligt flere felter end tidligere (auth/roller/helligdage/vagtplan tilføjet siden v5-v14) –
// se linje 15 for den fulde, aktuelle liste i stedet for at antage denne er komplet.
TYPE_LABELS = { normal: "Normal tid" }  // + fraværstyper tilføjes dynamisk (linje 101)
ABSENCE_LABELS = {}   // value → UPPERCASE badge-tekst (linje 102)
ABSENCE_TYPES = new Set()  // populeres af loadAbsenceTypes() (linje 103)
```

### Init & data-load
| Funktion | Linje | Hvad |
|---|---|---|
| `init()` | 5376 | Startup: loadAbsenceTypes → loadAgreementTypes → setView |
| `loadAbsenceTypes()` | 1573 | GET /absence-types → fylder TYPE_LABELS, ABSENCE_LABELS, ABSENCE_TYPES, #manual-type dropdown |
| `loadActivities()` | 465 | GET + renderActivitiesTable |
| `loadEmployees()` | 2348 | GET + renderEmployeeList |
| `loadPayrollPreview()` | 3116 | GET /api/payroll/preview + render |
| `loadAgreementTypes()` | 2500 | Fylder state.agreementTypes |

### Aktiviteter
| Funktion | Linje | Hvad |
|---|---|---|
| `renderActivitiesTable()` | 482 | 14-dages grid-rendering |
| `renderCellActivity(a, role)` | 1056 | Badge-HTML for én aktivitet i grid. Tooltip (`title`) på normal-badges: tidsrum, arbejdstid, `pause_minutes`, status, manuel samt Kørsel / Andet arbejde / Rådighed / Pause i % (Pause = restandel). Midnatsstykker (`role="piece"`) viser hele vagtens arbejdstid og pause |
| `openActivityDetail(id)` | 777 | Åbner modal-activity; Aktivitetsfordeling-bjælken beregner pause-% for manuelle aktiviteter uden segmentdata |
| `saveActivityTimes()` | 1163 | PATCH tider |
| `quickApprove(id)` | 717 | Sætter selectedActivityId → openApproveModal |
| `quickDeactivate(id)` | 721 | Sætter selectedActivityId → openDeactivateModal |
| `quickReopen(id)` | 725 | POST /reopen direkte |
| `openApproveModal()` | 1222 | Fylder #approve-by, åbner modal-approve |
| `confirmApprove()` | 1232 | POST /approve |
| `openDeactivateModal()` | 1267 | Fylder #deactivate-by, åbner modal-deactivate |
| `confirmDeactivate()` | 1278 | POST /deactivate |
| `modalDeactivate()` | 1263 | Fra modal → openDeactivateModal |
| `modalReopen()` | 1296 | POST /reopen fra modal |
| `openSplitModal()` | 1307 | Åbner modal-split |
| `confirmSplit()` | 1325 | POST /split |
| `undoEdit()` | 1142 | POST /undo-edit |
| `undoSplit()` | 1153 | POST /undo-split |

### Manuel aktivitet
| Funktion | Linje | Hvad |
|---|---|---|
| `openManualActivityModal()` | 1991 | Nulstiller form + manualPauses, sætter type=normal, åbner modal |
| `updateManualTypeVisibility()` | 1612 | Skjuler/viser felter afhængig af type; kalder defaults; skjuler pause-sektion for dato-kun-typer |
| `applyFerieDefaults()` | 1709 | Dato-kun, 06:00 + normaltimer (fallback 7,4 t) |
| `applySygdomDefaults()` | 1734 | Identisk med ferie; dato-kun |
| `applyAfspadseringDefaults()` | 1758 | 06:00 + normaltimer (fallback 7,4 t); tidsfelter synlige |
| `confirmManualActivity()` | 2123 | POST /api/activities inkl. pause_intervals |
| `renderManualPauses()` | 1793 | Opdaterer #manual-pauses-list med tilføjede pauser + slet-knapper |
| `addManualPause()` | 1807 | Validerer at starttid er sat; åbner modal-pause med korrekt titel og dato |
| `confirmPause()` | 1842 | Læser pause-picker, validerer, tilføjer til manualPauses, lukker modal |
| `deleteManualPause(idx)` | 1864 | Fjerner pause ved index og re-renderer listen |

**Dato-kun typer** (tidsfelter + sluttidsgruppe skjules): `ferie`, `sygdom`.  
**Heldagsstandard, redigerbar**: `afspadsering` og `skole_kursus` (enkeltdag: frie start-/sluttider; med 'Til dato' dato-kun med garanterede timer pr. hverdag, dage med 0 garanterede timer springes over – samme regel i `_range_day_defaults()`, ændret 2026-10-01). `#manual-start`s change-listener ignorerer ændringer i `.dt-time`, så defaults kun genanvendes ved datoskift – ellers blev en rettet starttid nulstillet til 06:00 (rettet 2026-09-30). Eksisterende afspadsering rettes via `edit-start`/`edit-end` → `saveActivityTimes()` (PATCH), ingen typespecifik logik.  
**Normal tid**: slutdato synkroniseres automatisk med startdato ved datoændring (kan tilsidesættes).  
**Pauser**: `let manualPauses = []` (modul-scope). Nulstilles ved åbning af modal. Medsendes som `pause_intervals` i POST. Fratrækkes i `_duration_minutes()` (backend) og lønberegning (via `_subtract_pauses()` i `overtime.py`).

### Medarbejdere
| Funktion | Linje | Hvad |
|---|---|---|
| `renderEmployeeList()` | 2358 | HTML for medarbejderlisten |
| `openNewEmployeeModal()` | 2578 | Nulstiller form |
| `openEditEmployee(id)` | 2604 | Fylder form med eksisterende data |
| `confirmEmployee()` | 2647 | Validerer, kører dublet-tjek (kun ved oprettelse), kalder `_saveEmployee` |
| `_saveEmployee(id, body)` | 2710 | Selve POST/PATCH – udtrukket fra `confirmEmployee` så dublet-advarslen kan kalde den bagefter |
| `_showEmployeeDuplicateWarning(body, nameMatches, cardMatches)` | 2727 | Bygger og åbner `modal-emp-duplicate-warning`; skjuler OK-knappen ved førerkort-match |
| `checkAnciennitetsAlerts()` | 2763 | GET /anciennitet-alerts; server filtrerer allerede dismissed; viser modal |
| `dismissAnciennitetsAlert(id)` | 2754 | POST /api/employees/{id}/dismiss-anciennitet (server-side, ikke localStorage) |
| `buildScheduleTable(schedule)` / `readScheduleTable()` | 2447 / 2485 | Se "Timefordeling – fra/til-tid" nedenfor |

### Lønkørsel
| Funktion | Linje | Hvad |
|---|---|---|
| `renderPayrollPreview(data)` | 3126 | Bygger medarbejder-kort HTML |
| `payrollRow(label,hours,rate)` | 3206 | Én datatabelrække (4 kolonner: label/timer/sats/DKK) |
| `payrollRowSalt(label,hours,rate,kr)` | 3217 | Salt-rækken |
| `proevekoersel(employeeId)` | 3258 | Åbner prøvekørsel-modal |
| `exportCsv()` | 3284 | Åbner CSV-modal |
| `downloadFile(path, body, fallbackFilename)` | 142 | Fælles helper: POST → blob → `<a download>`-browser-download; bruges af Prøvekørsel, Kør løn-CSV, PDF-timesedler og Lønafregning-CSV (se 2026-09-09) |
| `openPdfModal()` | 5123 | Åbner PDF-modal |

### Datetime-pickers
| Funktion | Linje | Hvad |
|---|---|---|
| `buildDatetimePicker(id, isoValue)` | 1361 | Injecter dato+time-inputs i #id |
| `readDatetimePicker(id)` | 1375 | → ISO-streng |
| `setDatetimePicker(id, isoValue)` | 1383 | Sætter værdier |
| `buildDatePicker(id, val)` | 1395 | Ren dato-picker |
| `setDatePicker(id, iso)` / `readDatePicker(id)` | 1548/1544 | |

### Format-hjælpere (linje 5194+)
```js
formatDate(iso)      // "15-06-2026"
formatTime(iso)      // "08:00"
formatDateTime(iso)  // "15-06-2026 08:00"
formatDuration(min)  // "8t 30m"
fmtHours(h)          // "8.50 t"
fmtKr(v)             // "1.234,56 kr"
statusLabel(s)       // "Afventer"/"Godkendt"/"Deaktiveret"
```

---

## HTML – vigtige modal-id'er og element-id'er

### Modaler
| id | Formål |
|---|---|
| modal-activity | Aktivitetsdetalje + rediger |
| modal-approve | Godkend (initialer + kommentar) |
| modal-deactivate | Deaktiver (initialer + kommentar) |
| modal-split | Split aktivitet |
| modal-manual-activity | Opret manuel aktivitet |
| modal-pause | Tilføj pause til manuel aktivitet (titel: "Pause N") |
| modal-employee | Opret/rediger medarbejder |
| modal-anciennitet | Anciennitetspåmindelse |
| modal-proevekoersel | Bekræft prøvekørsel (browser-download, intet mappe-felt siden 2026-09-09) |
| modal-csv | Bekræft/lås periode + Danløn CSV-download |
| modal-pdf | Fra/til-dato + medarbejder til PDF-timesedler-download |
| modal-settlement-csv | Bekræft lønafregnings-CSV-download |
| modal-admin | Genåbn lønperiode |

### Nøgle-inputs
| id | Formål |
|---|---|
| approve-by | Initialer i godkend-modal |
| approve-comment | Kommentar i godkend-modal |
| deactivate-by | Initialer i deaktiver-modal |
| deactivate-comment | Kommentar i deaktiver-modal |
| manual-type | Aktivitetstype-dropdown (opret) – "Normal tid" hardkodet, resten dynamisk |
| manual-pause-section | Div der indeholder pauseliste + "Tilføj pause"-knap (skjult for dato-kun-typer) |
| manual-pauses-list | Div med de tilføjede pauser (renderes af renderManualPauses) |
| pause-modal-title | h2 i modal-pause – sættes til "Pause 1", "Pause 2" osv. |
| pause-start / pause-end | dt-picker-divs i modal-pause (dato skjult, kun HH:MM vises) |
| edit-salt | Salttillæg checkbox (disabled hvis status ≠ pending) |
| filter-status | Statusfilter i toolbar |
| filter-employee | Medarbejderfilter |
| filter-dispatcher-group | Afdelingsfilter |
| period-label | Viser perioden |
| grid-head / grid-body | Aktivitetstabel |

---

## Brand-farver (CSS-variabler i style.css)
```css
--primary:       #317423   /* top-bar, payroll-header-baggrund */
--primary-dark:  #26631e
--accent:        #78b21a
--light-tint:    #d4edcc   /* payroll-col-header baggrund */
--danger:        rød
```

---

## Anciennitet – server-side dismiss
Gemmes i `employees.anciennitet_dismissed_at` (DateTime, nullable).  
`POST /api/employees/{id}/dismiss-anciennitet` sætter feltet til `utcnow()`.  
`GET /api/employees/anciennitet-alerts` springer medarbejdere over, hvor feltet ikke er `None`.  
Nulstilles automatisk på serveren, hvis `agreement_type` ændres via `PATCH /{id}`.  
Manuel dismiss: "Ændring foretaget"-knap (id: `btn-anciennitet-done`) → `dismissAnciennitetsAlert(id)` i app.js.

---

## Timefordeling – fra/til-tid (2026-07-27, app.js)
`work_schedule`-formatet er uændret (`{"even":[7 tal],"odd":[7 tal]}` – kun beregnede timetal persisteres, ikke klokketider). I medarbejder-modalen kan hver dag udfyldes med ÉT af to input: et timetal-felt (`.sched-even`/`.sched-odd`) eller et fra/til-tidspar (`.sched-even-start`/`-end`). Fra/til vinder altid, hvis begge er udfyldt: `_hoursFromTimes()` beregner timer (sluttid−starttid, wrapper til næste dag hvis negativt – dvs. vagt over midnat), overskriver timetal-feltet live via `input`-listener, og `readScheduleTable()` genberegner defensivt fra fra/til ved selve gemningen (falder tilbage til timetal-feltets værdi hvis fra/til er tomme). `_updateScheduleTotals()` opdaterer et "Ugentligt timeantal"-total pr. uge-kolonne (`#sched-even-total`/`#sched-odd-total`) på hver ændring, uanset input-metode. Ved rediger af eksisterende medarbejder er kun timetal-felterne udfyldt (fra/til gemmes ikke, kun det beregnede resultat).

---

## Rollerettigheder – approve_activities / view_calendar (2026-07-27, session.py)
`_ensure_activity_permissions()` tilføjer disse to nye tilladelser til ALLE eksisterende roller – siden 2026-09-30 kun ÉN gang pr. database via `_grant_permissions_once()` (se "Rettigheder håndhæves i backend" nedenfor) – seed-data for nye roller (`_seed_roles()`) inkluderer dem også fra start. Følger samme mønster som `_ensure_anciennitet_alert_permission()`/`_ensure_manage_baselines_permission()`.

---

## UI-robusthed for modaler og dato-vælger (2026-07-27, app.js)
`openModal(id)` nulstiller nu `.modal-body`s scroll-position til top ved hver åbning (før: bevarede scroll fra sidste gang modalen var åben – mærkbart i medarbejder-modalen efter man havde scrollet ned til timefordelingen). `buildDatePicker`s klik-handler måler nu popup-højden og flipper til at åbne OPAD i stedet for nedad, hvis nedad ville skubbe kalenderen uden for viewportet (fx felter langt nede i en scrollet modal) – se `_dpBindEvents()`.

---

## DDD-import (parsers/ddd_parser.py)
Filens dato/minutter er **UTC** – konverteres til Europe/Copenhagen (DST-korrekt via `zoneinfo`) i `_build_activities` for start_time/end_time/segments/pause_intervals. Kræver `tzdata`-pakken (i requirements.txt – Windows har ingen egen IANA-tidszonedatabase).
**Kortnummer**: rå felt i filen er 16 tegn (`[A-Z]{2}\d{14}`), men kun de første 14 tegn (`driverIdentification`) er det stabile nummer til medarbejder-matching – sidste 2 cifre er udskiftnings-/fornyelsesindeks og ændrer sig ved kortfornyelse. `_extract_card_number()` matcher det fulde felt, returnerer kun de første 14 tegn.
**Dagsstart**: changes[0] er altid en hvil-post ved minut 0 (videreført status, ikke reel pause). Er der en ekstra hvil-post lige efter (før første arbejde/kørsel) er det chaufførens faktiske dagsstart – bruges som `day_start_minute` så en indledende kort pause vises i arbejdstiden (og i `pause_intervals`), men forbliver ubetalt.
**Skip-årsager**: `_import_activity()` returnerer `new`/`updated`/`skipped_unknown_card`/`skipped_duplicate` – tælles separat af `_process_import_results()` og logges som én `ddd_import`-hændelse (log_action) med fuld opsummering inkl. konkrete ukendte kortnumre. Frontend viser resultatet i `modal-import-result` (success-visning eller opdelt årsagsliste) i stedet for kun en toast. `scan_ddd_folder()` returnerer nu `(results, errors)` – parse-fejl ved mappescanning ryger i `errors` i stedet for kun `print()` til konsollen.

**Dublet-tjek mod afgjorte linjer**: Rammer opslaget i `_import_activity()` en godkendt/deaktiveret linje der afviger, tjekkes ALLE øvrige overlappende afgjorte linjer via `_settled_line_covers()` (identisk med `_baseline()` eller forældet ufuldstændig genlæsning) før der oprettes en ny pending-linje. Uden det skabte en deaktiveret delvis udlæsning ved siden af den godkendte fulde vagt en ny dublet ved hver genimport (2026-10-01: Alexander B. Knudsen 28/9).
**Genimport af samme dag med mere komplet data**: Dedup matcher på `(employee_id, start_time, source=tachograph)`. Har en ny udlæsning et SENERE `end_time` end den eksisterende aktivitet (fx fordi kortet først blev downloadet midt på dagen og senere igen efter vagtens afslutning), udvides `end_time`/`segments`/`pause_intervals`/procentfelter i stedet for at blive sprunget over som duplikat. Var aktiviteten `approved`/`deactivated`, genåbnes den til `pending` (approved_by/approved_at/deactivated_by nulstilles) så den udvidede tid skal godkendes igen, før den tæller med i løn. Kun km-felterne blev opdateret ved duplikat før denne rettelse (2026-07-02) – resten af den nye tid gik tabt for altid ved delvise kortudlæsninger.
**Km-start/km-slut**: `_extract_daily_odometer()` finder en kæde af 20-byte (km, UTC-tidsstempel)-par (mindst 5 i træk, ingen fast offset) – tidsstemplet matcher dagens `day_start_minute`. `km_end = km_start + distance` (dagens egen activityDayDistance), IKKE næste tabelpost (håndterer køretøjsskift korrekt). Kortet gemmer kun et begrænset antal poster, så ikke alle dage har km-data. Erstatter den tidligere CardVehiclesUsed-baserede søgning, som byggede på en forkert byte-offset-antagelse.

---

## Periodegrænser i aktivitetsoversigten og sen registrering (2026-07-27)
**Visning af aktiviteter der krydser periodegrænsen:** `list_activities()` i `activities.py` filtrerer ikke længere kun på `pay_period_id` – et OR-filter medtager også aktiviteter hvor `start_time` ligger før periodens startdato, men `end_time` ligger på/efter den (fx en søndagsvagt der starter sidst i forrige periode og fortsætter ind i den viste periode). Kun aktiviteter der faktisk krydser grænsen påvirkes.

**Låst lønperiode (2026-09-30):** Manuel oprettelse (`POST /api/activities`), flytning via `PATCH` og tilføjelse af dage i en fraværsperiode på en dato i en låst periode AFVISES nu (`_forbid_date_in_closed_period` i `activities.py`) – sen registrering gælder kun DDD-import. Alle ændringer (PATCH, undo-edit, undo-split, split, segment-rettelser, reopen) af aktiviteter i en låst periode afvises (`_forbid_change_in_closed_period`), og fravær kan hverken slettes eller deaktiveres. Frontend bruger `ActivityResponse.period_closed` og `GET /api/activities/locked-dates`. **Udvidet samme dag:** deactivate/DELETE afvises for ALLE typer (`_forbid_removal_in_closed_period`), `undo_edit` tjekker den oprindelige dato med `_forbid_date_in_closed_period` FØR tiderne ændres, `hide-from-vagtplan` bruger `_forbid_change_in_closed_period`, `auto-approve-pending` returnerer 0/0 i låst periode, og `DELETE /api/vagtplan-comments/{id}` afvises på låst dato.

**Sen registrering på en allerede lukket periode (nu kun DDD-import):** ny hjælpefunktion `get_billing_period()` i `pay_period.py` – hvis den relevante dato hører til en periode med `status == closed`, returneres i stedet den PÅFØLGENDE periode (kalder `get_or_create_period_for_date()` på `end_date + 1 dag`). Bruges ved oprettelse af aktivitet (`POST /api/activities`), redigering af starttid (`PUT /api/activities/{id}`) og DDD-import (`_process_activity` i `import_ddd.py`). `reopen`-endpointet er bevidst IKKE ændret – en genåbnet aktivitet bevarer sin oprindelige `pay_period_id`; det er kun visningen (ovenstående OR-filter), der sørger for at den stadig ses i den efterfølgende periodes oversigt.

**Split af søn-/helligdagsvagter over midnat i aktivitetsoversigten (frontend, app.js):** en kørselsvagt (`activity_type == "normal"`) der starter på søndag/helligdag og strækker sig over midnat vises nu opdelt pr. kalenderdag i gitteret (matcher `_split_into_day_pieces()` i lønberegningen) – hvert stykke viser sit eget `HH:MM–HH:MM` i sin egen datokolonne, klik åbner altid den oprindelige aktivitet (`_orig_id`). Vagter der starter hverdage/lørdage er uændrede (kun start/slut-badge i hver ende).

---

## Auto-godkendelse ved oprettelse af aktivitet (2026-08-25, activities.py + auth.py + session.py)
Ny permission `auto_approve_manual_activities` ("Auto-godkend ved oprettelse") – styrer om `create_manual_activity()` sætter `status=approved` direkte i stedet for `pending` for normal arbejdstid. `admin` har den automatisk (systemrolle), `lonbogholder` får den som default-seed + migration (`_ensure_auto_approve_permission()`, samme mønster som `_ensure_manage_baselines_permission()`), `disponent` får den ikke som default men kan tildeles den via rolle-editoren. Er aktiviteten under 4 timer (samme beregning som `is_under_4h`/godkendelses-endpointet: `_duration_minutes()` + `_day_reaches_4h_with_approved()`) og kommentarfeltet er tomt, sættes `comment = current_user.initials` automatisk – kun for brugere med permissionen, og kun hvis de ikke selv har skrevet en kommentar. Fraværstypers eksisterende ubetingede auto-godkendelse (alle roller) er uændret; kommentar-fallback'en udløses dog ikke for roller uden permissionen.

**Rettet 2026-09-03:** Denne godkendelse er UAFHÆNGIG af den globale auto-godkendelses-kontakt (`SystemSettings.auto_approval_enabled`, se `docs/superpowers/specs/2026-08-27-global-auto-godkendelse-kontakt-design.md`). Kontakten styrer kun den statistiske baseline-godkendelse (DDD-import + bulk-knappen "Autogodkend aktiviteter"). `create_manual_activity()` tjekker derfor kun `auto_approve_manual_activities`-permissionen, ikke `is_auto_approval_enabled(db)` – oprindeligt (fejlagtigt) koblet sammen i den globale kontakt-implementering.

---

## Danløn CSV-struktur (payroll_router.py)

Kolonner: `CVR ; medarbejdernr ; Danløn-kode ; timer/antal ; sats ; (total)`

Én række per løntype der har antal > 0 OG `include_in_csv=true` i Stamdata → Løntypekoder
(`master_pay_types`). Koden, enheden (timer/antal) og om sats/total skal med er alt sammen
konfigureret pr. type i den tabel – DB er authoritative, ikke hardkodede konstanter. Ved seeding
(`session.py`, kun ved tom tabel) sættes koden fra `calculators/pay_rates.py`s `DANLOEN_CODE_*`-
konstanter, som (pt. 2026-09) alle er sat til placeholder `"1"` undtagen SH-koderne – se filens
egen kommentar ("kravdokument: disse findes pt. ikke"). De faktiske koder skal derfor slås op i
Stamdata → Løntypekoder for det aktuelle system, ikke antages fra denne tabel:

| code_key | Seedet default | Enhed | Bemærkning |
|---|---|---|---|
| NORMAL | 1 | timer | |
| SPRINGERTILLAEG | 1 (placeholder) | timer | kun med hvis flueben sat for medarbejder+periode, se afsnit nedenfor |
| OT_BEFORE | 1 (placeholder) | timer | |
| OT_13 | 1 (placeholder) | timer | |
| OT_EXTRA | 1 (placeholder) | timer | |
| SALT | 1 (placeholder) | timer | |
| OVERNATNING | 1 (placeholder) | antal | `csv_quantity_type="count"` |
| AFSPADSERING | 1 (placeholder) | timer | total (ikke sats) vises |
| SYGDOM / PARAGRAF_56 / BARSEL | 1 (placeholder, separate DANLOEN_CODE_*-konstanter, pt. samme værdi) | timer | §56 bruger dagpengesats, de øvrige medarbejderens timesats |
| BARN_1SYGEDAG | 1 (placeholder) | timer | dagpengesats |
| FERIEFRI | 1 (placeholder) / `DANLOEN_CODE_FERIEFRI_FULDLOENNET=5` for fuldlønnede feriefri-timer | timer/antal | enhed styres af Stamdata (se `_builtin_absence_qty()` nedenfor) |
| SKOLE_KURSUS | 1 (placeholder) | timer | total (ikke sats) vises |
| SH_FULDLOENNET / SH_TIMELOENNET | 4 / 63 (reelle koder, ikke placeholder) | timer | søgnehelligdag |
| `ferie` (brugerdefineret type, tilføjet via Stamdata) | 60 | timer | `include_in_csv=false` som default – ferie tælles og vises i UI, men skrives IKKE til CSV før det slås til i Stamdata |

**Case-bug rettet (2026-07-30):** `_get_pay_type_data()` slog op med den rå (case-sensitive)
`code_key` fra DB, mens `_user_pay_type_rows()` slog op med `.upper()`. For alle indbyggede
typer (som allerede er SKREVET MED STORE BOGSTAVER i DB) gjorde det ingen forskel, men for
brugerdefinerede typer med små bogstaver (fx `ferie`) matchede opslaget aldrig – koden,
`include_in_csv`, `csv_include_rate`/`csv_include_total` faldt derfor altid tilbage til
default (kode "1", altid inkluderet). Konsekvens: ferietimer blev skrevet ud som Normal tid
(kode 1) i stedet for kode 60, og kunne optræde som en ekstra "kode 1"-linje der lagde sig til
den rigtige normaltid i Danløn. Rettet ved at normalisere opslaget til store bogstaver.

**`_builtin_absence_qty(pt, key, activity_type, hours_value, emp_id, start, end, db)`:** ny
hjælpefunktion der lader Stamdatas `csv_quantity_type` ("timer"/"antal") styre antallet også
for indbyggede fraværstyper (i dag kun brugt til FERIEFRI) – uden den bruges altid det
akkumulerede timeantal fra `_calculate_employee()`, uanset stamdata-indstillingen.

**`_afspadsering_hours(emp, act)`:** en afspadsering-aktivitet der er lavet som en periode
("Til dato" udfyldt ved oprettelse, spænder over flere kalenderdage) tæller 7,4 t (eller
medarbejderens skemalagte timer) **pr. hverdag** i perioden, uanset de faktiske klokketider på
aktiviteten. En enkeltdags-aktivitet (delvis fridag) bruger stadig den reelle varighed. Uden
denne skelnen blev en flerdags-periode talt som rå klokketid (kan blive 30-100+ timer for en
uges fri, hvis aktiviteten fx er registreret som "fredag 06:00 → følgende fredag 14:00").

`_calculate_employee()` returnerer `sygdom_hours` og `afspadsering_hours` separat i result-dict.

**Periodegrænse-bug rettet (2026-07-30):** Aktivitets-forespørgslen i `_calculate_employee()`
filtrerede tidligere på `Activity.start_time >= start`, dvs. en vagt der starter søndag aften i
DEN FORRIGE periode og fortsætter forbi midnat ind i den nye periodes mandag blev slet ikke
hentet for den nye periode – hverken den forrige periodes dagsløkke (som stopper ved sin egen
`end_date`) eller den nye periodes forespørgsel fangede mandagsdelen, så de timer forsvandt
fuldstændigt fra lønberegningen i begge perioder. Rettet ved at forespørgslen nu bruger overlap
(`start_time < periodeslut+1 AND end_time > periodestart`) i stedet for kun `start_time`. Den
eksisterende søndags-splitning (`_split_into_day_pieces()`) håndterer herefter automatisk at
fordele timerne korrekt til de to perioders egne dage – ingen dobbelttælling, da hver periodes
dagsløkke kun summerer datoer inden for sit eget interval. Bekræftet med et konkret tilfælde
(vagt 12/7 19:00 → 13/7 19:00): før fix talte kun de 5 timer inden midnat (i forrige periode),
efter fix talte forrige periode stadig kun de 5 timer og den nye periode fik de resterende 19
timer – i alt 24 timer bevaret, ingen dubletter.

**Kør løn – låsning (2026-07-02, opdateret 2026-09-09):** `export_csv_post()` i `payroll_router.py` afviser med 400, hvis (a) perioden allerede har `status == PayPeriodStatus.closed`, eller (b) der findes `pending`-aktiviteter for aktive medarbejdere i perioden – begge dele skal være håndteret (godkendt/deaktiveret) først. CSV-indholdet bygges (`_build_danloen_csv()`) FØR perioden sættes til `closed`, så en fejl under selve beregningen ikke kan låse perioden uden gyldig eksport. Siden 2026-09-09 skrives filen ikke længere til disk på serveren – den returneres direkte som `Response` med `Content-Disposition: attachment` og downloades af browseren i stedet (tidligere krævede alle fire eksport-flows en mappesti, som fejlagtigt blev valideret mod SERVERENS hjemmemappe i stedet for klientens – se `_safe_save_dir()`/`is_under_allowed_root()`, som nu er ubrugte). Der er derfor ingen `PermissionError`-fangst længere, hverken her eller i `proevekoersel_gem()`.

**OBS – to forskellige "hvilken periode hører aktiviteten til"-kilder:** `pay_period_id` (sat ved oprettelse via `get_billing_period()`) styrer hvad Aktiviteter-fanen og tælleren (`period-info`) viser. Den faktiske lønberegning (`_calculate_employee()`, og dermed også pending-tjekket i `export_csv_post()`) bruger derimod `start_time`-datointervallet, UAFHÆNGIGT af `pay_period_id`. De to kan gå ud af sync: `get_billing_period()` ruller en aktivitet frem til NÆSTE åbne periode, hvis dens naturlige periode er `closed` på oprettelsestidspunktet ("sen registrering"). Genåbnes perioden senere, flytter `reopen_period()` (2026-07-02) automatisk sådanne aktiviteter tilbage (matchet på `start_time`), så de ikke bliver usynlige/fanget mellem to perioder.

---

## Overtidsberegning (calculators/overtime.py)
```python
OT_BEFORE_KEY = "Overtid 1 time før"
OT_13_KEY     = "Overtid 1-3 timer efter"
OT_EXTRA_KEY  = "Øvrigt overtid"   # NB: med 't' (ikke 'g')
# calculate_overtime(start, end, normal_cap, pauses) → OvertimeResult
# .normal_hours = ALLE arbejdede timer (= total_hours); OT-felter er additive tillæg
# .ot_before_hours, .ot_13_hours, .ot_extra_hours, .total_hours
# pauses = [(datetime, datetime), ...] – fratrækkes via _subtract_pauses() FØR beregning
```
Semantik (v15+): `normal_hours = total_hours` (alle timer efter pausefradrag). OT-koder er supplement-tillæg oven på normaltidsløn, ikke erstatning.

**Loft deles pr. dag, ikke pr. aktivitet (2026-07-02):** `_calculate_employee()` i `payroll_router.py` initialiserer `day_normal_remaining`/`day_ot13_remaining` ÉN gang pr. kalenderdag (før løkken over `acts_today`) og videresender dem til `calculate_overtime()`/`calculate_special_day_overtime()` via `normal_remaining`/`ot13_remaining`/`kode8_remaining`-parametrene; resultatet indeholder `ot.normal_remaining_after`/`ot.ot13_remaining_after` til næste aktivitet samme dag. Uden dette bliver 7-timers normalloft og 3-timers OT13-loft nulstillet for hver aktivitet, hvilket underberegner Øvrigt overtid (kode 9), når én dag er delt i flere godkendte aktiviteter (fx efter split eller flere separat godkendte DDD-fragmenter).

**Registreret normaltid forbruges kun i 06-18 (2026-07-02):** Nat- (21-05), "1 time før"- (05-06) og aften-timer (18-21) fortærer IKKE det registrerede normaltids-loft (`normal_remaining`) – kun arbejde i 06-18-vinduet gør. De giver stadig deres eget tillæg (ot_before/ot_13/ot_extra) og tæller med i `normal_hours` (kode 1), men reducerer ikke hvor meget af 06-18-arbejdet der regnes som "ren" normaltid. Rettelsen ophæver den tidligere "Eksempel 1"-fortolkning i `docs/OVERTIME_RULES.md` (som var en fejllæsning af kravdokumentet, bekræftet af bruger) – se `_test_overtime.py` for opdaterede forventede værdier.

**Vagter der krydser midnat – kun søndag/helligdag splittes (2026-07-02):** Normaltids-/OT13-loftet hører til VAGTEN (den dag den startede), ikke kalenderdagen – en fredag-til-lørdag-vagt bruger fredagens loft, indtil det er brugt op, helt automatisk via `calculate_overtime()`s kronologiske segment-løkke (intet split nødvendigt, loft-baserede dagtyper NORMAL/SATURDAY kan altid deles op i én sammenhængende beregning). Undtagelsen er søndage/helligdage, hvor reglen er loft-uafhængig ("alle kørte timer → kode 9, uanset tidspunkt") – en vagt der STARTER på en søndag/helligdag SKAL derfor splittes ved midnat (`_split_into_day_pieces()` i `payroll_router.py`), så resten af vagten falder tilbage til den følgende dags egne regler. `_calculate_employee()` afgør splittet via `classify_day(act.start_time.date(), holiday_map) in _ABSOLUTE_DAY_TYPES`. `DayType.SATURDAY` bruger nu altid `calculate_overtime()` (aldrig `calculate_special_day_overtime()`) – lørdagens tidligere særregel ("ingen garanterede timer → første 3 kørte timer = kode 8") er fjernet, da den modsagde de faktiske forventede tal; med lørdagens eget (typisk 0) loft rammer den normale dagvindues-logik automatisk samme resultat.

## Pausehåndtering (activities.py + overtime.py)
`_duration_minutes(a)` i `activities.py` fratrækker `pause_intervals` fra brutto-varighed → bruges til "Sum, effektiv tid" i UI og `is_under_4h`/`is_over_12h`. Pauser tages fra `rest`-segmenter når aktiviteten har `segments` (DDD), ellers fra `pause_intervals` (manuelle).  
`ActivityResponse.pause_minutes` (2026-09-30) = bruttovarighed − `_duration_minutes(a)`, beregnet i `_to_response()` – samme pausekilde, så arbejdstid + pause altid = vagtens længde. Vises i aktivitetens tooltip (`renderCellActivity`). For DDD-aktiviteter er pause-% lig `rest_pause_pct`; i UI hedder "Hvil" nu "Pause" overalt.  
`_calculate_employee()` i `payroll_router.py` sender pauser til `calculate_overtime()` som `[(datetime, datetime), ...]` → `_subtract_pauses()` fjerner dem fra arbejdsintervallerne FØR timefordeling.  
Pauser oprettes manuelt via `modal-pause` (kun HH:MM, dato arves fra aktivitetens startdato). Gemt som `[["ISO","ISO"],...]` i `pause_intervals`-kolonnen.

---

## Medarbejdertillæg (2026-08-13, employee_supplements.py + payroll_router.py + absence_overview_router.py)

Individuelt kr/time-tillæg pr. medarbejder oveni overenskomsttypens grundsats, administreret fra et selvstændigt sidebar-punkt "Tillæg" (permission `manage_employee_supplements`).

**Livscyklus** (`_create_supplement()` i `employee_supplements.py`): oprettelse af en ny række lukker automatisk medarbejderens forrige åbentstående række (`end_date` sættes til `ny_start_dato − 1 dag`); ny `start_date` skal være efter den forrige rækkes `start_date`, ellers 400. Ingen PATCH/DELETE – kun oprettelse og `POST /{id}/end` (se nedenfor). Partielt unikt indeks (`uq_employee_supplements_one_open_row`, kun WHERE `end_date='9999-12-31'`) forhindrer to samtidige åbentstående rækker for samme medarbejder; `IntegrityError` oversættes til 409.

**Afslutning af et tillæg** (`POST /api/employee-supplements/{id}/end`): sætter `end_date` til slutdatoen for den lønperiode `date.today()` falder i (`get_or_create_period_for_date()`), IKKE til dags dato selv – tillægget gælder derfor stadig resten af igangværende periode og bortfalder først fra den efterfølgende. Kun muligt på en række der er aktuelt aktiv OG åbentstående.

**Satsopslag** (`get_active_supplement_for_period(db, employee_id, period_start, period_end)` i `calculators/rates_loader.py` – IKKE i `employee_supplements.py`, flyttet dertil for at undgå at et routermodul importerer et andet): finder rækken hvis gyldighedsperiode overlapper den beregnede periode; overlapper flere (nyt tillæg oprettet midt i en periode), vinder rækken med nyeste `start_date` for HELE perioden (ingen dag-for-dag splitning). Gør genberegning af en gammel, afsluttet periode historisk korrekt.

**Integration i lønberegningen**: `payroll_router.py`, `_calculate_employee()` – `hourly_rate` forhøjes med et evt. tillæg umiddelbart efter overenskomstopslaget (linje ~270-276), FØR alle nedstrøms forbrug (normaltid/kode 1, SH-betaling, CSV-rækkerne AFSPADSERING/SYGDOM/BARSEL/SKOLE_KURSUS/FERIEFRI). Samme funktion kaldes fra `absence_overview_router.py`s eget satsopslag, så Fraværsoversigtens viste sats altid stemmer overens med den der reelt udbetales.

**API**: `GET /api/employee-supplements` (filtre `employee_id`/`from`/`to`), `GET /active/{employee_id}` (null hvis intet aktivt), `POST ""` (opret), `POST /{id}/end` (afslut). Alle kræver `manage_employee_supplements`.

**Frontend**: sidebar-punkt "Tillæg" → søgeliste (samme mønster som `employee-search`) → klik åbner `modal-supplement-detail` (IKKE en inline-boks – med ~79 medarbejdere ville en inline-visning lande langt uden for skærmen uden auto-scroll, rettet 2026-08-13) med historik-tabel (`table-layout:fixed`, procent-kolonnebredder, `width:96vw;max-width:1400px` – undgår horisontal scroll uanset antal medarbejdere/kolonneindhold). "+ Tilføj" findes både i sidens toolbar og i detaljemodalens footer (`openAddSupplementFromDetail()` lukker detaljemodalen midlertidigt for at undgå to overlappende `.modal-overlay` med samme z-index, genåbner den efter succesfuld oprettelse). Read-only felt (`emp-active-supplement`) i `modal-employee` under Overenskomsttype, gated bag `data-perm-require="manage_employee_supplements"` og et JS-permission-tjek før fetch (undgår unødvendige 403'ere for brugere uden rettigheden).

---

## Springertillæg (2026-08-14, activities.py + payroll_router.py + session.py)

Ny løntypekode `SPRINGERTILLAEG` (kr/time-sats fra `MasterSupplementRate`, label "Springertillæg") der giver samme timetal som løntypekode 1 (`calc["normal_hours"]`) — men KUN for de medarbejdere, der i den enkelte lønperiode har et flueben sat i aktivitetsoversigten (under navnet, samme række). Mønsteret følger Overnatning: hardcodet i `_resolve_rate()`/`_calculate_employee()`/CSV-raw_rows, ikke den generiske `_user_pay_type_rows()`-mekanisme (springertillæg er ikke knyttet til en `Activity`).

**Datamodel:** ny tabel `employee_springer_flags` (`employee_id`, `pay_period_id`, `enabled`), unikt indeks på `(employee_id, pay_period_id)`. Ingen række = ikke sat — nulstilles derfor automatisk hver ny periode uden seeding.

**Periodeopslag i `_calculate_employee()`:** perioden slås op internt via `get_or_create_period_for_date(start, db)` i stedet for at tilføje en `period_id`-parameter — funktionen har 8 kaldssteder, nogle med frie datointervaller (tidssedler/preview) uden noget naturligt periode-begreb.

**Endpoints** (`activities.py`): `GET /api/activities/springer-flags?pay_period_id=` (`view_calendar` eller `vagtplan_view` siden 2026-09-30 — samme niveau som resten af aktivitetsoversigten), `POST /api/activities/springer-flag` (kræver `toggle_springer`, upsert, afvises med 400 hvis perioden er `closed`).

**Permission `toggle_springer`:** gives til ALLE roller (system og ikke-system) ved migrering, jf. beslutning om at åbne den for alle roller for nu.

**Lønkørsel-fanen (2026-09-22, app.js `renderPayrollPreview()`):** viser en "Springertillæg"-linje pr. medarbejder (antal timer + beløb) via den generiske `payrollRow()`-helper, samme timetal/sats som CSV'en (`emp.normal_hours` × `emp.springer_rate`), kun når `emp.springer_enabled` er true — begge felter kommer allerede med i `/api/payroll/preview`-svaret fra `_calculate_employee()`. Beløbet er IKKE en del af `emp.total_kr` (ligesom Overnatning/DOB Overnatning), så det lægges manuelt til i "I alt"-rækken.

**PDF-timesedler (2026-09-22, timeseddel_router.py `_build_pdf()`):** samme "Springertillæg"-linje i LØNOPSUMMERING-tabellen, lige efter "Timer arbejdet" — betinget af `calc['springer_enabled']` (ikke kun timetal > 0, da `normal_hours` altid er sat). Beløbet (`springer_kr`) lægges til `total_display_kr` i "I alt"-rækken, samme mønster som `overnight_kr`/`dob_overnight_kr`.

**Klient-cache-faldgrube i aktivitetsoversigten (rettet 2026-09-22):** checkbox-listeneren for fluebenet skal opdatere `state.springerFlags` lokalt efter et vellykket POST — ellers overskriver en efterfølgende `renderActivitiesTable()`-gentegning (fx via `refreshActivities()` efter oprettelse af en aktivitet) fluebenet med den forældede værdi fra sidste periode-indlæsning.

---

## Aftale som Stamdata-tabel (2026-08-24, models.py + stamdata.py + employees.py + overtime.py + payroll_router.py)

"Aftale"-feltet på medarbejderen (tidl. hardcoded `<option>`-liste + Python-enum `AgreementKind`) er flyttet til en redigerbar Stamdata-tabel `master_agreement_kinds` (fane "Aftale"). Se `MasterAgreementKind` ovenfor for feltoversigt og `docs/superpowers/specs/2026-08-24-aftale-stamdata-design.md` for det fulde design.

**Nøglen (`key`) er fast for altid** — sættes kun ved oprettelse, kan ikke redigeres bagefter (heller ikke af en admin via UI'et), fordi `overtime.py`/`payroll_router.py` fortsat grener direkte på strengværdierne `"hourly_fixed"`/`"hourly_flexible"`. Kun `label`, `is_active` og `requires_agreement_type` er redigerbare.

**Ingen DB-migration nødvendig** for `Employee.agreement_kind` — kolonnen var allerede en almindelig `VARCHAR(15)` uden CHECK-constraint i SQLite (bekræftet via `sqlite_master`), så ændringen fra `Column(Enum(AgreementKind))` til `Column(String(50))` i `models.py` krævede ingen `ALTER TABLE`. `agreement_type` forbliver `NOT NULL` i DB'en — tom streng `""` bruges som sentinel for "ikke relevant" i stedet for en risikabel tabel-genopbygning til reelt NULL.

**Ny Aftale-type ⇒ intet OT-tillæg:** `_calculate_employee()` (`payroll_router.py`) tjekker `is_recognized_agreement_kind = emp.agreement_kind in (AgreementKind.hourly_fixed, AgreementKind.hourly_flexible)` FØR `day_type`-grenen. Er den `False`, kaldes `calculate_flat_hours(start, end, pauses)` (`overtime.py`) i stedet for `calculate_overtime()`/`calculate_special_day_overtime()` — ren timeopgørelse (arbejdstid minus pauser → `normal_hours`), ingen `ot_before`/`ot_13`/`ot_extra`/`sh_kode8`/`sh_kode9`, uanset dagtype (også søndag/helligdag). Bevidst midlertidig afgrænsning — den fremtidige "gruppe"-logik for nye aftaletyper er endnu ikke defineret.

**`requires_agreement_type` håndhæves i `employees.py`:** `create_employee`/`update_employee` slår den valgte `agreement_kind`s `requires_agreement_type` op (`_agreement_type_required()`) — er den `False`, sættes/tillades `agreement_type = ""`; er den `True`, er et ikke-tomt, gyldigt `agreement_type` påkrævet (400 ellers).

**Seeding:** `session.py: _seed_agreement_kinds()` opretter de to systemrækker (`is_user_created=False`) idempotent ved opstart — IKKE fra Excel, i modsætning til de øvrige master-tabeller.

**Endpoints:** `GET /api/employees/agreement-kinds` (kun aktive, `get_current_user` — bruges til medarbejder-modalens dropdown). Fuld CRUD under `/api/stamdata/agreement-kinds` (kræver `stamdata`): `DELETE` afviser systemtyper (`is_user_created=False`) og typer der er i brug af mindst én medarbejder.

**Frontend:** `fillAgreementKindSelect()` erstatter den tidligere hardcodede `<option>`-liste i `emp-agreement-kind`; `onAgreementKindChange()` viser/skjuler `#emp-agreement-type-required-star` ud fra den valgte types `requires_agreement_type`. `loadStamdataAgreementKinds()` genindlæser `state.agreementKinds` efter hver Stamdata-ændring, så nye typer er valgbare i medarbejder-modalen uden sideopdatering.

---

## Disponentgruppe 1:1 + vognnummer-autoudfyldning ved fravær (2026-08-26)
`Employee.dispatcher_groups` (mange-til-mange) er erstattet af `Employee.dispatcher_group_id`/`dispatcher_group` (én gruppe, nullable). `EmployeeDispatcherGroup`-tabellen er fjernet (migreret af `_migrate_dispatcher_group_to_single()` i `session.py`, som ved konflikt beholder den alfabetisk først sorterede gruppe; kolonnetilføjelserne selv sker i `_migrate()`, da den ORM-baserede `_migrate_dispatcher_groups()` ellers ville fejle på manglende kolonner). `DispatcherGroup.vehicle_id`/`vehicle`/`vehicle_number` (property) peger på et køretøj i vognparken, vedligeholdt via Stamdata → Disponentgrupper (søgbart vognnummer-felt, brugerdefineret dropdown – ikke native `<datalist>`, af hensyn til konsistent substring-søgning på tværs af browsere). **⚠️ Erstattet 2026-09-30:** fravær-default kommer nu fra `Employee.absence_vehicle_id` ("Vognnummer ved fravær") via `applyAbsenceVehicleDefault()` – gruppens vogn bruges ikke længere til fravær. Oprindeligt: `app.js`s `applyDispatcherGroupVehicleDefault()` foreslog automatisk gruppens vognnummer i opret-aktivitet-modalens vognnummer-felt for enhver fraværstype (kun hvis feltet er tomt) – rent frontend-prefill, ingen backend-håndhævelse. Fejl rettet undervejs: flerdags-fraværsregistrering (`confirmManualActivity()`s range-gren) sendte tidligere slet ikke `vehicle_number` med i sit `POST /api/activities`-kald.

---

## Dagsplan (2026-09-09, dagsplan_router.py + models.py + activities.py + app.js)

Ny sidebar-side der digitaliserer den daglige fordeling af vogne til chauffører (tidligere et Excel-ark uden for systemet). To underfaner, samme fane-mønster som Stamdata: "Dagsplan" og "Materiel fravær" – deler ét state-felt for valgt dato (`state.dagsplan.date`). Se `docs/superpowers/specs/2026-09-09-dagsplan-design.md` for det fulde design, og "Dagsplan-tabeller"/"/api/dagsplan"/"/api/vehicle-absences" ovenfor for datamodel og endpoints.

**Permissions** `dagsplan_view`/`dagsplan_edit` (`app/auth.py:34-35`) – tilføjes idempotent ved opstart, samme mønster som `manage_baselines`. `admin` får dem automatisk som systemrolle; andre roller kun via rolle-editoren.

**Mismatch-advarsel:** for hver tildelt medarbejder slås dagens `normal`-type aktiviteter op. Afviger en akivitets `vehicle_number` fra den tildelte vogns, sættes `mismatch_vehicle_number` (⚠️-ikon + tooltip "vognnummer i løn: xxx" i frontend). Kun `normal`-aktiviteter indgår – fravær sammenlignes ikke.

**Farveprioritet på medarbejderlisten** (altid ufiltreret, uanset disponentgruppe-/medarbejder-filtrene på hovedtabellen): gul (comment_only – vagtplan-kommentar) > rød (absent – fravær) > grøn (assigned) > grå (none). En medarbejder med fravær forbliver gul selv når vedkommende samtidig er tildelt en vogn.

**Dobbelttildeling blokeres ikke:** forsøger man at tildele en medarbejder der allerede har en anden tildeling eller registreret fravær samme dag, returneres 409 med en menneskelæsbar advarsel i stedet for en hård fejl – brugeren kan bekræfte og gennemføre alligevel. *(Tilføjet efter brugerønske – oprindeligt ingen validering.)*

**Autoudfyld af vognnummer:** `create_manual_activity()` (activities.py:~491-497) slår `daily_plan_assignments` op på `(employee_id, start_time.date())` når en `normal`-aktivitet oprettes med tomt `vehicle_number`. Gælder KUN "normal tid", overskriver aldrig et allerede udfyldt felt, og er uafhængig af den eksisterende disponentgruppe-baserede autoudfyldning for fraværstyper (`applyDispatcherGroupVehicleDefault()`) – de to mekanismer lever side om side. Frontend-modstykket er `applyDagsplanVehicleDefault()` i app.js (~linje 2237).

**EKSTRA-rækkerne** (10 faste pladser til hjælp på pladsen/lærlinge) indgår ALDRIG i vognnummer-autoudfyldning eller lønberegning – kun "Fast bil"/rigtige vogne gør.

---

## "Ændret af"-felt på aktiviteter (2026-09-10, models.py + schemas.py + activities.py + app.js)

`Activity.updated_by` (String nullable) sættes ubetinget til `current_user.initials` i `update_activity()` (`PATCH /api/activities/{id}`) ved HVERT kald – rammes af både "Gem ændringer" i redigeringsmodalen og øvrige steder der patcher en aktivitet. NULL indtil første redigering, overskrives uden historik ved hver efterfølgende (samme mønster som `approved_by`/`deactivated_by`, og som `SystemSettings.updated_by`). Vist i app.js (aktivitetsdetalje, ved siden af "Godkendt af"/"Deaktiveret af") kun når feltet er sat. Se `docs/superpowers/specs/2026-09-10-aendret-af-felt-design.md`.

---

## Særaftale: Øvrig overtid for alle timer (2026-09-10, overtime.py + payroll_router.py + models.py)

`Employee.ot_extra_alle_timer` (Boolean, default false) – generisk, togglebart per-medarbejder-flag til én navngiven medarbejders individuelle særaftale. UAFHÆNGIGT af `agreement_kind`-branchingen (linje ~573) – virker som et nyt, øverste tjek i `_calculate_employee()` FØR den gren, ikke som en ny aftaletype. Se `docs/superpowers/specs/2026-09-10-ot-extra-alle-timer-design.md`.

**Regler:** erstatter (lægger ikke oveni) de normale tidstillæg; INTET dagligt loft (fuld kode 1 for alle arbejdstimer); gælder alle dage inkl. søndag/helligdag/1. maj/Grundlovsdag; kode 8 (OT 1-3) gives ALDRIG, kun kode 1 + kode 9 (Øvrig overtid); kode 4/63 (`compute_sh_hours()`) er upåvirket og uændret.

**Implementering:** `override_ot_extra_alle_timer(result, is_special_day, rates)` i `overtime.py` – post-processing-funktion der nulstiller `ot_before_hours`/`ot_13_hours` og sætter enten `sh_kode9_hours=total_hours` (særdag) eller `ot_extra_hours=total_hours` + genberegner `supplements[OT_EXTRA_KEY]` (almindelig dag). `by_date`-bucket'ene (Lønafregning) opdateres samtidig. Kaldes fra `_calculate_employee()` (payroll_router.py, linje ~591/599/630/640) – slår automatisk igennem alle forbrugere: lønkørsel-preview, prøvekørsel, PDF-timesedler, Lønafregning, Danløn CSV.

**Frontend:** checkbox `emp-ot-extra-alle-timer` i `modal-employee` (samme mønster som `emp-afloeser`/`emp-fast-bil`), label "Særaftale: Øvrig overtid for alle timer". Ingen ny permission – gates af `manage_employees`/`stamdata` som resten af modalen.

---

## Overnatning over en periode (2026-09-16, activities.py + app.js)
- `_all_dates(start, end)` (activities.py, ved siden af `_weekday_dates`) – alle kalenderdage inkl.
  weekend/helligdage. `_COUNT_BASED_RANGE_TYPES = {"overnatning", "dob_overnatning"}`.
- `update_absence_group_dates()` bruger `_all_dates()` i stedet for `_weekday_dates()` for disse to
  typer, og opretter tilføjede dage med `start_time == end_time == midnat` (ingen timeberegning) i
  stedet for at kalde `_range_day_defaults()`.
- Frontend: overnatnings-grenen i `confirmManualActivity()` (app.js) har nu sin egen periode-gren
  (adskilt fra `_RANGE_TYPES`/`isRange`-mekanismen ferie m.fl. bruger) – ingen krav om
  registreringsnummer, alle kalenderdage medtages, ét DOB-flueben gælder hele perioden.
  `getAllDates(from, to)` ved siden af `getWeekdayDates()`.
- `saveAbsencePeriodDates()` genkender nu gruppens `activity_type` og bruger `getAllDates` +
  bredere overlapskontrol for overnatnings-grupper ved efterfølgende periode-redigering.
- Se `docs/superpowers/specs/2026-09-16-overnatning-periode-design.md` for fulde designbeslutninger.

## Flere biler på én vagt (2026-09-30, ddd_parser.py + vehicle_uses.py + overtime.py + day_type.py + payroll_router.py + payroll_settlement_router.py + activities.py + app.js)
- **Parser:** `_extract_vehicle_uses()` (strengere end `_extract_vehicle_usage_records()`): codePage-byte 1-16 (filtrerer forskudte læsninger som "M23112"), Gen1-poster foretrækkes; Gen2-poster (efterfulgt af 17-tegns VIN) kun på datoer uden Gen1-poster. `_lookup_vehicle_uses()` klipper til vagten, afrunder til hele minutter → `ParsedActivity.vehicle_uses`.
- **Hovedbilen** (`vehicle_registration`/`vehicle_number`, flest timer) er UÆNDRET → vagtplan, PDF-timeseddel og Danløn-CSV er upåvirkede (brugerkrav).
- **Import:** `_vehicle_uses_json()` i `import_ddd.py`; gemmes ved oprettelse, rettes ved genimport uanset status. Split kopierer listen.
- **`calculators/vehicle_uses.py`:** `clipped_vehicle_uses(act)` (klip til aktivitetens tider), `vehicle_assignment_intervals()` = nærmeste-bil-reglen (før første → første, hul → forrige, efter sidste → sidste; None ved én bil).
- **Beregning:** `calculate_overtime/calculate_flat_hours/calculate_special_day_overtime(..., vehicle_intervals=)` → `OvertimeResult.by_date_vehicle[(dato, reg)]`. Selve beregningen kører på de uændrede segmenter; `_allocate_to_vehicles()` fordeler bagefter kronologisk (første bil forbruger loftet først) → totalen ændres ALDRIG (test: `test_vehicle_split_never_changes_employee_total`).
- **Lønafregning:** `_calculate_employee()` lægger `by_vehicle` på dags-indgangen (vognnummer slås op i Vognpark ved beregning, tomt hvis bilen ikke findes); `_expand_day()` bruger `by_vehicle` før `by_date`; rækken får `vehicle_times` (vises IKKE – kun vognnummer i kolonnen, bekræftet af bruger 2026-09-30). Lønafregning-CSV får samme rækker (ingen ny kolonne).
- **Aktivitet:** `ActivityResponse.vehicle_uses` (kun ved ≥2 biler) → modal viser "Biler på vagten" mellem KM-felterne og Salttillæg; vognnummer-dropdown erstattes af skjult tomt felt, og `PATCH` afviser ændret `vehicle_number` (400).
- Tests: `tests/test_multi_vehicle.py`.

---

## Rettigheder håndhæves i backend (2026-09-30, auth.py + session.py + activities.py + employees.py + vehicles.py + vagtplan_comments.py + stamdata.py + app.js)
- **Engangstildeling:** `_grant_permissions_once(key, perms, role_name=None, lonbogholder_only=False)` i `session.py` + tabel `applied_permission_grants` (model `AppliedPermissionGrant`). Alle `_ensure_*_permission()` går gennem den → en rettighed fjernet af en admin kommer ikke igen ved genstart (før blev 5 rettigheder genindsat på ALLE roller hver nat). Nye tildelinger: tilføj en `_ensure_x()` med ny unik key og kald den i `init_db()`.
- **Ny permission `edit_activities`** ("Redigér aktiviteter", `auth.py` + `PERMISSION_LABELS`/`DESCRIPTIONS` i app.js), tildelt alle roller én gang (`_ensure_edit_activities_permission()`).
- **`_require_activity_permission(db, user, a, perm)`** (activities.py): `approve_activities` på approve/deactivate/DELETE/reopen (+ `auto-approve-pending` via `_has_activity_permission`); `edit_activities` på PATCH, undo-edit, undo-split, split, correct-segment, correct-all-segments, resize-segment, POST (ikke source=vagtplan) og PATCH absence-group (ikke vagtplan-perioder). Undtagelse: `source=vagtplan` + `_has_vagtplan_edit_access()`. Tests slår tjekket fra via autouse-fixture i `tests/conftest.py` – markér tests af selve tjekket `@pytest.mark.real_activity_permissions`.
- **`require_any_permission(*perms)`** (auth.py): GET activities/{id}/springer-flags/absence-group = `view_calendar|vagtplan_view`; GET `/api/employees` + `/{id}` og GET `/api/vehicles` = én af en række skærm-rettigheder (se `_employee_list_access`/`_vehicle_list_access`). `_visible_response()` sætter `_PRIVATE_EMPLOYEE_FIELDS` (kort, adresse, postnr., e-mail, telefon, mobil, hourly_rate, cvr_number) til None uden `view_employees`/`manage_employees`.
- Øvrige: GET vagtplan-comments = `vagtplan_view`; hide-from-vagtplan = vagtplan-redigeringsret; anciennitet-/§56-alerts + dismiss = `anciennitet_alert`/`paragraf_56_alert`; GET `/api/stamdata/holidays` = kun login (alle skal se helligdage). Kun login: agreement-types/-kinds, dispatcher-groups, absence-types, period-info, locked-dates, auto-approval/settings.
- **Frontend:** `_hasPerm()`, `_canActivity(a, perm)` (spejler backend inkl. vagtplan-undtagelsen), `_editLocked(a)` (låst periode ELLER mangler edit) styrer knapper i `openActivityDetail()`, `renderActionBtns()`, `renderSegmentTable()`; `confirmApprove()` springer PATCH over når `_editLocked`. "+ Tilføj aktivitet" og Aktiviteter-menupunktet har `data-perm-require` (edit_activities/view_calendar); `_firstPermittedView()` vælger startside; `applyRoleVisibility()` skjuler tomme menugrupper; Stamdata ligger ikke længere bag `user_management`.

## Øvrige rettelser 2026-09-30
- **Tømte felter:** `update_employee` tømmer `_CLEARABLE_EMPLOYEE_FIELDS` (kort, initialer, adresse, postnr., e-mail, telefon, mobil) når de sendes som null; `update_activity` tømmer km_start/km_end/vehicle_number (vognnr. ikke når `a.vehicle_uses` findes – tomt betyder dér "uændret"). `exclude_none` bevarer stadig felter der ikke sendes.
- **Split** bevarer segmenternes 4. element (rettet type) – før ValueError ved "Ret til andet arbejde" + split.
- **Lønkørsel "I alt" = Lønafregning:** `settlement_total_kr(calc, days=None)` i `payroll_settlement_router.py` bruges af både `_employee_settlement_data()` og `payroll_preview()` (lazy import) → `grand_total_kr` i preview-svaret. `totals["ferie"]` → `ferie_hours` (kun visning, ikke i CSV). app.js viser Ferie-linje og Afspadsering med sats. PDF-timesedlen er bevidst uændret (ingen Ferie).

## Medarbejderregister (2026-10-01, employees.py + stamdata.py + utils/employee_rules.py + models.py + session.py + app.js)
Spec: `docs/superpowers/specs/2026-10-01-medarbejderregister.md`. Funktionær = `agreement_kind == "funktionaer"` (`FUNKTIONAER`), chauffør = alt andet.
- **Nye kolonner** på `employees`: `position_id` (FK `master_positions`), `seniority_date`, `cpr_number`, `elev`/`elev_start_date`/`elev_end_date`, `personaleforening` (model-default True, migrering 0), `natarbejde_tillaeg`. Ny model `MasterPosition(id, name UNIQUE)`.
- **Validering:** `_validate_employee_fields(db, kind, values, check)` – Stilling+Email altid, Initialer (funktionær) / Førerkort (chauffør), elev-datoer. Kun felter i `check` (ved PATCH = `model_fields_set`). Klient: `confirmEmployee()`.
- **CPR:** `validate_cpr()`/`cpr_birthdate()`/`mask_cpr()`/`is_masked_cpr()` i `employee_rules.py`. `_apply_cpr_mask()` uden `view_cpr`; maskeret værdi i PATCH = uændret. `cpr_number` er i `_PRIVATE_EMPLOYEE_FIELDS`.
- **Endpoints:** `GET /api/employees/next-employee-number` (`next_employee_number()`, ≥34000 +1), `GET /check-number?number&exclude_id`, `GET /positions` (`_employee_list_access`), `GET /milestone-alerts` + `POST /{id}/dismiss-milestone-alert` (alert_key fx `birthday_40`/`jubilee_25`/`elev_ÅÅÅÅ-MM-DD`, gemt i `Paragraf56AlertDismissal`), `POST /export-xlsx` (body `employee_ids` i klientens rækkefølge, `employee_export`). Stamdata: `GET/POST/PATCH/DELETE /api/stamdata/positions` (sletning afvist hvis i brug).
- **§56-reset:** ændret §56-slutdato sletter nu kun dismissals med `alert_type in ("upcoming","expired")`.
- **Nye permissions:** `view_cpr`, `jubilee_alert`, `elev_alert`, `birthday_alert`, `employee_table_view`, `employee_export` – kun admin (ingen `_ensure_*`).
- **Frontend:** `_filteredEmployees()` (søgning inkl. `_normalizePhone()`, filtre stilling/personaleforening/natarbejde/elev), `renderEmployeeList()` liste/tabel (`_EMP_TABLE_COLUMNS`, `sortEmployeeTable()`, localStorage `employeeViewMode`), `exportEmployeesXlsx()`, `checkEmployeeNumber()`, `_showEmpHiddenFlags()`/`confirmEmpHiddenFlags()` (modal `modal-emp-hidden-flags`), `checkMilestoneAlerts()` (modal `modal-milestone-alert`; både OK og Luk afviser, × lukker kun), `loadStamdataPositions()`. Elev-farve: `isElev()`, `empCellHighlight()` → `elev-highlight` (#fff3b8), avatar #e0a800, tabel `elev-row`. Felter kun for chauffører har klassen `emp-driver-only`.
- **Kommentar-mærke** (`.comment-note` i `renderCellActivity()`) vises ikke for split-delenes automatiske kommentar "Split: første/anden del".

---

## Vigtige mønstre

### Tilføj ny modal-knap-handling
1. HTML: tilføj knap i modal-footer med `onclick="minFunktion()"`
2. JS: skriv `async function minFunktion()` med `POST(...)` + `toast(...)` + `closeAllModals()` + `refreshActivities()`

### Tilføj nyt aktivitetsfelt
1. `models.py`: ny `Column`
2. `schemas.py`: tilføj til `ActivityResponse` + `ActivityCreate`/`ActivityUpdate`
3. `activities.py` `_to_response()`: map feltet
4. `index.html`: vis i modal-activity-body
5. `app.js`: rediger/opret-logik

### Genstart-frit (kun JS/HTML)
Ændringer i `app.js`/`index.html` kræver kun browser-refresh (`app.js` cache-buster er automatisk).  
Ændringer i `style.css` kræver ALTID at versionsnummeret i `index.html` (`style.css?v=N`) bumpes manuelt – ellers cacher browsere den gamle fil.  
Ændringer i `.py`-filer: stop server, ryd `__pycache__`, genstart.

### Deaktiver knap + advarsel ved klik (i stedet for `disabled`-attribut)
Når en handling skal blokeres MED forklaring (ikke bare forsvinde): brug en CSS-klasse (fx `btn-muted`, se `style.css`) i stedet for `disabled`-attributten – en reelt `disabled` knap sender ikke klik-events, så en `toast()`-advarsel kan ikke vises. Mønster: `renderX()` sætter `btn.classList.toggle("btn-muted", betingelse)`, og handler-funktionen selv (fx `exportCsv()`) tjekker betingelsen først og kalder `toast(...)` + `return` før resten af logikken. Eksempel: "Kør løn"-knappen (`btn-koer-loen`) er nedtonet og viser en advarsel, hvis perioden allerede er låst (`state.periodClosed`) eller der er afventende aktiviteter (`state.hasUnresolvedPending`) – se `renderPayrollPreview()` og `exportCsv()` i `app.js`. Server-siden validerer det samme uafhængigt (`export_csv_post()` i `payroll_router.py`) som forsvar i dybden.

### Naturlig sortering af disponentgrupper (2026-09-29)
Disponentgrupper sorteres "naturligt" (0, 00, 000, 1, 2 … 10 – ikke 1, 10, 2). Backend: `utils/natural_sort.py` → `natural_key()`, brugt i `GET /api/employees/dispatcher-groups`, `GET /api/stamdata/dispatcher-groups` og fraværsoversigtens eksport-options (`absence_overview_router.py`). Frontend: `naturalCompare()` øverst i `app.js` (ved `jq`) til steder der selv sorterer. Nye lister over disponentgrupper skal bruge disse – ikke `order_by(DispatcherGroup.name)` eller `localeCompare`.
