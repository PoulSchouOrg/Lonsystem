# Dagsplan

## Baggrund

I dag foregår den daglige fordeling af vogne til chauffører manuelt i et Excel-ark
uden for lønsystemet: en liste af vogne/type, hvem der kører hvilken vogn, hvilken
opgave, samt en samlet chaufførliste der viser hvem der er fraværende. Denne
ændring bygger en digital "Dagsplan"-side, der dækker samme behov og kobler sig
til de data, der allerede findes i systemet (medarbejdere, vognpark, vagtplan/
fravær, aktivitetsoversigt).

Kilde: `Dagsplan i PS Løn.docx` (indeholder også et skærmbillede af det nuværende
Excel-ark som reference).

## Omfang

- Ny sidebar-side "Dagsplan" med to underfaner: "Dagsplan" og "Materiel fravær"
  (samme fane-mønster som Stamdata).
- Ny persisteret dag-for-dag tildeling af chauffør/opgave pr. vogn.
- Ny "Fast bil"-indstilling pr. medarbejder, der foreslår en standardtildeling.
- Nyt "materielt fravær"-begreb pr. vogn (periode med kommentar).
- Nye felter på `Vehicle`: `description`, `dispatcher_group_id`.
- Kobling til Aktivitetsoversigten: autoudfyldning af vognnummer ved oprettelse
  af en "normal tid"-aktivitet, samt en advarsel ved uoverensstemmelse.
- To nye permissions: `dagsplan_view`, `dagsplan_edit`.

## Datamodel

### `Vehicle` (nye felter)
| Felt | Type | Bemærk |
|---|---|---|
| `description` | Text, nullable | "Beskrivelse" – vises i Dagsplan kol. 2 |
| `dispatcher_group_id` | Integer FK → `dispatcher_groups.id`, nullable | Ny, separat relation (mange vogne → én gruppe). Erstatter IKKE det eksisterende `DispatcherGroup.vehicle_id` (én "standardvogn" pr. gruppe, fortsat brugt uændret til autoudfyld af vognnummer ved oprettelse af fraværstype-aktiviteter). De to felter løser hver sin opgave og lever side om side. |

Sættes/redigeres i den eksisterende Vognpark-sides opret/rediger-vogn-modal
(kræver fortsat `manage_vehicles`, uændret). `create_vehicle`/`update_vehicle`
afviser et ukendt `dispatcher_group_id` med 400 ("Ukendt disponentgruppe-id:
{id}"). *(Tilføjet efter implementering.)*

**`Vehicle.fast_bil_employee_name`** *(tilføjet efter implementering, ikke i
oprindeligt design):* beregnet property (ikke en DB-kolonne) – kommasepareret
liste af navne på medarbejdere der har denne vogn som `fast_bil_vehicle_id`
(håndterer det usandsynlige tilfælde at flere medarbejdere deler samme faste
vogn). Eksponeres på `VehicleResponse` og vises read-only i
Vognpark-modalen (`#vehicle-fast-bil-employee`) sammen med vognens
disponentgruppe (`#vehicle-fast-bil-group`) – se "Vognpark-siden" nedenfor.

### `Employee` (nye felter)
| Felt | Type | Bemærk |
|---|---|---|
| `fast_bil` | Boolean, default false | Krydsfelt i medarbejder-modalen |
| `fast_bil_vehicle_id` | Integer FK → `vehicles.id`, nullable | Kun udfyldt/relevant hvis `fast_bil=true`. Vognvalget er IKKE begrænset til medarbejderens egen disponentgruppe – alle vogne i vognparken kan vælges. |

`create_employee`/`update_employee` afviser et ukendt `fast_bil_vehicle_id`
med 400 ("Ukendt vogn-id: {id}"). `EmployeeResponse` medtager desuden det
afledte felt `fast_bil_vehicle_number` (vognens nummer, opslået server-side)
til at forudfylde søgefeltet i medarbejder-modalen uden en ekstra
frontend-lookup. *(Begge tilføjet efter implementering.)*

### Ny tabel `daily_plan_assignments`
| Felt | Type | Bemærk |
|---|---|---|
| `id` | Integer PK | |
| `date` | Date | |
| `vehicle_id` | Integer FK → `vehicles.id` | |
| `employee_id` | Integer FK → `employees.id`, nullable | Tom række (vogn uden chauffør den dag) er gyldig |
| `task` | String, nullable | "Opgave" |
| `informed` | Boolean, default false | "Chauffør informeret" |
| `created_at`/`updated_at` | DateTime | |

`UniqueConstraint(date, vehicle_id)` – én tildeling pr. vogn pr. dag (upsert).

**"EKSTRA"-rækkerne** (10 stk., til hjælp på pladsen/lærlinge) indgår ALDRIG i
autoudfyldningen af vognnummer på aktiviteter (der er intet rigtigt vognnummer
at udfylde med). *(Opdateret 2026-09-09: de persisteres nu også, i egen tabel
`daily_plan_extra_assignments` – se nedenfor. Oprindeligt var beslutningen at
de KUN skulle leve i frontend-state og nulstilles ved datoskift; brugeren bad
efterfølgende om at få dem gemt, så man kan se dem igen senere.)*

En medarbejder der forsøges tildelt en vogn/EKSTRA-plads, mens vedkommende
allerede har en anden effektiv tildeling samme dag, får en advarsel (409 med en
menneskelæsbar besked) i stedet for at blive blokeret – bekræfter brugeren,
gennemføres dobbelttildelingen alligevel. Samme mønster bruges til at advare,
hvis medarbejderen har registreret fravær den dag. *(Tilføjet 2026-09-09 efter
brugerønske – oprindeligt var her slet ingen validering.)*

**Præcisering (tilføjet efter implementering):** konflikttjekket
(`_conflicting_assignment_label()`) dækker alle fire kombinationer – vogn↔vogn,
vogn↔EKSTRA-plads, EKSTRA-plads↔vogn og EKSTRA-plads↔EKSTRA-plads – og
sammenligner mod den *effektive* tildeling (en gemt `daily_plan_assignment`
ELLER medarbejderens "Fast bil"-standard, ikke kun gemte rækker). Beskeden
navngiver konfliktkilden som "vogn {nummer}" eller "EKSTRA-plads {slot}".
Bekræftelsen sendes som `force: true` i PATCH-body'en (se endpoints nedenfor)
for at omgå både dobbelttildelings- og fraværsadvarslen.

### Ny tabel `vehicle_absences` (materielt fravær)
| Felt | Type | Bemærk |
|---|---|---|
| `id` | Integer PK | |
| `vehicle_id` | Integer FK → `vehicles.id` | |
| `date_from` | Date | |
| `date_to` | Date, nullable | `null` = samme dag som `date_from` (étdags-fravær) |
| `comment` | Text | Årsag/beskrivelse |
| `created_by` | String, nullable | Initialer |
| `created_at` | DateTime | |

En vogn regnes som materielt fraværende på dato `d`, hvis der findes en række
hvor `date_from <= d <= (date_to ?? date_from)`.

### Migration
Idempotent kolonnetilføjelse i `session.py`s `_migrate()` (samme mønster som
øvrige kolonner: `PRAGMA table_info` + `ALTER TABLE ADD COLUMN` hvis kolonnen
mangler) for `Vehicle`/`Employee`-felterne, samt oprettelse af de to nye tabeller
ved `Base.metadata.create_all` (som resten af skemaet).

## Backend

### Nye permissions (samme mønster som `absence_overview`/`toggle_springer`)
- `dagsplan_view` – se Dagsplan-siden (begge underfaner), read-only.
- `dagsplan_edit` – redigere tildelinger, afkrydse "informeret", melde/fjerne
  materielt fravær.

`admin` får dem automatisk som systemrolle (systemroller får ALLE permissions
ubetinget – ingen særlig kobling til disse to). Øvrige roller tildeles dem ikke
som default, men kan gives det via rolle-editoren.

**Rettelse (afviger fra oprindeligt design):** permissionerne seedes IKKE
idempotent ved opstart, i modsætning til hvad der oprindeligt var planlagt her
(der findes ingen `_ensure_dagsplan_permissions()`-funktion i `session.py`,
svarende til fx `_ensure_vagtplan_permissions()`). De to nøgler
(`dagsplan_view`/`dagsplan_edit`) findes udelukkende som statiske entries i
`ALL_PERMISSIONS`-dictet i `auth.py` – der er intet at migrere, da ikke-system-
roller uden dem blot mangler dem indtil en admin tildeler dem manuelt via
rolle-editoren.

### `GET /api/dagsplan?date=YYYY-MM-DD`
Kræver `dagsplan_view`. Ét samlet svar for hele dagsvisningen:

- `vehicles`: liste sorteret efter vognnummer – for hver vogn: `vehicle_number`,
  `description`, `dispatcher_group_id`, evt. tildeling (`employee_id`, `task`,
  `informed`), og – hvis en medarbejder er tildelt – et `mismatch_vehicle_number`
  felt (se nedenfor). Vogne med aktivt materielt fravær den dag markeres med
  `absent: true`.
- `employees`: den fulde medarbejderliste (alle aktive medarbejdere, samme
  grundmængde som Aktivitetsoversigten – IKKE påvirket af nedenstående filtre),
  hver med en farvestatus (`assigned` grøn / `absent` rød / `none` grå /
  `comment_only` gul – forrang: gul > rød > grøn > grå, jf. kravet om at forblive
  gul selv når medarbejderen er skrevet i chauffør-kolonnen) og evt. fraværstekst
  (type-label eller vagtplan-kommentar).
- `extra_rows` *(tilføjet efter implementering, ikke i oprindeligt design):* de
  10 faste EKSTRA-pladser (slot 1-10), hver med `slot`, `employee_id`,
  `employee_name`, `task`, `informed` – ingen `vehicle`/`absent`/`mismatch`-felter,
  da en EKSTRA-plads ikke er en rigtig vogn. Altid ufiltreret, ligesom
  `employees`. En medarbejder tildelt en EKSTRA-plads tæller også som `assigned`
  (grøn) i medarbejderlistens farvestatus.

Disponentgruppe- og medarbejder-filtrering sker på query-parametre
(`dispatcher_group_id?`, `employee_id?`) og påvirker KUN `vehicles`-listen –
`employees`-listen returneres altid ufiltreret.

**Mismatch-beregning:** for hver tildelt medarbejder slås dagens `normal`-type
aktiviteter op (samme dato som `date`). Findes mindst én med et `vehicle_number`
der afviger fra den tildelte vogns `vehicle_number`, sættes
`mismatch_vehicle_number` til den afvigende værdi (bruges til advarselstrekant +
tooltip "vognnummer i løn: xxx" i frontend). Andre aktivitetstyper (fravær)
indgår ikke i denne sammenligning.

### `PATCH /api/dagsplan/assignment`
Kræver `dagsplan_edit`. Body: `{date, vehicle_id, employee_id?, task?,
informed?, force?}`. Upsert på `(date, vehicle_id)`. `force: bool = false`
*(tilføjet efter implementering, ikke i oprindeligt design)* – sæt til `true`
for at gennemføre en tildeling på trods af den dobbelttildelings-/
fraværsadvarsel der ellers returneres som 409 (se "Ny tabel
`daily_plan_assignments`" ovenfor).

### `PATCH /api/dagsplan/extra-assignment`
*(Manglede i det oprindelige design – tilføjet sammen med at EKSTRA-rækkerne
blev gjort persisterede 2026-09-09.)* Kræver `dagsplan_edit`. Body: `{date,
slot, employee_id?, task?, informed?, force?}`, `slot` valideret til 1-10.
Upsert på `(date, slot)` i `daily_plan_extra_assignments`. Samme `force`-flag
og samme konflikttjek som `/assignment` (se ovenfor).

### `POST /api/vehicle-absences`
Kræver `dagsplan_edit`. Body: `{vehicle_id, date_from, date_to?, comment}`.

### `DELETE /api/vehicle-absences/{id}`
Kræver `dagsplan_edit`.

### `GET /api/vehicle-absences?date=YYYY-MM-DD`
Kræver `dagsplan_view`. Liste over materielt fravær der er aktivt på den angivne
dato (bruges af "Materiel fravær"-underfanen, som deler valgt dato med
"Dagsplan"-fanen – ingen egen datonavigation).

### `vehicles.py`
`VehicleCreate`/`VehicleUpdate`/`VehicleResponse` udvides med
`description`/`dispatcher_group_id` (+ `fast_bil_employee_name` på
`VehicleResponse`, se Datamodel ovenfor). Uændret permission
(`manage_vehicles`). `dispatcher_group_id` valideres til at pege på en
eksisterende gruppe (400 ellers, se Datamodel).

### `employees.py`
`EmployeeCreate`/`EmployeeUpdate`/`EmployeeResponse` udvides med
`fast_bil`/`fast_bil_vehicle_id` (+ det afledte `fast_bil_vehicle_number` på
`EmployeeResponse`, se Datamodel ovenfor). `fast_bil_vehicle_id` valideres til
at pege på en eksisterende vogn (400 ellers).

### Autoudfyld ved oprettelse af manuel aktivitet (`create_manual_activity`, `activities.py`)
Hvis `activity_type == "normal"` og request-body'ens `vehicle_number` er tomt:
slå den EFFEKTIVE vogn op for `(employee_id, start_time.date())` via
`effective_vehicle_for_employee()` (`calculators/dagsplan_helpers.py`) – samme
regel som Dagsplan-tabellen selv bruger: en gemt `daily_plan_assignment` for
dagen, og ELLERS medarbejderens "Fast bil" (`fast_bil_vehicle_id`), hvis sat.
*(Rettelse: det oprindelige design nævnte kun opslag i `daily_plan_assignments`
– Fast bil-fallbacket blev tilføjet under implementeringen og er dækket af
`tests/test_dagsplan_activity_autofill.py`.)* Gælder KUN "normal tid" – den
eksisterende disponentgruppe-baserede autoudfyldning for fraværstyper
(`applyDispatcherGroupVehicleDefault()` i frontend) er uændret og upåvirket.

## Frontend (`app.js` + `index.html`)

### Sidebar
Ny post `data-view="dagsplan"` med `data-perm-require="dagsplan_view"`. Placeret
sidst i "Løn"-sidebargruppen, lige efter "Vagtplan" – IKKE mellem to punkter i
samme flade liste som først antaget: "Importer .ddd" er første punkt i den
efterfølgende gruppe "Registre", altså visuelt lige under, men i en anden
sidebar-sektion.

### Fanestruktur
To underfaner på Dagsplan-siden (samme tab-switch-mønster som Stamdata):
"Dagsplan" og "Materiel fravær". Begge deler samme valgte dato (ét
state-felt, fx `state.dagsplan.date`).

### Underfane "Dagsplan"
- Topbar: dato-navigation (◀ / date-picker / ▶, default dags dato), overskrift
  "Dagsplan – d. [dato]", disponentgruppe-filter, medarbejder-filter (søgbar) –
  begge filtre påvirker kun hovedtabellen.
- Hovedtabel (5 kolonner): Vognnummer | Beskrivelse | Chauffør (søgbar
  select/combobox, samme mønster som andre medarbejder-søgefelter i appen) |
  Opgave (tekstfelt) | Informeret (checkbox). Efterfulgt af 10 faste
  "EKSTRA"-rækker (ingen beskrivelse, samme redigerbare felter, men INGEN
  persistering og INGEN vognnummer-autoudfyldning ved brug).
  - Er medarbejderens `fast_bil_vehicle_id` sat, foreslås vedkommende som
    default chauffør på den vogns række (kan altid ændres). Har medarbejderen
    fravær den dag, vises vedkommende stadig på sin faste vogn, men rødt.
  - Ved `mismatch_vehicle_number`: ⚠️-ikon ved chaufførnavnet, tooltip
    "vognnummer i løn: {mismatch_vehicle_number}".
  - Vogne med `absent: true` (materielt fravær) vises rødt.
- Sideliste (separat lille tabel ved siden af, ALDRIG påvirket af filtrene): den
  fulde medarbejderliste, farvekodet, med fraværstekst.
- Uden `dagsplan_edit`: samme visning, men alle inputs/knapper er
  read-only/deaktiverede (samme mønster som andre steder i appen –
  `data-perm-require`/`btn-muted`).

**Kobling til Aktivitetsoversigten (tilføjet efter implementering):**
`applyDagsplanVehicleDefault()` i `app.js` er et selvstændigt, klient-side
modstykke til backend-autoudfyldningen ovenfor – kaldes når den manuelle
aktivitets-formular åbnes/opdateres (medarbejder eller dato ændres) og henter
`GET /api/dagsplan?date=...&employee_id=...` for at forudfylde
vognnummer-feltet i UI'et FØR selve oprettelsen sendes. No-op'er stille ved
manglende `dagsplan_view`-rettighed eller fejlet kald – samme mønster som
`applyDispatcherGroupVehicleDefault()` for fraværstyper.

### Underfane "Materiel fravær"
- "Meld materielt fravær"-knap (kræver `dagsplan_edit`) → modal: vognvalg,
  "Fra dato" (default: fanens valgte dato), "Til dato" (valgfri – tom betyder
  étdags-fravær), kommentar.
- Tabel over dagens meldte fravær: Vognnummer | Periode | Kommentar, med en
  slet-knap (kræver `dagsplan_edit`).

### Vognpark-siden (`data-view="vehicles"`, eksisterende)
Opret/rediger-vogn-modalen udvides med "Beskrivelse" (tekstfelt) og
disponentgruppe (samme dropdown-mønster som medarbejder-modalens
disponentgruppe-felt). Uændret permission (`manage_vehicles`).

**Read-only Fast bil-visning (tilføjet efter implementering, ikke i
oprindeligt design):** modalen viser desuden to read-only felter –
`#vehicle-fast-bil-employee` (fra `VehicleResponse.fast_bil_employee_name`) og
`#vehicle-fast-bil-group` – så man kan se, uden at forlade Vognpark-siden,
hvilken medarbejder der evt. har denne vogn som fast bil, og hvilken
disponentgruppe vognen tilhører.

### Medarbejder-modalen (`modal-employee`, eksisterende)
Nyt "Fast bil"-krydsfelt; når krydset, vises et søgbart vognnummer-felt
(`fast_bil_vehicle_id`), ubegrænset af disponentgruppe.

## Tests
Fordelt over seks filer i stedet for én samlet `test_dagsplan.py`:
`test_dagsplan_router.py`, `test_dagsplan_datamodel.py`,
`test_dagsplan_activity_autofill.py`, `test_dagsplan_permission_keys.py`,
`test_employee_fast_bil_endpoint.py`, `test_vehicle_dispatcher_group_field.py`.

- `daily_plan_assignments`/`daily_plan_extra_assignments`: upsert (opret +
  opdater eksisterende), unik pr. (date, vehicle_id) hhv. (date, slot),
  `slot`-validering (1-10).
- `vehicle_absences`: opret med/uden `date_to`, korrekt "aktiv på dato"-logik,
  sletning.
- Konflikttjek: alle fire kombinationer vogn↔vogn/EKSTRA, inkl. "Fast bil" som
  konfliktkilde (ikke kun gemte tildelinger), samt at `force: true` omgår
  advarslen.
- Autoudfyld: `create_manual_activity` udfylder vognnummer for "normal tid" fra
  dagens EFFEKTIVE tildeling (gemt tildeling ELLER Fast bil), rører IKKE ved
  fraværstyper, overskriver ALDRIG et allerede udfyldt vognnummer.
- `GET /api/dagsplan`: filtrering påvirker kun `vehicles`, aldrig
  `employees`/`extra_rows`; mismatch-felt sættes korrekt ved afvigende
  vognnummer på en "normal tid"-aktivitet; farveprioritet (gul > rød > grøn >
  grå) på medarbejderlisten; medarbejderlisten ekskluderer medarbejdere uden en
  synlig disponentgruppe (samme grundmængde som Aktivitetsoversigten).
- 400-validering: ukendt `dispatcher_group_id` (vogn) og ukendt
  `fast_bil_vehicle_id` (medarbejder) afvises.
- `fast_bil_employee_name`: korrekt (inkl. flere medarbejdere på samme vogn).

**Ikke dækket (bevidst, samme konvention som fx `test_employee_supplements.py`):**
Permission-håndhævelse af `dagsplan_view`/`dagsplan_edit` er IKKE testet –
`test_dagsplan_router.py` kalder route-funktionerne direkte og springer
dermed FastAPIs `Depends()`-injektion over. `test_dagsplan_permission_keys.py`
tjekker kun at de to nøgler findes i `ALL_PERMISSIONS`, ikke at de håndhæves.
Det oprindelige design antog fejlagtigt at håndhævelse var testdækket.

## Ændringer 2026-10-08 (bekræftet af bruger)

1. **Autoudfyld = Dagsplanens regel.** `effective_vehicle_for_employee()` bruger kun
   Vognpark-markerede, ikke-slettede vogne, og Fast bil foreslås ikke, hvis vognen
   har en gemt tildeling den dag (givet til en anden eller ryddet).
2. **Overnatning (inkl. DOB) er ikke fravær** i Dagsplanen – ingen rød farve og
   ingen fraværsadvarsel. Fraværsoversigten er uændret.
3. **⚠️** vises, hvis *nogen* anden bil end den tildelte er kørt på dagens normal
   tid-vagter (flere biler tjekkes via `vehicle_uses`); deaktiverede aktiviteter
   tæller ikke med.
4. **Sletning af vogn er blød** (`Vehicle.deleted_at`). Brug i ulåst lønperiode
   → advarsel, sletning tilladt ved bekræftelse; vognnummeret står som død tekst
   på vagter (låste og ulåste), i Lønafregning og i historiske Dagsplan-rækker/
   materielt fravær. Fast bil, vognnummer ved fravær og standardvogn nulstilles;
   fremtidige tildelinger/fravær fjernes. Genbruges nummerpladen, omdøbes den
   slettede vogns plade.
5. **Fast bil kræver aktiv medarbejder.**
6. **Chaufførlister ens:** sideliste og chauffør-vælger viser aktive
   ikke-funktionærer i disponentgrupper med det nye flueben "Medtag i Dagsplan"
   (Stamdata → Disponentgrupper; eksisterende grupper = Nej). Erstatter filteret
   på "Vis i aktivitetsoversigt".
7. **Permission-håndhævelse testes** over HTTP
   (`tests/test_dagsplan_permission_enforcement.py`) – afsnittet "Ikke dækket"
   ovenfor gælder ikke længere.
9. **Afdelingsfilteret** på Dagsplan-fanen viser kun disponentgrupper med
   "Medtag i Dagsplan".
10. **Vogntype-filter** (afkrydsning, flere valg): Forvogn (Beskrivelse starter
    med F eller M), Trækker (T), Ladbil (L), Øvrige (alt andet/tom). Store/små
    bogstaver og mellemrum foran ignoreres. Intet afkrydset = alle vises. Med
    filter vises EKSTRA-linjer kun med en vogn, der passer. Kun frontend.
    Afdeling og vogntype **lægges sammen** (Storkran + Trækker = alle Storkrans
    vogne + alle trækkere); medarbejderfilteret skal altid passe.
11. **Opgavefeltet** ombryder lang tekst (rækken bliver højere); Enter gemmer.

8. **Vogn på EKSTRA-linjer.** Linjen forbliver EKSTRA, men der kan for den valgte
   dag vælges en vogn uden Vognpark-flueben (`daily_plan_extra_assignments.vehicle_id`).
   Beskrivelsen følger med, og vognens faste chauffør skrives på linjen. Vognen
   bruges kun til ⚠️-advarslen – ikke til autoudfyld af vognnummer eller materielt
   fravær. Samme vogn på to EKSTRA-linjer samme dag giver en advarsel. Fjernes
   vognen igen, fjernes chaufføren også, og linjen bliver grå.

## Ikke omfattet
- Ingen ændring af den eksisterende disponentgruppe-baserede
  autoudfyldning for fraværstyper.
- Ingen tilbagevirkende migrering/gruppering af historiske Excel-data.
- "EKSTRA"-rækkerne indgår ikke i nogen lønberegning eller
  vognnummer-autoudfyldning (kun i "Fast bil"/rigtige vogne).
