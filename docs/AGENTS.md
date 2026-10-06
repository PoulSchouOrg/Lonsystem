# AI Agent Context – Lønsystem

Dette dokument er til brug for AI-agenter der arbejder på lønsystemet. Det giver et hurtigt overblik over systemet, regler og kodebasen.

---

## Hvad er systemet?

Et webbaseret lønsystem til behandling af tachografdata (.ddd-filer) og lønberegning for lastbilchauffører under **Transport- og Logistikoverenskomsten 2025-2028** (DIO I (ATL) / 3F).

**CVR-nummer:** 13246505

---

## Teknologistack

| Komponent | Teknologi |
|-----------|-----------|
| Backend | Python 3.11+ / FastAPI |
| Database | SQLite (WAL-mode) |
| Frontend | HTML + Vanilla JS + CSS / Jinja2 |
| .ddd-parsing | Selvskrevet binær parser, ingen ekstern pakke (`app/parsers/ddd_parser.py`) |
| Excel-output | openpyxl |
| CSV-output | Python stdlib |

---

## Vigtige regler

### Lønperioder
- Altid præcis **14 dage**, mandag-søndag
- Starter ikke nødvendigvis d. 1. i måneden
- Beregnes fra et fast anker (mandag 1/6-2026) med 14-dages modulo – IKKE "næste hverdag efter forrige periode"
- Systemet udleder automatisk lønperiode fra valgt dato

### Effektiv arbejdstid
- **Total tid fra start til slut** (sluttid minus starttid)
- Inkluderer rådighedstid, hvil, kørsel, andet arbejde
- Inkluderer manuelt tastede pålæsnings-/aflæsningstider

### Minimum 4-timer regel
- Vagter under 4 timer → forbliver `pending` (🔵 Blå) med advarselsikon, kræver manuel godkendelse
- Godkendelse kræver initialer og begrundelse

### Overtime (se `OVERTIME_RULES.md` – opdateret 2026-07-02)
- Tidlig overarbejde: kl. 05:00–06:00 → +44,54 kr./time (fortærer IKKE normaltids-loftet)
- Normalt overarbejde (op til 3 t i kl. 06-18/18-21): +44,54 kr./time
- Ekstra overarbejde (nat 21-05, samt over 3 t): +109,40 kr./time
- Registreret normaltid (7/7,5/8 t) kan kun forbruges i tidsrummet 06-18; loftet deles pr. dag på tværs af flere aktiviteter, og hører til vagten (kan krydse midnat) medmindre vagten starter på en søndag/helligdag
- Søndage/helligdage: al kørt tid → kode 1 + kode 9, uanset tidspunkt. Lørdag har INGEN særregel – regnes altid som en normal hverdag med lørdagens eget (typisk 0) loft

### Ubekvem tid – UDGÅET (erstattet 10/6-2026)
Var oprindeligt +46,93 kr./time (18-23) og +52,65 kr./time (23-06), men er fuldstændigt
erstattet af de tre overtidstillæg beskrevet ovenfor under "Overtime". Findes IKKE i den
nuværende kode.

### Anciennitet
- Automatisk tæller fra ansættelsesdato
- 9 måneder → pop-up ved programopstart hvis løngruppe ikke opdateret

---

## Farvestatus for aktiviteter (bjælker)

| Farve | Status | Betydning |
|-------|--------|------------|
| 🔴 Rød | `deactivated` | Kræver handling (split eller deaktivering) |
| 🟢 Grøn | `approved` | Godkendt af medarbejder med initialer |
| 🔵 Blå | `pending` | Ikke godkendt endnu, men data OK |

Alle bjælker skal være 🟢 grønne eller 🔴 røde (ikke 🔵 blå/`pending`) før "Kør løn" er aktiv.

---

## Aktivitet (bjælke) – vigtige felter

- `source`: `tachograph` eller `manual` – manuelle vises med `(K)` prefix
- `parent_activity_id` + `split_part`: bruges ved split af aktivitet
- Split: den oprindelige aktivitet deaktiveres; del 1 og del 2 oprettes som nye, begge afventende (skal godkendes hver for sig)

---

## CSV til Danløn

Kolonner (6 felter, semikolon-separeret): CVR (13246505), medarbejdernr, Danløn-kode, antal (timer/antal), sats, total. Sats/total er valgfrie pr. løntype – se `docs/aendringer-danloen.md` for det præcise, gældende format (bl.a. hvornår afsluttende semikolon skrives).

Medarbejdere med `agreement_kind == "funktionaer"` udelades af Danløn-CSV'en (`_build_danloen_csv`), men vises stadig i Lønkørsel, Lønafregning og Fraværsoversigt (2026-10-06).

**Danløn-koder er ikke længere hardkodede.** De konfigureres pr. løntype i Stamdata → Løntypekoder (`master_pay_types`, DB er authoritative). Ved allerførste seeding sættes de fleste standardkoder dog stadig til placeholder-værdien `"1"` (`calculators/pay_rates.py: DANLOEN_CODE_*`), fordi de rigtige koder ikke var kendt da systemet blev bygget – de skal derfor gennemgås og rettes i Stamdata pr. installation før produktionsbrug. Undtaget er søgnehelligdagskoderne (4/63) og feriefri-koden for fuldlønnede (5), som er reelle koder fra start.

---

## Medarbejdertyper

Der er ikke længere en fast type-enum (`trainee`/`driver`/`driver_senior`/`driver_qualified` +
`qualification_allowance` findes ikke i koden). I stedet har `Employee` en Stamdata-styret
`agreement_kind` (systemnøgler `hourly_fixed`/`hourly_flexible`, de eneste to overtidsberegningen
kender) samt en fritekst `agreement_type` med tilhørende timesats fra Excel/Stamdata
("Overenskomsttyper og timesatser.xlsx"). Nye aftaletyper kan tilføjes via Stamdata → "Aftale".

---

## Filstruktur

```
Lønsystem/
├── CODEREF.md               ← kode-referenceguide (rodmappen)
├── docs/
│   ├── AGENTS.md            ← dette dokument
│   ├── REQUIREMENTS.md      ← fuld kravspecifikation
│   ├── ARCHITECTURE.md      ← teknisk arkitektur
│   ├── DATA_MODEL.md        ← databasemodel
│   ├── PAYROLL_RULES.md     ← lønberegningsregler
│   ├── OVERTIME_RULES.md    ← overtidsregler
│   └── DDD_FORMAT.md        ← .ddd filformat
└── app/
    ├── main.py               ← FastAPI app
    ├── database/
    ├── parsers/
    ├── calculators/
    ├── exporters/
    ├── routers/
    ├── static/
    └── templates/
```

---

## Åbne spørgsmål (spørg bruger – gæt aldrig)

Følgende er stadig reelt uafklarede/miljøspecifikke punkter. Se `deploy/PRODUKTION_OPSAETNING.md`
for hvordan de faktisk besvares på den konkrete produktionsserver (IP/port/backup/autostart er
alle løst der, blot ikke hardkodet nogen steder i kildekoden):

- Serverens konkrete IP/hostname og port ved en ny installation (default port 8000, men den
  faktiske IP er miljøspecifik).
- Om `.ddd`-inputmappen og output-mapperne på en given installation skal justeres væk fra
  standardplaceringen (`app/ddd_input/`, `app/output/`).

Følgende er AFKLARET og skal ikke længere gættes på eller genåbnes:

- Danløn-koder konfigureres pr. løntype i Stamdata → Løntypekoder, ikke hardkodet – se afsnittet "CSV til Danløn" ovenfor.
- .ddd-parsing bruger en selvskrevet binær parser (`app/parsers/ddd_parser.py`), intet eksternt bibliotek.
- Overtid beregnes dagligt for `hourly_fixed`-medarbejdere og ugentligt (37t+5t, fælles pulje mandag–søndag) for `hourly_flexible`-medarbejdere – se `docs/OVERTIME_RULES.md`.
- Afspadsering indgår i CSV'en under sin egen løntypekode (AFSPADSERING), konfigureret som alle andre løntyper i Stamdata.
