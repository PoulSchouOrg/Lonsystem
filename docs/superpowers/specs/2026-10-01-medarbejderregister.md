# Spec: Udvidet medarbejderregister

**Kilde:** `Medarbejder registeret i PS Løn.docx` (TO-BE-afsnittet) + afklaringer med Sofie 2026-10-01
**Dato:** 2026-10-01
**Status:** GODKENDT og IMPLEMENTERET 2026-10-01 (commit 017d5ca). Afvigelse: Excel-eksporten er `POST /api/employees/export-xlsx` med `employee_ids` i klientens rækkefølge (ikke GET med filtre). Plan: `docs/superpowers/plans/2026-10-01-medarbejderregister.md`.

---

## 1. Overblik

| # | Funktion | Kort |
|---|---|---|
| 1 | Lønnummer-generator | Forslag = højeste lønnummer (≥ 34000) + 1, kan overskrives, dublettjek |
| 2 | Felter – funktionærer | Nye: Stilling*, Anciennitetsdato, CPR, Personaleforening. Ændret: Initialer*, Email (Poulschou)*. Skjules: Afløser, Fast bil, Særaftale |
| 3 | Felter – chauffører | Nye: Stilling*, Anciennitetsdato, CPR, Elev (+start/slut*), Personaleforening, Natarbejdetillæg. Ændret: Email (Privat)*, Førerkortnummer* |
| 4 | Stamdata-fane "Stillinger" | Opret/redigér/slet valgmuligheder til feltet Stilling |
| 5 | Advarsler | Nye: jubilæum 25/40/50 år, elev slutter, rund fødselsdag – hver med egen rettighed. 9-mdr. og §56 uændret |
| 6 | Søgning | Også på telefon- og mobilnummer |
| 7 | Filtre | Nye: Stilling, Personaleforening, Natarbejdetillæg, Elev |
| 8 | Visning | Listen viser "Lønnr. · Stilling", elev-farve, tabelvisning (rettighed), Excel-eksport (rettighed) |
| 9 | CPR-beskyttelse | Ny rettighed "Se CPR-nummer". Uden den maskeres de sidste 4 cifre |

**Definition:** "Funktionær" = `agreement_kind == "funktionaer"`. "Chauffør" = alle andre aftaletyper (i dag `hourly_fixed`, `hourly_flexible`).

---

## 2. Lønnummer-generator

### Adfærd
- Når "+ Opret medarbejder" åbnes, udfyldes **Lønnummer** automatisk med et forslag. Forslaget kan overskrives manuelt.
- **Forslag = højeste numeriske lønnummer ≥ 34000, plus 1.** Huller udfyldes ikke: er 34637 og 34640 taget, foreslås 34641.
- Når 34999 er brugt, fortsætter forslaget bare med 35000, 35001 osv.
- Ignoreres: ikke-numeriske numre (fx `TEST998`) og numre under 34000 (fx 33425, 1234).
- Både aktive og inaktive medarbejdere tæller med.
- Findes der intet nummer ≥ 34000, foreslås 34000.

### Dublettjek
- Findes allerede på serveren (`create_employee` giver fejl ved dublet).
- Nyt: et **live-tjek i modalen**. Når lønnummerfeltet forlades, spørges serveren, og der vises en rød besked under feltet, fx *"Lønnummer 34625 bruges allerede af Alexander B. Knudsen"*. Der kan ikke gemmes, så længe nummeret er taget.
- Gælder både ved opret og redigér. Ved redigér tæller medarbejderen selv ikke med.

### Teknik
- `GET /api/employees/next-employee-number` → `{ "suggestion": "34629" }` (rettighed `manage_employees`).
- `GET /api/employees/check-number?number=…&exclude_id=…` → `{ "taken": true, "employee_name": "…" }` (rettighed `manage_employees`).

---

## 3. Felter pr. medarbejdertype

### 3.1 Feltmatrix (fremtidig tilstand)

`*` = påkrævet. `–` = skjult for typen.

| Felt | Funktionær | Chauffør | Status |
|---|---|---|---|
| Aftale | * | * | |
| Overenskomsttype | – | * | uændret |
| Disponentgruppe | ja | ja | |
| Vognnummer ved fravær | * | * | |
| Lønnummer | * | * | + generator |
| Førerkortnummer | – | * | **bliver påkrævet** |
| Stilling | * | * | **NY** |
| Initialer | * | ja | **bliver påkrævet for funktionær** |
| Fornavn / Efternavn | * | * | |
| Adresse / Postnummer | ja | ja | |
| Email | * – label **"Email (Poulschou)"** | * – label **"Email (Privat)"** | samme felt som i dag, omdøbes + bliver påkrævet |
| Telefon / Mobil | ja | ja | |
| Ansættelsesdato | * | * | |
| Fratrædelsesdato | ja | ja | |
| Anciennitetsdato | ja (må være tom) | ja (må være tom) | **NY** |
| CPR-nummer | ja | ja | **NY** |
| Aktiv | ☑ | ☑ | |
| Fuldlønnet | ☑ | ☑ | |
| Elev | – | ☐ (+ Start/Slutdato*) | **NY** |
| §56 | ☐ | ☐ | uændret |
| Medlem af Personaleforening | ☑ | ☑ | **NY** |
| Afløser | – | ☐ | **skjules for funktionær** |
| Fast bil | – | ☐ | **skjules for funktionær** |
| Særaftale: Øvrig overtid for alle timer | – | ☐ | **skjules for funktionær** |
| Natarbejdetillæg | – | ☐ | **NY** |
| Timefordeling | ja | ja | |

### 3.2 Detaljer pr. felt

**Stilling**
- Dropdown med værdier fra stamdata-fanen "Stillinger" (afsnit 4). Listen er fælles for funktionærer og chauffører.
- DB: `employees.position_id` (FK → `master_positions`, nullable i DB).

**Påkrævede felter og eksisterende medarbejdere**
- Det gælder Stilling, Initialer (funktionær), Email og Førerkortnummer (chauffør).
- Ingen eksisterende medarbejder bliver ugyldig. Reglerne håndhæves først, næste gang medarbejderen gemmes.

**Initialer**
- Påkrævet for funktionærer. Ellers uændret: uppercase, max 10 tegn.

**Email**
- Samme DB-felt som i dag (`employees.email`). Labelen skifter efter type, og feltet bliver påkrævet.
- Ingen kontrol af domænet.
- Al eksisterende brug, fx afsendelse af timesedler, er uændret.

**Førerkortnummer**
- Påkrævet, når Aftale ≠ Funktionær. Skjult og ikke påkrævet for funktionærer.

**Anciennitetsdato**
- Dato-felt med dt-picker, som ansættelse og fratrædelse. Må være tom.
- DB: `employees.seniority_date` (Date, nullable).
- Bruges **kun** til jubilæumsadvarslen.
- Påvirker ikke 9-måneders-advarslen, "mdr. anciennitet" eller satser. De regner fortsat fra ansættelsesdato.

**CPR-nummer**
- Tekstfelt i formatet `ddmmåå-xxxx`.
- Validering: 6 cifre, bindestreg, 4 cifre, og de første 6 cifre skal være en gyldig dato. Ingen modulus-11-kontrol.
- Fødselsåret udledes efter den officielle regel: 7. ciffer + årstal giver 1800-, 1900- eller 2000-tallet.
- DB: `employees.cpr_number` (String, nullable).
- CPR er unikt i virkeligheden, men der laves **intet unikhedstjek** og ingen DB-constraint.
- Adgang til CPR: se afsnit 9.

**Elev (kun chauffør)**
- Afkrydsning, default ikke afkrydset.
- Når den er afkrydset, vises **Elev startdato\*** og **Elev slutdato\***. Slutdato må ikke ligge før startdato (samme mønster som §56).
- DB: `employees.elev` (Bool, default False), `elev_start_date` og `elev_end_date` (Date, nullable).
- Ingen lønmæssig effekt. Elev bruges kun til advarsel (afsnit 5), filter (afsnit 7) og farvemarkering (afsnit 8.4).

**Medlem af Personaleforening (begge typer)**
- Afkrydsning. Default afkrydset ved **oprettelse af nye** medarbejdere.
- DB: `employees.personaleforening` (Bool).
- Eksisterende medarbejdere sættes **ikke** automatisk som medlem. Ved migreringen får de ikke afkrydset og kan rettes manuelt.

**Natarbejdetillæg (kun chauffør)**
- Afkrydsning, default ikke afkrydset.
- DB: `employees.natarbejde_tillaeg` (Bool, default False).
- Ingen beregningseffekt. Bruges kun til filter og tabel.

### 3.3 Skjulte felter ved typeskift
- Felter, der ikke gælder for typen, **skjules kun**. Den gemte værdi bevares, så den er der igen, hvis man skifter tilbage.
- Det gælder Førerkortnummer, Elev med datoer, Natarbejdetillæg, Afløser, Fast bil og Særaftale for funktionærer, og Overenskomsttype som i dag.
- Et påkrævet felt, der er skjult, er **ikke påkrævet**. Det gælder på både klient og server, fx Førerkortnummer og Elev-datoer for funktionærer.
- **Skjulte flag ved skift til funktionær:** gemmes en medarbejder som funktionær, mens en eller flere af **Afløser**, **Fast bil** og **Særaftale: Øvrig overtid for alle timer** stadig er afkrydset fra chauffør-tiden, vises en popup før gem.
  - Popup'en lister de afkrydsede flag, hver med valget **Behold** / **Fjern**, fx *"[Navn] har stadig følgende markeringer fra chauffør-tiden: …"*.
  - Fjern sætter flaget til false. For Fast bil nulstilles også den tilknyttede bil. Behold gemmer uændret.
- Overenskomsttype bliver i dag tømt for typer, der ikke kræver den (`onAgreementKindChange()` og serveren sætter `""`). Den adfærd er uændret, da Overenskomsttype styrer satsen.

### 3.4 Validering
Påkrævet-reglerne håndhæves både i `confirmEmployee()` (klient) og i `create_employee`/`update_employee` (server).

---

## 4. Stamdata-fane "Stillinger"

- Ny fane i Stamdata, samme mønster som Fraværstyper og CVR-nummer.
- Fanen har en tabel med **Navn**, en Rediger-knap, en Slet-knap og "+ Tilføj stilling".
- Tabel: `master_positions(id, name UNIQUE)`. Der er ingen aktiv/inaktiv-markering, så en stilling slettes, når den ikke skal bruges mere. Stillingerne vises alfabetisk både i stamdata og i dropdown'en.
- Endpoints: `GET/POST/PATCH/DELETE /api/stamdata/positions`.
  - Ændringer audit-logges med `log_action`.
  - Ændringer kræver rettigheden `stamdata`, som de øvrige faner.
  - Læsning (GET) er tilladt for alle, der kan se medarbejderregisteret, fordi filter og dropdown skal bruge listen.
- Sletning afvises, hvis stillingen bruges af en medarbejder. Fejlbeskeden viser antallet.

---

## 5. Advarsler

Samme mekanisme som i dag: popup-modal efter login. Den viser første advarsel + "+ N flere" og har knapperne "Gå til medarbejder" og "OK".

| Advarsel | Udløses | Rettighed | Status |
|---|---|---|---|
| 9 måneders anciennitet (chauffør) | som i dag | `anciennitet_alert` | uændret |
| §56 udløber | som i dag | `paragraf_56_alert` | uændret |
| Jubilæum 25, 40 og 50 år | 1 måned før. Regnes fra Anciennitetsdato hvis udfyldt, ellers Ansættelsesdato | NY `jubilee_alert` "Jubilæumsadvarsel" | ny |
| Elev slutter | 1 måned før `elev_end_date` | NY `elev_alert` "Elevadvarsel" | ny |
| Rund fødselsdag | 1 måned før. Fødselsdato fra CPR. Alle runde: 10, 20, 30, 40, 50, 60 … | NY `birthday_alert` "Fødselsdagsadvarsel" | ny |

Fælles regler for de tre nye advarsler:
- Kun aktive medarbejdere. Elev-advarslen gælder kun, når Elev er afkrydset.
- Vinduet er **fra og med samme dato måneden før til og med selve dagen**. Fx vises en fødselsdag den 15/11 fra den 15/10.
- **Er dagen overskredet, kommer der ingen popup.**
- **Når en bruger har klikket "OK", kommer advarslen ikke igen for den bruger.** Afvisningen er pr. bruger.
  - Den gemmes i den eksisterende tabel `Paragraf56AlertDismissal` (unik på medarbejder + bruger + `alert_type`). Tabellen genbruges med nye `alert_type`-værdier.
  - Afvisningen gælder én konkret begivenhed, fx "40-års fødselsdag" eller "25-års jubilæum". Næste runde fødselsdag eller jubilæum giver derfor en ny advarsel.
  - `alert_type` indeholder begivenheden, fx `birthday_40` eller `jubilee_25`. Elev-advarslen indeholder slutdatoen, så den kommer igen, hvis slutdatoen ændres.
- Fødselsdagsadvarslen beregnes på serveren ud fra det fulde CPR, så den også virker for brugere uden "Se CPR-nummer". CPR vises ikke i popup'en.
- **Rettigheder:** Kun admin har dem fra start. Admin har implicit alle rettigheder, så ingen andre roller tildeles noget automatisk. Rettighederne kan slås til i brugerstyring.

---

## 6. Søgning

- Søgefeltet matcher i dag navn og lønnummer. Det udvides til også at matche **Telefon** og **Mobil**.
- Mellemrum og `+45` ignoreres ved sammenligningen, så en søgning på "12345678" finder "+45 12 34 56 78".
- Placeholder: "Søg navn, lønnr. eller telefon…".

---

## 7. Filtre

Ud over de eksisterende "Afdeling" og "Vis inaktive" kommer nye dropdowns i værktøjslinjen:

| Filter | Valg |
|---|---|
| Stilling | Alle stillinger / Ingen stilling / hver stilling fra stamdata (som Disponentgruppe) |
| Personaleforening | Alle / Medlem / Ikke medlem |
| Natarbejdetillæg | Alle / Ja / Nej |
| Elev | Alle / Elev / Ikke elev |

Filtrene virker i både liste- og tabelvisning. Excel-eksporten indeholder præcis det, der vises.

---

## 8. Visning

### 8.1 Listevisning
- Linjen under navnet bliver `Lønnr. 34625 · Chauffør`, hvor sidste del er stillingens navn. Den udelades, hvis der ikke er en stilling.
- Overenskomst, timeløn og ansættelsesdato er allerede fjernet (2026-10-01).

### 8.2 Tabelvisning (ny)
- En knap i værktøjslinjen skifter mellem **Liste** og **Tabel**. Valget huskes pr. bruger i browseren (`localStorage`).
- Knappen vises kun med den nye rettighed `employee_table_view` "Tabelvisning af medarbejdere". Kun admin har den fra start.
- Kolonner:

| Lønnummer | Navn | Fuldlønnet | Natarbejdetillæg | Stilling | Disponentgruppe | Ansættelsesdato | Telefon | Mobil | Email | Elev |
|---|---|---|---|---|---|---|---|---|---|---|
| | | ✓ / – | ✓ / – | | | | | | | Ja (01.08.2026–31.07.2029) / Nej |

- Man sorterer ved at klikke på kolonneoverskriften.
- Klik på en række åbner redigér, hvis brugeren har `manage_employees`, som i listen.
- CPR vises ikke.

### 8.3 Excel-eksport (ny)
- Knappen "Eksportér til Excel" vises i tabelvisningen, kun med den nye rettighed `employee_export` "Eksportér medarbejderregister". Kun admin har den fra start.
- `GET /api/employees/export-xlsx?…filtre…` bygger en `.xlsx` med openpyxl, som fraværsoversigten. Filen hentes direkte i browseren som `Medarbejderregister_ÅÅÅÅ-MM-DD.xlsx`.
- Kolonnerne er de samme som i tabellen, men Elev deles i tre: Elev (Ja/Nej), Elev start og Elev slut.
- Eksporten følger de aktuelle filtre, søgningen og sorteringen.
- **CPR kommer ikke med.**
- Eksporten audit-logges.

### 8.4 Farvemarkering af elever
- Afløsere er i dag markeret tre steder:
  - avataren i medarbejderlisten (`--accent` `#78b21a`)
  - navnecellen i Vagtplan (`#d4edcc`, klassen `afloeser-highlight`)
  - navnecellen i Aktivitetskalenderen (samme klasse)
- Elever markeres de samme tre steder med en **anden lysegrøn farve**, så man kan skelne dem fra afløsere. Tabelvisningen markerer elev-rækker i samme farve.
- **Besluttet 2026-10-01:**
  - gul til elever: celle `#fff3b8`, avatar `#e0a800`
  - afløsere beholder deres grønne `#d4edcc` / `#78b21a`
- Er en medarbejder både elev og afløser, vises elev-farven.
- Kun når Elev er afkrydset og medarbejderen er chauffør.

---

## 9. CPR-beskyttelse

- Ny rettighed `view_cpr` "Se CPR-nummer". Kun admin har den fra start.
- Alle med `manage_employees` kan **indtaste og overskrive** CPR på en medarbejder.
- Kun brugere med `view_cpr` får det fulde CPR fra serveren. Alle andre får det maskeret som `120385-****`. Maskeringen sker på serveren, så de sidste fire cifre aldrig sendes til browseren.
- Har brugeren `manage_employees` men ikke `view_cpr`, vises feltet maskeret i modalen:
  - Gemmes der uden at ændre feltet, bevares det gemte CPR.
  - Skrives et nyt, fuldt CPR, overskrives det.
- Uden `view_employees`/`manage_employees` returneres CPR slet ikke. Feltet tilføjes `_PRIVATE_EMPLOYEE_FIELDS`.
- CPR vises ikke i tabelvisningen og kommer ikke med i Excel-eksporten.

---

## 10. Nye rettigheder (samlet)

| Nøgle | Label | Fra start |
|---|---|---|
| `view_cpr` | Se CPR-nummer | kun admin |
| `jubilee_alert` | Jubilæumsadvarsel | kun admin |
| `elev_alert` | Elevadvarsel | kun admin |
| `birthday_alert` | Fødselsdagsadvarsel | kun admin |
| `employee_table_view` | Tabelvisning af medarbejdere | kun admin |
| `employee_export` | Eksportér medarbejderregister | kun admin |

Rettighederne tilføjes `ALL_PERMISSIONS` (auth.py) og `PERMISSION_LABELS`/`PERMISSION_DESCRIPTIONS` (app.js).

---

## 11. Berørte filer (forventet)

| Fil | Ændring |
|---|---|
| `app/database/models.py` | nye kolonner, `MasterPosition` |
| `app/database/session.py` | `_migrate()` ALTER TABLE, `personaleforening` = 0 for eksisterende |
| `app/database/schemas.py` | Create, Update og Response |
| `app/routers/employees.py` | validering pr. type, generator, nummertjek, CPR-maskering, nye advarsler, eksport |
| `app/routers/stamdata.py` | CRUD for Stillinger |
| `app/auth.py` | nye rettigheder |
| `app/templates/index.html` | modal-felter, stamdata-fane, værktøjslinje, tabel, advarselsmodal |
| `app/static/js/app.js` | alt frontend inkl. elev-farve i vagtplan og aktivitetskalender |
| `app/static/css/style.css` | `elev-highlight` |
| `tests/` | generator, CPR-validering og -maskering, advarselsvinduer og -afvisning, påkrævede felter pr. type, rettigheder, eksport |
| `docs/build_docs.py`, `CODEREF.md`, `docs/DATA_MODEL.md` | dokumentation |

Fejl fundet undervejs, **rettet 2026-10-01**: `onAgreementKindChange()` ledte efter checkboksene `#emp-dispatcher-groups`, som ikke findes. Den bruger nu `<select id="emp-dispatcher-group">`, så nye funktionærer får "0 - Kontor" forvalgt.
