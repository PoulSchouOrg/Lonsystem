"""
Bygger Teknisk dokumentation.docx og Brugervejledning.docx til Lønsystemet.
Kør med: python build_docs.py
"""
from pathlib import Path
from datetime import datetime
from docx import Document
from docx.shared import Pt, Cm, RGBColor, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_ALIGN_VERTICAL
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
import copy

OUT = Path(__file__).parent

_DANSKE_MAANEDER = [
    "Januar", "Februar", "Marts", "April", "Maj", "Juni",
    "Juli", "August", "September", "Oktober", "November", "December",
]


def genereringsdato() -> str:
    """Forsidedato = det faktiske tidspunkt scriptet køres, ikke en hardkodet værdi.
    Dokumenterne opdateres løbende, så coverdatoen skal altid afspejle seneste regenerering."""
    now = datetime.now()
    return f"{_DANSKE_MAANEDER[now.month - 1]} {now.year}"

DARK_BLUE = RGBColor(0x1B, 0x3A, 0x6B)
MID_BLUE  = RGBColor(0x2E, 0x6D, 0xB8)
LIGHT_BLUE = RGBColor(0xD5, 0xE8, 0xF5)
GRAY      = RGBColor(0x60, 0x60, 0x60)
WHITE     = RGBColor(0xFF, 0xFF, 0xFF)
BLACK     = RGBColor(0x00, 0x00, 0x00)


# ─── helpers ───────────────────────────────────────────────────────────────

def set_cell_bg(cell, hex_color: str):
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_color)
    tcPr.append(shd)


def set_cell_borders(cell, color="CCCCCC"):
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    tcBorders = OxmlElement("w:tcBorders")
    for side in ("top", "left", "bottom", "right"):
        el = OxmlElement(f"w:{side}")
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), "4")
        el.set(qn("w:color"), color)
        tcBorders.append(el)
    tcPr.append(tcBorders)


def add_run(para, text, bold=False, italic=False, color=None, size=None):
    run = para.add_run(text)
    run.bold = bold
    run.italic = italic
    if color:
        run.font.color.rgb = color
    if size:
        run.font.size = Pt(size)
    run.font.name = "Arial"
    return run


def heading(doc, text, level=1, num=None):
    p = doc.add_paragraph(style=f"Heading {level}")
    p.paragraph_format.space_before = Pt(18 if level == 1 else 10)
    p.paragraph_format.space_after  = Pt(6)
    label = f"{num}  " if num else ""
    run = p.add_run(label + text)
    run.font.name = "Arial"
    run.font.bold = True
    run.font.size = Pt(16 if level == 1 else 13 if level == 2 else 11)
    run.font.color.rgb = DARK_BLUE if level == 1 else MID_BLUE if level == 2 else BLACK
    return p


def body(doc, text, space_after=6):
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(space_after)
    r = p.add_run(text)
    r.font.name = "Arial"
    r.font.size = Pt(11)
    return p


def bullet(doc, text, bold_prefix=None):
    p = doc.add_paragraph(style="List Bullet")
    p.paragraph_format.space_after = Pt(2)
    p.paragraph_format.left_indent = Cm(0.8)
    if bold_prefix:
        rb = p.add_run(bold_prefix)
        rb.bold = True
        rb.font.name = "Arial"
        rb.font.size = Pt(11)
        r = p.add_run(text)
    else:
        r = p.add_run(text)
    r.font.name = "Arial"
    r.font.size = Pt(11)
    return p


def cover(doc, title, subtitle, date_str):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(80)
    p.paragraph_format.space_after  = Pt(4)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run(title)
    r.font.name = "Arial"
    r.font.bold = True
    r.font.size = Pt(28)
    r.font.color.rgb = DARK_BLUE

    p2 = doc.add_paragraph()
    p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p2.paragraph_format.space_after = Pt(6)
    r2 = p2.add_run(subtitle)
    r2.font.name = "Arial"
    r2.font.size = Pt(14)
    r2.font.color.rgb = MID_BLUE

    p3 = doc.add_paragraph()
    p3.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p3.paragraph_format.space_before = Pt(60)
    r3 = p3.add_run("Poul Schou A/S  ·  CVR 13246505")
    r3.font.name = "Arial"
    r3.font.size = Pt(11)
    r3.font.color.rgb = GRAY

    p4 = doc.add_paragraph()
    p4.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r4 = p4.add_run(date_str)
    r4.font.name = "Arial"
    r4.font.size = Pt(11)
    r4.font.color.rgb = GRAY

    doc.add_page_break()


def two_col_table(doc, rows, col1_w=Cm(5), col2_w=Cm(11.5)):
    tbl = doc.add_table(rows=0, cols=2)
    tbl.style = "Table Grid"
    for label, val in rows:
        row = tbl.add_row()
        c0, c1 = row.cells[0], row.cells[1]
        set_cell_bg(c0, "D5E8F5")
        set_cell_borders(c0, "9BBDD6")
        set_cell_borders(c1, "9BBDD6")
        c0.width = col1_w
        c1.width = col2_w
        p0 = c0.paragraphs[0]
        r0 = p0.add_run(label)
        r0.bold = True; r0.font.name = "Arial"; r0.font.size = Pt(10)
        p1 = c1.paragraphs[0]
        r1 = p1.add_run(val)
        r1.font.name = "Arial"; r1.font.size = Pt(10)
    doc.add_paragraph()


def header_table(doc, headers, rows, col_widths=None):
    ncols = len(headers)
    tbl = doc.add_table(rows=1, cols=ncols)
    tbl.style = "Table Grid"
    hdr_row = tbl.rows[0]
    for i, h in enumerate(headers):
        cell = hdr_row.cells[i]
        set_cell_bg(cell, "1B3A6B")
        p = cell.paragraphs[0]
        r = p.add_run(h)
        r.bold = True; r.font.name = "Arial"; r.font.size = Pt(10)
        r.font.color.rgb = WHITE
    for row_data in rows:
        row = tbl.add_row()
        for i, val in enumerate(row_data):
            cell = row.cells[i]
            set_cell_borders(cell)
            p = cell.paragraphs[0]
            r = p.add_run(str(val))
            r.font.name = "Arial"; r.font.size = Pt(10)
    doc.add_paragraph()


def note_box(doc, text, label="OBS"):
    p = doc.add_paragraph()
    p.paragraph_format.left_indent  = Cm(0.5)
    p.paragraph_format.right_indent = Cm(0.5)
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after  = Pt(8)
    rb = p.add_run(f"{label}: ")
    rb.bold = True; rb.font.name = "Arial"; rb.font.size = Pt(11)
    rb.font.color.rgb = MID_BLUE
    r = p.add_run(text)
    r.font.name = "Arial"; r.font.size = Pt(11)
    r.font.color.rgb = GRAY
    return p


# ══════════════════════════════════════════════════════════════════════════════
#  TEKNISK DOKUMENTATION
# ══════════════════════════════════════════════════════════════════════════════

def build_teknisk():
    doc = Document()

    # Sider og margener
    for section in doc.sections:
        section.page_width  = Cm(21)
        section.page_height = Cm(29.7)
        section.left_margin = section.right_margin = Cm(2.5)
        section.top_margin  = section.bottom_margin = Cm(2.5)

    # Forside
    cover(doc, "Lønsystem", "Teknisk dokumentation", genereringsdato())

    # ── 1. Systemarkitektur ────────────────────────────────────────────────
    heading(doc, "Systemarkitektur", 1, "1")
    body(doc, (
        "Lønsystemet er en webbaseret applikation til registrering og lønberegning for "
        "lastbilchauffører hos Poul Schou A/S. Systemet kører på én central server og "
        "tilgås via en webbrowser på det lokale netværk."
    ))

    heading(doc, "Teknologistack", 2, "1.1")
    header_table(doc,
        ["Komponent", "Teknologi", "Formål"],
        [
            ["Backend", "Python 3.13 + FastAPI", "REST-API, forretningslogik, filgenerering"],
            ["Database", "SQLite (WAL-mode)", "Vedvarende lagring af medarbejder- og aktivitetsdata"],
            ["Frontend", "HTML5 + Vanilla JavaScript + CSS", "Brugerflade – ét HTML-dokument"],
            ["Server", "Uvicorn (ASGI)", "Serverer FastAPI-applikationen"],
            ["PDF-generering", "ReportLab", "Timesedler til medarbejdere"],
            ["Excel-generering", "openpyxl", "Prøvekørsel og satser"],
            ["Filparsing", "Binær parsing (ingen eksternt bibliotek)", "Indlæsning af .ddd tachografdata"],
        ],
        [Cm(3), Cm(5), Cm(8.5)]
    )

    heading(doc, "Autentificering", 2, "1.2")
    body(doc, (
        "Login foregår på to måder, begge understøttet samtidig: almindeligt login med "
        "initialer + adgangskode (SessionMiddleware, session-cookie med 24 timers levetid), "
        "eller 'Log ind med Microsoft' via Microsoft Entra ID (SSO). SSO verificerer et "
        "id_token mod Entra ID's egen JWKS-nøgle og matcher herefter brugerens UPN "
        "case-insensitivt mod AppUser.email – der oprettes IKKE en ny bruger automatisk ved "
        "første SSO-login, brugeren skal allerede findes i systemet med den korrekte "
        "mailadresse udfyldt."
    ))
    note_box(doc,
        "SSO kræver ingen særskilt tilladelse ud over at være en oprettet, aktiv bruger. "
        "Login-endepunktet (POST /api/auth/login) er derudover rate-begrænset til 5 forsøg "
        "pr. IP-adresse pr. 60 sekunder for at modvirke brute-force-angreb.",
        "TEKNISK NOTE"
    )

    heading(doc, "Mappestruktur", 2, "1.3")
    body(doc, "Projektmappen er organiseret i fire hoveddele:")
    two_col_table(doc, [
        ["app/",          "Al Python-kode, statiske filer, database og Excel-satser"],
        ["docs/",         "Projektdokumentation (.md-filer og denne fil)"],
        ["præsentation/", "Præsentationsbygger og slides (til intern brug)"],
        ["Rodmappen",     "Brugerdokumenter: overenskomst-PDF, kravdokument, statusmøde-pptx m.m."],
    ])

    heading(doc, "Centrale filer i app/", 2, "1.4")
    two_col_table(doc, [
        ["main.py",                   "Applikationens indgangspunkt. Registrerer alle routere, monterer statiske filer og serverer index.html med cache-busting."],
        ["routers/activities.py",     "API-endepunkter for aktivitetshåndtering (opret, godkend, ret, opdel, fortryd)."],
        ["routers/employees.py",      "API-endepunkter for medarbejderstamdata og overenskomsttyper."],
        ["routers/payroll_router.py", "Lønkørsel: preview, prøvekørsel (Excel), Danløn CSV og PDF-timesedler."],
        ["routers/import_ddd.py",     "Import af .ddd-filer via fildialoger (tkinter) og batch-import."],
        ["calculators/overtime.py",   "Overtids- og tillægsberegning pr. aktivitet."],
        ["calculators/rates_loader.py","Indlæser timesatser og overtidssatser fra DB (Stamdata). Excel-funktioner bruges kun som fallback ved tom DB."],
        ["routers/stamdata.py",       "CRUD-endepunkter for stamdata: overenskomsttyper, overtidssatser, tillæg, løntypekoder og fraværstyper. Kræver 'stamdata'-rettighed."],
        ["calculators/pay_period.py", "Beregner og opretter 14-dages lønperioder."],
        ["database/models.py",        "SQLAlchemy-modeller (Employee, Activity, PayPeriod m.fl.)."],
        ["database/schemas.py",       "Pydantic-skemaer til validering af API-input og -output."],
        ["parsers/ddd_parser.py",     "Binær parser for EU-tachografdata (.ddd-format)."],
        ["templates/index.html",      "Hele frontend-applikationen (ét HTML-dokument)."],
        ["static/js/app.js",          "JavaScript-applikationslogik (~5540 linjer)."],
    ])

    # ── 2. Databasemodel ──────────────────────────────────────────────────
    doc.add_page_break()
    heading(doc, "Databasemodel", 1, "2")
    body(doc, (
        "Databasen er SQLite og oprettes automatisk ved første opstart. WAL-mode "
        "(Write-Ahead Logging) aktiveres, så flere samtidige læsere kan tilgå databasen "
        "mens en skrivning foregår."
    ))

    heading(doc, "Employee – medarbejdere", 2, "2.1")
    header_table(doc,
        ["Felt", "Type", "Beskrivelse"],
        [
            ["employee_number",       "String (unik)",   "Lønnummer – primær identifikator i lønsystemet"],
            ["tachograph_card_number","String (unik)",   "EU-førerkortnummer – bruges til at matche .ddd-filer"],
            ["first_name / last_name","String",          "Navn"],
            ["address / postal_code", "String (opt.)",   "Adresse"],
            ["email / phone / mobile","String (opt.)",   "Kontaktoplysninger"],
            ["agreement_kind",        "String",          "Nøgle fra master_agreement_kinds.key (se afsnit 2.5) – ikke længere en fast enum-kolonne. Systemnøglerne hourly_fixed/hourly_flexible styrer stadig overtidsberegningen (se afsnit 5.5); nye, brugeroprettede nøgler springes automatisk over i den"],
            ["agreement_type",        "String",          "Overenskomsttype fra Excel-filen – bestemmer timesats"],
            ["fuldloennet",           "Boolean",         "Fuldlønnet status"],
            ["active",                "Boolean",         "Aktiv medarbejder (filtreres ved opslag)"],
            ["hire_date",             "Date",            "Ansættelsesdato"],
            ["termination_date",      "Date",            "Fratrædelsesdato (default 31-12-9999)"],
            ["work_schedule",         "JSON",            '{"even":[man..søn], "odd":[man..søn]} – normaltimer pr. dag i lig/ulige uge'],
            ["anciennitet_dismissed_at","DateTime (opt.)","Tidspunkt for afvisning af anciennitetsvarsel (nulstilles ved overenskomstskifte)"],
            ["dispatcher_group_id",   "Integer FK (opt.)","Én disponentgruppe (nullable) – se nedenfor"],
            ["fast_bil",              "Boolean",         "'Fast bil'-indstilling – foreslår medarbejderen som standardchauffør på en bestemt vogn i Dagsplan (kapitel 14)"],
            ["fast_bil_vehicle_id",   "Integer FK (opt.)","Den faste vogn – kun relevant når fast_bil=true. Ikke begrænset til medarbejderens egen disponentgruppe"],
            ["ot_extra_alle_timer",   "Boolean",         "Særaftale: alle arbejdstimer giver Øvrig overtid (kode 9) oveni normal løn, uden dagligt loft – se afsnit 5.6"],
            ["afloeser",              "Boolean, default false", "Afløser/substitutmedarbejder. Undertrykker søn-/helligdagstillæg (kode 4/63, afsnit 5.4) på søndage/helligdage MEDMINDRE der findes en godkendt 'normal tid'-aktivitet den dag – findes der kørsel, gælder de almindelige SH-regler uændret. Påvirker intet på almindelige hverdage/lørdage. Medarbejderen farvemarkeres separat i Medarbejderlisten, Vagtplan og Aktivitetsoversigten"],
            ["paragraf_56 / paragraf_56_start_date / paragraf_56_end_date", "Boolean / Date (opt.) / Date (opt.)", "§56-aftale (se afsnit 6.5) – begge datoer er påkrævede når paragraf_56=true, nulstilles til NULL server-side når feltet slås fra"],
            ["cvr_number",             "String(20) (opt.)", "Tilknyttet CVR-nummer – None betyder 'brug standard-CVR'. Se afsnit 6.6"],
            ["terminsdato",            "Date (opt.)",     "Seneste terminsdato angivet ved oprettelse af en barsel-aktivitet – gemmes for genbrug. Se afsnit 8.7"],
        ]
    )
    body(doc, (
        "Disponentgruppe (afdeling) er ét enkelt, valgfrit felt på medarbejderen (dispatcher_group_id, "
        "FK til dispatcher_groups) – ikke en mange-til-mange-relation. En medarbejder tilhører højst "
        "0-1 gruppe ad gangen og vælges via en dropdown i medarbejder-modalen, ikke afkrydsningsbokse. "
        "Grupperne selv (navn, beskrivelse) administreres under Stamdata → Disponentgrupper "
        "(opret/omdøb/slet). Feltet har historisk skiftet form to gange: oprindeligt en enkelt "
        "tekststreng, dernæst (fra 27. juli 2026) en mange-til-mange-relation via en "
        "EmployeeDispatcherGroup-jointabel, og siden igen erstattet af den nuværende enkelte FK – "
        "begge tidligere ordninger er fjernet fra databasen."
    ))

    heading(doc, "Activity – aktiviteter", 2, "2.2")
    header_table(doc,
        ["Felt", "Type", "Beskrivelse"],
        [
            ["employee_id",           "FK → Employee",  "Tilknyttet medarbejder"],
            ["pay_period_id",         "FK → PayPeriod", "Tilknyttet lønperiode"],
            ["trip_number",           "String (opt.)",  "Turnummer (max 6 tegn)"],
            ["source",                "Enum",           "tachograph (DDD-import) / manual (manuelt oprettet) / vagtplan"],
            ["activity_type",         "String(50)",     "normal / ferie / fri / afspadsering / skole/kursus / overnatning / dob_overnatning (se afsnit 7.7) / sygdom(_u_8uger) / barn_1sygedag(_u_8uger) / barsel(_u_loen) / §56 syg / graviditetsbetinget sygdom / selvbetalt fridag / løn andet sted fra (2026-09-22, se afsnit 7.9) – de '_u_...'/'_u_loen'-varianter sættes automatisk af anciennitetsreglerne i afsnit 8.7, ikke valgt direkte af brugeren"],
            ["start_time / end_time", "DateTime",       "Start- og sluttidspunkt"],
            ["availability_time_pct", "Decimal",        "Rådighedstid i % (fra tachograf)"],
            ["rest_pause_pct",        "Decimal",        "Hvil/pause i % (fra tachograf)"],
            ["other_work_pct",        "Decimal",        "Andet arbejde i % (fra tachograf)"],
            ["driving_pct",           "Decimal",        "Kørsel i % (fra tachograf)"],
            ["loading_minutes",       "Integer (opt.)", "Pålæsningstid i minutter"],
            ["unloading_minutes",     "Integer (opt.)", "Aflæsningstid i minutter"],
            ["pause_intervals",       "JSON",           '[ ["ISO-start","ISO-slut"], ... ] – pauseintervaller'],
            ["segments",              "JSON",           '[ ["ISO-start","ISO-slut","type"], ... ] – tachografsegmenter'],
            ["original_start_time",   "DateTime (opt.)","Original tachograftid inden første rettelse"],
            ["original_end_time",     "DateTime (opt.)","Original tachograftid inden første rettelse"],
            ["status",                "Enum",           "pending / approved / deactivated"],
            ["approved_by",           "String (opt.)",  "Initialer på godkender (kun ved godkendelse)"],
            ["approved_at",           "DateTime (opt.)","Godkendelsestidspunkt"],
            ["deactivated_by",        "String (opt.)",  "Initialer på den der deaktiverede (kun ved deaktivering)"],
            ["updated_by",            "String (opt.)",  "Initialer på den bruger der senest gemte en rettelse via PATCH /api/activities/{id} – NULL indtil første redigering, overskrives ubetinget ved hver efterfølgende (ingen historik, samme mønster som approved_by/deactivated_by)"],
            ["comment",               "Text (opt.)",    "Kommentar (påkrævet ved godkendelse < 4 timer)"],
            ["parent_activity_id",    "FK → Activity",  "Peger på moderaktivitet ved opdeling"],
            ["split_part",            "Integer (opt.)", "1 eller 2 – rækkefølge af opdelingsdele"],
            ["auto_approved / auto_approval_flags", "Boolean / JSON", "Sat af den statistiske baseline-auto-godkendelse (kapitel 18) – flags er en liste af menneskelæsbare afvigelsesårsager, tom hvis auto-godkendt"],
            ["absence_group_id",      "Integer (opt.)", "Fælles id for aktiviteter der stammer fra samme flerdags-fraværsperiode ('Til dato' ved oprettelse) – bruges til at redigere hele periodens datointerval bagefter (afsnit 8.8)"],
            ["hidden_from_vagtplan",  "Boolean, default false", "Skjuler aktiviteten fra Vagtplan-visningen uden at deaktivere den. Nulstilles automatisk ved 'Genåbn'. Backend-understøttet (POST /{id}/hide-from-vagtplan), men INGEN knap i frontend kalder endpointet pt. – reelt utilgængelig for brugeren i den nuværende UI"],
            ["original_segments",     "JSON (opt.)",    "Segmenternes tilstand før første 'Ret til andet arbejde'/'Tilpas'-rettelse (afsnit 8.5) – bruges til at diffe mod ved en senere DDD-genimport, uafhængigt af original_start_time/original_end_time"],
        ]
    )

    heading(doc, "PayPeriod – lønperioder", 2, "2.3")
    two_col_table(doc, [
        ["start_date / end_date", "Altid mandag–søndag, 14 dage"],
        ["status",                "open (aktiv) / preview (under kørsel) / closed (afsluttet)"],
        ["closed_at / closed_by", "Tidspunkt og bruger ved afslutning"],
    ])

    heading(doc, "PayrollRun – lønkørsler", 2, "2.4")
    two_col_table(doc, [
        ["pay_period_id", "FK til lønperioden"],
        ["run_type",      '"preview" (prøvekørsel) eller "final" (endelig kørsel)'],
        ["run_at",        "Tidspunkt for kørslen"],
        ["run_by",        "Initialer på den der kørte løn"],
        ["csv_path",      "Sti til genereret Danløn CSV-fil"],
        ["excel_path",    "Sti til genereret Excel-fil"],
    ])

    heading(doc, "Stamdata – masterdatatabeller", 2, "2.5")
    body(doc, (
        "Seks tabeller holder systemets masterdata. De fleste seedes automatisk fra Excel-filerne "
        "ved første opstart (Excel-filerne bruges herefter kun som fallback hvis en tabel er tom); "
        "master_agreement_kinds seedes i stedet fra to faste, hardkodede systemrækker (se nedenfor). "
        "Alle tabeller redigeres derefter via Stamdata-modulet i systemets brugerflade."
    ))
    header_table(doc,
        ["Tabel", "Indhold", "Vigtige felter"],
        [
            ["master_agreement_types",  "Overenskomsttyper og timesatser", "name (unik), hourly_rate"],
            ["master_agreement_kinds",  "Aftaletyper (\"Aftale\"-feltet på medarbejderen)", "key (unik, fast efter oprettelse), label, is_active, is_user_created, requires_agreement_type, sort_order"],
            ["master_overtime_rates",   "De tre overtidssatser",           "label (unik), rate"],
            ["master_supplement_rates", "Salttillæg, Overnatning, Dagpenge §56", "label (unik), rate"],
            ["master_pay_types",        "Løntypekoder til Danløn CSV",     "code_key (unik), danloen_code, include_in_csv, csv_quantity_type, csv_rate_source, csv_include_rate, csv_include_total, sort_order"],
            ["master_absence_types",    "Fraværstyper der vises i UI",     "label, normalized_key (unik), is_active, is_user_created, sort_order"],
        ]
    )
    body(doc, (
        "Normaliserede nøgler i master_absence_types genereres én gang ved oprettelse og ændres "
        "ikke efterfølgende – de bruges internt i beregnings- og aktivitetslogikken. "
        "Alle fraværstyper kan slettes via Stamdata-UI'et."
    ))
    body(doc, (
        "master_agreement_kinds seedes ved opstart med de to systemrækker hourly_fixed og "
        "hourly_flexible (is_user_created=False) – de kan ikke slettes, men deres label kan redigeres "
        "frit. key sættes kun ved oprettelse og kan ALDRIG ændres bagefter (heller ikke for "
        "brugeroprettede rækker), fordi overtidsberegningen i overtime.py/payroll_router.py grener "
        "direkte på strengværdierne hourly_fixed/hourly_flexible – se afsnit 5.5. Feltet "
        "requires_agreement_type styrer om Overenskomsttype er påkrævet for medarbejdere med den "
        "pågældende aftaletype (håndhæves i routers/employees.py)."
    ))

    heading(doc, "Holidays – helligdagskalender", 2, "2.6")
    body(doc, (
        "Holidays-tabellen gemmer danske helligdage og administreres separat fra de Excel-seedede "
        "masterdatatabeller. Den seedes automatisk ved serveropstart via _seed_holidays() i session.py."
    ))
    header_table(doc,
        ["Felt", "Type", "Beskrivelse"],
        [
            ["date",              "DATE UNIQUE NOT NULL", "Helligdagens dato – UNIQUE constraint forhindrer dubletter"],
            ["name",              "String NOT NULL",      "Navn, fx 'Påskedag', '1. maj', 'Grundlovsdag'"],
            ["half_day_from",     "String(5) NULL",       "'12:00' = fri fra middag; NULL = heldagshelligdag"],
            ["is_auto_generated", "Boolean DEFAULT TRUE", "TRUE = genereret af systemet; FALSE = manuelt oprettet"],
        ]
    )
    for item in [
        "5 løbende år genereres ved opstart (indeværende år + 4 fremover).",
        "Seeding er idempotent – eksisterende datoer springes over.",
        "Påskedato beregnes via anonym Gregoriansk Computus-algoritme i app/calculators/holidays.py.",
        "Deduplicering: faste helligdage vinder over bevægelige ved datokollision "
        "(fx 2028: 2. pinsedag og Grundlovsdag falder begge den 5. juni – Grundlovsdag bevares).",
        "Store Bededag medtages ikke (afskaffet fra 2024).",
    ]:
        bullet(doc, item)
    note_box(doc,
        "half_day_from-feltet er forberedt til brug i fremtidig lønberegning (helligdagstillæg). "
        "Feltet bruges allerede i aktivitetskalenderens '½ fra HH:MM'-badge.",
        "TEKNISK NOTE"
    )

    heading(doc, "Vehicle – køretøjer", 2, "2.7")
    header_table(doc,
        ["Felt", "Type", "Beskrivelse"],
        [
            ["registration_number", "String",           "Nummerplade"],
            ["vehicle_number",      "String",            "Internt vognnummer"],
            ["description",         "Text (opt.)",       "'Beskrivelse' – vises som kolonne 2 i Dagsplan (afsnit 14.3)"],
            ["dispatcher_group_id", "Integer FK (opt.)", "Mange vogne → én disponentgruppe. Adskilt fra DispatcherGroup.vehicle_id (gruppens egen 'standardvogn', bruges uændret til den eksisterende autoudfyldning af vognnummer på fraværstype-aktiviteter) – de to felter løser hver sin opgave og lever side om side"],
        ]
    )
    body(doc, (
        "description og dispatcher_group_id sættes/redigeres i den eksisterende Vognpark-sides "
        "opret/rediger-vogn-modal (kræver fortsat 'manage_vehicles')."
    ))

    heading(doc, "Dagsplan – tabeller", 2, "2.8")
    body(doc, (
        "Tre tabeller understøtter Dagsplan-siden (kapitel 14): daglig vogn/chauffør-tildeling, "
        "de 10 faste 'EKSTRA'-rækker og materielt fravær pr. vogn."
    ))
    header_table(doc,
        ["Tabel", "Felt", "Beskrivelse"],
        [
            ["daily_plan_assignments",       "date / vehicle_id / employee_id (opt.) / task (opt.) / informed", "Én tildeling pr. vogn pr. dag. UniqueConstraint(date, vehicle_id) – upsert. employee_id kan være tomt (vogn uden chauffør den dag)."],
            ["daily_plan_extra_assignments", "date / slot (1-10) / employee_id (opt.) / task (opt.) / informed", "De 10 faste 'EKSTRA'-rækker (hjælp på pladsen/lærlinge). Persisteres i egen tabel siden 2026-09-09 (oprindeligt kun frontend-state, nulstillet ved datoskift – ændret efter brugerønske om at kunne se dem igen senere). Indgår ALDRIG i vognnummer-autoudfyldning."],
            ["vehicle_absences",             "vehicle_id / date_from / date_to (opt.) / comment / created_by", "Materielt fravær for en vogn. date_to=NULL betyder étdags-fravær (samme dag som date_from). En vogn regnes fraværende på dato d hvis date_from ≤ d ≤ (date_to ?? date_from)."],
        ],
        [Cm(3.8), Cm(4.2), Cm(8)]
    )
    note_box(doc,
        "Forsøges en medarbejder tildelt en vogn/EKSTRA-plads, mens vedkommende allerede har en "
        "anden effektiv tildeling samme dag (eller har registreret fravær den dag), blokeres "
        "handlingen ikke – i stedet vises en advarsel (409 med menneskelæsbar besked), som "
        "brugeren kan bekræfte for at gennemføre dobbelttildelingen alligevel.",
        "TEKNISK NOTE"
    )

    # ── 3. Lønperioder ────────────────────────────────────────────────────
    doc.add_page_break()
    heading(doc, "Lønperioder", 1, "3")
    body(doc, (
        "Lønperioderne er faste 14-dages intervaller fra mandag til søndag. "
        "Systemet bruger en ankerperiode til at beregne alle andre perioder."
    ))
    two_col_table(doc, [
        ["Ankerperiode",  "Mandag 1. juni 2026 – søndag 14. juni 2026"],
        ["Periode-start", "Altid en mandag"],
        ["Periode-slut",  "Altid en søndag (14 dage efter start)"],
        ["Beregning",     "period_start_for_date(d): finder nærmeste mandag via modulo-14 fra ankerpunktet"],
    ])
    body(doc, (
        "get_billing_period() i pay_period.py bestemmer hvilken periode en NY eller RETTET aktivitet skal "
        "placeres i: hører datoen til en periode der allerede har status 'closed' (der er kørt løn), "
        "returneres i stedet den efterfølgende periode (get_or_create_period_for_date() kaldt på "
        "periodens slutdato + 1 dag). Bruges ved oprettelse af aktivitet, rettelse af starttid og "
        "DDD-import. Genåbning af en allerede placeret aktivitet ændrer bevidst ikke dens pay_period_id – "
        "kun oversigtsvisningen (se afsnit 4.4 i Brugervejledningen) sørger for at den stadig ses korrekt."
    ))
    body(doc, (
        "Timefordelingen på medarbejderen skelner mellem 'lige' og 'ulige' uger. "
        "Dette bestemmes af is_even_week(d): ISO-ugenummer % 2 == 0 → 'even' (lige uge). "
        "Mandag 1. juni 2026 er i ISO-uge 23 (ulige), så 'even'-skemaet bruges i ISO-uge 24, 26 osv."
    ))

    # ── 4. DDD-filparsing ─────────────────────────────────────────────────
    heading(doc, "DDD-filparsing (tachografdata)", 1, "4")
    body(doc, (
        "EU-tachografer gemmer data i .ddd-filer (EU Forordning 165/2014). Filen er binær "
        "og indeholder daglige poster med tidsstempler og aktivitetsskift."
    ))

    heading(doc, "Parsingsflow", 2, "4.1")
    for i, step in enumerate([
        ("Filidentifikation", "Kortnummeret matches som landekode (2 bogstaver) + 14 cifre (fx DK00000012666013), men kun de første 14 tegn (landekode + 12 cifre = driverIdentification) er det stabile kortnummer der bruges til medarbejder-matching. De sidste 2 cifre er cardReplacementIndex + cardRenewalIndex og ændrer sig når kortet udskiftes/fornys."),
        ("Lokalisering af poster", "Heuristisk søgning efter timestamp-mønstre identificerer starten på daglige poster."),
        ("Afkodning af ActivityChangeInfo", "2-byte records afkodes bit-for-bit: slot (bit 15-14), aktivitetstype (bit 13-11), minutter fra midnat (bit 10-0). Dato og minutter er UTC."),
        ("Aktivitetstyper", "Rest (hvil), Availability (rådighedstid), Work (andet arbejde), Driving (kørsel)."),
        ("Dagsstart", "Hver dags aktivitetsarray starter altid med en hvil-post ved minut 0 (videreført status fra dagen før, ikke en reel pause). Findes der en ekstra hvil-post lige derefter, er det chaufførens faktiske dagsstart – en kort pause inden arbejdet begynder – og den bruges som visningsstart for dagen."),
        ("Tidszonekonvertering", "Start/sluttid, segmenter og pauseintervaller konverteres fra UTC til dansk lokal tid (Europe/Copenhagen, DST-korrekt via Python-modulet zoneinfo) inden de gemmes."),
        ("Bygning af ParsedActivity", "Start/sluttid, procentfordelinger, pauseintervaller og segmenter samles til et ParsedActivity-objekt."),
        ("Duplikat-tjek/udvidelse", "Findes der allerede en aktivitet med samme medarbejder + starttid, opdateres km-data hvis de mangler. Har den nye fil desuden et SENERE sluttidspunkt end den eksisterende aktivitet (fx fordi kortet først blev læst af midt på en vagt og senere igen efter vagtens afslutning), udvides aktiviteten (sluttid, segmenter, pauser, procentfordeling) i stedet for at blive sprunget over – ellers ville den ekstra tid gå tabt for altid. Var aktiviteten allerede godkendt/deaktiveret, genåbnes den til 'afventende', så den udvidede tid skal godkendes igen (rettet 2026-07-02)."),
        ("Import af aktivitet", "_import_activity() returnerer 'new' (ny aktivitet), 'updated' (eksisterende aktivitet fik km-data udfyldt og/eller blev udvidet med en senere sluttid), 'skipped_unknown_card' (intet førerkortnummer matcher) eller 'skipped_duplicate' (allerede importeret, intet nyt at tilføje) – hver årsag tælles separat."),
        ("Km-start/km-slut", "_extract_daily_odometer() finder et separat array af (km, tidsstempel)-par i filen ved kæde-validering (mindst 5 elementer med præcis 20 bytes' afstand, ingen fast offset). km_start = km-standen tættest på dagens beregnede startminut; km_end = km_start + dagens egen kørte distance."),
        ("Ufuldstændig-markering (is_likely_incomplete)", "Kun for filens ALLERSIDSTE vagt: markeres som formentlig ufuldstændig hvis vagten IKKE slutter i hvil OG (dagens km-distance er 0 ELLER vagtens varighed er under LONG_REST_THRESHOLD_MINUTES) – et signal om at kortet blev læst af midt i vagten, så resten af dagen mangler i filen. Vises i aktivitetstabellen som et rødt ✕-mærke med forklarende tooltip. En efterfølgende genimport med en nyere, mere komplet fil kan udvide/erstatte den ufuldstændige linje (se genimport-reglerne nedenfor); omvendt må en NY udlæsning der selv er markeret ufuldstændig, ALDRIG lægges fuldt ind oveni en allerede komplet linje – kun udvides."),
    ], 1):
        bullet(doc, f"{step[1]}", f"{i}. {step[0]}: ")

    note_box(doc,
        "zoneinfo kræver på Windows Python-pakken tzdata (installeret via requirements.txt), "
        "da Windows ikke leverer sin egen IANA-tidszonedatabase.",
        "TEKNISK NOTE"
    )
    note_box(doc,
        "En indledende kort pause (fx 1-11 minutter) tælles med i den viste arbejdstid og "
        "fremgår af pause_intervals, men er stadig ubetalt – pause_intervals fratrækkes altid "
        "i lønberegningen uanset hvor i dagen de ligger.",
        "GODT AT VIDE"
    )
    note_box(doc,
        "Førerkort gemmer kun et begrænset antal køretøjsbrug-poster, så km-tabellen dækker "
        "ikke nødvendigvis hele kortets historik. Ældre dage vil derfor mangle km-start/km-slut "
        "– det er en begrænsning i kortets egne data, ikke en fejl i importen.",
        "GODT AT VIDE"
    )
    note_box(doc,
        "Videreudviklet 2026-09: matching mod eksisterende aktiviteter bruger nu tidsoverlap "
        "(ikke eksakt lighed i starttid), og sammenligner altid mod den oprindeligt importerede "
        "original_*-værdi frem for evt. manuelt rettede tider – så en manuel korrektion aldrig "
        "utilsigtet bliver overskrevet af en senere genimport af samme fil. Findes der BÅDE en "
        "godkendt/deaktiveret linje og en afventende rettelseslinje der overlapper det samme "
        "tidsrum, foretrækker systemet altid den afventende rettelseslinje – rettet efter en fejl "
        "der i praksis havde skabt 1.273 dublet-aktiviteter (fundet og rettet 2026-09-11). En "
        "allerede godkendt/deaktiveret aktivitet ændres ALDRIG direkte af en genimport; afviger "
        "den nye udlæsning, oprettes i stedet en ny, separat afventende linje. Opstår der en fejl "
        "midt i importen af én aktivitet, rulles hele databasetransaktionen for den fil tilbage "
        "(ikke kun den ene aktivitet springes over), for at forhindre at én defekt post får "
        "efterfølgende poster til at fejle i kaskade.",
        "TEKNISK NOTE"
    )
    note_box(doc,
        "Rettet 2026-09-18: en ufuldstændig genlæsning (is_likely_incomplete) der intet nyt "
        "fortæller i forhold til en allerede godkendt/deaktiveret linje – samme startpunkt, "
        "tidligere sluttidspunkt, og segmenter/pauser der er et rent præfiks af den afgjorte linje "
        "– springes nu stille over i stedet for at skabe en ny konkurrerende afventende linje. "
        "scan_ddd_folder() genparser nemlig ALLE .ddd-filer under 7 dage gamle ved hver import, "
        "ikke kun nye filer – en gammel, delvis kortudlæsning der bliver liggende i ddd_input/ "
        "udløste derfor tidligere en frisk dublet-linje ved hver eneste efterfølgende import "
        "(bekræftet for Alexander B. Knudsen 11/9-2026).",
        "TEKNISK NOTE"
    )
    note_box(doc,
        "Rettet 2026-09-22: en udlæsning på under VERY_SHORT_READING_MINUTES (15 minutter) i alt "
        "markeres nu ALTID som is_likely_incomplete, uanset om den slutter i hvil eller ej. Kortet "
        "stukket i læseren minutter inde i 'hvil' tidligt om morgenen (før dagens kørsel er "
        "begyndt) blev tidligere IKKE fanget, fordi den oprindelige regel krævede at vagten ikke "
        "endte i hvil – en kort morgenudlæsning der tilfældigvis endte i hvil blev derfor "
        "fejlagtigt opfattet som en fuldgyldig, afsluttet vagt og udløste en ny dublet-linje ved "
        "hver genimport, indtil filen faldt ud af det 7-dages importvindue (bekræftet for Claus "
        "Lindskov Schmidt 15-16/9-2026, samme mønster fundet i ca. 35 andre vagter i ddd_input/).",
        "TEKNISK NOTE"
    )

    heading(doc, "Import-flow", 2, "4.2")
    body(doc, (
        "Brugeren klikker 'Tjek ddd_input-mappe' i browsergrænsefladen, som kalder "
        "POST /api/import-ddd. Denne scanner ddd_input/-mappen (inkl. alle undermapper) "
        "på serveren, parser alle fundne .ddd-filer og gemmer nye aktiviteter i databasen."
    ))
    body(doc, (
        "_process_import_results() i import_ddd.py samler resultatet af alle filer: antal "
        "importeret, opdateret (km-data udfyldt på en eksisterende aktivitet), samt sprunget "
        "over opdelt på årsag (ukendt førerkortnummer – med de konkrete kortnumre – eller "
        "allerede importeret). Filer der giver 0 aktiviteter og eventuelle parse-fejl (også "
        "ved mappe-scanning) indgår i samme resultat. Frontenden viser resultatet i en "
        "pop-up (modal-import-result): 'Importering succesfuld' hvis alt gik igennem uden "
        "sprungne aktiviteter/fejl, ellers en opdelt oversigt over årsagerne."
    ))
    body(doc, (
        "Hver importkørsel logges som én hændelse (action 'ddd_import') i hændelsesloggen "
        "via log_action(), med samme opdelte opsummering i tekstform i details-feltet – så "
        "årsager til sprungne aktiviteter kan slås op bagefter, ikke kun ses i pop-up'en "
        "lige efter kørslen."
    ))
    body(doc, (
        "Hører et importeret skifts dato til en allerede LUKKET lønperiode, importeres det ikke "
        "automatisk. I stedet returneres det som 'pending_closed_period', og frontenden beder "
        "brugeren bekræfte om skiftet alligevel skal importeres (ind i den efterfølgende, åbne "
        "periode). Afviser brugeren, huskes afvisningen permanent i tabellen DeclinedImport "
        "(nøglet på medarbejder + starttidspunkt), så samme skift ikke bliver spurgt om igen ved "
        "en senere geninport af samme mappe. Bekræftelsen sendes via "
        "POST /api/decline-closed-period-import."
    ))

    # ── 5. Overtidsberegning ──────────────────────────────────────────────
    doc.add_page_break()
    heading(doc, "Overtidsberegning", 1, "5")
    body(doc, (
        "Beregningen udføres i calculators/overtime.py ved funktionen "
        "calculate_overtime(start, end, pause_intervals, normal_hours, rates). "
        "Satserne hentes fra Stamdata-databasen (master_overtime_rates). "
        "Excel bruges kun som fallback hvis DB-tabellen er tom."
    ))

    heading(doc, "De tre tillægstyper", 2, "5.1")
    header_table(doc,
        ["Nøgle", "Tidsvindue", "Betingelse", "Beskrivelse"],
        [
            ["OT_BEFORE\n(1 time før)", "05:00–06:00", "Arbejde i dette interval", "Tillæg for arbejde 1 time inden normal arbejdstid. Sats × timer i vinduet."],
            ["OT_13\n(1-3 timer efter)", "18:00–21:00\n+ 06:00–18:00 over normaltid", "Max 3 timer samlet", "Tillæg for de første 3 overarbejdstimer. Inkluderer dag-timer ud over normaltid (06-18) og aftentimer (18-21)."],
            ["OT_EXTRA\n(Øvrigt overtid)", "21:00–05:00\n+ overarbejde > 3 timer", "Al resterende overarbejde", "Tillæg for natarbejde og overarbejde ud over 3 timer. Højeste sats."],
        ]
    )

    heading(doc, "Beregningsgang", 2, "5.2")
    for step in [
        "Pauseintervaller fratrækkes i de tidsrum de afholdes (korrekt placering i tillægsvindue).",
        "Arbejdstimerne opdeles i 4 vinduer: before (05-06), day (06-18), evening (18-21), night (21-05).",
        "Alle arbejdstimer tæller med i normal_hours (kode 1) uanset vindue – men det REGISTREREDE normaltids-loft (fra medarbejderens timefordeling, fx 7/7,5/8 t) kan kun forbruges af timer i day-vinduet (06-18). Nat-, før- og aftentimer er altid rent tillæg og fortærer ikke loftet (rettet 2026-07-02, se OBS nedenfor).",
        "Day-timer der overskrider det (uforbrugte) normaltids-loft går til OT_13, op til et loft på 3 timer – derefter evening-timer, i den rækkefølge de forekommer kronologisk.",
        "Resterende evening-timer (når OT_13-puljen på 3 timer er brugt op) og alle night-timer går til OT_EXTRA.",
        "Resultat: OvertimeResult med normal_hours, ot_before_hours, ot_13_hours, ot_extra_hours samt beregnede tillæg i kr.",
    ]:
        bullet(doc, step)

    note_box(doc,
        "Pauser skal altid registreres korrekt, da de fratrækkes i det præcise tidsvindue de afholdes. "
        "En pause kl. 20:00 fratrækkes i OT_13-vinduet og reducerer dermed tillægget korrekt.",
        "VIGTIGT"
    )
    note_box(doc,
        "Det REGISTREREDE normaltids-loft er ikke den samme størrelse for alle medarbejdere: for "
        "agreement_kind='hourly_fixed' er loftet DAGLIGT (medarbejderens timefordeling for den "
        "pågældende ugedag, nulstilles hver dag). For agreement_kind='hourly_flexible' er loftet i "
        "stedet UGENTLIGT og FÆLLES for hele ugen: 37 timer normaltid + 5 timer OT_13, delt på "
        "tværs af alle vagter mandag–søndag og først nulstillet den følgende mandag. Forskellen "
        "afgøres i _calculate_employee() (payroll_router.py), som enten videresender et dagligt "
        "restloft (next_day_normal_hours) til calculate_overtime() ved midnatsovergange for "
        "hourly_fixed, eller lader det ugentlige loft løbe uændret videre for hourly_flexible – se "
        "afsnit 5.3 for hvordan denne forskel konkret udmønter sig ved vagter der krydser midnat.",
        "VIGTIGT"
    )
    note_box(doc,
        "Frem til 2026-07-02 fortærede nat-, før- og aftentimer også normaltids-loftet, hvilket "
        "gjorde for mange senere dagtimer til overarbejde for medarbejdere med tidlig morgenstart. "
        "Reglen er rettet, og calculate_overtime() kan nu tage imod og videresende det resterende "
        "loft (normal_remaining/ot13_remaining) fra en tidligere aktivitet SAMME dag, så loftet "
        "deles pr. dag og ikke nulstilles pr. aktivitet (relevant når en dag er delt i flere "
        "godkendte aktiviteter, fx efter en opdeling).",
        "TEKNISK NOTE"
    )

    heading(doc, "Vagter der krydser midnat", 2, "5.3")
    body(doc, (
        "Normaltids-/OT_13-loftet hører til vagten – den dag den startede – og fortsætter "
        "uændret hen over midnat, så længe det ikke er brugt op. Et eksempel: en vagt fra "
        "fredag kl. 20:30 til lørdag kl. 08:02 bruger fredagens loft for hele vagten; er "
        "fredagens 7 timer slet ikke rørt endnu (fordi aften/nat/'1 time før' aldrig fortærer "
        "det), fylder lørdagsmorgenens dagtimer bare videre op i det samme loft. Dette kræver "
        "ingen særlig kode – calculate_overtime()s kronologiske gennemløb af tidssegmenter "
        "håndterer det automatisk, når vagten IKKE splittes."
    ))
    body(doc, (
        "Søndage og helligdage har derimod en loft-uafhængig regel (se afsnit 5.4): "
        "\"alle kørte timer → kode 9, uanset tidspunkt\". Den regel kan ikke deles med en "
        "efterfølgende hverdags tidsvindues-baserede beregning, så en vagt der STARTER på en "
        "søndag/helligdag splittes altid i to ved midnat – søndagsdelen får søndagens regel, "
        "resten falder tilbage til den følgende dags egne regler."
    ))
    note_box(doc,
        "_split_into_day_pieces() i payroll_router.py udfører splittet. Om en aktivitet skal "
        "splittes afgøres af classify_day(aktivitetens startdato) – kun søndag og helligdage "
        "(inkl. halvdagshelligdage) udløser split. Lørdag og almindelige hverdage splittes ALDRIG, "
        "uanset hvor mange kalenderdage vagten strækker sig over (bekræftet af bruger 2026-07-02).",
        "TEKNISK NOTE"
    )
    note_box(doc,
        "Den beskrevne loft-videreførsel hen over midnat gælder kun for hourly_fixed (dagligt "
        "loft) – dér gives det NÆSTE døgns egne garanterede timer eksplicit videre som "
        "next_day_normal_hours, netop for at undgå at et ubrugt loft fra én dag fejlagtigt "
        "dækker en helt anden dags arbejde (den konkrete fejlrettelse er kendt internt som "
        "'Jesper Rosengreen-sagen', 2026-08-17). For hourly_flexible findes intet dagsskift at "
        "videreføre overhovedet – loftet er allerede ét sammenhængende, ugentligt loft (37 t + "
        "5 t OT_13) der løber uændret fra mandag til søndag, se afsnit 5.2.",
        "TEKNISK NOTE"
    )

    heading(doc, "Lørdage, søndage og helligdage (SH-betaling)", 2, "5.4")
    body(doc, (
        "Ud over de tre almindelige tillægstyper gælder særlige regler for lørdage, søndage og "
        "helligdage, implementeret i calculators/day_type.py. Dagtypen afgøres af classify_day() "
        "ud fra ugedag og helligdagskalenderen – en helligdag trumfer altid lørdag/søndag."
    ))
    header_table(doc,
        ["Dagtype", "Regel"],
        [
            ["Lørdag", "Regnes ALTID som en normal hverdag via calculate_overtime(), med lørdagens egne garanterede timer (typisk 0) som loft. Er loftet 0, giver den almindelige dagvindues-logik automatisk 'første op til 3 dagtimer → kode 8, resten → kode 9' – uden særkode (rettet 2026-07-02; den tidligere særregel for lørdag er fjernet)."],
            ["Søndag / heldagshelligdag", "Alle garanterede timer → kode 4 (fuldlønnet) / kode 63 (timelønnet), additivt oveni kørselslønnen. Alle kørte timer → kode 1 + kode 9, UANSET tidspunkt (tids-tillæg tilsidesættes)."],
            ["1. maj (halvdagshelligdag, fri fra 12:00)", "Garanti/2 → kode 4/63. Kørsel før 12:00 → kode 1. Kørsel efter 12:00: første 3 timer → kode 8, resten → kode 9."],
            ["Grundlovsdag (halvdagshelligdag, fri fra 12:00)", "Garanti/2 → kode 4/63. Kørsel før 12:00 → kode 1. Kørsel efter 12:00: ALLE timer → kode 9 (intet kode 8-trin)."],
        ]
    )
    note_box(doc,
        "Reglerne er bekræftet af bruger 2026-06-23 (søndag/helligdag) og 2026-07-02 (lørdag). "
        "Se afsnit 5.3 for hvordan vagter der krydser midnat ind i/ud af disse dage håndteres.",
        "BEMÆRK"
    )
    body(doc, (
        "Undtagelse – Employee.afloeser (2026-08-27): en medarbejder markeret som afløser "
        "får IKKE de garanterede SH-timer (kode 4/63) på en søndag/helligdag, medmindre der "
        "samme dag findes en godkendt 'normal tid'-aktivitet (dvs. vedkommende faktisk har "
        "kørt). Er der kørsel, gælder ovenstående regler helt uændret – flaget suspenderer "
        "kun den ellers automatiske garantibetaling på dage uden kørsel. Flaget påvirker intet "
        "på almindelige hverdage eller lørdage."
    ))

    heading(doc, "Aftale-typer uden fast overtidsregel", 2, "5.5")
    body(doc, (
        "Fra og med indførelsen af Stamdata-fanen \"Aftale\" (se afsnit 2.5 og 6.2) kan der oprettes "
        "flere aftaletyper end de to oprindelige, hourly_fixed og hourly_flexible. Kun disse to "
        "nøgler er kendt af overtidsberegningen ovenfor (afsnit 5.1–5.4)."
    ))
    body(doc, (
        "For en medarbejder hvis agreement_kind IKKE er hourly_fixed eller hourly_flexible, "
        "springer _calculate_employee() (payroll_router.py) hele den daglige/ugentlige "
        "loft-beregning og alle tillæg over. I stedet kaldes calculate_flat_hours() "
        "(calculators/overtime.py), som blot summerer arbejdstiden minus pauser til normal_hours – "
        "ingen ot_before/ot_13/ot_extra, og ingen søndags-/helligdagstillæg (sh_kode8/sh_kode9). "
        "Dette gælder for ALLE dagtyper, ikke kun almindelige hverdage."
    ))
    note_box(doc,
        "Dette er en bevidst, midlertidig afgrænsning: den konkrete beregningslogik for nye "
        "aftaletyper (hvis den overhovedet skal afvige fra flad normaltid) er endnu ikke defineret "
        "og er ikke en del af denne opgave. Se docs/superpowers/specs/2026-08-24-aftale-stamdata-design.md.",
        "TEKNISK NOTE"
    )

    heading(doc, "Særaftale: Øvrig overtid for alle timer", 2, "5.6")
    body(doc, (
        "Employee.ot_extra_alle_timer (Boolean, default false) er et generisk, togglebart "
        "per-medarbejder-flag til én navngiven medarbejders individuelle særaftale: ALLE hans "
        "arbejdstimer giver Øvrig overtid (kode 9) oveni normal løn – uanset tidspunkt, dagtype "
        "eller det sædvanlige daglige loft. Flaget er UAFHÆNGIGT af agreement_kind-branchingen i "
        "afsnit 5.5 – det virker ovenpå den almindelige beregning, ikke som en ny aftaletype."
    ))
    for step in [
        "Erstatter de normale tidstillæg (nat/aften/'1 time før', OT 1-3/kode 8) i stedet for at lægge oveni dem.",
        "Intet dagligt loft: fuld normalløn (kode 1) for samtlige arbejdstimer, uanset det sædvanlige loft på 7/7,5/8 timer.",
        "Gælder alle dage – hverdag, lørdag, søndag og alle helligdagstyper (inkl. 1. maj og Grundlovsdag).",
        "Kode 8 (Overtid 1-3 timer) gives ALDRIG – kun kode 1 og kode 9, begge for samtlige arbejdstimer.",
        "Kode 4/63 (SH-garantibetaling, compute_sh_hours()) beregnes helt uændret – uafhængig af flaget.",
    ]:
        bullet(doc, step)
    body(doc, (
        "Implementeret som override_ot_extra_alle_timer() i overtime.py, kaldt fra "
        "_calculate_employee() (payroll_router.py) som et nyt, øverste tjek FØR den eksisterende "
        "agreement_kind-gren. Slår automatisk igennem alle steder der bruger _calculate_employee(): "
        "lønkørsel-preview, prøvekørsel, PDF-timesedler, Lønafregning-fanen og Danløn CSV."
    ))
    note_box(doc,
        "Ingen ny løntypekode/Danløn-kode – genbruger den eksisterende kode 9-infrastruktur "
        "(OT_EXTRA_KEY). Ingen ændring af salttillæg, overnatningstillæg eller afløser-logik. "
        "Sættes via en checkbox i medarbejder-modalen ('Særaftale: Øvrig overtid for alle timer'), "
        "gated af samme manage_employees/stamdata-tilladelse som resten af modalen – ingen ny "
        "permission. Se docs/superpowers/specs/2026-09-10-ot-extra-alle-timer-design.md.",
        "TEKNISK NOTE"
    )

    # ── 6. Timesatser og overenskomst ─────────────────────────────────────
    heading(doc, "Timesatser og overenskomst", 1, "6")
    body(doc, (
        "Alle timesatser og overenskomsttyper opbevares i Stamdata-databasen og redigeres "
        "via Stamdata-modulet i systemets brugerflade. Excel-filerne bruges kun til initial "
        "seeding af databasen ved første opstart og er derefter irrelevante for driften."
    ))

    heading(doc, "Stamdata-tabeller og DB-funktioner", 2, "6.1")
    header_table(doc,
        ["Stamdata-tabel", "DB-funktion (rates_loader.py)", "Indhold"],
        [
            ["master_agreement_types",  "load_agreement_types_from_db(db)", "Overenskomstnavn → timesats i kr."],
            ["master_overtime_rates",   "load_overtime_rates_from_db(db)",  "De tre overtidstillæg og deres satser."],
            ["master_supplement_rates", "load_supplement_rates_from_db(db)","Salttillæg, Overnatning, Dagpenge §56."],
            ["master_pay_types",        "load_pay_types_from_db(db)",       "Løntypekoder og Danløn-koder."],
            ["master_absence_types",    "— (forespørges direkte i routers)", "Fraværstyper der vises i UI."],
            ["master_agreement_kinds",  "— (forespørges direkte i routers)", "Aftaletyper til medarbejder-modalens 'Aftale'-dropdown."],
        ]
    )

    body(doc, "")
    bullet(doc, "load_agreement_types_from_db(db): returnerer dict {navn: Decimal sats}", "rates_loader.py: ")
    bullet(doc, "load_overtime_rates_from_db(db): returnerer dict {nøgle: Decimal sats}")
    bullet(doc, "load_salt_supplement_rate_from_db(db): returnerer Decimal sats for salttillæg pr. time")
    bullet(doc, "load_overnight_rate_from_db(db): returnerer Decimal sats for overnatning pr. forekomst")
    bullet(doc, "seniority_variant_exists(type, db): tjekker om der findes en '9 mdr anciennitet'-variant i DB")
    bullet(doc, "Alle _from_db-funktioner har Excel som fallback, der kun aktiveres hvis DB-tabellen er tom")

    body(doc, "")
    body(doc, (
        "Anciennitetsvarsler: systemet kontrollerer løbende om aktive medarbejdere har ≥9 måneder "
        "og en tilsvarende 9-mdr-variant af overenskomsttypen – i så fald vises et varsel i UI. "
        "Varslet styres af tilladelsen 'anciennitet_alert' (checkAnciennitetsAlerts() returnerer tidligt "
        "hvis !state.currentUser.permissions.includes('anciennitet_alert')). "
        "Tilladelsen er som standard slået til for Administrator og Lønbogholder, og kan klikkes til/fra "
        "per rolle i Brugerstyring."
    ))

    heading(doc, "Stamdata-modulet i brugerfladen", 2, "6.2")
    body(doc, (
        "Stamdata-menupunktet (⚙️ Stamdata) i venstre menu giver administratorer adgang til "
        "ti faner med CRUD-funktionalitet for alle masterdatatabeller:"
    ))
    header_table(doc,
        ["Fane", "Indhold", "CRUD-muligheder"],
        [
            ["Overenskomsttyper", "master_agreement_types", "Opret, rediger navn/sats, slet"],
            ["Overtidssatser",    "master_overtime_rates",  "Rediger de tre systemsatser; opret/slet egne, brugeroprettede satser (kan ikke slettes, hvis en løntypekode bruger den som sats-kilde)"],
            ["Tillæg",            "master_supplement_rates","Rediger systemsatserne (salttillæg, overnatning, DOB-overnatning, §56); opret/slet egne, brugeroprettede tillæg (samme slette-spærre som Overtidssatser)"],
            ["Løntypekoder",      "master_pay_types",       "Opret nye, rediger type/kode/CSV-flag/antal-type/sats-kilde/inkl. sats/inkl. total, slet alle – INGEN 'i brug'-spærre ved sletning, heller ikke for systemsatser (kode 1/normal tid m.fl.)"],
            ["Fraværstyper",      "master_absence_types",   "Opret nye, aktiver/deaktiver, slet alle"],
            ["CVR nummer",        "master_cvr_numbers",     "Opret, rediger, sæt standard, slet"],
            ["Helligdage",        "holidays",               "Auto-generer for år, opret manuelt, slet. Kræver 'manage_holidays'-rettighed."],
            ["Disponentgrupper",  "dispatcher_groups",      "Opret, omdøb/rediger beskrivelse, slet (fjerner automatisk tilknytning hos medlemmer)"],
            ["Aftale",            "master_agreement_kinds", "Opret nye, rediger label/aktiv/kræver overenskomsttype. De to systemtyper (hourly_fixed/hourly_flexible) kan ikke slettes; nye typer kan slettes hvis ingen medarbejder bruger dem."],
            ["Auto-godkendelse",  "(indstilling, ingen egen tabel)", "Slå den statistiske baseline-auto-godkendelse til/fra globalt (GET/POST /api/auto-approval/settings). Kræver desuden 'manage_auto_approval'-rettigheden ud over 'stamdata'."],
        ]
    )
    note_box(doc,
        "Alle handlinger i Stamdata-modulet kræver 'stamdata'-rettighed. "
        "Helligdage-fanen kræver desuden 'manage_holidays'-rettighed.",
        "BEMÆRK"
    )
    note_box(doc,
        "Opretter en admin en HELT NY overtids- eller tillægssats (en ny RÆKKE i "
        "Overtidssatser/Tillæg-fanerne, ud over de faste satser systemet allerede kender), "
        "gemmes den i databasen, men beregningsmotoren (calculate_overtime()/day_type.py) "
        "bruger den IKKE automatisk nogen steder – den nye sats har reelt kun effekt, hvis den "
        "efterfølgende også kobles på en løntypekode via feltet 'Sats-kilde' i Stamdata → "
        "Løntypekoder (afsnit 6.1, dynamisk id-baseret opslag i _resolve_rate()), og selv da "
        "kun for CSV-eksporten – IKKE for selve lønberegningen/visningen i prøvekørsel og "
        "PDF-timesedler. En helt ny form for tillæg (fx et nyt tidsvindue eller en ny dagtype-"
        "regel) kræver udviklerarbejde i calculators/overtime.py eller day_type.py.",
        "VIGTIGT"
    )
    note_box(doc,
        "I modsætning til Overenskomsttyper/Overtidssatser/Tillæg/Aftale, som alle blokerer "
        "sletning af en række der er i brug, har Løntypekoder-fanens Slet-knap INGEN tilsvarende "
        "spærre – heller ikke for en systemseedet kode (fx den der ligger bag kode 1/normal tid). "
        "delete_pay_type() sletter ubetinget uanset hvor mange steder koden bruges. Slet derfor "
        "kun en løntypekode, hvis du er helt sikker på at den ikke længere skal med i Danløn CSV'en.",
        "VIGTIGT"
    )

    heading(doc, "Helligdage – API-endepunkter", 2, "6.3")
    header_table(doc,
        ["Endepunkt", "Metode", "Rettighed", "Beskrivelse"],
        [
            ["GET /api/stamdata/holidays",                  "GET",    "stamdata",        "Henter alle helligdage. Valgfri ?year=YYYY-filter."],
            ["POST /api/stamdata/holidays",                 "POST",   "manage_holidays", "Opretter helligdag. Body: date (YYYY-MM-DD), name, half_day_from (opt.)."],
            ["DELETE /api/stamdata/holidays/{id}",          "DELETE", "manage_holidays", "Sletter helligdag med angivet id."],
            ["POST /api/stamdata/holidays/generate/{year}", "POST",   "manage_holidays", "Auto-genererer helligdage for ét år (idempotent). År: 2020–2100."],
        ]
    )
    body(doc, (
        "Helligdagsdata bruges i aktivitetskalenderens frontend: "
        "loadHolidaysForPeriod(startDate, endDate) kaldes parallelt med loadActivities() og "
        "gemmer resultatet i state.holidays[]. renderActivitiesTable() markerer helligdagskolonner "
        "med baggrundsfarven #056a10 (mørkegrøn). Halvdagshelligdage vises med et '½ fra HH:MM'-badge "
        "og helligdagsnavnet som tooltip. Hvis dagens dato falder på en helligdag, bevares "
        "today-indikatoren via border-bottom i accentfarven."
    ))

    heading(doc, "Medarbejdertillæg (employee_supplements)", 2, "6.4")
    body(doc, (
        "Ud over overenskomsttypens timesats kan hver medarbejder have et individuelt kr/time-tillæg "
        "('Ikke overenskomstmæssigt tillæg'), historisk sporet i en selvstændig tabel employee_supplements. "
        "Tabellen administreres fra det selvstændige sidebar-punktet 'Tillæg' (kræver rettigheden "
        "manage_employee_supplements) og påvirker selve lønberegningen – ikke kun visning."
    ))
    header_table(doc,
        ["Felt", "Type", "Beskrivelse"],
        [
            ["employee_id",  "FK → Employee",  "Tilknyttet medarbejder"],
            ["name",         "String",         "Altid 'Ikke overenskomstmæssigt tillæg' – hardkodet server-side, ikke redigerbar"],
            ["type",         "String",         "Altid 'Timebaseret' – hardkodet server-side"],
            ["value",        "Numeric(10,2)",  "Tillæggets værdi i kr/time. Skal være > 0, afrundes til 2 decimaler før gemning"],
            ["start_date",   "Date",           "Gyldighedsperiodens start – default dags dato ved oprettelse"],
            ["end_date",     "Date",           "Gyldighedsperiodens slut – default 9999-12-31 (åbentstående)"],
        ]
    )
    body(doc, (
        "Status (Aktiv/Inaktiv) er IKKE et lagret felt – det beregnes ved hver visning ud fra om "
        "dags dato ligger i intervallet [start_date, end_date]. Et tillæg med fremtidig startdato "
        "vises derfor som Inaktiv, indtil startdatoen er nået."
    ))

    heading(doc, "Livscyklus og satsopslag", 2, "6.4.1")
    for step in [
        "Oprettelse (POST /api/employee-supplements): den medarbejders eksisterende åbentstående række (end_date = 9999-12-31) får automatisk sin end_date sat til ny_start_dato − 1 dag, og en ny åbentstående række indsættes. Ny start_date skal være efter den forrige rækkes start_date, ellers afvises oprettelsen.",
        "Afslutning (POST /api/employee-supplements/{id}/end): sætter IKKE end_date til dags dato, men til slutdatoen for den lønperiode dags dato falder i (get_or_create_period_for_date()). Tillægget gælder derfor stadig resten af den igangværende lønperiode og bortfalder først fra den efterfølgende periode.",
        "Der findes ingen redigerings- eller sletningsmulighed for eksisterende rækker – kun oprettelse af nye og afslutning af den aktive.",
        "Et partielt unikt indeks (uq_employee_supplements_one_open_row) sikrer på databaseniveau at en medarbejder kun kan have ÉN åbentstående række ad gangen (WHERE end_date = '9999-12-31') – forhindrer et race condition ved samtidige oprettelser.",
    ]:
        bullet(doc, step)
    body(doc, (
        "Ved lønberegning slår get_active_supplement_for_period(db, employee_id, periode_start, periode_slut) "
        "(calculators/rates_loader.py) op efter den række hvis gyldighedsperiode OVERLAPPER den beregnede periode. "
        "Overlapper flere rækker (fordi et nyt tillæg er oprettet midt i en periode), vinder rækken med nyeste "
        "start_date – for hele perioden (ingen dag-for-dag splitning). Denne regel gør samtidig en genberegning "
        "af en gammel, afsluttet periode historisk korrekt: det tillæg der dengang overlappede perioden, ændres "
        "ikke bagudrettet af senere oprettede tillæg."
    ))
    note_box(doc,
        "hourly_rate forhøjes med tillæggets value umiddelbart efter det almindelige overenskomstopslag i "
        "_calculate_employee() (payroll_router.py) – ÉN variabel der allerede bruges alle steder nedstrøms "
        "(normaltid/kode 1, SH-betaling, CSV-rækkerne for AFSPADSERING/SYGDOM/BARSEL/SKOLE_KURSUS m.fl.). "
        "Samme funktion genbruges af absence_overview_router.py, så Fraværsoversigtens viste sats altid stemmer "
        "overens med den sats der reelt udbetales i lønkørslen.",
        "TEKNISK NOTE"
    )

    heading(doc, "API-endepunkter", 2, "6.4.2")
    header_table(doc,
        ["Endepunkt", "Metode", "Beskrivelse"],
        [
            ["/api/employee-supplements",              "GET",  "Liste, filtreret på employee_id/from/to (gyldighedsperiode-overlap)."],
            ["/api/employee-supplements/active/{id}",   "GET",  "Det aktuelt aktive tillæg for én medarbejder, eller null."],
            ["/api/employee-supplements",               "POST", "Opret nyt tillæg (se livscyklus ovenfor)."],
            ["/api/employee-supplements/{id}/end",      "POST", "Afslut det aktuelt aktive tillæg fra og med den efterfølgende lønperiode."],
        ]
    )
    body(doc, (
        "Alle fire endepunkter kræver rettigheden manage_employee_supplements. Medarbejder-modalen "
        "(fanen 'Medarbejdere') viser tillæggets aktuelle værdi i et read-only felt under Overenskomsttype "
        "(hentet via GET /active/{id}) – feltet kan ikke redigeres eller udfyldes derfra, kun under fanen 'Tillæg'."
    ))

    heading(doc, "§56-aftale og advarsler", 2, "6.5")
    body(doc, (
        "Employee.paragraf_56 (Boolean) markerer at en medarbejder har en §56-aftale, med "
        "paragraf_56_start_date og paragraf_56_end_date som begge er påkrævede felter når "
        "flaget er sat. Sættes flaget til false (via medarbejder-modalen eller automatisk, se "
        "nedenfor), nulstiller serveren begge datofelter til NULL. Feltet har PT. ingen direkte "
        "kobling til selve lønberegningen eller den eksisterende fraværstype '§56 syg' – det er "
        "et rent stamdata-/varslingsfelt."
    ))
    body(doc, (
        "En daglig baggrundstjek (kørt ved hvert kald til GET /api/employees, "
        "_sweep_expired_paragraf_56()) slår automatisk paragraf_56 fra for enhver medarbejder "
        "hvis paragraf_56_end_date er overskredet – datoerne bevares uændret, kun det aktive "
        "flag ryddes. Brugere med rettigheden paragraf_56_alert advares to steder:"
    ))
    for step in [
        "GET /api/employees/paragraf56-alerts returnerer medarbejdere hvis slutdato ligger inden for 30 dage (kommende udløb) og medarbejdere der netop er auto-deaktiveret (nyligt udløbet).",
        "Frontend viser popup ved login for begge kategorier. Afvisning gemmes pr. bruger og pr. alert-type (Paragraf56AlertDismissal-tabellen) via POST /api/employees/{id}/dismiss-paragraf56-alert – IKKE globalt: en kollega uden afvisning ser stadig advarslen.",
        "Ændres paragraf_56_end_date på medarbejderen, nulstilles ALLE brugeres afvisninger for den medarbejder automatisk, så advarslen kan dukke op igen.",
    ]:
        bullet(doc, step)
    note_box(doc,
        "Oprettes en 'Sygdom'-aktivitet manuelt for en medarbejder med aktivt paragraf_56-flag, "
        "viser frontend (ikke backend) et bekræftelsesvalg: fortsæt som almindelig 'Sygdom', "
        "eller konvertér til den eksisterende fraværstype '§56 syg' i stedet. Der er ingen "
        "automatisk konvertering – begge veje kræver et aktivt valg fra brugeren.",
        "TEKNISK NOTE"
    )

    heading(doc, "CVR-numre og flere selskaber", 2, "6.6")
    body(doc, (
        "master_cvr_numbers (fane 'CVR nummer' i Stamdata) understøtter flere CVR-numre – "
        "relevant for koncerner med flere selskaber. Hver række har cvr_number (unik), "
        "company_name og is_default (Boolean, præcis én række kan være standard ad gangen)."
    ))
    body(doc, (
        "Employee.cvr_number (String, nullable) knytter valgfrit en medarbejder til ét bestemt "
        "CVR-nummer. _get_employee_cvr(emp, db) (duplikeret identisk i payroll_router.py og "
        "timeseddel_router.py) slår op: emp.cvr_number hvis sat, ELLERS den række hvor "
        "is_default=true. Findes intet standard-CVR overhovedet, fejler opslaget med 500 "
        "('Intet standard-CVR fundet – tilføj et CVR-nummer i Stamdata → CVR-nummer')."
    ))
    body(doc, (
        "Stamdata-endepunkterne (stamdata.py): POST opretter en ny CVR-række og markerer den "
        "automatisk som standard, hvis det er den allerførste (is_default = tabellen var tom); "
        "POST /{id}/set-default rydder alle andre standard-flag og sætter det valgte; DELETE "
        "afviser både standard-CVR'et ('Standard CVR-nummeret kan ikke slettes') og et CVR der "
        "stadig er tilknyttet mindst én medarbejder ('CVR-nummeret er tilknyttet medarbejdere og "
        "kan ikke slettes')."
    ))
    body(doc, (
        "cvr_number indgår som første kolonne i hver Danløn CSV-pay-type-række (afsnit 7.4) og "
        "trykkes i PDF-timesedlens header/footer ('CVR: {cvr_number}', afsnit 7.5)."
    ))
    note_box(doc,
        "Med kun ét CVR-nummer i Stamdata skjules CVR-dropdownet i medarbejder-modalen helt "
        "(frontend: _loadEmpCvrDropdown() viser kun feltet hvis der er ≥2 rækker) – enkeltselskaber "
        "ser derfor intet CVR-valg og alle medarbejdere bruger implicit standard-CVR'et.",
        "TEKNISK NOTE"
    )

    # ── 7. Lønkørsel ─────────────────────────────────────────────────────
    doc.add_page_break()
    heading(doc, "Lønkørsel", 1, "7")
    body(doc, (
        "Lønkørslen foregår i routers/payroll_router.py. KUN aktiviteter med status "
        "'approved' indgår i beregningen."
    ))

    heading(doc, "API-endepunkter", 2, "7.1")
    header_table(doc,
        ["Endepunkt", "Metode", "Beskrivelse"],
        [
            ["/api/payroll/preview",         "GET",  "Returnerer JSON med mellemregninger for alle eller én medarbejder."],
            ["/api/payroll/proevekoersel-gem","POST","Genererer Excel-fil med prøvekørsel og downloader den til browseren (siden 2026-09-09 – tidligere blev filen gemt i en brugervalgt mappe på serveren)."],
            ["/api/payroll/export-csv",      "POST", "Genererer Danløn CSV-fil og downloader den til browseren. Afviser (400) hvis perioden allerede er låst, eller der er afventende aktiviteter i perioden."],
            ["/api/payroll/pdf-timesedler",  "POST", "Genererer PDF-timesedler og downloader dem til browseren – én PDF direkte, eller en ZIP hvis flere medarbejdere har data."],
            ["/api/payroll/reopen-period",   "POST", "Genåbner en lukket ('closed') periode til 'open' igen. Kræver 'reopen_period'-rettighed."],
        ]
    )
    body(doc, (
        "Genåbning sveiper desuden 'forvildede' aktiviteter: aktiviteter der er blevet oprettet, "
        "mens perioden var lukket, bliver af get_billing_period() automatisk placeret i den "
        "EFTERFØLGENDE periode i stedet (se kapitel 3). Ved genåbning flyttes disse aktiviteter "
        "automatisk tilbage til den nu-genåbnede periode, så de igen indgår i dens beregning."
    ))

    heading(doc, "Beregningslogik (_calculate_employee)", 2, "7.2")
    for step in [
        "Itererer alle 14 dage i perioden – ikke kun dage med aktiviteter.",
        "Dage uden aktivitet returneres med 0 timer på alle kolonner.",
        "Overnatning (activity_type = 'overnatning'): tæller forekomster som overnight_count og springer dagslinje-logikken over (continue). Eksponeres i resultatet som overnight_count, overnight_rate og overnight_kr (flat sats pr. forekomst fra Salttillæg og overnatning.xlsx).",
        "Fraværsdage vises med typenavn i stedet for timer i dagsoversigten, men timerne beregnes og summeres stadig separat pr. fraværstype (fx sygdom_hours, afspadsering_hours, feriefri_hours, barsel_hours) og indgår i Danløn CSV'en, hvis løntypen er sat til 'Medtag i CSV' i Stamdata. Ferie er en undtagelse: den tælles, men er som default ekskluderet fra CSV'en.",
        "For normale aktiviteter: kalder calculate_overtime() med aktivitetens start/slut, pauseintervaller og normaltimer for den pågældende dag.",
        "Summerer normal tid, OT_BEFORE, OT_13 og OT_EXTRA timer samt pålæsning/aflæsning.",
        "Beregner kr. = timer × timesats (normal) + tillægstimer × satser.",
        "Returnerer dict med totaler og linjeposter pr. dag (alle 14 dage i perioden).",
    ]:
        bullet(doc, step)

    heading(doc, "Excel-formatering i prøvekørsel", 2, "7.3")
    body(doc, (
        "Excel-filen (_build_proevekoersel_workbook() i payroll_router.py) har 16 kolonner, "
        "i denne rækkefølge:"
    ))
    header_table(doc,
        ["#", "Kolonne", "Indhold"],
        [
            ["1",  "Medarbejder",              "Navn – suffikset ' (springer)' tilføjes hvis medarbejderen har springertillæg aktiveret for perioden (afsnit 6.4)."],
            ["2",  "Lønnr",                    "Medarbejderens lønnummer."],
            ["3",  "Vognnr.",                  "Køretøjsnummer for dagens aktivitet (blank ved fravær/totallinjer)."],
            ["4",  "Dag",                      "Dato (ÅÅÅÅ-MM-DD), eller 'TOTAL'/en tillægslabel (fx 'Søgnehelligdag', 'Sygdom med løn') på de fede opsummeringslinjer."],
            ["5",  "Starttid",                 "Aktivitetens starttidspunkt."],
            ["6",  "Sluttid",                  "Aktivitetens sluttidspunkt."],
            ["7",  "Total tid",                "Alle arbejdede timer den dag (efter fratrukne pauser), uanset om de udløser tillæg."],
            ["8",  "Pause i alt (min)",        "Summen af registrerede pauser den dag, i minutter. Segmenter der er rettet fra pause til arbejde via 'Ret til andet arbejde' (activities.py: correct_segment) tælles ikke med."],
            ["9",  "Normal tid",               "Kun de timer af Total tid der IKKE udløser et overtidstillæg (kolonne 7 minus kolonne 10-12). Ved fravær vises fraværstypen her i stedet for et tal."],
            ["10", "Overtid 1 time før",       "Timer i 05-06-vinduet (OT_BEFORE)."],
            ["11", "Overtid 1-3 timer efter",  "OT_13-timer, inkl. søndags-/helligdagskode 8."],
            ["12", "Øvrig overtid",            "OT_EXTRA-timer, inkl. søndags-/helligdagskode 9."],
            ["13", "Salttillæg (t)",           "Timer med salttillæg, hvis aktiveret på aktiviteten."],
            ["14", "Salttillæg (kr.)",         "Beregnet salttillæg i kr."],
            ["15", "Overnatning",              "1 hvis dagen har en overnatnings-aktivitet, ellers blank."],
            ["16", "Total kr.",                "Dagens/totallinjens samlede kronebeløb."],
        ],
        [Cm(0.8), Cm(3.5), Cm(11.7)]
    )
    note_box(doc,
        "Excel-kolonnen 'Normal tid' er IKKE det samme som calc['normal_hours'] i beregnings-"
        "resultatet (afsnit 7.2), som indeholder ALLE arbejdede timer (tillæg er additive, se "
        "afsnit 5.2). Excel-kolonnen trækker OT_BEFORE, OT_13 (+ kode 8) og OT_EXTRA (+ kode 9) "
        "fra, så den udelukkende viser timer der udbetales til ren normalsats uden tillæg oveni "
        "– til brug for kontrolformål.",
        "TEKNISK NOTE"
    )
    two_col_table(doc, [
        ["Grøn første række",    "Første datalinje for hver medarbejder markeres med grøn baggrund (farve #D4EDCC, samme lyse brandtint som resten af systemet) for nem identifikation af ny medarbejder."],
        ["Tom skillerække",      "Efter hver medarbejders totallinje indsættes en tom række som visuel adskillelse."],
        ["Frossen headerrække",  "Headerrækken (række 1) er frossen og følger med ved lodret scroll. Overskrifter der er længere end dataindholdet (fx 'Overtid 1-3 timer efter') ombrydes over flere linjer i stedet for at gøre kolonnen unødvendigt bred."],
        ["Kolonnebredder",       "Hver kolonne har en bredde tilpasset dataindholdet (8-24 enheder), så alle 16 kolonner kan ses uden vandret scroll på en almindelig skærm."],
        ["Nul-dage",             "Dage uden aktivitet vises med 0 på alle talkolonner."],
    ])

    heading(doc, "Danløn CSV-format", 2, "7.4")
    body(doc, (
        "Kolonnerne i den eksporterede CSV-fil (semikolon-separeret). "
        "Kolonne 5 og 6 er valgfrie per løntypekode og styres via Stamdata:"
    ))
    header_table(doc,
        ["Kolonne", "Altid med?", "Indhold"],
        [
            ["CVR",           "Ja",      "Virksomhedens CVR-nummer"],
            ["Medarbejdernr", "Ja",      "Lønnummer fra medarbejderkortet"],
            ["Lønkode",       "Ja",      "Danløn-kode for lønarten (konfigureres i Stamdata)"],
            ["Antal",         "Ja",      "Timer (2 decimaler) eller antal forekomster (heltal) afhængigt af Antal-type"],
            ["Sats",          "Valgfri", "Sats i kr. (2 decimaler). Slås fra ved 'Inkluder sats' = Nej i Stamdata"],
            ["Total",         "Valgfri", "Antal × Sats (2 decimaler). Tilføjes ved 'Inkluder total' = Ja i Stamdata"],
        ]
    )
    body(doc, (
        "CSV-kolonneopsætningen konfigureres per løntypekode i Stamdata → Løntypekoder: "
        "Antal-type (Timer/Antal), Sats-kilde (timesats, overtidssatser, salttillæg, overnatning, dagpenge), "
        "Inkluder sats og Inkluder total."
    ))
    note_box(doc,
        "De fleste Danløn-koder der seedes automatisk ved allerførste opstart (fra "
        "calculators/pay_rates.py's DANLOEN_CODE_*-konstanter) er STADIG placeholder-værdien "
        "\"1\" – de rigtige koder var pt. ikke oplyst af lønafdelingen da systemet blev bygget. "
        "Eneste undtagelser med reelle koder fra start er søgnehelligdagskoderne (4/63) og "
        "feriefri-koden for fuldlønnede (5). FØR systemet tages i egentlig produktionsbrug, skal "
        "hver enkelt løntypekode under Stamdata → Løntypekoder derfor gennemgås og rettes til den "
        "faktiske Danløn-kode – ellers vil flere forskellige lønarter blive eksporteret under "
        "samme (forkerte) kode \"1\".",
        "VIGTIGT"
    )
    note_box(doc,
        "Filnavnet på den downloadede CSV-fil er rettet 2026-09-22 til det format Danløn-"
        "importen forventer: \"danloen, Lønuge {uge1}-{uge2}, {dd-mm-åååå}-{dd-mm-åååå}.csv\" "
        "(fx \"danloen, Lønuge 23-24, 01-06-2026-14-06-2026.csv\") – ugenumrene beregnes med "
        "isocalendar() ud fra periodens start-/slutdato. Tidligere format var "
        "\"danloen_ÅÅÅÅ-MM-DD_ÅÅÅÅ-MM-DD.csv\".",
        "TEKNISK NOTE"
    )

    heading(doc, "Timeseddel-udsendelse pr. mail", 2, "7.5")
    body(doc, (
        "Ud over PDF-download (afsnit 7.1/7.3) kan PDF-timesedler sendes direkte til "
        "medarbejderens registrerede mailadresse via routers/timeseddel_router.py."
    ))
    header_table(doc,
        ["Endepunkt", "Metode", "Beskrivelse"],
        [
            ["/api/timeseddel/{id}/pdf",   "GET",  "Download én medarbejders PDF-timeseddel for en periode."],
            ["/api/timeseddel/{id}/send",  "POST", "Mailer PDF-timesedlen til medarbejderens registrerede e-mail. Fejler pænt (uden at afsløre SMTP-detaljer for brugeren) hvis medarbejderen ikke har en e-mailadresse registreret."],
            ["/api/timeseddel/send-all",   "POST", "Bulk-udsendelse for en periode (evt. filtreret til én medarbejder). Returnerer en opdelt status: sendt / sprunget over (ingen mail) / sprunget over (ingen aktiviteter) / fejlet."],
        ]
    )
    note_box(doc,
        "Alle tre endepunkter kræver 'payroll'-rettigheden. Fejl ved selve mailafsendelsen "
        "(fx forkert SMTP-opsætning) logges internt med medarbejderens navn/id, mens brugeren "
        "kun ser en generisk fejlbesked – hærdet 2026-08-29 for ikke at lække interne "
        "SMTP-fejldetaljer. SMTP-opsætningen (server, port, afsenderadresse, adgangskode) "
        "konfigureres i .env-filen, ikke i Stamdata.",
        "TEKNISK NOTE"
    )

    heading(doc, "Springertillæg", 2, "7.6")
    body(doc, (
        "Springertillæg (2026-08-14) er en løntypekode (SPRINGERTILLAEG) der giver samme "
        "timetal som løntypekode 1 (Normal tid), men KUN for de medarbejdere der i den enkelte "
        "lønperiode har fået sat et flueben i aktivitetsoversigten – ét flueben under "
        "medarbejderens navn, ét pr. medarbejder pr. periode. Fluebenet nulstilles automatisk "
        "hver ny periode (ingen række i employee_springer_flags = ikke sat) og kan ikke ændres "
        "når perioden er låst."
    ))
    body(doc, (
        "Tilladelsen toggle_springer styrer hvem der må sætte/fjerne fluebenet – den gives som "
        "standard til alle roller (se afsnit 11.3 i Brugervejledningen). Satsen konfigureres i "
        "Stamdata → Tillæg (label 'Springertillæg') ligesom salttillæg/overnatning."
    ))
    header_table(doc,
        ["Endepunkt", "Metode", "Beskrivelse"],
        [
            ["/api/activities/springer-flags?pay_period_id=", "GET",  "Returnerer {employee_id: true} for alle medarbejdere med fluebenet sat i perioden. Kræver kun login."],
            ["/api/activities/springer-flag",                  "POST", "Upsert på (employee_id, pay_period_id). Kræver toggle_springer. Afvises (400) hvis perioden er lukket."],
        ]
    )
    body(doc, (
        "Siden 2026-09-22 vises springertillæg desuden som en selvstændig linje (timer + beløb, "
        "samme timetal/sats som CSV'en: emp.normal_hours × emp.springer_rate) i Lønkørsel-fanens "
        "medarbejderkort (renderPayrollPreview(), app.js) og i PDF-timesedlens LØNOPSUMMERING "
        "(_build_pdf(), timeseddel_router.py), lige efter 'Timer arbejdet'. Beløbet er – ligesom "
        "Overnatning/DOB Overnatning – IKKE en del af emp.total_kr/calc['total_kr'], og lægges "
        "derfor manuelt til i begge steders 'I alt'-linje (se afsnit 7.9)."
    ))
    note_box(doc,
        "Rettet 2026-09-22: fluebenets checkbox-listener i aktivitetsoversigten opdaterer nu "
        "state.springerFlags lokalt med det samme efter et vellykket gem. Uden denne rettelse "
        "kunne en efterfølgende gentegning af tabellen (fx efter oprettelse af en ny aktivitet "
        "via refreshActivities()) overskrive brugerens netop satte flueben med den forældede "
        "værdi fra sidste periode-indlæsning, så springertillægget så ud til at forsvinde igen.",
        "TEKNISK NOTE"
    )

    heading(doc, "DOB Overnatning", 2, "7.7")
    body(doc, (
        "DOB Overnatning er IKKE en selvstændig aktivitetstype i oprettelsesmodalens dropdown "
        "(activities.py: 'dob_overnatning' er placeret i _BACKEND_ONLY_TYPES) – det er et "
        "krydsfelt ('DOB') inde i den almindelige Overnatning-modal, der ved oprettelse "
        "omdøber POST-body'ens activity_type til 'dob_overnatning' i stedet for 'overnatning'. "
        "Aktiviteten oprettes i øvrigt identisk: nul varighed, midnatsstemplet."
    ))
    body(doc, (
        "Satsen hentes separat via load_dob_overnight_rate_from_db() (rates_loader.py), som slår "
        "op på MasterSupplementRate.label == 'DOB_overnatning'. I modsætning til almindelig "
        "Overnatning (load_overnight_rate_from_db()) har DOB INGEN Excel-fallback – er satsen "
        "ikke oprettet i Stamdata → Tillæg, bruges 0 kr."
    ))
    body(doc, (
        "De to overnatningstyper tælles og prissættes helt uafhængigt af hinanden "
        "(overnight_count/overnight_kr hhv. dob_overnight_count/dob_overnight_kr, "
        "payroll_router.py). DOB vises som egen linje 'DOB Overnatning' i PDF-timesedlen "
        "(timeseddel_router.py) og som en 'DOB Overnatning (kr.)'-totallinje i prøvekørslens "
        "Excel-ark (afsnit 7.3), når beløbet er > 0."
    ))
    note_box(doc,
        "DOB Overnatning har PT. ingen tilsvarende række i Danløn CSV'en (_build_danloen_csv() "
        "har ingen DOB_OVERNATNING-nøgle i raw_rows) – kun almindelig Overnatning eksporteres til "
        "CSV. Beløbet indgår derfor i prøvekørsel og PDF-timeseddel, men skal pt. afregnes uden "
        "om Danløn-eksporten.",
        "VIGTIGT"
    )

    heading(doc, "Overnatning som periode", 2, "7.8")
    body(doc, (
        "Siden 2026-09-16 kan overnatning/DOB-overnatning oprettes for et datointerval ('Til dato' "
        "i opret-modalen) i stedet for kun én dag ad gangen. Den isolerede overnatnings-gren i "
        "confirmManualActivity() (app.js) udvides til selv at forgrene på om 'Til dato' er udfyldt "
        "– den generelle periode-gren/_RANGE_TYPES (brugt af ferie/sygdom/afspadsering m.fl.) "
        "røres IKKE, da overnatning hverken kræver registreringsnummer eller skematimer."
    ))
    body(doc, (
        "getAllDates(fra, til) (app.js) / _all_dates() (activities.py, ny hjælpefunktion ved "
        "siden af _weekday_dates()) genererer ALLE kalenderdage i intervallet, inkl. weekend og "
        "helligdage – i modsætning til _weekday_dates(), som de øvrige periodetyper bruger. Ét "
        "POST /api/activities pr. dag, alle med samme absence_group_id (samme mønster som "
        "ferie-perioder) og enten alle 'overnatning' eller alle 'dob_overnatning' – DOB-fluebenet "
        "gælder for hele perioden, ingen blanding pr. dag understøttet i ét opret-kald."
    ))
    body(doc, (
        "Overlapskontrollen genbruger IKKE modal-absence-conflict/_absenceConflictConfirmed (den "
        "mekanisme øvrige periodetyper bruger) – i stedet en simpel window.confirm() med op til 5 "
        "konkrete overlap listet, som tjekker mod ENHVER overlappende aktivitet (ikke kun "
        "'normal'). Samme bredere logik er kopieret ind (ikke delt som funktion, for at holde "
        "overnatnings-grenen selvstændig)."
    ))
    note_box(doc,
        "_calculate_employee() krævede INGEN ændring: overnight_count/dob_overnight_count tæller "
        "allerede simpelthen antal Activity-rækker af typen i perioden, uanset om de stammer fra "
        "enkeltdags- eller periode-oprettelse – lønkørsel, PDF-timeseddel og Danløn CSV er derfor "
        "upåvirkede af denne ændring. Se docs/superpowers/specs/2026-09-16-overnatning-periode-design.md.",
        "TEKNISK NOTE"
    )

    heading(doc, "Løn andet sted fra", 2, "7.9")
    body(doc, (
        "Ny fraværstype (2026-09-22, normaliseret nøgle loen_andet_sted_fra) – IKKE en del af "
        "Fraværstyper.xlsx, men seedet idempotent til master_absence_types ved opstart af "
        "_ensure_loen_andet_sted_fra_absence_type() (session.py), samme mønster som "
        "_ensure_springer_pay_type(). Opfører sig i beregningen fuldstændig som 'Selvbetalt "
        "fridag': ingen gren i _calculate_employee() (payroll_router.py) → altid 0 kr., ingen "
        "linje i Danløn CSV'en. Typen er tænkt som en kommentar til lønbogholderne om, at en "
        "given dag bevidst er uden data i dette system (fx fordi medarbejderen har kørt for et "
        "andet selskab/eksport den dag) – ikke som en fraværstype der skal udløse betaling her."
    ))

    heading(doc, "Selvbetalt fridag som periode", 2, "7.10")
    body(doc, (
        "Siden 2026-09-22 kan 'Selvbetalt fridag' (og 'Løn andet sted fra') oprettes for et "
        "datointerval ('Til dato' udfyldt) på samme måde som Ferie – begge typer er tilføjet til "
        "app.js' _RANGE_TYPES og isRangeType/isFerie-kontrollerne i updateManualTypeVisibility()/"
        "confirmManualActivity(). Der oprettes én aktivitet PR. HVERDAG i perioden (_weekday_dates(), "
        "ikke _all_dates() som Overnatning bruger, se afsnit 7.8), med samme 06:00-start og "
        "normaltime-beregnede sluttid som en enkeltstående fraværsdag."
    ))

    heading(doc, "Lønkørsel-fanens og PDF-timesedlens samlede beløb ('I alt')", 2, "7.11")
    body(doc, (
        "Rettet 2026-09-22: Lønkørsel-fanens 'I alt'-beløb pr. medarbejder (renderPayrollPreview(), "
        "app.js) medregnede tidligere kun total_kr + overnatning + DOB-overnatning + springertillæg. "
        "Fraværstyper med et beregnet beløb (Sygdom, §56 syg/Barn 1.sygedag u. løn til dagpengesats, "
        "Feriefri, Barsel, Skole/kursus – samme sæt som Lønafregningens absence_kr, afsnit 13.2) "
        "talte IKKE med, selvom de reelt udbetales. grandTotalKr beregnes nu ved at lægge disse "
        "fraværsbeløb (timer × hourly_rate hhv. dagpenge_sats) oveni de øvrige tillæg."
    ))
    body(doc, (
        "Samme rettelse er lavet i PDF-timesedlens LØNOPSUMMERING (_build_pdf(), "
        "timeseddel_router.py, 2026-09-22): fraværslinjerne (Afspadsering, Sygdom, Feriefri, "
        "Barsel, §56 syg, Barn 1.sygedag u. løn, Kursus/Skole) viste tidligere kun timer og "
        "'–'/'–' i Sats/DKK-kolonnerne. De viser nu den faktiske sats og det beregnede beløb "
        "(samme satser som ovenfor: hourly_rate, eller dagpenge_sats for §56/Barn 1.sygedag u. "
        "løn), og beløbet lægges til 'I alt'-linjens total_display_kr samt timerne til den viste "
        "totaltid – så PDF-timesedlens 'I alt' nu stemmer overens med det beløb medarbejderen "
        "reelt får i løn, og med Lønkørsel-fanens 'I alt' beskrevet ovenfor."
    ))
    note_box(doc,
        "Begge rettelser er rene VISNINGS-rettelser i frontend/PDF-lag – selve lønberegningen i "
        "_calculate_employee() og dermed Danløn CSV-eksporten var upåvirket af buggen; fraværet "
        "blev allerede korrekt betalt, det var kun 'I alt'-summen i Lønkørsel-fanen og PDF-"
        "timesedlen der tidligere undervurderede den reelle udbetaling.",
        "TEKNISK NOTE"
    )

    # ── 8. Aktivitetshåndtering ───────────────────────────────────────────
    heading(doc, "Aktivitetshåndtering", 1, "8")

    heading(doc, "Statusflow", 2, "8.1")
    body(doc,
        "pending → approved (godkendt – approved_by sættes til brugerens initialer) → "
        "deactivated (deaktiveret – deactivated_by sættes til brugerens initialer).\n"
        "Fraværstyper (ferie, sygdom, afspadsering, skole/kursus mv.) oprettes direkte som approved, med approved_by sat til den opretstende brugers initialer (ikke pending, da de ikke skal manuelt godkendes bagefter).\n"
        "approved_by og deactivated_by er separate felter – approved_by bruges udelukkende til godkendelser."
    )
    body(doc, (
        "Rettigheden auto_approve_manual_activities ('Auto-godkend ved oprettelse') sætter "
        "status direkte til approved for ALLE manuelt oprettede aktiviteter (både normal tid og "
        "fraværstyper) for brugere der har den – rent regelbaseret ud fra hvem der opretter, "
        "ingen statistik involveret. Uafhængig af den statistiske baseline-auto-godkendelse i "
        "kapitel 18, som udelukkende gælder tachograf-importerede kørselsdage."
    ))

    heading(doc, "Rettelse og fortryd", 2, "8.2")
    for step in [
        "Første rettelse: original_start_time og original_end_time gemmes automatisk.",
        "Efterfølgende rettelser: originaltiderne overskrives ikke.",
        "Fortryd: nulstiller start_time og end_time til de gemte originaler.",
    ]:
        bullet(doc, step)

    heading(doc, "Opdeling (split)", 2, "8.3")
    body(doc, (
        "En aktivitet kan opdeles ved et valgt tidspunkt. Systemet opretter to "
        "børneaktiviteter med parent_activity_id og split_part (1 og 2). "
        "Pauser og segmenter fordeles proportionalt til den korrekte del."
    ))

    heading(doc, "Aktivitetsflags", 2, "8.4")
    two_col_table(doc, [
        ["is_under_4h",  "Aktiviteten er under 4 timer – kommentar påkrævet ved godkendelse."],
        ["is_over_12h",  "Aktiviteten er over 12 timer – vises som advarsel i UI."],
        ["is_manual",    "Aktiviteten er manuelt oprettet (source=manual, ikke fra tachograf)."],
        ["is_edited",    "Tiderne er blevet ændret fra tachografdata."],
        ["has_split_children", "Aktiviteten er opdelt i to børneaktiviteter."],
    ])

    heading(doc, "Segmentrettelse ('Ret til andet arbejde' / 'Tilpas')", 2, "8.5")
    body(doc, (
        "To separate endepunkter lader en bruger justere de enkelte tachografsegmenter "
        "(segments-feltet) på en aktivitet, uafhængigt af hele aktivitetens start-/sluttid."
    ))
    header_table(doc,
        ["Endepunkt", "Beskrivelse"],
        [
            ["POST /{id}/correct-segment",     "Body: {segment_index, revert?}. Omklassificerer ét pausesegment ('rest') til 'Andet arbejde' ('work') – kun tilladt på segmenter der endnu ikke er rettet. Original type gemmes som et 4. listeelement, så revert=true kan fortryde præcis den ene rettelse."],
            ["POST /{id}/correct-all-segments","Anvender samme rest→work-omklassificering på ALLE endnu urettede pausesegmenter i aktiviteten samlet ('Al pause til andet arbejde'-knappen)."],
            ["POST /{id}/resize-segment",      "Body: {segment_index, new_end_iso}. Ændrer KUN et pausesegments sluttidspunkt, aldrig typen. Forkortning opretter et nyt 'work'-segment af den frigjorte hale; forlængelse låner tid fra det efterfølgende segment (fejler hvis der intet næste segment er, eller hvis den nye sluttid ville overskride dettes sluttid)."],
        ],
        [Cm(5), Cm(10)]
    )
    body(doc, (
        "Første rettelse på en aktivitet gemmer segments-feltets tilstand i original_segments, "
        "FØR ændringen – bruges til at sammenligne mod ved en senere DDD-genimport, uafhængigt af "
        "original_start_time/original_end_time (afsnit 8.2)."
    ))
    note_box(doc,
        "Et pausesegment der omklassificeres til 'work' tæller derefter med som betalt "
        "arbejdstid i stedet for at blive fratrukket som ubetalt pause i calculate_overtime() "
        "(payroll_router.py ekskluderer kun segmenter tagget 'rest' fra dagens arbejdsvinduer) – "
        "rettelsen påvirker derfor lønberegningen direkte.",
        "TEKNISK NOTE"
    )

    heading(doc, "Permanent sletning og skjul fra Vagtplan", 2, "8.6")
    body(doc, (
        "DELETE /api/activities/{id} sletter aktiviteten PERMANENT fra databasen – i modsætning "
        "til Deaktiver (afsnit 8.1), som blot ændrer status. Reglen for hvad der må slettes helt: "
        "alle fraværstyper (uanset kilde) må altid slettes helt; 'normal tid' må KUN slettes helt "
        "hvis den er manuelt oprettet (source=manual) – takograf-importeret normal tid kan aldrig "
        "slettes helt, kun deaktiveres, da det er rå kørselsdata fra kortet. En aktivitet med "
        "split-børn kan ikke slettes, før splittet er fortrudt."
    ))
    note_box(doc,
        "Hverken /deactivate eller DELETE-endepunktet kræver andet end almindeligt login "
        "(get_current_user) – der er ingen data-perm-require på sletning i frontend heller. "
        "Enhver logget ind bruger kan altså slette en aktivitet permanent, hvis reglerne ovenfor "
        "er opfyldt.",
        "VIGTIGT"
    )
    body(doc, (
        "POST /{id}/hide-from-vagtplan (body: {hidden}) sætter Activity.hidden_from_vagtplan, "
        "som ekskluderer aktiviteten fra Vagtplan-forespørgsler uden at ændre dens status. "
        "Nulstilles automatisk ved 'Genåbn' (reopen)."
    ))
    note_box(doc,
        "hidden_from_vagtplan-endepunktet har INGEN kaldssted i app.js/index.html pt. – "
        "funktionen er implementeret og testet server-side, men der findes ingen knap eller "
        "menupunkt i den nuværende brugerflade der kalder den. Ikke at forveksle med "
        "'Slet aktiviteten helt'-fluebenet ovenfor, hvis label nævner Vagtplan, men som er en "
        "helt anden, fuldt tilgængelig handling (permanent sletning).",
        "TEKNISK NOTE"
    )

    heading(doc, "Automatisk omklassificering ved lav anciennitet", 2, "8.7")
    body(doc, (
        "create_manual_activity() (activities.py) omklassificerer stiltiende tre fraværstyper "
        "til deres ulønnede variant, hvis medarbejderens anciennitet på det relevante tidspunkt "
        "er for lav:"
    ))
    header_table(doc,
        ["Type", "Betingelse", "Bliver til"],
        [
            ["sygdom",         "(start_time.date() − hire_date).days <= 56 (8 uger)", "sygdom_u_8uger"],
            ["barn_1sygedag",  "Under 9 hele kalendermåneders anciennitet (hire_date → start_time.date())", "barn_1sygedag_u_8uger"],
            ["barsel",         "Under 9 hele kalendermåneders anciennitet (hire_date → terminsdato, IKKE aktivitetens startdato)", "barsel_u_loen"],
        ]
    )
    body(doc, (
        "terminsdato (forventet fødselsdato) er PÅKRÆVET for at oprette en barsel-aktivitet – "
        "mangler den, afviser endepunktet med 400 ('Terminsdato er påkrævet for barsel'). Værdien "
        "gemmes samtidig på Employee.terminsdato (afsnit 2.1) til genbrug, så den ikke skal "
        "genindtastes ved en senere barsel-aktivitet for samme medarbejder."
    ))

    heading(doc, "Redigering af fraværsperiodens datointerval", 2, "8.8")
    body(doc, (
        "PATCH /api/activities/absence-group/{group_id} (body: {new_start_date, new_end_date}) "
        "lader en bruger udvide eller indskrænke en allerede oprettet flerdags-fraværsperiode "
        "(aktiviteter der deler samme absence_group_id, se afsnit 2.2) ved at redigere én af "
        "periodens dage."
    ))
    for step in [
        "Kun hverdage (mandag–fredag) indgår i beregningen af det nye datointerval for de fleste typer – UNDTAGEN overnatning/dob_overnatning (_COUNT_BASED_RANGE_TYPES), hvor _all_dates() bruges i stedet, så weekend/helligdage tælles med (afsnit 7.8).",
        "Dage der FJERNES fra perioden: afvises alt-eller-intet hvis nogen af dem hører til en lukket lønperiode, eller er splittet – ellers SLETTES de tilhørende aktiviteter permanent (db.delete()), ikke deaktiveres.",
        "Dage der TILFØJES: for almindelige fraværstyper oprettes en ny aktivitet med standardtimer fra medarbejderens timefordeling (lige/ulige uge) – er de skemalagte timer 0 for en given ugedag, springes dagen over og rapporteres i svarets skipped-liste i stedet for at fejle. For overnatning/dob_overnatning oprettes i stedet en midnatsstemplet nul-varighed-aktivitet pr. dag, som ved almindelig oprettelse – ingen skematime-beregning, ingen skip-mulighed.",
        "Backend udfører INGEN konflikttjek mod eksisterende kørsel ('normal tid') på de tilføjede dage for de fleste typer – det tjek er kun implementeret i frontend (se Brugervejledningen, afsnit 6.4). For overnatning/dob_overnatning tjekker frontend i stedet mod ENHVER overlappende aktivitet, ikke kun 'normal'.",
    ]:
        bullet(doc, step)
    body(doc, (
        "UI-indgang: aktivitetsdetaljens 'Fraværsperiode'-sektion (kun synlig når aktiviteten "
        "tilhører en gruppe) med Fra-/Til-dato-felter og knappen 'Gem periodedatoer'."
    ))

    # ── 9. Frontend ───────────────────────────────────────────────────────
    doc.add_page_break()
    heading(doc, "Frontendarkitektur", 1, "9")
    body(doc, (
        "Hele frontenden er én HTML-fil (templates/index.html) med én JavaScript-fil "
        "(static/js/app.js). Der bruges ingen React, Vue eller andre frameworks."
    ))

    heading(doc, "State-management", 2, "9.1")
    body(doc, "Et globalt state-objekt holder applikationens tilstand:")
    two_col_table(doc, [
        ["state.employees",      "Liste af alle aktive medarbejdere (inkl. dispatcher_group, work_schedule osv.)"],
        ["state.activities",     "Alle aktiviteter for den valgte periode"],
        ["state.periodInfo",     "Aktuel periodeinfo: start/slut, tæller for pending/approved/deactivated"],
        ["state.agreementTypes", "Overenskomsttyper og satser"],
        ["state.splitMin/Max",   "Grænser for opdeling (gemmes i state for validering)"],
        ["manualPauses",         "Pauseintervaller for aktivitet under oprettelse: liste af [ISO-start, ISO-slut]-par. Nulstilles ved åbning af oprettelsesmodalen."],
    ])

    heading(doc, "Cache-busting", 2, "9.2")
    body(doc, (
        "main.py beregner app.js's ændringstidspunkt (st_mtime) og indsætter det som "
        "forespørgselsparameter: <script src='/static/js/app.js?v={mtime}'>. "
        "Browsercachen brydes automatisk ved hver ændring af filen."
    ))

    heading(doc, "Datetime-picker", 2, "9.3")
    body(doc, (
        "En brugerdefineret datetime-komponent erstatter browserens native datetime-local "
        "scroll-input. Komponenten består af: date-input (dato) + number-input (time, 0-23) "
        "+ ':' + number-input (minut, 0-59). Alle styles er inline i JavaScript for at "
        "undgå browsercache-problemer."
    ))
    two_col_table(doc, [
        ["buildDatetimePicker(id, isoValue)", "Bygger komponenten og indsætter den i elementet med det givne id."],
        ["readDatetimePicker(id)",            "Læser de tre felter og returnerer ISO-datetime-streng."],
        ["setDatetimePicker(id, isoValue)",   "Sætter alle tre felter fra en ISO-datetime-streng."],
    ])

    heading(doc, "Date-picker (datovalg)", 2, "9.4")
    body(doc, (
        "En brugerdefineret dato-komponent (buildDatePicker) erstatter browserens native "
        "date-input på steder hvor det er vigtigt at kunne vælge årstal fra dropdown. "
        "Komponenten består af et tekstfelt der åbner et popup-kalender med måned-dropdown, "
        "årstal-dropdown (1950–2100) og en klassisk månedsgrid med klikbare datoer."
    ))
    two_col_table(doc, [
        ["buildDatePicker(id, initialValue)", "Bygger komponenten i elementet med det givne id. Accepts ISO-dato eller tom streng."],
        ["readDatePicker(id)",                "Returnerer den valgte dato som ISO-streng (YYYY-MM-DD)."],
        ["setDatePicker(id, iso)",            "Opdaterer display og hidden-felt til en ny ISO-dato. Opdaterer også kalender-griddet."],
    ])
    body(doc, "Bruges på to steder i applikationen:")
    bullet(doc, "Medarbejdermodal: 'Ansættelsesdato' og 'Fratrædelsesdato'.")
    bullet(doc, "Aktivitetsoversigt: Datovælgeren i periodelinjen (hop til dato).")
    note_box(doc,
        "Popup'en bruger position:fixed og getBoundingClientRect() for korrekt placering "
        "inde i scrollbare modaler. Specialtilfældet 9999-12-31 (ingen fratrædelse) "
        "vises som '31-12-9999' og åbner kalenderen ved indeværende år.",
        "TEKNISK NOTE"
    )

    heading(doc, "Filtrering", 2, "9.5")
    body(doc, "Aktivitetstabellen har tre filtre der kombineres:")
    two_col_table(doc, [
        ["Status-filter",      "Alle / Afventer / Godkendt / Deaktiveret"],
        ["Medarbejder-filter", "Viser kun aktiviteter for valgte medarbejder. Opdateres automatisk når afdelingsfilter ændres."],
        ["Afdelings-filter",   "Filtrerer aktivitetstabellen OG medarbejder-dropdown til kun at vise medarbejdere i den valgte disponentgruppe."],
    ])

    heading(doc, "Stamdata-view", 2, "9.6")
    body(doc, (
        "Stamdata-view aktiveres fra menupunktet '⚙️ Stamdata' i venstre menu (kræver 'stamdata'-rettighed). "
        "View'et indeholder en tab-navigator med ti faner – kun én pane er synlig ad gangen:"
    ))
    two_col_table(doc, [
        ["switchStamdataTab(tab)", "Skifter aktiv pane og opdaterer fane-styling (border, farve, vægt)."],
        ["loadStamdata()",         "Kaldes fra setView('stamdata') og indlæser data til alle ti faner parallelt."],
        ["btn-stamdata-add-*",     "'+Tilføj'-knap i toolbar vises kun for den aktive fane."],
    ])
    body(doc, (
        "Fraværstyper-fanen viser alle rækker fra master_absence_types med Aktiv-badge (grøn/grå). "
        "Alle typer har Rediger- og Slet-knap. "
        "Løntypekoder-fanen giver mulighed for at redigere type (label), Danløn-kode, Medtag i CSV, "
        "Antal-type (Timer/Antal), Sats-kilde, Inkluder sats og Inkluder total samt slette alle koder. "
        "Alle disse felter kan også sættes ved oprettelse af en ny løntypekode."
    ))
    body(doc, (
        "Aftale-fanen viser rækkerne fra master_agreement_kinds med badges for Type "
        "(System/Brugeroprettet), Kræver overenskomsttype (Ja/Nej) og Aktiv. Systemtyperne har "
        "kun en Rediger-knap (label/aktiv/kræver overenskomsttype); brugeroprettede typer har "
        "desuden en Slet-knap. loadStamdataAgreementKinds() genindlæser efter hver ændring også "
        "state.agreementKinds via GET /api/employees/agreement-kinds, så medarbejder-modalens "
        "'Aftale'-dropdown (fillAgreementKindSelect()) altid er opdateret uden sideopdatering. "
        "onAgreementKindChange() slår den valgte types requires_agreement_type op og viser/skjuler "
        "den røde stjerne ved Overenskomsttype-feltet i medarbejder-modalen."
    ))

    heading(doc, "Pausehåndtering i oprettelsesmodalen", 2, "9.7")
    body(doc, (
        "Når en manuel aktivitet oprettes, kan der tilføjes et vilkårligt antal pauser via "
        "'+ Tilføj pause'-knappen. Pauserne gemmes i databasefeltet pause_intervals og fratrækkes "
        "automatisk i lønberegning, varighedsvisning og aktivitetsfordeling."
    ))
    header_table(doc,
        ["Funktion (app.js)", "Beskrivelse"],
        [
            ["addManualPause()",      "Læser startdato fra aktivitetens starttid og åbner modal-pause med dt-picker (datofeltet skjult – kun HH:MM vises)."],
            ["confirmPause()",        "Validerer at slut > start, tilføjer [ISO-start, ISO-slut] til manualPauses[] og lukker modal-pause."],
            ["deleteManualPause(idx)","Fjerner pause ved index fra manualPauses[] og opdaterer listen."],
            ["renderManualPauses()", "Tegner #manual-pauses-list med pause-badges og ×-slet-knapper."],
        ]
    )
    body(doc, "Pauseinterval-flow ved POST af aktivitet:")
    for step in [
        "manualPauses[] sendes som pause_intervals i POST-body til POST /api/activities.",
        "ActivityCreate-skemaet validerer listen (list[list[str]]).",
        "_duration_minutes(a) i activities.py klipper hvert interval til aktivitetens bounds og fratrækker det fra bruttotiden. Påvirker is_under_4h og is_over_12h.",
        "_to_response() sender pause_minutes med i ActivityResponse (bruttovarighed minus _duration_minutes(a)), så arbejdstid + pause altid giver vagtens længde. renderCellActivity() i app.js viser feltet i aktivitetens tooltip.",
        "calculate_overtime() i overtime.py bruger _subtract_pauses() til at fratrække pauserne i det korrekte tillægsvindue.",
        "openActivityDetail() i app.js beregner Aktivitetsfordeling-bjælken: for manuelle aktiviteter uden tachografsegmentdata beregnes Pause-% fra pause_intervals og Effektiv tid-% som resten.",
    ]:
        bullet(doc, step)
    note_box(doc,
        "Pausemodalen (modal-pause) bruger buildDatetimePicker med datofeltet skjult – "
        "brugeren ser kun HH:MM. Datoen arves fra aktivitetens startdato.",
        "TEKNISK NOTE"
    )

    heading(doc, "Validering ved oprettelse af manuel aktivitet", 2, "9.8")
    body(doc, (
        "confirmManualActivity() (app.js) udfører to klient-side valideringstjek, BEGGE UDEN "
        "server-side modstykke i create_manual_activity() (activities.py) – backend stoler på "
        "at frontend har valideret, og afviser hverken et tomt/ukendt vognnummer eller en "
        "kørsels-/fraværskonflikt med en HTTPException."
    ))
    header_table(doc,
        ["Tjek", "Trigger", "Adfærd"],
        [
            ["Vognnummer",             "Alle typer UNDTAGEN overnatning og den interne '__none__' (kun vagtplan-kommentar) typen – altså også fraværstyper, ikke kun 'normal tid'.", "Tomt felt → toast-fejl, ingen modal. Udfyldt men matcher hverken en vogns registration_number eller vehicle_number i state.vehicles → modal-reg-error ('Ukendt registreringsnummer' – 'Registreringsnummeret er ikke genkendt fra Vognparken. Opret køretøjet før du opretter aktiviteten.')."],
            ["Kørsel-/fraværskonflikt","Ved oprettelse af en fraværstype (evt. som periode) hvis der allerede findes en ikke-deaktiveret 'normal tid'-aktivitet for medarbejderen på (en af) datoen/datoerne.", "modal-absence-conflict ('Advarsel: kørsel på samme dag' – lister de berørte datoer). 'Annuller' afbryder uden at sende noget; 'Fortsæt alligevel' sætter et engangsflag og gennemfører oprettelsen uden yderligere spørgsmål."],
        ],
        [Cm(3.5), Cm(6), Cm(6.5)]
    )

    heading(doc, "Vognnummer-søgefelt: tastaturnavigation", 2, "9.9")
    body(doc, (
        "Tilføjet 2026-09-17 (_renderManualRegDropdown()/_moveManualRegHighlight()/"
        "_selectManualRegHighlighted() i app.js): vognnummer-feltet i opret-aktivitet-modalen "
        "kan nu betjenes uden mus. Pil ned/Tab flytter markeringen én række ned i "
        "søgeresultat-listen (wrapper til første række efter sidste), Shift+Tab/Pil op flytter "
        "op, Enter vælger den markerede række, og Escape lukker dropdown'en uden at vælge. "
        "_manualRegHighlightIndex (modul-scope) holder styr på den aktuelt markerede række og "
        "nulstilles ved hvert nyt søgeopslag."
    ))

    # ── 10. Drift og vedligehold (FAQ) ────────────────────────────────────────
    doc.add_page_break()
    heading(doc, "Drift og vedligehold – ofte stillede spørgsmål", 1, "10")

    heading(doc, "Hvor er databasen, og hvordan kører den?", 2, "10.1")
    body(doc, (
        "Databasen er én enkelt fil: app/database/lonsystem.db. "
        "SQLite er ikke et separat program der skal startes – Python-koden "
        "læser og skriver direkte i filen. Ingen databaseserver, ingen porte, "
        "ingen baggrundstjeneste. Systemet opretter automatisk en ny, tom database "
        "første gang det startes, hvis filen ikke eksisterer."
    ))
    two_col_table(doc, [
        ["Placering",   "app/database/lonsystem.db"],
        ["Størrelse",   "Starter ved ~140 KB, vokser efterhånden som data opbygges"],
        ["Backup",      "Kopiér filen (mens serveren er stoppet) for at tage backup"],
        ["Nulstilling", "Slet filen – systemet opretter en tom database ved næste opstart"],
    ])

    note_box(doc,
        "Filen bør IKKE ligge i en OneDrive- eller Dropbox-mappe når systemet er i produktion. "
        "Cloud-synkronisering og SQLite konflikter og kan i sjældne tilfælde korruptere databasen. "
        "På en produktionsserver skal filen ligge lokalt på serveren.",
        "VIGTIGT"
    )

    heading(doc, "Hvordan starter og stopper jeg serveren?", 2, "10.2")
    body(doc, "Serveren (uvicorn) er den proces der holder systemet kørende og svarer på browser-forespørgsler.")

    p = doc.add_paragraph()
    r = p.add_run("Stop serveren")
    r.bold = True; r.font.name = "Arial"; r.font.size = Pt(11)
    body(doc, "Tryk Ctrl+C i det terminalvindue hvor uvicorn kører.", space_after=2)
    body(doc, "Alternativt: Åbn Task Manager → find python.exe → Afslut opgave.", space_after=6)

    p2 = doc.add_paragraph()
    r2 = p2.add_run("Start serveren")
    r2.bold = True; r2.font.name = "Arial"; r2.font.size = Pt(11)

    body(doc, "Der er to måder at starte serveren på, afhængigt af situationen:", space_after=4)

    body(doc, "Daglig drift (anbefalet):", space_after=2)
    code = doc.add_paragraph()
    code.paragraph_format.left_indent = Cm(1)
    code.paragraph_format.space_after = Pt(4)
    cr = code.add_run(
        'python.exe -m uvicorn --app-dir app main:app --host 0.0.0.0 --port 8000'
    )
    cr.font.name = "Courier New"; cr.font.size = Pt(9)
    body(doc, "Hurtig og stabil. Ændringer i Python-filer kræver manuel servergenstart (Ctrl+C → start igen).", space_after=8)

    body(doc, "Under udvikling (når programmet ændres af en udvikler):", space_after=2)
    code2 = doc.add_paragraph()
    code2.paragraph_format.left_indent = Cm(1)
    code2.paragraph_format.space_after = Pt(4)
    cr2 = code2.add_run(
        'python.exe -m uvicorn --app-dir app main:app --host 0.0.0.0 --port 8000 --reload'
    )
    cr2.font.name = "Courier New"; cr2.font.size = Pt(9)
    body(doc, (
        "Med --reload genstarter serveren automatisk hver gang en Python-fil gemmes, "
        "så ændringer træder i kraft ved næste browser-reload uden manuel genstart. "
        "Lidt langsommere end daglig drift, men bekvem under aktiv udvikling."
    ), space_after=8)

    body(doc, (
        "Når serveren kører, er systemet tilgængeligt i browseren på "
        "http://127.0.0.1:8000 (lokal maskine) eller serverens IP-adresse "
        "på netværket."
    ))

    note_box(doc,
        "Ændringer i JavaScript-, CSS- og HTML-filer (app.js, style.css, index.html) "
        "træder altid i kraft ved browser-reload – uanset om serveren kører med eller uden --reload. "
        "Det er kun ændringer i Python-filer (.py) der kræver servergenstart.",
        "BEMÆRK"
    )

    heading(doc, "Hvad kræves for at flytte systemet til en fælles server?", 2, "10.3")
    body(doc, (
        "Da systemet er bygget som en webapplikation er det designet til delt brug. "
        "Alle ansatte tilgår det via en browser – ingen installation på klientmaskinen. "
        "Flytningen til en fælles server kræver:"
    ))
    for step in [
        "En dedikeret maskine (eksisterende server, spare-PC eller cloud-VM) der er tændt i arbejdstiden.",
        "Python 3.13 installeret på serveren.",
        "Koden og databasefilen kopieret til serveren (uden for en cloud-synkroniseret mappe).",
        "En fast lokal IP-adresse på servermaskinen (konfigureres i router eller af IT).",
        "Serveren sat op til at starte uvicorn automatisk ved opstart – på den nuværende produktionsserver løst via Windows Task Scheduler-opgaver (ikke en egentlig Windows-tjeneste/NSSM), se deploy/PRODUKTION_OPSAETNING.md for den fulde, trin-for-trin opsætning inkl. auto-deploy og natlig genstart.",
        "Ansatte åbner browseren og går til serverens IP-adresse og port, f.eks. http://192.168.1.50:8000.",
    ]:
        bullet(doc, step)

    note_box(doc,
        "Hvis systemet skal tilgås uden for virksomhedens netværk (hjemmefra, fra mobil), "
        "kræves enten VPN-adgang til netværket eller en cloudserver med HTTPS-certifikat. "
        "Dette er en IT-beslutning der også indebærer en GDPR-vurdering af datalokation.",
        "BEMÆRK"
    )

    heading(doc, "Hvordan ryddes testdata og systemet gøres klar til produktion?", 2, "10.4")
    body(doc, "Følgende fremgangsmåde sikrer et rent produktionssystem:")
    for i, step in enumerate([
        "Stop serveren (Ctrl+C eller Task Manager).",
        "Notér alle rigtige medarbejdere der skal oprettes: lønnumre, førerkortnumre, overenskomsttyper, timefordeling og afdelinger.",
        "Slet filen app/database/lonsystem.db.",
        "Kontrollér at Excel-filerne (Overtid satser.xlsx, Overenskomsttyper og timesatser.xlsx, Fraværstyper.xlsx) indeholder de korrekte satser – de bruges som udgangspunkt for seeding af Stamdata-tabellerne.",
        "Start serveren igen – systemet opretter automatisk en tom database og seeder Stamdata-tabellerne fra Excel-filerne.",
        "Kontrollér og juster om nødvendigt satser og fraværstyper i Stamdata-modulet (⚙️ Stamdata i menuen).",
        "Opret de rigtige medarbejdere i systemet.",
        "Systemet er klar til produktionsbrug.",
    ], 1):
        bullet(doc, step, f"Trin {i}: ")

    body(doc, (
        "Excel-filerne bruges kun til den initiale seeding. Efterfølgende ændringer i satser og "
        "fraværstyper skal foretages via Stamdata-modulet i brugerfladen – ikke i Excel-filerne."
    ))

    # ── 11. Backup-utility ────────────────────────────────────────────────────
    doc.add_page_break()
    heading(doc, "Backup-utility", 1, "11")
    body(doc, (
        "Systemet leveres med et separat backup-utility der kører automatisk 4 gange "
        "dagligt og bevarer de seneste 5 dages backup-historik. Utility'et ligger i "
        "backup/-mappen ved siden af app/-mappen."
    ))

    heading(doc, "Filer", 2, "11.1")
    two_col_table(doc, [
        ["backup/backup.py",       "Selve backup-scriptet. Kan køres manuelt eller via Task Scheduler."],
        ["backup/installer.ps1",   "PowerShell-script der registrerer backup-opgaven i Windows Task Scheduler."],
        ["backup/arkiv/",          "Mappe med ZIP-filer – én pr. kørsel."],
        ["backup/backup.log",      "Logfil med tidsstempler og resultater for alle kørsler."],
    ])

    heading(doc, "Hvad der tages backup af", 2, "11.2")
    two_col_table(doc, [
        ["app/database/lonsystem.db",                    "Databasen – det vigtigste. Kopieres via SQLites eget backup-API, sikkert mens systemet kører."],
        ["app/Overtid satser.xlsx",                      "Overtidssatser."],
        ["app/Overenskomsttyper og timesatser.xlsx",     "Timesatser og overenskomsttyper."],
        ["app/Afdelinger.xlsx",                          "Historisk Excel-fil – disponentgrupper læses ikke længere herfra, men fra databasetabellen dispatcher_groups (se afsnit 2.1)."],
    ])
    body(doc, (
        "Hvert backup gemmes som en ZIP-fil med navneformatet lonsystem_YYYY-MM-DD_HH-MM.zip. "
        "ZIP-filer ældre end 5 dage slettes automatisk. Med 4 kørsler dagligt i 5 dage "
        "er der til enhver tid 20 backups i arkivet."
    ))

    heading(doc, "Teknisk detalje – sikker kopiering", 2, "11.3")
    body(doc, (
        "SQLite-databasen kopieres via Pythons sqlite3.backup()-metode. Denne metode "
        "bruger SQLites interne backup-API og producerer en konsistent snapshot selv "
        "om der skrives til databasen samtidig (WAL-mode). Det er ikke sikkert blot "
        "at kopiere .db-filen direkte med shutil.copy() mens systemet kører."
    ))

    heading(doc, "Installation", 2, "11.4")
    body(doc, "Kør installer.ps1 én gang som Administrator:")
    for i, step in enumerate([
        "Søg på 'PowerShell' i Start-menuen.",
        "Højreklik → Kør som administrator.",
        'Kør: & "...\\backup\\installer.ps1"',
        "Test med: Start-ScheduledTask -TaskName \"Lønsystem Backup\"",
    ], 1):
        bullet(doc, step, f"Trin {i}: ")

    body(doc, (
        "Opgaven kører som NT AUTHORITY\\SYSTEM og kræver ingen gemt adgangskode. "
        "Den kører selv når ingen bruger er logget ind på serveren."
    ))

    heading(doc, "Gendannelse fra backup", 2, "11.5")
    for i, step in enumerate([
        "Stop serveren (uvicorn).",
        "Pak den ønskede ZIP-fil ud.",
        "Kopier lonsystem.db til app/database/lonsystem.db (erstat den eksisterende).",
        "Kopier eventuelt Excel-filerne tilbage til app/ hvis de også er beskadigede.",
        "Start serveren igen.",
    ], 1):
        bullet(doc, step, f"Trin {i}: ")

    # ── 12. Netværksadgang og adgang fra andre maskiner ────────────────────
    heading(doc, "Netværksadgang fra andre maskiner", 1, "12")
    body(doc, (
        "Systemet er designet til at køre på én server og tilgås fra mange klientmaskiner "
        "via en webbrowser. Der kræves ingen installation på klientmaskinerne."
    ))

    heading(doc, "Forudsætninger", 2, "12.1")
    two_col_table(doc, [
        ["--host 0.0.0.0",          "Uvicorn skal lytte på alle netværksgrænseflader (ikke kun 127.0.0.1). Sat i .claude/launch.json."],
        ["Windows Firewall",        "Port 8000 skal åbnes for indgående TCP-trafik på det private netværk."],
        ["Fast lokal IP-adresse",   "Servermaskinens IP bør være fast (konfigureres i router eller netværksindstillinger)."],
    ])

    heading(doc, "Åbn port 8000 i Windows Firewall", 2, "12.2")
    body(doc, "Kør én gang som Administrator i PowerShell:")
    code = doc.add_paragraph()
    code.paragraph_format.left_indent = Cm(1)
    code.paragraph_format.space_after = Pt(8)
    cr = code.add_run(
        'New-NetFirewallRule -DisplayName "Lønsystem port 8000" '
        '-Direction Inbound -Protocol TCP -LocalPort 8000 '
        '-Action Allow -Profile Private'
    )
    cr.font.name = "Courier New"; cr.font.size = Pt(9)

    heading(doc, "Find serverens IP-adresse", 2, "12.3")
    body(doc, "Kør ipconfig i PowerShell og aflæs IPv4 Address under det aktive netværkskort:")
    code2 = doc.add_paragraph()
    code2.paragraph_format.left_indent = Cm(1)
    code2.paragraph_format.space_after = Pt(8)
    cr2 = code2.add_run("ipconfig | Select-String 'IPv4'")
    cr2.font.name = "Courier New"; cr2.font.size = Pt(9)

    heading(doc, "Tilgang fra klientmaskine", 2, "12.4")
    body(doc, (
        "Åbn en webbrowser på klientmaskinen og gå til serverens IP-adresse og port 8000. "
        "Eksempel hvis serverens IP er 192.168.1.29:"
    ))
    code3 = doc.add_paragraph()
    code3.paragraph_format.left_indent = Cm(1)
    code3.paragraph_format.space_after = Pt(8)
    cr3 = code3.add_run("http://192.168.1.29:8000")
    cr3.font.name = "Courier New"; cr3.font.size = Pt(9)

    note_box(doc,
        "Adressen 127.0.0.1 eller localhost virker kun på selve servermaskinen. "
        "Andre maskiner skal bruge serverens rigtige IP-adresse på netværket.",
        "OBS"
    )

    # ── 13. Lønafregning ──────────────────────────────────────────────────
    doc.add_page_break()
    heading(doc, "Lønafregning", 1, "13")
    body(doc, (
        "Lønafregning (routers/payroll_settlement_router.py) er en selvstændig fane placeret "
        "under 'Lønkørsel' i venstre menu. Den viser periodetotaler og en 14-dages tabel pr. "
        "medarbejder, og genbruger _calculate_employee() (payroll_router.py) som eneste "
        "beregningskilde – ingen lønmatematik er duplikeret."
    ))
    body(doc, (
        "I modsætning til de fleste andre visninger har Lønafregning ingen egen "
        "periode-navigation. Siden følger i stedet den globale periode (state.currentPeriodStart), "
        "som vælges via frem/tilbage-pilene i Aktivitetsoversigten – nøjagtig samme mekanisme "
        "som Lønkørsel allerede bruger. Uden valgt periode falder den tilbage til dagens periode."
    ))

    heading(doc, "API-endepunkter", 2, "13.1")
    header_table(doc,
        ["Endepunkt", "Metode", "Beskrivelse"],
        [
            ["/api/payroll-settlement/preview",          "GET",  "JSON med periodetotaler og pr.-medarbejder headline + 14-dages tabel. Parameter period_start (valgfri, default dagens periode)."],
            ["/api/payroll-settlement/export-csv",       "POST", "Genererer CSV-filen og downloader den til browseren (siden 2026-09-09 – tidligere blev filen gemt i en brugervalgt mappe på serveren). Kræver låst periode – se afsnit 13.3."],
        ]
    )
    body(doc, (
        "Begge endepunkter kræver rettigheden payroll_settlement_view; export-csv kræver "
        "derudover payroll_settlement_export. Se afsnit 11.3/rettighedsoversigten i Brugervejledningen."
    ))

    heading(doc, "Beregningslogik og fraværsbetaling", 2, "13.2")
    body(doc, (
        "_employee_settlement_data() (payroll_settlement_router.py) kalder _calculate_employee() "
        "og lægger to ting oveni: (1) overenskomstsats og personligt tillæg vises som to adskilte "
        "tal i stedet for kun den kombinerede hourly_rate, og (2) springertillæg (normalt usynligt "
        "i Lønkørsel-visningen) lægges til medarbejderens totale løn med eget kr-beløb."
    ))
    body(doc, (
        "Fraværstyper med en etableret betalingsregel viser deres egne timer og beløb i dagens "
        "række (i stedet for 0,00) OG tæller med i medarbejderens 'Total løn' samt periodens "
        "samlede total. Følgende typer er dækket, hver med sin egen linje i topsummeringen "
        "'Total sum for perioden' (kun vist hvis beløbet er større end 0 kr):"
    ))
    header_table(doc,
        ["Fraværstype", "Sats der bruges"],
        [
            ["Sygdom, Barn 1.sygedag, Graviditetsbetinget sygdom", "Medarbejderens timesats (hourly_rate)"],
            ["§56 syg, Barn 1.sygedag u. 8 uger", "Dagpengesats (Stamdata → Tillæg, 'Dagpenge §56')"],
            ["Sygdom u. 8 uger", "Ulønnet – altid 0 kr., men timerne vises"],
            ["Barsel, Feriefri, Ferie, Skole/kursus, Afspadsering", "Medarbejderens timesats (hourly_rate)"],
        ]
    )
    note_box(doc,
        "Feriefri vises som ÉN samlet linje uanset om medarbejderen er fuldlønnet eller "
        "timelønnet – emp.fuldloennet afgør i den almindelige Danløn-CSV kun hvilken kode "
        "(FERIEFRI_FULDLOENNET/-TIMELOENNET) timerne rapporteres under, ikke selve beløbet, "
        "som beregnes ens i begge tilfælde (hours × hourly_rate). Bekræftet af bruger 2026-08-25.",
        "TEKNISK NOTE"
    )
    body(doc, (
        "Selvbetalt fridag, Løn andet sted fra (afsnit 7.9), Barn 2-3.sygedag, Barsel u. løn og "
        "typen 'Fri' har ingen etableret betalingsregel i systemet (samme som i den almindelige "
        "Danløn CSV) og har derfor hverken beløb i dagsrækken eller egen linje i topsummeringen."
    ))
    body(doc, (
        "'Total uden fravær' er en delsum der lægger Grundtimeløn inkl. tillæg, Overtid Timen "
        "før, Overtid 1-3 time efter og Øvrig overtid sammen – IKKE salttillæg, overnatning eller "
        "nogen fraværstype. Den samlede 'Total sum for denne periode' er summen af alle "
        "medarbejderes fulde total_kr (arbejdstid + salt + springer + al fraværsbetaling)."
    ))
    body(doc, (
        "Rettet 2026-09-21: Overnatning og DOB Overnatning manglede tidligere helt i "
        "topsummeringens 'Total sum for denne periode' og i den enkelte medarbejders total – "
        "beløbene (overnight_kr/dob_overnight_kr) lægges nu oveni total_kr på samme måde som "
        "springer_kr/absence_kr_total. Topsummeringen viser dem som to selvstændige linjer "
        "'Overnatning (N gange)' og 'DOB Overnatning (N gange)', placeret lige efter Salttillæg – "
        "men de tæller fortsat IKKE med i delsummen 'Total uden fravær' (samme princip som "
        "Salttillæg: vist separat, men inkluderet i den store total)."
    ))

    heading(doc, "CSV-eksportformat", 2, "13.3")
    body(doc, (
        "CSV-filen (semikolon-separeret, UTF-8) indeholder KUN data pr. medarbejder – "
        "topsummeringen 'Total sum for perioden' skrives ikke med. For hver medarbejder skrives "
        "én række pr. dag i perioden (alle 14, også dage uden aktivitet), efterfulgt af én "
        "'Total løn for [navn]'-række:"
    ))
    header_table(doc,
        ["Kolonne", "Indhold"],
        [
            ["Dato",                        "dd-mm-åååå"],
            ["Lønnummer",                   "Medarbejderens employee_number"],
            ["Normal timer … Øvrig overtid","Format T:mm (fx '7:30'), ikke decimaltal"],
            ["Total tid",                   "Decimaltal med komma (fx '7,50')"],
            ["Total i kr. / Beløb",         "Dansk kr-format (fx '1.234,56'), identiske værdier"],
            ["Vognnummer",                  "Aktivitetens vognnummer – overskrives af fraværstypens navn på fraværsdage"],
        ]
    )
    body(doc, (
        "Eksport kræver at den valgte periode er låst (status 'closed') – knappen giver en "
        "fejlbesked og udfører intet, hvis perioden stadig er åben. Administratorer er undtaget "
        "og kan altid eksportere, uanset periodens status. Eksport LÅSER ikke selv perioden "
        "(det gør kun 'Kør løn' under Lønkørsel)."
    ))

    # ── 14. Dagsplan ─────────────────────────────────────────────────────
    doc.add_page_break()
    heading(doc, "Dagsplan", 1, "14")
    body(doc, (
        "Dagsplan (routers/dagsplan_router.py) digitaliserer den daglige fordeling af vogne til "
        "chauffører, der tidligere foregik manuelt i et Excel-ark uden for systemet. Siden kobler "
        "sig til data der allerede findes i systemet: medarbejdere, vognpark, vagtplan/fravær og "
        "Aktivitetsoversigten. Databasemodellerne er beskrevet i afsnit 2.7-2.8."
    ))

    heading(doc, "Permissions", 2, "14.1")
    two_col_table(doc, [
        ["dagsplan_view", "Se Dagsplan-siden (begge underfaner Dagsplan og Materiel fravær), read-only."],
        ["dagsplan_edit", "Redigere tildelinger, afkrydse 'informeret', melde/fjerne materielt fravær."],
    ])
    body(doc, (
        "Tilføjes idempotent ved opstart (samme mønster som manage_baselines-permissionen). "
        "'admin' får dem automatisk som systemrolle; øvrige roller tildeles dem ikke som default, "
        "men kan gives det via rolle-editoren."
    ))

    heading(doc, "API-endepunkter", 2, "14.2")
    header_table(doc,
        ["Endepunkt", "Metode", "Rettighed", "Beskrivelse"],
        [
            ["/api/dagsplan?date=",            "GET",    "dagsplan_view", "Samlet svar for én dag: vehicles (filtrerbar på disponentgruppe/medarbejder) + employees (altid ufiltreret, farvestatus + fraværstekst)."],
            ["/api/dagsplan/assignment",       "PATCH",  "dagsplan_edit", "Upsert på (date, vehicle_id). Body: {date, vehicle_id, employee_id?, task?, informed?}."],
            ["/api/dagsplan/extra-assignment", "PATCH",  "dagsplan_edit", "Upsert på en af de 10 faste EKSTRA-rækker."],
            ["/api/vehicle-absences?date=",    "GET",    "dagsplan_view", "Materielt fravær der er aktivt på den angivne dato."],
            ["/api/vehicle-absences",          "POST",   "dagsplan_edit", "Meld materielt fravær. Body: {vehicle_id, date_from, date_to?, comment}."],
            ["/api/vehicle-absences/{id}",     "DELETE", "dagsplan_edit", "Fjern en materielt fravær-registrering."],
        ],
        [Cm(4), Cm(2), Cm(3), Cm(7.5)]
    )
    body(doc, (
        "vehicles.py (VehicleCreate/VehicleUpdate/VehicleResponse) og employees.py "
        "(EmployeeCreate/EmployeeUpdate/EmployeeResponse) er udvidet med hhv. "
        "description/dispatcher_group_id og fast_bil/fast_bil_vehicle_id – uændrede permissions "
        "(manage_vehicles/manage_employees)."
    ))

    heading(doc, "Farvestatus og mismatch-advarsel", 2, "14.3")
    body(doc, (
        "Medarbejderlisten i GET /api/dagsplan farvekoder hver medarbejder efter forrang "
        "gul > rød > grøn > grå: gul (comment_only – vagtplan-kommentar uden egentligt fravær), "
        "rød (absent – registreret fravær den dag), grøn (assigned – tildelt en vogn/EKSTRA-plads) "
        "og grå (none – hverken tildelt eller fraværende). En medarbejder med fravær forbliver gul "
        "selv når vedkommende samtidig er skrevet i chauffør-kolonnen."
    ))
    body(doc, (
        "For hver tildelt medarbejder slås dagens 'normal'-type aktiviteter op. Findes mindst én "
        "med et vehicle_number der afviger fra den tildelte vogns vehicle_number, sættes "
        "mismatch_vehicle_number til den afvigende værdi – vist i frontend som et ⚠️-ikon med "
        "tooltip 'vognnummer i løn: xxx'. Andre aktivitetstyper (fravær) indgår ikke i "
        "sammenligningen."
    ))

    heading(doc, "Autoudfyld af vognnummer", 2, "14.4")
    body(doc, (
        "create_manual_activity() (activities.py) slår daily_plan_assignments op på "
        "(employee_id, start_time.date()), når en 'normal tid'-aktivitet oprettes med tomt "
        "vehicle_number. Findes en tildeling med en vogn, udfyldes vehicle_number automatisk fra "
        "den. Gælder KUN 'normal tid' og overskriver aldrig et allerede udfyldt vognnummer – den "
        "eksisterende disponentgruppe-baserede autoudfyldning for fraværstyper "
        "(applyDispatcherGroupVehicleDefault() i frontend) er uændret og upåvirket. "
        "applyDagsplanVehicleDefault() i app.js udfører den tilsvarende autoudfyldning i "
        "frontend-formularen inden POST sendes."
    ))
    note_box(doc,
        "'EKSTRA'-rækkerne indgår aldrig i denne autoudfyldning (der er intet rigtigt vognnummer "
        "at udfylde med), og de indgår heller ikke i nogen lønberegning – kun 'Fast bil'/rigtige "
        "vogne gør. Se docs/superpowers/specs/2026-09-09-dagsplan-design.md for det fulde design.",
        "TEKNISK NOTE"
    )

    # ── 15. Vagtplan ─────────────────────────────────────────────────────
    doc.add_page_break()
    heading(doc, "Vagtplan", 1, "15")
    body(doc, (
        "Vagtplan (routers/vagtplan_comments.py, 2026-08-21) er en flerugers oversigt over alle "
        "medarbejderes fravær og frie kommentarer, bygget oven på de samme render-funktioner som "
        "Aktivitetsoversigten (renderCellActivity, openManualActivityModal, openActivityDetail) i "
        "stedet for at duplikere dem. Backend er additivt: én ny tabel (vagtplan_comments) og én "
        "ny forespørgselstilstand på det eksisterende GET /api/activities-endepunkt."
    ))

    heading(doc, "Datamodel", 2, "15.1")
    header_table(doc,
        ["Felt", "Type", "Beskrivelse"],
        [
            ["employee_id", "FK → Employee", "Tilknyttet medarbejder"],
            ["date",        "Date",          "Den dag kommentaren gælder for"],
            ["comment",     "Text",          "Fri tekst"],
        ]
    )
    body(doc, (
        "Unik constraint på (employee_id, date) – kun én kommentar pr. medarbejder pr. dag. "
        "POST fungerer som upsert (opret/overskriv)."
    ))

    heading(doc, "API-endepunkter", 2, "15.2")
    header_table(doc,
        ["Endepunkt", "Metode", "Rettighed", "Beskrivelse"],
        [
            ["/api/vagtplan-comments?from=&to=&employee_id=", "GET",    "vagtplan_view",                       "Kommentarer i en datointerval, valgfrit filtreret på medarbejder."],
            ["/api/vagtplan-comments",                        "POST",   "vagtplan_edit_own / vagtplan_edit_all", "Opret/overskriv kommentar (upsert). 'edit_own' tillader kun brugerens egen række (matches på initialer mod medarbejderens initials-felt)."],
            ["/api/vagtplan-comments/{id}",                   "DELETE", "vagtplan_edit_own / vagtplan_edit_all", "Slet kommentar."],
            ["/api/activities?date_from=&date_to=",           "GET",    "vagtplan_view",                       "Ny forespørgselstilstand på det eksisterende aktivitets-endepunkt: frit datointerval i stedet for period_start – bruges kun af Vagtplan."],
        ]
    )
    note_box(doc,
        "'Redigér egen linje' (vagtplan_edit_own) matcher udelukkende på Employee.initials mod "
        "den indloggede brugers AppUser.initials – der er INGEN eksplicit kobling mellem en "
        "AppUser-konto og et Employee-id ud over dette tekstmatch. Stemmer initialerne ikke "
        "overens, kan brugeren ikke redigere sin egen linje, selv med vagtplan_edit_own.",
        "TEKNISK NOTE"
    )

    heading(doc, "Frontend", 2, "15.3")
    body(doc, (
        "DAYS_PER_VAGTPLAN_VIEW = 21 (app.js) – griddet viser 21 dage (3 uger: forrige, "
        "nuværende og næste) med ISO-ugenummer i kolonneoverskriften. "
        "_vagtplanDefaultWeekStart() sætter default-vinduet til mandagen I UGEN FØR den "
        "nuværende, så den aktuelle uge lander i midten af de tre viste uger. ‹/› "
        "(navigateVagtplan()) flytter vinduet ±7 dage (én uge) ad gangen – IKKE et helt "
        "3-ugers-spring – og '📅 I dag' (jumpToVagtplanToday()) nulstiller til default-vinduet. "
        "*(Rettet 2026-09-15, commit 570a627 – vinduet var oprindeligt 28 dage/4 uger med "
        "helvindues-paging.)*"
    ))
    body(doc, (
        "Klik på en tom celle åbner samme opret-aktivitet-modal som Aktivitetsoversigten, men med "
        "en ekstra aktivitetstype 'Ingen (kun kommentar)' der IKKE opretter en Activity-række, "
        "kun en VagtplanComment. Klik på en eksisterende fraværs- eller kommentarcelle åbner hhv. "
        "den almindelige aktivitetsdetalje eller en dedikeret rediger/slet-kommentar-modal."
    ))
    body(doc, (
        "'Fravær i morgen'-knappen viser en opsummeringsmodal med alle medarbejdere (inden for "
        "det valgte disponentgruppe-filter) der har fravær eller en kommentar registreret på "
        "dagen efter dags dato – et hurtigt overblik uden at skulle bladre til næste uge."
    ))

    # ── 16. Fraværsoversigt ──────────────────────────────────────────────
    doc.add_page_break()
    heading(doc, "Fraværsoversigt", 1, "16")
    body(doc, (
        "Fraværsoversigt (routers/absence_overview_router.py) viser aggregerede fraværstimer/"
        "-dage pr. medarbejder og pr. fraværstype over en valgfri datointerval, uafhængigt af "
        "lønperiodeinddelingen, samt en sats i kr/time pr. række."
    ))

    heading(doc, "API-endepunkter", 2, "16.1")
    header_table(doc,
        ["Endepunkt", "Metode", "Beskrivelse"],
        [
            ["/api/absence-overview/data",                "GET", "Fraværstotaler (timer/dage) + rate (kr/t) pr. medarbejder og -type for en fra/til-datointerval."],
            ["/api/absence-overview/employee-options",    "GET", "Medarbejdere + disponentgrupper til filterdropdowns."],
            ["/api/absence-overview/export-per-employee", "GET", "Excel-eksport: én række pr. kalenderdag med fravær pr. medarbejder. Filtreres på alle/disponentgruppe/enkelt medarbejder."],
            ["/api/absence-overview/export-per-type",     "GET", "Excel-eksport aggregeret pr. fraværstype. Filtreres på hvilke fraværstyper der skal medtages."],
        ]
    )
    body(doc, "Alle fire endepunkter kræver rettigheden 'absence_overview'.")

    heading(doc, "Satsberegning – egen, ikke-delt logik", 2, "16.2")
    body(doc, (
        "I MODSÆTNING til Lønafregning (kapitel 13), som eksplicit genbruger "
        "_calculate_employee() for at undgå duplikeret lønlogik, har Fraværsoversigt sin egen, "
        "selvstændige sats-beregning (_PAID_ABSENCE_TYPES/_FIXED_RATE_ABSENCE, "
        "absence_overview_router.py) – IKKE koblet til payroll_router.py."
    ))
    header_table(doc,
        ["Konstant", "Indhold", "Betydning"],
        [
            ["_PAID_ABSENCE_TYPES", "sygdom, barn_1sygedag, barn_2_3sygedag, barsel, graviditetsbetinget_sygdom, skole_kursus", "Disse typer vises med emp.hourly_rate (overenskomstsats + evt. personligt tillæg) som rate. Alle andre typer, der ikke er i denne mængde eller i _FIXED_RATE_ABSENCE, vises med rate=0."],
            ["_FIXED_RATE_ABSENCE",  "{'paragraf_56_syg': 137.43}",                                                             "Hardkodet kr-værdi direkte i koden – IKKE opslået fra Stamdata → Tillæg ('Dagpenge §56')."],
        ],
        [Cm(3.5), Cm(6), Cm(6.5)]
    )
    note_box(doc,
        "Kendt uoverensstemmelse med den øvrige lønlogik (Lønafregning/Danløn CSV, kapitel 13): "
        "(1) 137.43 for §56 syg er hardkodet her og opdateres IKKE hvis Stamdata → Tillæg → "
        "'Dagpenge §56' ændres – de to steder kan derfor vise forskellige satser for samme "
        "fraværstype. (2) _PAID_ABSENCE_TYPES udelader afspadsering, ferie og feriefri (som "
        "Lønafregning betaler til hourly_rate) samt barn_1sygedag_u_8uger (som Lønafregning "
        "betaler til dagpengesats) – disse vises derfor med rate=0 kr/t i Fraværsoversigt, selvom "
        "de reelt udbetales. Dette er formentlig utilsigtet drift, ikke en bevidst designbeslutning "
        "– bør rettes til at genbruge samme opslag som Lønafregning/_calculate_employee().",
        "VIGTIGT"
    )

    # ── 17. Vognpark ─────────────────────────────────────────────────────
    doc.add_page_break()
    heading(doc, "Vognpark", 1, "17")
    body(doc, (
        "Vognpark-siden (routers/vehicles.py) administrerer køretøjer. Databasemodellen er "
        "beskrevet i afsnit 2.7; dette kapitel dækker selve administrationsfladen."
    ))
    header_table(doc,
        ["Endepunkt", "Metode", "Rettighed", "Beskrivelse"],
        [
            ["/api/vehicles",       "GET",    "login",           "Liste over alle køretøjer."],
            ["/api/vehicles",       "POST",   "manage_vehicles", "Opret. Registration_number skal være unikt."],
            ["/api/vehicles/{id}",  "PATCH",  "manage_vehicles", "Rediger."],
            ["/api/vehicles/{id}",  "DELETE", "manage_vehicles", "Slet – blokeres (400) hvis vognens registration_number bruges af eksisterende aktiviteter."],
        ]
    )
    body(doc, (
        "Fra og med 2026-09-11 har hver vogn et boolean-felt 'vognpark' (default false). "
        "Vognpark-siden har to underfaner: 'Vognpark' (kun vogne med vognpark=true, standard-"
        "visningen) og 'Alle' (alle vogne, inkl. dem der reelt er afdelinger/interne poster). "
        "Dagsplans vognliste (kapitel 14) og medarbejder-modalens 'Fast bil'-dropdown filtreres "
        "BEGGE til kun vognpark=true – nyoprettede vogne vises derfor ikke i Dagsplan før feltet "
        "aktivt sættes. 'Meld materielt fravær'-vognsøgningen (afsnit 14.2) er upåvirket og viser "
        "fortsat alle vogne."
    ))
    note_box(doc,
        "Da default-værdien for vognpark er false, vil Dagsplans vognkolonne fremstå tom for "
        "alle vogne der er oprettet før denne funktion, indtil en administrator aktivt "
        "gennemgår Vognpark → fanen 'Alle' og markerer de relevante vogne.",
        "VIGTIGT"
    )

    # ── 18. Auto-godkendelse (statistisk baseline) ─────────────────────────
    doc.add_page_break()
    heading(doc, "Auto-godkendelse (statistisk baseline)", 1, "18")
    body(doc, (
        "To HELT ADSKILTE mekanismer deler ordet 'auto-godkendelse' i systemet – forveksl dem "
        "ikke ved videre læsning eller ved fejlfinding:"
    ))
    two_col_table(doc, [
        ["auto_approve_manual_activities", "Manuel oprettelse (activities.py: create_manual_activity()) sættes direkte til approved i stedet for pending, hvis den opretstende bruger har denne permission. Rent regelbaseret, ingen statistik. Beskrevet i afsnit 8.1/'Auto-godkend ved oprettelse'."],
        ["Statistisk baseline-auto-godkendelse (dette kapitel)", "Gælder KUN tachograf-importerede 'normal tid'-aktiviteter. Sammenligner en aktivitets varighed/starttid mod medarbejderens egen historik for den ugedag – styres af manage_auto_approval."],
    ])

    heading(doc, "Global til/fra-kontakt", 2, "18.1")
    body(doc, (
        "SystemSettings.auto_approval_enabled (id=1-rækken; mangler rækken helt, tolkes som "
        "slået TIL som default – is_auto_approval_enabled(), baseline_updater.py). "
        "GET /api/auto-approval/settings er åben for enhver logget ind bruger (så frontend kan "
        "skjule bulk-knappen); POST kræver manage_auto_approval og logger handlingen "
        "(toggle_auto_approval). UI: Stamdata → 'Auto-godkendelse'-fanen (#sd-tab-autoapproval, "
        "gated på manage_auto_approval), status-badge + til/fra-knap."
    ))

    heading(doc, "should_auto_approve() – statistikken", 2, "18.2")
    body(doc, (
        "calculators/auto_approval.py. Kører KUN hvis activity_type=='normal' OG "
        "source==tachograph OG den globale kontakt er slået til. MIN_SAMPLES=5: findes færre end "
        "5 historiske samples for medarbejderens ugedag (0=mandag...6=søndag) i "
        "EmployeeBaseline, flages aktiviteten med 'Ikke nok data (n/5 registreringer for denne "
        "ugedag)' og godkendes ikke."
    ))
    header_table(doc,
        ["Test", "Sammenligning", "Tolerance"],
        [
            ["Varighed",  "Effektiv varighed (total minus rest-segmenter) vs. ugedagens løbende gennemsnit", "max(std × 2,5, gennemsnit × 30%)"],
            ["Starttid",  "Starttime (decimal) vs. ugedagens løbende gennemsnit",                             "max(std × 2,5, 1,5 time)"],
        ]
    )
    body(doc, (
        "Fejler én eller begge test, godkendes aktiviteten IKKE, og en menneskelæsbar "
        "afvigelsesstreng tilføjes til auto_approval_flags (fx 'Varighed afviger: 540min vs. "
        "typisk 480±20min (for lang)'). Baselines er Welford-glidende gennemsnit/varians pr. "
        "medarbejder+ugedag (baseline_updater.py), opdateret KUN fra godkendte, normale, "
        "tachograf-aktiviteter – gen-godkendelse af uændrede data tæller ikke dobbelt, og ændres "
        "en tidligere bidragende aktivitet, fjernes dens gamle bidrag først (Welford-downdate)."
    ))

    heading(doc, "Brugerflade", 2, "18.3")
    two_col_table(doc, [
        ["'Auto-godkendt'-prik",       "Vises på tidsbadgen når status=approved OG auto_approved=true (app.js ~1065)."],
        ["'Afvigelser registreret (ikke auto-godkendt)'", "Liste i aktivitetsdetaljen når auto_approval_flags er ikke-tom – viser præcis de(n) afvigelse(r) der forhindrede auto-godkendelse."],
        ["'Autogodkend aktiviteter'-knap", "Toolbar (#btn-auto-approve, kun synlig når den globale kontakt er slået til). Kalder POST /api/activities/auto-approve-pending?period_start=."],
    ])
    body(doc, (
        "Bulk-endepunktet (activities.py) afviser (400) hvis den globale kontakt er slået fra. "
        "Forespørgslen har INGEN type-/kilde-filter – den henter alle pending-aktiviteter i "
        "perioden, men should_auto_approve() afviser internt alt der ikke er "
        "normal+tachograf ('Kun normale tachograf-aktiviteter auto-godkendes' / 'Kun "
        "tachograf-aktiviteter auto-godkendes'). Godkendte får approved_by='AUTO' og bidrager "
        "straks til baseline; toast'en opsummerer: 'Auto-godkendt: X aktiviteter. Flagget til "
        "gennemgang: Y.'"
    ))

    doc.save(OUT / "Teknisk dokumentation.docx")
    print("Teknisk dokumentation.docx gemt.")


# ══════════════════════════════════════════════════════════════════════════════
#  BRUGERVEJLEDNING
# ══════════════════════════════════════════════════════════════════════════════

def build_bruger():
    doc = Document()

    for section in doc.sections:
        section.page_width  = Cm(21)
        section.page_height = Cm(29.7)
        section.left_margin = section.right_margin = Cm(2.5)
        section.top_margin  = section.bottom_margin = Cm(2.5)

    cover(doc, "Lønsystem", "Brugervejledning", genereringsdato())

    # ── Introduktion ───────────────────────────────────────────────────────
    heading(doc, "Introduktion", 1, "1")
    body(doc, (
        "Lønsystemet er et webbaseret program der håndterer registrering og lønberegning "
        "for lastbilchauffører hos Poul Schou A/S. Systemet henter automatisk kørselsdata "
        "fra chaufførernes digitale tachografer (.ddd-filer) og giver mulighed for at "
        "godkende, rette og eksportere løndata til Danløn."
    ))
    body(doc, (
        "Systemet tilgås via en almindelig webbrowser – der er ingen installation nødvendig "
        "på den enkelte computer. Åbn browseren og gå til systemets adresse på det lokale netværk."
    ))
    body(doc, (
        "Log ind med initialer og adgangskode, eller med knappen 'Log ind med Microsoft' hvis "
        "virksomhedens IT har aktiveret single sign-on (Microsoft Entra ID). SSO-login kræver "
        "stadig at du allerede er oprettet som bruger i systemet med den korrekte mailadresse "
        "udfyldt – der oprettes ikke automatisk en ny bruger ved første SSO-login."
    ))

    heading(doc, "Tre hovedområder", 2, "1.1")
    header_table(doc,
        ["Område", "Formål"],
        [
            ["Aktiviteter",  "Viser og håndterer alle chaufførers registrerede arbejdsdage i den aktuelle lønperiode."],
            ["Lønkørsel",    "Beregner og eksporterer løn til Danløn samt genererer timesedler og prøvekørsler."],
            ["Medarbejdere", "Stamdata for alle chauffører: lønnummer, overenskomst, normaltimer, afdeling m.m."],
        ]
    )

    # ── 2. Navigation ─────────────────────────────────────────────────────
    heading(doc, "Navigation", 1, "2")

    heading(doc, "Venstre menu", 2, "2.1")
    body(doc, "Menuen er delt i tre grupper. Hvilke punkter du ser afhænger af din rolles rettigheder (se kapitel 11).")
    two_col_table(doc, [
        ["📋 Aktiviteter",    "Viser aktivitetstabellen for den aktuelle lønperiode."],
        ["💰 Lønkørsel",      "Åbner lønkørselspanelet med prøvekørsel, PDF og CSV-eksport. Kræver 'Lønkørsel'-rettigheden."],
        ["🧾 Lønafregning",   "Periodetotaler og pr.-medarbejder oversigt over lønnen (kapitel 12). Kræver 'Lønafregning (se)'."],
        ["📊 Fraværsoversigt","Samlet oversigt over fravær pr. medarbejder/type, med eksport. Kræver 'Fraværsoversigt'-rettigheden."],
        ["🗓️ Vagtplan",       "Ugentlig/periodisk vagtplanlægning pr. medarbejder. Kræver 'Se vagtplan'; redigering kræver desuden 'Redigér egen linje' eller 'Redigér alle linjer'."],
        ["🗓️ Dagsplan",       "Daglig vogn/chauffør-fordeling og materielt fravær (kapitel 13). Kræver 'Se dagsplan'; redigering kræver desuden 'Redigér dagsplan'."],
    ])
    body(doc, "")
    two_col_table(doc, [
        ["📥 Importer .ddd",  "Import af tachografdata fra fil eller mappe. Kræver 'Importer .ddd'-rettigheden."],
        ["👤 Medarbejdere",   "Oversigt over og redigering af medarbejderstamdata. Kræver mindst 'Se medarbejdere'."],
        ["🚛 Vognpark",       "Oversigt over og redigering af køretøjer. Kræver mindst 'Se vognpark'."],
        ["💵 Tillæg",         "Administration af individuelle kr/time-tillæg pr. medarbejder. Kræver 'Administrér medarbejdertillæg'."],
    ])
    body(doc, "")
    two_col_table(doc, [
        ["🔑 Brugere",     "Opret/rediger brugere og roller, se hændelseslog (kapitel 11). Kun synlig med 'Brugerstyring'-rettigheden."],
        ["⚙️ Stamdata",    "Konfiguration af systemets masterdata: overenskomsttyper, overtidssatser, tillæg, løntypekoder (inkl. CSV-kolonneopsætning), fraværstyper, CVR-numre, helligdage, disponentgrupper, aftaletyper og auto-godkendelse (kapitel 17). Alle typer og koder kan oprettes, redigeres og slettes. Kræver 'Stamdata'-rettigheden."],
    ])

    heading(doc, "Periodenavigation", 2, "2.2")
    body(doc, (
        "Øverst på skærmen vises den aktuelle lønperiode (14 dage). "
        "Brug piletasterne (‹ og ›) til at navigere til forrige eller næste periode. "
        "Du kan også bruge datovælgeren til at hoppe direkte til en specifik dato: "
        "klik på datofeltet for at åbne en kalender med måned- og årstaldropdown."
    ))

    heading(doc, "Statuschips", 2, "2.3")
    header_table(doc,
        ["Chip", "Farve", "Betydning"],
        [
            ["Afventer",     "Blå",   "Antal aktiviteter der venter på godkendelse."],
            ["Godkendt",     "Grøn",  "Antal godkendte aktiviteter."],
            ["Deaktiveret",  "Rød",   "Antal deaktiverede (inaktive) aktiviteter."],
        ]
    )
    body(doc, "Du kan klikke på en chip for hurtigt at filtrere tabellen til den pågældende status.")

    # ── 3. Import af tachografdata ────────────────────────────────────────
    doc.add_page_break()
    heading(doc, "Import af tachografdata", 1, "3")
    body(doc, (
        "Tachografdata gemmes på chaufførernes digitale fører-kort som .ddd-filer. "
        "Disse filer importeres i systemet, som automatisk opretter aktiviteter for "
        "alle registrerede arbejdsdage."
    ))

    heading(doc, "Fremgangsmåde", 2, "3.1")
    for i, step in enumerate([
        "Klik på 'Importer .ddd' i den venstre menu.",
        "Vælg 'Vælg filer' for at importere enkeltfiler, eller 'Vælg mappe' for at importere alle .ddd-filer i en mappe.",
        "En Windows-filhåndterings-dialog åbner sig – naviger til filerne og bekræft valget.",
        "Systemet importerer filerne og viser en pop-up med resultatet: enten '✅ Importering succesfuld', "
        "eller en opdelt oversigt over antal importerede, opdaterede og sprunget over – med den konkrete "
        "årsag til hver sprunget-over-gruppe.",
    ], 1):
        bullet(doc, step, f"Trin {i}: ")

    note_box(doc,
        "Systemet springer automatisk allerede importerede aktiviteter over "
        "(baseret på medarbejder + starttidspunkt). Det er sikkert at importere "
        "samme mappe flere gange. Pop-up'en skelner mellem 'sprunget over – allerede "
        "importeret' og 'sprunget over – ukendt førerkortnummer' (med de konkrete "
        "kortnumre), så det altid er tydeligt hvorfor en aktivitet ikke kom med.",
        "GODT AT VIDE"
    )
    note_box(doc,
        "Bliver et førerkort læst af flere gange (fx først midt på en vagt og senere igen "
        "efter vagtens afslutning), genkender systemet nu automatisk den mere komplette "
        "udlæsning og UDVIDER den eksisterende aktivitet i stedet for at springe den over "
        "(rettet 2026-07-02). Var aktiviteten allerede godkendt, bliver den automatisk sat "
        "tilbage til 'Afventer', så den udvidede tid skal godkendes igen, før den tæller med "
        "i lønkørslen.",
        "GODT AT VIDE"
    )
    note_box(doc,
        "Alle importkørsler logges under Brugerstyring → Hændelseslog med samme "
        "opsummering, så du kan slå det op igen senere – også selvom pop-up'en er lukket.",
        "GODT AT VIDE"
    )

    heading(doc, "Forudsætninger", 2, "3.2")
    bullet(doc, "Chaufføren skal være oprettet i systemet med korrekt førerkortnummer.")
    bullet(doc, (
        "Førerkortnummeret i systemet skal være de første 14 tegn af kortnummeret: "
        "landekode (2 bogstaver) + 12 cifre (f.eks. DK000000178901) – IKKE de sidste "
        "2 cifre. De sidste 2 cifre er kortets udskiftnings-/fornyelsesindeks og "
        "ændrer sig hver gang kortet fornys, så de er ikke en del af det stabile "
        "kortnummer."
    ))
    bullet(doc, (
        "Stemmer kortnummeret ikke, importeres 0 aktiviteter uden fejlmelding – kun "
        "'Sprunget over'-tallet stiger. Kontrollér og ret kortnummeret i Stamdata "
        "hvis en import ikke giver de forventede aktiviteter."
    ))

    note_box(doc,
        "Starter chaufførens dag med en kort pause (fx et par minutter inden kørslen "
        "begynder), vises denne pause nu som en del af dagens arbejdstid i "
        "aktivitetstabellen. Pausen aflønnes stadig ikke – den trækkes fra som hvil/pause "
        "ligesom systemets øvrige pauser.",
        "GODT AT VIDE"
    )
    note_box(doc,
        "Km-start og km-slut hentes fra førerkortet, som kun gemmer et begrænset antal "
        "køretøjsbrug-poster. Ældre dage vil derfor kunne mangle km-data, selvom resten "
        "af aktiviteten er importeret korrekt.",
        "GODT AT VIDE"
    )
    note_box(doc,
        "Hører et importeret skift til en periode der allerede er kørt løn på (status "
        "'Lukket'), importeres det ikke stiltiende. Systemet spørger i stedet om det skal "
        "importeres ind i den EFTERFØLGENDE, åbne periode. Svarer du nej, husker systemet dit "
        "svar permanent – samme skift bliver ikke spurgt om igen ved en senere import af samme "
        "mappe.",
        "BEMÆRK"
    )

    # ── 4. Aktivitetstabellen ─────────────────────────────────────────────
    heading(doc, "Aktivitetstabellen", 1, "4")
    body(doc, (
        "Aktivitetstabellen er systemets hovedvisning. Den viser alle chauffører "
        "i rækker og de 14 dage i perioden som kolonner. Hver celle indeholder "
        "aktiviteternes start- og sluttidspunkt."
    ))

    heading(doc, "Farvekodning", 2, "4.1")
    header_table(doc,
        ["Farve", "Betydning"],
        [
            ["Mørkeblå/grå (#44546a)", "Afventer godkendelse (pending)."],
            ["Grøn",       "Godkendt aktivitet."],
            ["Rød",        "Deaktiveret aktivitet."],
            ["(K)-præfiks","Manuel aktivitet (ikke fra tachograf) vises med samme statusfarve som ovenfor, men med et '(K) '-præfiks i teksten – ingen separat farve."],
            ["FERIE/FRI",  "Fraværstype – vises med tekst i grøn boks."],
            ["Mørkegrøn kolonne (#056a10)", "Helligdag – søjleoverskriften fremhæves med mørk grøn baggrund. Halvdagshelligdage vises med '½ fra HH:MM'-badge og navn som tooltip."],
        ]
    )

    heading(doc, "Symboler og advarsler", 2, "4.2")
    two_col_table(doc, [
        ["❗ (udråbstegn)",        "Aktiviteten er under 4 timer lang. Kræver kommentar ved godkendelse. Vises kun når status er Afventer eller Deaktiveret – forsvinder ved godkendelse."],
        ["⚠️ (advarselstrekant)", "Aktiviteten er over 12 timer lang. Advarsel om usædvanlig lang vagt. Vises kun når status er Afventer eller Deaktiveret – forsvinder ved godkendelse."],
        ["(K) prefix",             "Aktiviteten er et barn af en opdelt aktivitet."],
        ["● (lille prik)",         "Aktiviteten er auto-godkendt af systemet (statistisk baseline) – se kapitel 17."],
        ["✕ (rødt kryds)",         "Vises kun på dagens sidste importerede vagt. Betyder at kortet formentlig er læst af MIDT i vagten (fx 0 km registreret den dag, eller vagten er usædvanligt kort) – resten af dagen mangler sandsynligvis. Hent en ny fil fra kortet senere og importér igen, så udvides/rettes vagten automatisk."],
    ])

    heading(doc, "Filtrering", 2, "4.3")
    body(doc, "Brug filtrene i toppen af tabellen til at indsnævre visningen:")
    bullet(doc, "Vis alle aktiviteter, kun afventende, kun godkendte eller kun deaktiverede.", "Status: ")
    bullet(doc, "Filtrer til én bestemt chauffør.", "Medarbejder: ")
    bullet(doc, "Vis kun chauffører fra den valgte afdeling. Medarbejder-filteret opdateres automatisk.", "Afdeling: ")

    heading(doc, "Vagter over midnat og periodegrænser", 2, "4.4")
    body(doc, (
        "En kørselsvagt der starter på en søndag eller en helligdag og strækker sig over midnat vises "
        "opdelt i to – ét stykke i hver af de to datokolonner, med sit eget klokkeslæt-interval. Det er "
        "kun en visningsmæssig opdeling (samme princip som lønberegningen bruger for søn-/helligdage); "
        "klik på et af stykkerne åbner altid den samlede, oprindelige aktivitet. Vagter der starter en "
        "almindelig hverdag eller lørdag vises som hidtil (start i én kolonne, slut i den næste)."
    ))
    body(doc, (
        "En vagt der starter sidst i én periode og slutter ind i den næste periode, vises nu i begge "
        "perioders aktivitetstabel, så den ikke 'forsvinder' ved periodeskifte."
    ))
    note_box(doc,
        "Registrerer eller retter du en aktivitet, hvis dato hører til en periode der allerede er "
        "kørt løn på (status 'Lukket'), lægges den automatisk over i den EFTERFØLGENDE periode i "
        "stedet for at blive afvist. Det gælder både manuel oprettelse/rettelse og import af .ddd-filer.",
        "BEMÆRK"
    )

    heading(doc, "Springertillæg-flueben", 2, "4.5")
    body(doc, (
        "Under hver medarbejders navn i aktivitetstabellen findes et lille flueben "
        "'Springertillæg'. Er det sat for en medarbejder, får vedkommende springertillæg for hele "
        "den viste lønperiode – samme timetal som Normal tid, men udbetalt under sin egen "
        "lønkode. Kræver rettigheden 'Sæt springertillæg' (gives som standard til alle roller)."
    ))
    bullet(doc, "Fluebenet gælder KUN den periode du står i – det nulstilles automatisk ved næste periode og skal sættes igen.")
    bullet(doc, "Fluebenet kan ikke ændres når perioden er låst (der er kørt løn).")
    bullet(doc, "Beløbet vises særskilt i prøvekørslen (' (springer)' efter navnet, afsnit 9.1), som egen linje i Lønkørsel-fanens medarbejderkort og i PDF-timesedlen (afsnit 9.4), samt i Lønafregning (afsnit 12.2).")
    bullet(doc, "Sætter du fluebenet, og der derefter oprettes en ny aktivitet for medarbejderen (fx via import eller manuel oprettelse), forbliver fluebenet sat – det bliver ikke nulstillet ved en gentegning af aktivitetsoversigten (rettet 2026-09-22).")

    # ── 5. Aktivitetsdetaljer og godkendelse ──────────────────────────────
    doc.add_page_break()
    heading(doc, "Aktivitetsdetaljer og godkendelse", 1, "5")
    body(doc, (
        "Klik på et tidsemærke i tabellen for at åbne detaljevisningen for aktiviteten. "
        "Her kan du se alle oplysninger og foretage ændringer."
    ))

    heading(doc, "Hvad kan du se?", 2, "5.1")
    two_col_table(doc, [
        ["Start- og sluttid",        "Registreret tidspunkt fra tachografen (eller manuelt angivet)."],
        ["Effektiv tid",              "Samlet arbejdstid fratrukket pauser."],
        ["Aktivitetsfordeling",       "Fordeling mellem kørsel, rådighedstid, andet arbejde og hvil/pause (fra tachografen)."],
        ["Detaljeret tidslinje",      "Alle segmenter med præcise tidspunkter."],
        ["Status og godkender",       "Hvem har godkendt og hvornår."],
        ["Ændret af",                 "Initialerne på den bruger der sidst gemte en rettelse. Vises kun når aktiviteten faktisk er blevet redigeret."],
        ["Afvigelser registreret (ikke auto-godkendt)", "Vises kun hvis aktiviteten IKKE blev auto-godkendt (kapitel 17) – lister præcis hvorfor (fx afvigende varighed eller starttid i forhold til medarbejderens sædvanlige mønster)."],
    ])

    heading(doc, "Hvad kan du gøre?", 2, "5.2")

    p = doc.add_paragraph()
    r = p.add_run("Ret starttid / sluttid")
    r.bold = True; r.font.name = "Arial"; r.font.size = Pt(11)
    body(doc, (
        "Angiv en ny dato og et nyt klokkeslæt. Brug piltasterne i time- og minutfeltet "
        "eller skriv tallene direkte. Klik 'Gem rettelse' for at gemme. "
        "Systemet bevarer de originale tachograftider automatisk."
    ), space_after=4)

    p2 = doc.add_paragraph()
    r2 = p2.add_run("Fortryd rettelse")
    r2.bold = True; r2.font.name = "Arial"; r2.font.size = Pt(11)
    body(doc, "Nulstiller tiderne til de originale værdier fra tachografen.", space_after=4)

    p3 = doc.add_paragraph()
    r3 = p3.add_run("Opdel aktivitet")
    r3.bold = True; r3.font.name = "Arial"; r3.font.size = Pt(11)
    body(doc, (
        "Del en vagt i to – fx hvis en chauffør skifter tur midt på dagen. "
        "Vælg tidspunktet for opdelingen. Systemet opretter to nye aktiviteter "
        "og fordeler pauser og segmenter korrekt."
    ), space_after=4)

    p3b = doc.add_paragraph()
    r3b = p3b.add_run("Ret til andet arbejde / Tilpas (i den detaljerede tidslinje)")
    r3b.bold = True; r3b.font.name = "Arial"; r3b.font.size = Pt(11)
    body(doc, (
        "Ud for et pausesegment (hvil) i den detaljerede tidslinje kan du klikke 'Ret til andet arbejde' for "
        "at omklassificere det til 'Andet arbejde' – bruges fx hvis tachografen har registreret "
        "en pause der reelt var arbejde. En 'Gendan'-knap kan fortryde præcis den rettelse igen. "
        "'Tilpas' åbner i stedet en dialog hvor du kan justere pausens sluttidspunkt (forlænge "
        "eller forkorte) uden at ændre dens type – en forhåndsvisning viser hvor mange minutter "
        "der flyttes, og fra/til hvilket segment. Begge dele påvirker den beregnede løn direkte, "
        "da et pausesegment der bliver til arbejde tæller med i timerne."
    ), space_after=4)

    p4 = doc.add_paragraph()
    r4 = p4.add_run("Godkend")
    r4.bold = True; r4.font.name = "Arial"; r4.font.size = Pt(11)
    body(doc, (
        "Godkend aktiviteten så den indgår i lønkørslen. Angiv dine initialer. "
        "Aktiviteter under 4 timer kræver altid en kommentar."
    ), space_after=4)

    p5 = doc.add_paragraph()
    r5 = p5.add_run("Deaktiver")
    r5.bold = True; r5.font.name = "Arial"; r5.font.size = Pt(11)
    body(doc, (
        "Markér aktiviteten som inaktiv. Den indgår ikke i lønberegningen "
        "men slettes ikke fra databasen."
    ), space_after=4)
    note_box(doc,
        "Deaktiver-dialogen har et ekstra flueben 'Slet aktiviteten helt', som sletter "
        "aktiviteten PERMANENT i stedet for blot at deaktivere den – kan ikke fortrydes. "
        "Fluebenet er kun tilgængeligt for fraværstyper (altid) og for manuelt oprettet normal "
        "tid – en takograf-importeret kørselsaktivitet kan aldrig slettes helt, kun deaktiveres, "
        "fordi den er rå kørselsdata fra førerkortet. Brug det med omtanke: der er ingen "
        "'Gendan' for en permanent slettet aktivitet.",
        "VIGTIGT"
    )

    note_box(doc,
        "KUN godkendte aktiviteter medtages i lønkørslen. Husk at gennemgå og "
        "godkende alle relevante aktiviteter inden du kører løn.",
        "VIGTIGT"
    )

    # ── 6. Manuelle aktiviteter ───────────────────────────────────────────
    heading(doc, "Manuelle aktiviteter", 1, "6")
    body(doc, (
        "Brug manuelle aktiviteter til at registrere ferie, afspadsering, fri, "
        "skole/kursus eller andre vagter der ikke fremgår af tachografen."
    ))
    note_box(doc,
        "Har din rolle rettigheden 'Auto-godkend ved oprettelse' (se rettighedsoversigten, "
        "kapitel 11), bliver de aktiviteter DU opretter manuelt godkendt med det samme, uden det "
        "sædvanlige 'Afventer'-trin. Ikke at forveksle med den statistiske auto-godkendelse i "
        "kapitel 17, som kun gælder tachograf-importerede kørselsdage.",
        "GODT AT VIDE"
    )

    heading(doc, "Oprettelse", 2, "6.1")
    for i, step in enumerate([
        "Klik på '+ Tilføj aktivitet' knappen i aktivitetstabellen.",
        "Vælg medarbejder og aktivitetstype.",
        "Angiv start- og sluttidspunkt.",
        "Tilføj eventuelle pauser ved at klikke '+ Tilføj pause' (se afsnit 6.3).",
        "Udfyld eventuelt turnummer og pålæsning/aflæsning (kun for normale aktiviteter).",
        "Klik 'Gem aktivitet'.",
    ], 1):
        bullet(doc, step, f"Trin {i}: ")
    note_box(doc,
        "Vognnummer/registreringsnummer er PÅKRÆVET for alle aktivitetstyper undtagen "
        "overnatning – også for fraværstyper. Feltet valideres mod Vognparken: stemmer det ikke "
        "med et kendt vognnummer, viser systemet 'Ukendt registreringsnummer' og beder dig "
        "oprette køretøjet i Vognpark først, i stedet for at gemme aktiviteten.",
        "BEMÆRK"
    )
    note_box(doc,
        "Vognnummer-feltets søgeliste kan siden 2026-09-17 betjenes med tastaturet: Pil ned/Tab "
        "flytter markeringen ned i listen (Shift+Tab/Pil op flytter op), Enter vælger det "
        "markerede køretøj, og Escape lukker listen igen.",
        "TIP"
    )
    note_box(doc,
        "Registrerer du en fraværstype på en dag hvor medarbejderen allerede har en kørsel "
        "('normal tid') registreret, viser systemet en advarsel med de(n) berørte dato(er) og "
        "spørger om du vil fortsætte alligevel. Vælg 'Annuller' for at rette datoen, eller "
        "'Fortsæt alligevel' hvis begge registreringer skal stå.",
        "BEMÆRK"
    )

    heading(doc, "Fraværstyper og overnatning", 2, "6.2")
    body(doc, "Når du vælger en fraværstype eller overnatning, sker følgende automatisk:")
    bullet(doc, "Felterne for turnummer, pålæsning og aflæsning skjules (ikke relevante).")
    bullet(doc, "Aktiviteten godkendes automatisk (approved_by sættes til din bruger) – kræver ikke separat godkendelse bagefter.")
    bullet(doc, "Ferie, sygdom, feriefri m.fl.: starttidspunktet sættes automatisk til 06:00, og sluttidspunktet beregnes ud fra medarbejderens normaltimer den pågældende dag. Vælger du 'Til dato' for at oprette en periode, oprettes én aktivitet PR. HVERDAG i perioden (ikke én sammenhængende aktivitet) – hver dag tæller sine egne normaltimer (typisk 7,4 t).")
    bullet(doc, "Selvbetalt fridag og Løn andet sted fra kan siden 2026-09-22 også oprettes som en periode ('Til dato' udfyldt), på nøjagtig samme måde som Ferie – én aktivitet pr. hverdag i intervallet.")
    bullet(doc, "Afspadsering som periode ('Til dato' udfyldt) følger samme regel: 7,4 t (eller medarbejderens skemalagte timer) pr. hverdag, uanset klokketid. En enkelt afspadseringsdag (uden 'Til dato') kan derimod redigeres til en delvis dag med selvvalgt start-/sluttid, og den faktiske varighed bruges da i lønberegningen.")

    body(doc, (
        "De tilgængelige fraværstyper administreres i Stamdata-modulet under fanen 'Fraværstyper'. "
        "Her kan du aktivere og deaktivere typer, tilføje nye typer og slette eksisterende."
    ))
    header_table(doc,
        ["Type", "Beskrivelse"],
        [
            ["Ferie",          "Registrerer en feriedag. Start: 06:00. Slut: 06:00 + normaltimer for dagen. Tælles i timeoversigten, men er som default IKKE med i Danløn-CSV'en (kan slås til i Stamdata)."],
            ["Afspadsering",   "Registrerer afspadsering. Som periode ('Til dato') tæller hver hverdag 7,4 t/skemalagte timer; som enkeltdag bruges den faktiske start-/sluttid."],
            ["Fri",            "Registrerer fridag."],
            ["Løn andet sted fra", "Tilføjet 2026-09-22. Fungerer som Selvbetalt fridag (0 kr., ingen linje i Danløn CSV) – bruges som en kommentar til lønbogholderne om, at dagen bevidst er korrekt uden data i dette system, fx fordi medarbejderen har kørt eksport/for et andet selskab den dag."],
            ["Skole/kursus",   "Registrerer skole- eller kursusdag."],
            ["Overnatning",    "Registrerer en overnatning (flat sats pr. forekomst – ikke timer). Angiv datoen, eller udfyld 'Til dato' for at registrere flere overnatninger i træk (se note nedenfor). Satsen hentes automatisk fra Stamdata (Tillæg-fanen)."],
            ["Overnatning – DOB",   "Krydses af INDE I Overnatning-oprettelsen (samme modal, ekstra 'DOB'-flueben) – registreres som en separat overnatningstype med sin egen sats i Stamdata → Tillæg. Vises som egen linje i PDF-timesedlen og prøvekørslens Excel-ark, men indgår PT. IKKE i Danløn CSV-eksporten."],
        ]
    )
    note_box(doc,
        "Overnatning som periode ('Til dato' udfyldt) opretter ÉN overnatning PR. KALENDERDAG i "
        "intervallet – inkl. lørdag, søndag OG helligdage (i modsætning til Ferie/Afspadsering "
        "m.fl., som kun tæller hverdage). DOB-fluebenet gælder for hele perioden på én gang – det "
        "er ikke muligt at blande almindelig og DOB-overnatning i samme oprettelse. Overlapper en "
        "af dagene en anden allerede registreret aktivitet, vises en advarsel med de(n) berørte "
        "dato(er), som du skal bekræfte for at fortsætte. En oprettet overnatningsperiode kan "
        "bagefter forlænges/afkortes på samme måde som andre fraværsperioder (afsnit 6.4). "
        "Registreringsnummer kræves fortsat ikke, hverken for én enkelt overnatning eller en "
        "periode.",
        "GODT AT VIDE"
    )
    body(doc, (
        "Sygdom, Barn 1.sygedag og Barsel omklassificeres automatisk til en ulønnet variant, "
        "hvis medarbejderens anciennitet er for lav på registreringstidspunktet – du behøver ikke "
        "gøre noget aktivt, systemet vælger den rigtige type for dig:"
    ))
    bullet(doc, "Sygdom → 'Sygdom u. 8 uger' hvis medarbejderen har været ansat 8 uger eller mindre på sygedagen.")
    bullet(doc, "Barn 1.sygedag → 'Barn 1.sygedag u. 8 uger' hvis medarbejderen har under 9 måneders anciennitet.")
    bullet(doc, "Barsel → 'Barsel u. løn' hvis medarbejderen har under 9 måneders anciennitet regnet fra terminsdatoen (se nedenfor), ikke fra selve barselsdagen.")
    note_box(doc,
        "Ved oprettelse af en barsel-aktivitet skal du angive medarbejderens 'Terminsdato' "
        "(forventet fødselsdato) – uden den kan aktiviteten ikke gemmes. Terminsdatoen huskes på "
        "medarbejderen, så du ikke skal indtaste den igen næste gang.",
        "BEMÆRK"
    )

    heading(doc, "Registrering af pauser", 2, "6.3")
    body(doc, (
        "For normale aktiviteter kan du registrere de pauser chaufforen har holdt i løbet af "
        "arbejdsdagen. Pauserne fratrækkes automatisk i den effektive arbejdstid og indgår korrekt "
        "i beregningen af overtidstillæg."
    ))
    for i, step in enumerate([
        "Angiv aktivitetens starttidspunkt (påkrævet – pausedatoen arves herfra).",
        "Klik '+ Tilføj pause'. En dialogboks åbner sig med titel 'Pause 1', 'Pause 2' osv.",
        "Angiv pausens starttidspunkt og sluttidspunkt (kun klokkeslæt – dato sættes automatisk).",
        "Klik 'Tilføj'. Pausen vises i listen med start- og sluttid og en ×-slet-knap.",
        "Gentag for yderligere pauser. Klik × for at fjerne en pause.",
    ], 1):
        bullet(doc, step, f"Trin {i}: ")
    note_box(doc,
        "Pausefelterne vises kun for normale aktiviteter. "
        "For fraværstyper (ferie, fri m.fl.) og overnatning er pausesektionen skjult.",
        "GODT AT VIDE"
    )
    body(doc, "Pauserne påvirker fire steder i systemet:")
    bullet(doc, "Sum, effektiv tid – vises i aktivitetsdetaljerne og er fratrukket pausetid.")
    bullet(doc, "Tooltip i aktivitetsoversigten – hold musen over en vagt for at se tidsrum, arbejdstid, pause, status og fordelingen Kørsel / Andet arbejde / Rådighed / Pause i %.")
    bullet(doc, "Aktivitetsfordeling – manuelle aktiviteter med pauser viser 'Effektiv tid' (blå) og 'Pause' (grå) i %-bjælken.")
    bullet(doc, "Lønberegning – pauser fratrækkes i det præcise tidsvindue de afholdes, så overtidstillæg beregnes korrekt.")

    heading(doc, "Redigering af en fraværsperiode", 2, "6.4")
    body(doc, (
        "Har du oprettet en flerdags-fraværsperiode (med 'Til dato'), kan du efterfølgende "
        "udvide eller forkorte den, uden at slette og genoprette alt: åbn en hvilken som helst "
        "dag i perioden, og en 'Fraværsperiode'-boks øverst i detaljevisningen lader dig ændre "
        "'Fra dato' og/eller 'Til dato'. Klik 'Gem periodedatoer' for at gennemføre ændringen."
    ))
    bullet(doc, "Dage der TILFØJES til perioden, får en ny aktivitet med samme standardtimer som ved oprettelse. Har medarbejderen 0 skemalagte timer den ugedag, springes dagen automatisk over.")
    bullet(doc, "Dage der FJERNES fra perioden, bliver PERMANENT slettet – ikke deaktiveret. Systemet viser altid en opsummering ('N dage slettes permanent / N dage oprettes') til bekræftelse, før noget gennemføres.")
    bullet(doc, "For en Overnatnings-periode (afsnit 6.2) tælles ALLE kalenderdage i det nye interval, inkl. weekend/helligdage – ikke kun hverdage som for de øvrige fraværstyper.")
    note_box(doc,
        "Er en af dagene der skal fjernes i en lønperiode der allerede er kørt løn på ('Lukket'), "
        "afvises hele ændringen – ingen dage fjernes, før perioden evt. genåbnes. Det samme "
        "gælder hvis en af dagene er blevet opdelt (split) – fortryd splittet først.",
        "BEMÆRK"
    )

    # ── 7. Medarbejdere ───────────────────────────────────────────────────
    doc.add_page_break()
    heading(doc, "Medarbejdere", 1, "7")
    body(doc, "Klik på 'Medarbejdere' i venstre menu for at se og redigere medarbejderstamdata.")

    heading(doc, "Søg og filtrér", 2, "7.1")
    body(doc, "Øverst på siden kan medarbejderlisten indsnævres på tre måder, som kan kombineres frit:")
    bullet(doc, "skriv et navn eller lønnummer for hurtigt at finde en bestemt medarbejder.", "Søgefelt: ")
    bullet(doc, (
        "vælg én afdeling for kun at se dens medarbejdere, eller 'Ingen gruppe' for at se "
        "medarbejdere uden en tilknyttet afdeling. Alle afdelinger er med i listen, også dem der "
        "i Stamdata er sat til ikke at vises i aktivitetsoversigten."
    ), "Afdeling: ")
    bullet(doc, "medtag fratrådte/deaktiverede medarbejdere i listen.", "Vis inaktive: ")

    heading(doc, "Opret ny medarbejder", 2, "7.2")
    body(doc, "Klik '+ Opret medarbejder' og udfyld felterne:")

    header_table(doc,
        ["Felt", "Påkrævet", "Beskrivelse"],
        [
            ["Aftale",              "Ja", "Vælg fra listen der stammer fra Stamdata (Aftale-fanen) – som udgangspunkt 'Timelønnet, fast arbejdstid' eller 'Timelønnet, ikke fastlagt arbejdstid'. Administratorer kan tilføje flere aftaletyper i Stamdata."],
            ["Overenskomsttype",    "Afhænger af Aftale", "Bestemmer timesatsen. Vælg fra listen der stammer fra Stamdata (Overenskomsttyper-fanen). Feltet er kun obligatorisk (rød *) hvis den valgte Aftale-type kræver det – styres pr. aftaletype i Stamdata."],
            ["Disponentgruppe",     "Nej","Afdeling – dropdown, en medarbejder kan højst tilhøre én gruppe ad gangen. Bruges til at filtrere aktivitetstabellen og fraværsoversigt-eksporten."],
            ["Fast bil",            "Nej","Afkryds for at medarbejderen skal foreslås som standardchauffør på en bestemt vogn i Dagsplan (kapitel 13). Vises herefter et søgbart vognnummer-felt, ikke begrænset til egen disponentgruppe."],
            ["Særaftale: Øvrig overtid for alle timer", "Nej", "Afkryds KUN for en medarbejder med en individuel aftale om at alle arbejdstimer skal give Øvrig overtid oveni normal løn, uden dagligt loft (se afsnit 9.6). Berører lønberegningen direkte – brug med omtanke."],
            ["Afløser",             "Nej", "Afkryd for en afløser/substitutmedarbejder. Medarbejderen får IKKE søgnehelligdagsbetaling (kode 4/63) på søndage/helligdage medmindre vedkommende faktisk har kørt den dag – se afsnit 9.5. Farvemarkeres separat i medarbejderlisten, Vagtplan og Aktivitetsoversigten."],
            ["CVR-nummer",          "Nej","Kun synligt hvis der er oprettet 2 eller flere CVR-numre i Stamdata → CVR nummer. Vælger hvilket CVR-nummer medarbejderens Danløn-eksport og PDF-timeseddel skal bruge. Tomt/skjult felt = medarbejderen bruger automatisk standard-CVR'et."],
            ["Lønnummer",           "Ja", "Unikt lønnummer (bruges i Danløn-eksporten)."],
            ["Førerkortnummer",     "Nej","EU-førerkortnummer – påkrævet for at importere .ddd-filer korrekt."],
            ["Navn",                "Ja", "Fornavn og efternavn."],
            ["Adresse / postnummer","Nej","Adresseoplysninger."],
            ["E-mail / telefon",    "Nej","Kontaktoplysninger."],
            ["Ansættelsesdato",     "Ja", "Startdato for ansættelsen. Klik på feltet for at åbne en kalender med måned- og årstaldropdown."],
            ["Fratrædelsesdato",    "Nej","Udfyldes KUN ved fratrædelse. Default er 31-12-9999. Klik på feltet for at åbne kalender-pickeren."],
            ["Aktiv",               "—", "Afkryd for at medarbejderen er aktiv i systemet."],
            ["Fuldlønnet",          "—", "Afkryd hvis medarbejderen er fuldlønnet."],
            ["§56",                 "—", "Afkryd hvis medarbejderen har en §56-aftale. Herefter skal start- og slutdato udfyldes (begge påkrævede, rød *) – slutdatoen skal ligge efter startdatoen. Se afsnit 7.6 om §56-advarslen."],
        ]
    )
    note_box(doc,
        "De tilgængelige aftaletyper administreres i Stamdata-modulet under fanen 'Aftale'. Her "
        "kan en administrator ændre teksten på de to oprindelige typer, samt tilføje flere "
        "aftaletyper og bestemme om Overenskomsttype skal være påkrævet for hver af dem. "
        "Vælges en type der ikke kræver Overenskomsttype, forsvinder den røde stjerne ved feltet, "
        "og det kan stå tomt.",
        "GODT AT VIDE"
    )
    note_box(doc,
        "Opret KUN en ny aftaletype hvis du er indforstået med konsekvensen: medarbejdere på "
        "en aftaletype ud over de to oprindelige ('Timelønnet, fast arbejdstid' og 'Timelønnet, "
        "ikke fastlagt arbejdstid') får IKKE noget overtidstillæg og INGEN søgnehelligdagsbetaling "
        "overhovedet – kun almindelig timeløn for de faktisk arbejdede timer, uanset tidspunkt "
        "eller dagtype. Den konkrete beregningsregel for en ny aftaletype skal udvikles særskilt, "
        "hvis den overhovedet skal afvige fra flad timeløn. Kontakt systemudvikler før en ny "
        "aftaletype tages i brug til en medarbejder, hvis der forventes overtid/SH-betaling.",
        "VIGTIGT"
    )
    note_box(doc,
        "Hvis navn (for- og efternavn) eller førerkortnummer allerede findes på en anden medarbejder "
        "(aktiv eller inaktiv), viser systemet en advarsel ved oprettelse. Ved navnesammenfald kan du "
        "vælge 'OK, opret alligevel' for at oprette begge, eller 'Ændre' for at vende tilbage og rette. "
        "Ved sammenfald på førerkortnummer kan du KUN vælge 'Ændre' – to medarbejdere kan ikke dele samme "
        "førerkortnummer i databasen.",
        "BEMÆRK"
    )

    heading(doc, "Timefordeling", 2, "7.3")
    body(doc, (
        "Timefordelingen angiver medarbejderens normaltimer pr. ugedag i en 14-dages periode "
        "(uge A og uge B, svarende til ulige og lige ISO-uger). Standardværdier er:"
    ))
    bullet(doc, "Mandag–torsdag: 7,5 timer")
    bullet(doc, "Fredag: 7 timer")
    bullet(doc, "Lørdag–søndag: 0 timer")
    body(doc, (
        "For hver dag kan du udfylde ENTEN et timeantal ELLER en fra/til-tid – begge felter står altid "
        "synlige side om side. Udfylder du fra/til-tid, beregner systemet automatisk timeantallet "
        "(sluttid minus starttid – en sluttid tidligere end starttid tolkes som en vagt der går over "
        "midnat) og overskriver timeantal-feltet. Et 'Ugentligt timeantal'-felt nederst i tabellen "
        "summerer automatisk timerne for hver uge, og opdateres med det samme uanset hvilken af de to "
        "indtastningsmåder du bruger."
    ))
    body(doc, (
        "Normaltimerne bruges til beregning af overtidstillæg og til at auto-udfylde sluttidspunktet ved registrering af ferie."
    ))

    heading(doc, "Anciennitetsvarsler", 2, "7.4")
    body(doc, (
        "Systemet kontrollerer løbende om medarbejdere har nået 9 måneders anciennitet "
        "og en tilsvarende overenskomsttype med højere sats. Hvis det er tilfældet, vises "
        "et pop-up-varsel. Varslet er styret af tilladelsen 'Anciennitetsvarsel' i Brugerstyring – "
        "som standard er den slået til for Administrator og Lønbogholder og fra for Disponent og Kontor. "
        "En administrator kan klikke tilladelsen til eller fra for enhver rolle. "
        "Husk at opdatere overenskomsttypen for medarbejderen."
    ))
    body(doc, (
        "Når du klikker \"Ændring foretaget\" i varslet, gemmes afvisningen på medarbejderen i databasen "
        "(feltet anciennitet_dismissed_at). Varslet vises ikke igen – uanset computer eller browser. "
        "Hvis overenskomsttypen ændres på medarbejderen, nulstilles afvisningen automatisk, "
        "så varslet kan dukke op igen hvis ancienniteten stadig er relevant."
    ))

    heading(doc, "Tillæg", 2, "7.5")
    body(doc, (
        "Ud over overenskomsttypens timesats kan en medarbejder have et individuelt kr/time-tillæg. "
        "Klik på 'Tillæg' i venstre menu for at administrere dette (kræver rettigheden 'Administrér "
        "medarbejdertillæg')."
    ))
    for i, step in enumerate([
        "Søg medarbejderen frem i søgefeltet (navn eller lønnummer).",
        "Klik på medarbejderen. En boks åbner sig med medarbejderens fulde tillægshistorik: status "
        "(Aktiv/Inaktiv), lønnummer, tillægsnavn, type, gyldighedsperiode og værdi i kr. Brug 'Fra'/'Til'-"
        "felterne til at indsnævre visningen til en bestemt periode – lader du dem stå tomme, vises hele "
        "historikken.",
        "Klik '+ Tilføj' (enten i boksen eller i toolbaren øverst på siden) for at oprette et nyt tillæg: "
        "vælg medarbejder (forudvalgt hvis du kom fra dennes boks), startdato (default dags dato) og "
        "værdi i kr/time. Tillægsnavn og type sættes automatisk og kan ikke ændres.",
    ], 1):
        bullet(doc, step, f"Trin {i}: ")
    note_box(doc,
        "Når et nyt tillæg oprettes, bliver medarbejderens tidligere tillæg automatisk gjort inaktivt "
        "fra og med dagen før den nye startdato. Der findes ikke en 'rediger'-funktion – en fejl rettes "
        "ved at oprette et nyt tillæg med den korrekte værdi.",
        "GODT AT VIDE"
    )
    body(doc, (
        "Har en medarbejder et aktivt tillæg der ikke længere skal gælde, klik 'Afslut' på den aktive "
        "række. Tillægget fortsætter med at gælde resten af den igangværende lønperiode og bortfalder "
        "først fra den efterfølgende periode – det stopper altså ikke med øjeblikkelig virkning midt i "
        "en periode."
    ))
    note_box(doc,
        "Tillægget lægges automatisk til medarbejderens grundsats i selve lønberegningen – både i "
        "prøvekørslen, PDF-timesedlerne, Danløn CSV'en (kode 1/normaltid) og i afspadsering, sygdom, "
        "barsel og skole/kursus. Det kræver ingen særskilt handling ud over at oprette/afslutte "
        "tillægget her.",
        "VIGTIGT"
    )
    body(doc, (
        "Findes der et aktivt tillæg på en medarbejder, vises værdien også som et read-only felt under "
        "Overenskomsttype, når du åbner medarbejderen under fanen 'Medarbejdere'. Feltet kan ikke "
        "redigeres derfra – kun under fanen 'Tillæg'."
    ))

    heading(doc, "§56-advarsel", 2, "7.6")
    body(doc, (
        "Nærmer en medarbejders §56-slutdato (jf. §56-feltet i afsnit 7.2) sig, kan systemet advare "
        "brugere med tilladelsen '§56-advarsel' i Brugerstyring – som standard slået til for "
        "Lønbogholder, fra for Disponent og Kontor. En administrator kan klikke tilladelsen til eller "
        "fra for enhver rolle."
    ))
    bullet(doc, (
        "vises fra 30 dage før slutdatoen og indeholder medarbejderens navn og den aktuelle slutdato."
    ), "Advarsel om snarlig udløb: ")
    bullet(doc, (
        "overskrides slutdatoen uden at nogen har grebet ind, sætter systemet automatisk §56-feltet "
        "til fra på medarbejderen. Brugere med tilladelsen får i stedet en informationsbesked om at "
        "det er sket."
    ), "Automatisk deaktivering: ")
    note_box(doc,
        "Begge popups afvises PR. BRUGER, ikke pr. medarbejder – ser du en advarsel og afviser den, "
        "vises den stadig for kolleger med samme tilladelse, indtil de selv afviser den. Ændres "
        "medarbejderens §56-slutdato bagefter, nulstilles alle brugeres afvisning automatisk, så "
        "advarslen kan dukke op igen.",
        "BEMÆRK"
    )

    heading(doc, "§56-oversigt", 2, "7.7")
    body(doc, (
        "Klik på knappen '§56' i toolbaren på Medarbejdere-siden for at åbne en read-only liste "
        "over alle aktive medarbejdere der aktuelt har §56 afkrydset – med navn, startdato og "
        "slutdato. Listen følger det afdelingsfilter der er valgt på siden (afsnit 7.1), men "
        "ignorerer søgefeltet og 'Vis inaktive'."
    ))
    note_box(doc,
        "Opretter du en 'Sygdom'-aktivitet for en medarbejder der har §56 afkrydset, spørger "
        "systemet om aktiviteten skal forblive almindelig 'Sygdom', eller i stedet oprettes som "
        "den eksisterende fraværstype '§56 syg'. Fortryder du dialogen (klik uden for/Annuller), "
        "oprettes ingen aktivitet overhovedet.",
        "GODT AT VIDE"
    )

    # ── 8. Helligdagskalender ─────────────────────────────────────────────
    heading(doc, "Helligdagskalender", 1, "8")
    body(doc, (
        "Systemet vedligeholder automatisk en kalender over danske helligdage. "
        "Helligdage fremhæves i aktivitetskalenderen og danner grundlag for fremtidig "
        "beregning af helligdagstillæg."
    ))

    heading(doc, "Markering i aktivitetskalenderen", 2, "8.1")
    body(doc, (
        "Dage der er helligdage fremhæves med mørk grøn baggrund (#056a10) i "
        "aktivitetskalenderens kolonneoverskrifter. Halvdagshelligdage (1. maj og Grundlovsdag) "
        "vises med et '½ fra 12:00'-badge. Hold musen over overskriften for at se helligdagens navn."
    ))
    note_box(doc,
        "Helligdagskalenderen genereres automatisk for de næste 5 år ved serveropstart. "
        "Du behøver ikke gøre noget – den opdaterer sig selv.",
        "GODT AT VIDE"
    )

    heading(doc, "Administration af helligdage (Stamdata → Helligdage)", 2, "8.2")
    body(doc, (
        "Brugere med rettigheden 'Administrér helligdage' kan administrere helligdagskalenderen "
        "via Stamdata-menupunktet → fanen 'Helligdage':"
    ))
    header_table(doc,
        ["Handling", "Beskrivelse"],
        [
            ["Generer for år",   "Klik 'Generer [årstal]' for at auto-generere alle danske helligdage for det valgte år. Eksisterende datoer overskrives ikke."],
            ["Tilføj manuelt",   "Klik '+Tilføj helligdag' for at oprette en særlig fridag med valgfri halvdagstid (fx en lukkedag)."],
            ["Slet helligdag",   "Klik 'Slet' på en helligdag for at fjerne den fra kalenderen. Auto-genererede og manuelle helligdage kan begge slettes."],
        ]
    )
    two_col_table(doc, [
        ["Faste helligdage",      "Nytårsdag, 1. maj (½), Grundlovsdag (½), Juleaftensdag, 1. og 2. juledag, Nytårsaftensdag"],
        ["Bevægelige helligdage", "Skærtorsdag, Langfredag, Påskedag, 2. påskedag, Kristi Himmelfartsdag, Pinsedag, 2. pinsedag"],
        ["Store Bededag",         "Medtages ikke – afskaffet fra 2024"],
    ])

    # ── 9. Lønkørsel ─────────────────────────────────────────────────────
    heading(doc, "Lønkørsel", 1, "9")
    body(doc, (
        "Klik på 'Lønkørsel' i venstre menu for at beregne og eksportere løn. "
        "Husk: kun aktiviteter med status 'Godkendt' indgår i beregningen."
    ))

    heading(doc, "Prøvekørsel", 2, "9.1")
    body(doc, (
        "Prøvekørslen beregner lønnen og downloader resultatet som en Excel-fil til din computer. "
        "Brug denne til at tjekke tallene inden den endelige kørsel."
    ))
    bullet(doc, "Klik 'Prøvekørsel'.")
    bullet(doc, "Vælg evt. en bestemt medarbejder, eller lad feltet stå tomt for alle.")
    bullet(doc, "Klik 'Dan Excel'. Filen downloades til din computer, og pop-up-vinduet lukker automatisk.")

    body(doc, "Excel-filen viser alle 14 dage i perioden for hver medarbejder, med bl.a. disse kolonner:")
    bullet(doc, "Total tid: alle arbejdede timer den dag.")
    bullet(doc, "Pause i alt (min): summen af medarbejderens pauser den dag, i minutter.")
    bullet(doc, "Normal tid, Tillæg 05-06, Tillæg OT1-3 og Øvrigt OT: fordeling af Total tid – Normal tid er de timer der IKKE udløser noget tillæg.")
    bullet(doc, "Fraværsdage (Ferie, Fri, Afspadsering, Skole/kursus): vises med fraværstype i Normal tid-kolonnen.")
    bullet(doc, "Dage uden registrering: vises med 0 på alle kolonner.")
    bullet(doc, "Medarbejdere med springertillæg i perioden: får ' (springer)' tilføjet efter navnet.")
    bullet(doc, "Første linje pr. medarbejder er markeret med grøn baggrund. Tom linje adskiller medarbejdere.")
    note_box(doc,
        "Kolonnerne er gjort så smalle som muligt, og lange overskrifter ombrydes over flere "
        "linjer, så hele tabellen kan ses uden at skulle scrolle vandret.",
        "GODT AT VIDE"
    )

    heading(doc, "Dan PDF'er", 2, "9.2")
    body(doc, (
        "Genererer individuelle timesedler til alle medarbejdere som PDF-filer og downloader "
        "dem til din computer – én PDF direkte, hvis kun én medarbejder har data i perioden, "
        "ellers en samlet ZIP-fil."
    ))
    bullet(doc, "Klik 'Dan PDF'er'.")
    bullet(doc, "Vælg fra/til-dato og evt. en bestemt medarbejder.")
    bullet(doc, "Klik 'Dan PDF'er'. Filen(erne) downloades til din computer.")
    note_box(doc,
        "Ud over download kan timesedler sendes direkte pr. mail til medarbejderens "
        "registrerede mailadresse – enten enkeltvis fra den relevante medarbejders linje i "
        "lønkørsel-visningen, eller samlet for alle med knappen 'Send timesedler' i "
        "PDF-modalen. Medarbejdere uden en registreret mailadresse springes automatisk over, "
        "og fejl ved selve afsendelsen (fx forkert mailopsætning) vises som en generel "
        "fejlbesked uden tekniske detaljer.",
        "GODT AT VIDE"
    )

    heading(doc, "Kør løn (Danløn CSV)", 2, "9.3")
    body(doc, (
        "Eksporterer den endelige lønfil til Danløn. "
        "Filen er i CSV-format og kan importeres direkte i Danløn."
    ))
    bullet(doc, "Klik 'Kør løn'.")
    bullet(doc, "Bekræft at du er klar til at køre endelig løn.")
    bullet(doc, "CSV-filen downloades til din computer. Filnavnet er (siden 2026-09-22) på formen 'danloen, Lønuge 23-24, 01-06-2026-14-06-2026.csv' – lønuge-numrene og datointervallet for den kørte periode.")
    body(doc, (
        "CSV-filen indeholder op til 6 kolonner per lønpost: CVR-nummer, medarbejdernr., lønkode, "
        "antal (timer eller forekomster), sats og evt. total. "
        "Hvilke kolonner der medtages afhænger af opsætningen i Stamdata → Løntypekoder."
    ))
    body(doc, (
        "'Kør løn'-knappen er grå og kan ikke bruges, hvis der enten er aktiviteter i perioden, "
        "der endnu ikke er godkendt eller deaktiveret, eller hvis lønperioden allerede er kørt og låst. "
        "I begge tilfælde vises en advarsel, hvis man alligevel klikker på knappen. Afventende aktiviteter "
        "skal godkendes eller deaktiveres under fanen 'Aktiviteter', før knappen aktiveres igen. En allerede "
        "låst periode kan genåbnes under 'Administration' (kræver rettigheden 'Åbn låst lønperiode'), hvis "
        "der skal foretages ændringer og køres løn igen."
    ))
    note_box(doc,
        "Genåbner du en låst periode, henter systemet automatisk eventuelle aktiviteter der i "
        "mellemtiden er registreret for den periodes datoer (og som derfor blev lagt i den "
        "efterfølgende periode, se afsnit 3.2) tilbage til den nu-genåbnede periode. Du behøver "
        "ikke selv flytte dem.",
        "GODT AT VIDE"
    )
    note_box(doc,
        "Kontrollér Danløn-koderne i Stamdata → Løntypekoder inden systemet tages i "
        "produktionsbrug: en del koder er ved leveringen sat til en midlertidig placeholder "
        "('1') indtil lønafdelingen oplyser de rigtige Danløn-koder. Bruges systemet med "
        "placeholder-koder, kan flere forskellige lønarter havne under samme kode i Danløn.",
        "VIGTIGT"
    )

    heading(doc, "CSV-kolonneopsætning per løntypekode", 2, "9.3.1")
    body(doc, (
        "Under Stamdata → Løntypekoder kan du for hver løntype styre præcis hvad der eksporteres i CSV-filen:"
    ))
    header_table(doc,
        ["Indstilling", "Valgmuligheder", "Beskrivelse"],
        [
            ["Antal-type",    "Timer / Antal",                 "Timer: eksporterer timetal med 2 decimaler. Antal: eksporterer antal forekomster som heltal (fx overnatninger)."],
            ["Sats-kilde",    "Timesats, OT-satser, Salt, Overnatning, Dagpenge §56", "Bestemmer hvilken sats der bruges til kolonnen Sats og beregning af Total."],
            ["Inkluder sats", "Ja / Nej",                      "Ja: sats-kolonnen skrives i CSV. Nej: satsen udelades fra CSV, men bruges stadig til beregning af Total."],
            ["Inkluder total","Ja / Nej",                      "Ja: en ekstra total-kolonne tilføjes (antal × sats). Nej: ingen total-kolonne."],
        ]
    )
    note_box(doc,
        "Inkluder sats = Nej og Inkluder total = Ja giver en CSV med kun antal og total – "
        "nyttigt når Danløn selv beregner satsen ud fra lønkoden.",
        "TIP"
    )

    heading(doc, "Hvad beregnes?", 2, "9.4")
    body(doc, "For hver godkendt aktivitet beregnes følgende lønposter:")
    header_table(doc,
        ["Lønpost", "Beskrivelse"],
        [
            ["Normal løn",         "Timesats × normaltimer for dagen (fra medarbejderens timefordeling)."],
            ["Tillæg 05-06",       "Forhøjet sats for arbejde mellem kl. 05:00 og 06:00."],
            ["Tillæg 18-21 / OT",  "Forhøjet sats for arbejde kl. 18-21 og overarbejde op til 3 timer."],
            ["Nat / ekstra OT",    "Højeste sats for natarbejde (21-05) og overarbejde over 3 timer."],
            ["Pålæsning",          "Tillæg for pålæsningstid (minutter × minutsats)."],
            ["Aflæsning",          "Tillæg for aflæsningstid (minutter × minutsats)."],
            ["Salttillæg",         "Tillæg pr. time for kørsel med salt (registreret på aktiviteten). Sats fra Stamdata (Tillæg-fanen)."],
            ["Overnatning",        "Fast sats pr. overnatning (antal forekomster × sats). Sats fra Stamdata (Tillæg-fanen)."],
            ["Springertillæg",     "Samme timetal som Normal løn, kun for medarbejdere med springertillæg-fluebenet sat for perioden (afsnit 4.5). Sats fra Stamdata (Tillæg-fanen)."],
        ]
    )
    note_box(doc,
        "Rettet 2026-09-22: 'I alt'-beløbet pr. medarbejder i Lønkørsel-fanen og i PDF-"
        "timesedlens LØNOPSUMMERING medregner nu også fraværstyper med et beregnet beløb "
        "(Sygdom, §56 syg, Barn 1.sygedag u. løn, Feriefri, Barsel, Skole/kursus – samme typer "
        "som i Lønafregningen, afsnit 12.1). Tidligere manglede disse i selve 'I alt'-summen, "
        "selvom de altid har talt korrekt med i den eksporterede Danløn CSV. PDF-timesedlens "
        "fraværslinjer viser nu desuden sats og beløb i stedet for '–', så beløbet i 'I alt' på "
        "timesedlen stemmer overens med det medarbejderen reelt får udbetalt.",
        "GODT AT VIDE"
    )

    heading(doc, "Lørdage, søndage og helligdage", 2, "9.5")
    body(doc, (
        "Lørdage, søndage og helligdage har deres egne lønkoder ud over de tre almindelige "
        "tillæg (kode 1, 7, 8 og 9). Du behøver ikke gøre noget særligt ved registreringen – "
        "systemet genkender automatisk dagtypen ud fra helligdagskalenderen og ugedagen."
    ))
    header_table(doc,
        ["Dag", "Hvad sker der?"],
        [
            ["Lørdag",   "Regnes som en almindelig hverdag. Har medarbejderen ingen garanterede timer den lørdag (det typiske), bliver kørte timer automatisk til kode 8/9 efter samme regler som en hverdags overarbejde."],
            ["Søndag / helligdag", "Garanterede timer udbetales som kode 4 (fuldlønnet) eller kode 63 (timelønnet), oveni evt. kørsel. Alt kørt arbejde går til kode 1 + kode 9 – uanset klokkeslæt."],
            ["1. maj / Grundlovsdag", "Halve helligdage: fri fra kl. 12:00. Kørsel før 12 tæller normalt, kørsel efter 12 følger særlige regler for disse dage."],
        ]
    )
    note_box(doc,
        "En vagt der starter aftenen/natten før en søndag eller helligdag og fortsætter ind i "
        "den, vil i prøvekørslen og PDF-timesedlen kunne vise sig som to linjer i stedet for én "
        "– én for delen inden midnat, én for delen efter. Det er korrekt: de to dele følger hver "
        "sin dags regler. En vagt der fortsætter fra en almindelig hverdag/lørdag ind i en anden "
        "almindelig hverdag/lørdag vises derimod stadig som én sammenhængende linje.",
        "GODT AT VIDE"
    )
    note_box(doc,
        "En medarbejder markeret som 'Afløser' (afsnit 7.2) får IKKE de garanterede "
        "søgnehelligdagstimer på en søndag/helligdag, medmindre vedkommende faktisk har en "
        "godkendt kørselsaktivitet den dag. Har afløseren kørt, gælder alle reglerne ovenfor "
        "helt som normalt.",
        "BEMÆRK"
    )

    heading(doc, "Særaftale: Øvrig overtid for alle timer", 2, "9.6")
    body(doc, (
        "En enkelt navngiven medarbejder kan have en individuel særaftale om at ALLE hans "
        "arbejdstimer giver Øvrig overtid oveni normal løn – uanset tidspunkt på døgnet, "
        "dagtype eller det sædvanlige daglige loft. Aftalen slås til via krydsfeltet 'Særaftale: "
        "Øvrig overtid for alle timer' i medarbejder-modalen (se afsnit 7.2)."
    ))
    bullet(doc, "Erstatter de normale tillæg (05-06, 18-21/OT, nat) i stedet for at lægge oveni dem.")
    bullet(doc, "Intet dagligt loft – fuld normalløn for samtlige arbejdstimer, uanset medarbejderens skemalagte timer.")
    bullet(doc, "Gælder alle dage, også søndage, helligdage, 1. maj og Grundlovsdag.")
    bullet(doc, "Kode 4/63 (søgnehelligdagsbetaling) er upåvirket og beregnes helt som normalt.")
    note_box(doc,
        "Krydses feltet af for en medarbejder, slår ændringen automatisk igennem overalt: "
        "lønkørsel-preview, prøvekørsel, PDF-timesedler, Lønafregning og Danløn CSV. Brug kun "
        "feltet til den konkrete særaftale det er lavet til – det er ikke en generel "
        "'overtidsbonus'-indstilling.",
        "VIGTIGT"
    )

    # ── 10. Vigtige regler ────────────────────────────────────────────────
    doc.add_page_break()
    heading(doc, "Vigtige regler og opmærksomhedspunkter", 1, "10")

    heading(doc, "Inden lønkørsel – tjekliste", 2, "10.1")
    for item in [
        "Alle .ddd-filer er importeret for perioden.",
        "Alle relevante aktiviteter er gennemgået og godkendt.",
        "Aktiviteter med ! (under 4 timer) er godkendt med kommentar.",
        "Eventuelle rettelser er kontrolleret – brug 'Fortryd rettelse' ved fejl.",
        "Prøvekørsel er gennemgået og tallene ser korrekte ud.",
    ]:
        bullet(doc, item)

    heading(doc, "Opdatering af satser", 2, "10.2")
    body(doc, (
        "Timesatser og overtidssatser opdateres via Stamdata-modulet i systemets brugerflade. "
        "Ændringerne slår igennem ved næste beregning uden genstart."
    ))
    for i, step in enumerate([
        "Klik på '⚙️ Stamdata' i venstre menu (kræver administrator-login).",
        "Vælg den relevante fane: 'Overenskomsttyper', 'Overtidssatser' eller 'Tillæg'.",
        "Klik på 'Rediger' ud for den sats der skal ændres.",
        "Indtast den nye sats og klik 'Gem'.",
    ], 1):
        bullet(doc, step, f"Trin {i}: ")
    two_col_table(doc, [
        ["Overenskomsttyper-fanen", "Timesatser for overenskomsttyper (normal løn)."],
        ["Overtidssatser-fanen",    "Satser for de tre overtidstillæg (1 time før, 1-3 timer efter, øvrigt)."],
        ["Tillæg-fanen",            "Sats for salttillæg (pr. time), overnatning (pr. forekomst) og §56."],
    ])
    note_box(doc,
        "Rediger ikke Excel-filerne med forventning om at ændringerne slår igennem. "
        "Excel bruges KUN til den initiale seeding af databasen ved første opstart. "
        "Al efterfølgende konfiguration sker via Stamdata-modulet.",
        "VIGTIGT"
    )
    note_box(doc,
        "Opretter du en helt ny SATS (en ny række i Overtidssatser eller Tillæg, ikke bare en "
        "ny værdi på en eksisterende), har den IKKE automatisk nogen effekt på lønberegningen – "
        "kun eksisterende, kendte tillægstyper beregnes automatisk. En ny sats skal derefter "
        "kobles på en løntypekode via 'Sats-kilde' i Stamdata → Løntypekoder for i det hele "
        "taget at kunne komme med i CSV-eksporten, og selv da påvirker den ikke selve "
        "lønberegningen/prøvekørslen. Skal en helt ny tillægsregel indgå i selve "
        "lønberegningen, kræver det udviklerarbejde – kontakt systemudvikler.",
        "VIGTIGT"
    )

    heading(doc, "Fejl og usædvanlige situationer", 2, "10.3")
    header_table(doc,
        ["Situation", "Hvad gør du?"],
        [
            ["Forkert start- eller sluttid importeret",
             "Åbn aktiviteten og brug 'Ret starttid/sluttid'. Brug 'Fortryd rettelse' hvis du fortryder."],
            ["Chauffør er ikke i systemet (import fejler)",
             "Opret medarbejderen med korrekt førerkortnummer og importér .ddd-filen igen."],
            ["Import viser 0 importerede og mange 'sprunget over', selvom filerne er nye",
             "Kontrollér medarbejderens førerkortnummer i Stamdata: det skal være de "
             "første 14 tegn (landekode + 12 cifre), uden de sidste 2 udskiftnings-/"
             "fornyelsescifre. Ret nummeret og importér filen igen."],
            ["Aktivitet skal deles i to (f.eks. skift af tur)",
             "Brug 'Opdel aktivitet' og angiv tidspunktet for opdelingen."],
            ["Aktivitet skal ignoreres",
             "Brug 'Deaktiver' – aktiviteten medtages ikke i lønberegningen men slettes ikke."],
            ["Medarbejder har nået 9 måneder",
             "Systemet viser et varsel. Opdater overenskomsttypen for medarbejderen."],
            ["Lønkørslen viser ikke nye lønposter (fx overnatning)",
             "Genstart serveren: tryk Ctrl+C i terminalvinduet hvor den kører (eller luk python.exe via Jobliste) og start den igen. Systemet indlæser ny beregningslogik ved opstart – se kapitel 10.2 i Teknisk dokumentation."],
        ]
    )

    note_box(doc,
        "Fratrædelsesdatoen for aktive medarbejdere skal stå på 31-12-9999. "
        "Udfyld kun fratrædelsesdatoen den dag en medarbejder forlader virksomheden.",
        "HUSK"
    )

    # ── 11. Brugerstyring og roller ───────────────────────────────────────
    doc.add_page_break()
    heading(doc, "Brugerstyring og roller", 1, "11")
    body(doc, (
        "Klik på '🔑 Brugere' i venstre menu for at oprette login-brugere, styre hvilke "
        "roller de har, og se hændelsesloggen. Menupunktet er kun synligt for brugere hvis "
        "rolle har rettigheden 'Brugerstyring'. Siden har tre faner: Brugere, Roller og "
        "Hændelseslog."
    ))

    heading(doc, "Brugere-fanen", 2, "11.1")
    body(doc, "Klik '+ Opret bruger' og udfyld navn, initialer/brugernavn (bruges til login), mail (valgfri), rolle og adgangskode.")
    two_col_table(doc, [
        ["Rediger",                "Ændrer navn, initialer, mail, rolle eller adgangskode på en eksisterende bruger."],
        ["Aktiver / Deaktiver",    "Slår login til/fra uden at slette brugeren eller dens historik. En deaktiveret bruger kan ikke logge ind."],
        ["Din egen konto",         "Kan redigeres, men ikke deaktiveres – knappen erstattes af teksten '(dig selv)'."],
    ])
    note_box(doc,
        "Initialer skal være unikke (store/små bogstaver behandles ens) og bruges som "
        "brugernavn ved login.",
        "BEMÆRK"
    )

    heading(doc, "Roller-fanen", 2, "11.2")
    body(doc, (
        "En rolle er en navngivet samling af rettigheder. Hver bruger har præcis én rolle "
        "(sat i Brugere-fanen), og rollen bestemmer hvad brugeren kan se og gøre i systemet."
    ))
    header_table(doc,
        ["Rolle", "Type", "Typiske rettigheder ved oprettelse"],
        [
            ["Administrator", "Systemrolle – kan ikke slettes, rettigheder kan ikke redigeres",
             "Alt: lønkørsel, import, brugerstyring, åbn låst periode, administrér baselines, godkend aktiviteter, se kalender, sæt springertillæg, vagtplan (se + redigér alle linjer)"],
            ["Lønbogholder", "Almindelig rolle – kan redigeres/slettes",
             "Lønkørsel, fraværsoversigt, import, se/tilføj medarbejdere, se/tilføj vogne, anciennitetsvarsel, godkend aktiviteter, se kalender, administrér medarbejdertillæg, sæt springertillæg, vagtplan (se + redigér alle linjer)"],
            ["Disponent", "Almindelig rolle – kan redigeres/slettes",
             "Se medarbejdere, se vogne, godkend aktiviteter, se kalender, sæt springertillæg, vagtplan (se + redigér alle linjer)"],
            ["Kontor", "Almindelig rolle – kan redigeres/slettes",
             "Se vagtplan, redigér egen linje i vagtplan"],
        ]
    )
    note_box(doc,
        "'Administrér baselines' er ikke en selvstændig, tildelbar rettighed som de øvrige i "
        "rettighedsoversigten (afsnit 11.3) – kun Administrator-rollen har adgang til baseline-genopbygning "
        "(POST /api/auto-approval/rebuild-baselines), fordi systemroller altid har fuld adgang. Den kan IKKE "
        "tildeles en anden rolle via afkrydsningsboksene i Roller-fanen. 'Slå auto-godkendelse til/fra' "
        "(manage_auto_approval) er derimod en almindelig, tildelbar rettighed – se afsnit 11.3.",
        "TEKNISK NOTE"
    )
    note_box(doc,
        "Kun 'Administrator' er en beskyttet systemrolle. De øvrige roller – herunder "
        "'Lønbogholder' og 'Disponent' – kan en administrator frit redigere (rettigheder og "
        "visningsnavn) eller slette, og der kan oprettes helt nye, skræddersyede roller efter "
        "behov. 'Kontor' er et eksempel på en sådan senere oprettet rolle, målrettet "
        "medarbejdere der kun skal kunne se og redigere deres egen linje i Vagtplan.",
        "BEMÆRK"
    )
    body(doc, "Klik '+ Opret rolle' for at oprette en ny rolle: angiv et internt rollenavn (kun bogstaver, tal og underscore), et visningsnavn, og afkryds de ønskede rettigheder fra listen nedenfor. Klik 'Rediger' på en eksisterende, ikke-system-rolle for at ændre visningsnavn og rettigheder. En rolle kan kun slettes, hvis ingen brugere har den.")

    heading(doc, "Rettighedsoversigt", 2, "11.3")
    header_table(doc,
        ["Rettighed (nøgle)", "Vises som", "Giver adgang til"],
        [
            ["payroll",                     "Lønkørsel",                          "Menupunktet 'Lønkørsel': prøvekørsel, PDF-timesedler og Danløn CSV-eksport."],
            ["absence_overview",            "Fraværsoversigt",                    "Menupunktet 'Fraværsoversigt'."],
            ["import_ddd",                  "Importer .ddd",                      "Menupunktet 'Importer .ddd' – import af tachografdata."],
            ["user_management",             "Brugerstyring",                     "Menupunktet '🔑 Brugere' – denne side (brugere, roller, hændelseslog)."],
            ["reopen_period",               "Åbn låst lønperiode",                "Mulighed for at genåbne en periode hvor der allerede er kørt løn."],
            ["stamdata",                     "Stamdata",                          "Menupunktet '⚙️ Stamdata' – alle ti faner (se kapitel 7). Auto-godkendelse-fanen kræver desuden 'manage_auto_approval'."],
            ["view_employees",              "Se medarbejdere",                   "Menupunktet 'Medarbejdere' (læse-adgang)."],
            ["manage_employees",            "Tilføj medarbejdere",               "Opret/rediger medarbejdere under 'Medarbejdere'."],
            ["view_vehicles",               "Se vognpark",                       "Menupunktet 'Vognpark' (læse-adgang)."],
            ["manage_vehicles",             "Tilføj vogn",                       "Opret/rediger køretøjer under 'Vognpark'."],
            ["manage_employee_supplements", "Administrér medarbejdertillæg",     "Menupunktet 'Tillæg' – oprette/afslutte kr/time-tillæg."],
            ["manage_holidays",             "Administrér helligdage",            "Stamdata → Helligdage: opret, auto-generer og slet."],
            ["anciennitet_alert",           "Anciennitetsvarsel",                "Modtag pop-up-varsler om medarbejdere med 9 måneders anciennitet."],
            ["paragraf_56_alert",           "§56-advarsel",                      "Modtag pop-up-varsler når en medarbejders §56-aftale nærmer sig udløb, og besked når den automatisk deaktiveres (se afsnit 7.6)."],
            ["approve_activities",          "Godkend aktiviteter",               "Godkend/deaktiver/ret/opdel aktiviteter i aktivitetstabellen."],
            ["auto_approve_manual_activities", "Auto-godkend ved oprettelse",     "Manuelt oprettede aktiviteter godkendes automatisk ved oprettelse, uden separat godkendelsestrin."],
            ["manage_auto_approval",        "Slå auto-godkendelse til/fra",       "Slå den statistiske baseline-auto-godkendelse til/fra globalt, og genopbyg baselines."],
            ["view_calendar",               "Se aktivitetskalender",             "Se aktivitetstabellen (kalendervisningen på forsiden)."],
            ["toggle_springer",             "Sæt springertillæg",                "Afkryds springertillæg-fluebenet i aktivitetsoversigten."],
            ["vagtplan_view",               "Se vagtplan",                       "Menupunktet 'Vagtplan' (læse-adgang)."],
            ["vagtplan_edit_own",           "Redigér egen linje i vagtplan",     "Ret kun sin egen række i Vagtplan (matches på initialer)."],
            ["vagtplan_edit_all",           "Redigér alle linjer i vagtplan",    "Ret alle medarbejderes rækker i Vagtplan."],
            ["payroll_settlement_view",     "Lønafregning (se)",                 "Menupunktet 'Lønafregning': periodetotaler og pr.-medarbejder oversigt (se kapitel 12)."],
            ["payroll_settlement_export",   "Lønafregning (eksport)",            "Eksportér Lønafregning som CSV. Kræver låst periode, medmindre brugeren er administrator."],
            ["dagsplan_view",               "Se dagsplan",                       "Menupunktet 'Dagsplan' (læse-adgang, se kapitel 13)."],
            ["dagsplan_edit",               "Redigér dagsplan",                  "Redigér tildelinger og 'informeret'-afkrydsning, meld/fjern materielt fravær."],
        ],
        [Cm(3.5), Cm(4), Cm(8.5)]
    )
    note_box(doc,
        "Rettigheder er additive og uafhængige af hinanden – der er ingen indbygget "
        "hierarki. En rolle med kun 'Se vagtplan' + 'Redigér egen linje i vagtplan' (som "
        "'Kontor') ser IKKE Aktiviteter, Lønkørsel eller andre menupunkter, uanset hvor "
        "'lille' rettigheden lyder.",
        "TEKNISK NOTE"
    )

    heading(doc, "Hændelseslog-fanen", 2, "11.4")
    body(doc, (
        "Viser de seneste 500 hændelser i systemet, nyeste øverst: oprettelse/redigering af "
        "brugere og roller, rolleskift, samt Stamdata-ændringer (opret/redigér/slet). Hver "
        "linje viser tidspunkt, hvilken bruger der udførte handlingen, selve handlingen og en "
        "kort detaljetekst. Søgefeltet filtrerer på tværs af bruger, handling og detaljer; "
        "'⟲ Opdater' genindlæser listen."
    ))

    # ── 12. Lønafregning ──────────────────────────────────────────────────
    doc.add_page_break()
    heading(doc, "Lønafregning", 1, "12")
    body(doc, (
        "Klik på '🧾 Lønafregning' i venstre menu, lige under 'Lønkørsel'. Fanen giver et samlet "
        "overblik over periodens løn: én total-tabel øverst for hele perioden, og derunder én "
        "tabel pr. medarbejder med alle 14 dage. Menupunktet kræver rettigheden "
        "'Lønafregning (se)', og eksportknappen kræver derudover 'Lønafregning (eksport)' "
        "(se afsnit 11.3)."
    ))

    heading(doc, "Periodetotalen øverst", 2, "12.1")
    body(doc, (
        "Den øverste tabel 'Total sum for perioden' viser: Grundtimeløn inkl. tillæg, Overtid "
        "Timen før, Overtid 1-3 time efter og Øvrig overtid, efterfulgt af delsummen "
        "'Total uden fravær'. Herefter følger Salttillæg, Overnatning og DOB Overnatning (hver "
        "med antal forekomster i parentes, fx 'Overnatning (3 gange)') og op til 11 fraværstyper "
        "(Sygdom, Sygdom u. 8 uger, Barn 1.sygedag, Barn 1.sygedag u. 8 uger, Graviditetsbetinget "
        "sygdom, §56 syg, Barsel, Feriefri, Ferie, Skole/kursus og Afspadsering), og til sidst "
        "'Total sum for denne periode'. En linje vises KUN hvis den har et beløb større end 0 kr "
        "for den viste periode – har ingen medarbejder fx haft barsel, udelades 'Barsel'-linjen "
        "helt."
    ))
    note_box(doc,
        "Rettet 2026-09-21: Overnatning og DOB Overnatning talte tidligere IKKE med i 'Total sum "
        "for denne periode' eller i den enkelte medarbejders samlede løn i denne fane – kun i "
        "Lønkørsel-fanen og PDF-timesedlen. Beløbene indgår nu korrekt begge steder.",
        "GODT AT VIDE"
    )

    heading(doc, "Medarbejder-tabellerne", 2, "12.2")
    body(doc, (
        "Hver medarbejders kort viser i overskriften: overenskomsttype med sats i kr/time, "
        "personligt tillæg (hvis medarbejderen har et) og springertillæg (hvis aktiveret for "
        "perioden) – alle tre vist som separate tal, ikke lagt sammen. Derunder følger en "
        "tabel med én række pr. dag i perioden (også dage uden aktivitet, som vises med 0)."
    ))
    header_table(doc,
        ["Kolonne", "Indhold"],
        [
            ["Normal timer / Overtid 1 time før / Overtid 1-3 timer efter / Øvrig overtid",
             "Vist som timer:minutter (fx '7:30'), ikke decimaltal."],
            ["Total tid",     "Dagens samlede tid som decimaltal (fx '7,50')."],
            ["Total i kr. / Beløb", "Dagens samlede løn i kr. På en fraværsdag med en betalt "
             "fraværstype (se afsnit 12.1) vises fraværstimernes egen værdi her i stedet for 0,00."],
            ["Vognnummer",    "Aktivitetens vognnummer – på en fraværsdag vises i stedet "
             "fraværstypens navn (fx 'Sygdom'), selvom aktiviteten har et udfyldt vognnummer-felt."],
        ]
    )
    body(doc, (
        "Nederst i hver medarbejders tabel står 'Total løn for [navn]' – den fulde sum for "
        "medarbejderen i perioden: arbejdstid, overtid, salttillæg, overnatning, DOB "
        "overnatning, springertillæg OG al fraværsbetaling med et beregnet beløb (se afsnit "
        "12.1 for hvilke typer det gælder)."
    ))

    heading(doc, "Periode-visning", 2, "12.3")
    body(doc, (
        "Lønafregning har ingen egen periodevælger – siden følger i stedet den periode du "
        "senest har navigeret til med pilene (‹ ›) i Aktivitetsoversigten, ligesom Lønkørsel "
        "allerede gør. Har du ikke navigeret til en bestemt periode, vises dagens periode. "
        "Skal du fx tjekke eller eksportere en periode der er kørt løn for og siden er blevet "
        "'gammel' (dagens periode er rykket videre), skal du først gå til Aktiviteter og "
        "bladre tilbage til den ønskede periode med '‹', og derefter klikke på Lønafregning."
    ))

    heading(doc, "Eksportér CSV", 2, "12.4")
    body(doc, (
        "Knappen '💾 Eksportér CSV' downloader én CSV-fil til din computer for hele den viste "
        "periode med data for alle medarbejdere – ikke topsummeringen."
    ))
    bullet(doc, "Naviger til den ønskede periode (se afsnit 12.3).")
    bullet(doc, "Klik '💾 Eksportér CSV'.")
    bullet(doc, "Klik 'Eksportér'. Filen downloades til din computer.")
    body(doc, (
        "CSV-filen (semikolon-separeret) indeholder kolonnerne Dato, Lønnummer, Normal timer, "
        "Overtid 1 time før, Overtid 1-3 timer efter, Øvrig overtid, Total tid, Total i kr., "
        "Vognnummer og Beløb – én række pr. dag pr. medarbejder, efterfulgt af en "
        "'Total løn for [navn]'-række."
    ))
    note_box(doc,
        "Eksport kræver at den viste periode er låst (der er kørt løn for den under "
        "Lønkørsel) – ellers vises en fejlbesked, og der eksporteres ikke. Administratorer "
        "er undtaget og kan altid eksportere, uanset periodens status. Selve eksporten LÅSER "
        "ikke perioden – det sker kun ved 'Kør løn' under Lønkørsel.",
        "VIGTIGT"
    )

    # ── 13. Dagsplan ─────────────────────────────────────────────────────
    doc.add_page_break()
    heading(doc, "Dagsplan", 1, "13")
    body(doc, (
        "Klik på '🗓️ Dagsplan' i venstre menu for at se og redigere dagens fordeling af vogne "
        "til chauffører – den digitale afløser for det Excel-ark, der tidligere blev brugt uden "
        "for systemet. Siden kræver rettigheden 'Se dagsplan'; redigering kræver desuden "
        "'Redigér dagsplan' (se afsnit 11.3). Uden redigeringsrettighed ser du samme visning, "
        "men alle felter og knapper er låst."
    ))
    body(doc, "Siden har to underfaner, der deler samme valgte dato: 'Dagsplan' og 'Materiel fravær'.")

    heading(doc, "Dagsplan-fanen", 2, "13.1")
    body(doc, (
        "Øverst navigerer du mellem dage med ◀ / ▶ eller datovælgeren (default: dags dato). "
        "Disponentgruppe-filteret og det søgbare medarbejder-filter indsnævrer kun hovedtabellen "
        "– sidelisten med den fulde medarbejderoversigt er altid upåvirket af filtrene."
    ))
    header_table(doc,
        ["Kolonne", "Indhold"],
        [
            ["Vognnummer",  "Vognens nummer (fra Vognpark)."],
            ["Beskrivelse", "Vognens beskrivelse, hvis udfyldt under Vognpark."],
            ["Chauffør",    "Søgbar medarbejder-vælger. Er medarbejderens 'Fast bil' sat til denne vogn (se afsnit 7.2), foreslås vedkommende automatisk – forslaget kan altid ændres."],
            ["Opgave",      "Frit tekstfelt."],
            ["Informeret",  "Afkrydsningsfelt – markér når chaufføren er informeret om dagens tildeling."],
        ]
    )
    body(doc, (
        "Under hovedtabellen findes 10 faste 'EKSTRA'-rækker til hjælp på pladsen eller lærlinge "
        "– samme felter som ovenfor, men uden vognnummer og uden vognnummer-autoudfyldning på "
        "aktiviteter."
    ))
    bullet(doc, "En medarbejder med registreret fravær den valgte dag vises med rødt i sidelisten – og forbliver rødt, selv hvis vedkommende samtidig er skrevet i en Chauffør-kolonne.")
    bullet(doc, "En vogn med meldt materielt fravær (se afsnit 13.2) vises rødt i hovedtabellen.")
    bullet(doc, "Er der uoverensstemmelse mellem den tildelte vogn og vognnummeret på chaufførens egen 'normal tid'-aktivitet den dag, vises et ⚠️-ikon med tooltip 'vognnummer i løn: xxx' ved chaufførnavnet.")
    note_box(doc,
        "Forsøger du at tildele en medarbejder, der allerede har en anden tildeling (eller "
        "registreret fravær) samme dag, viser systemet en advarsel i stedet for at blokere "
        "handlingen – bekræfter du, gennemføres dobbelttildelingen alligevel.",
        "BEMÆRK"
    )
    note_box(doc,
        "Opretter du en 'normal tid'-aktivitet for en chauffør med en tildelt vogn i Dagsplan "
        "den pågældende dag, udfyldes vognnummeret automatisk på aktiviteten – medmindre feltet "
        "allerede er udfyldt. Dette rører ikke ved fraværstyper eller EKSTRA-rækkerne.",
        "GODT AT VIDE"
    )

    heading(doc, "Materiel fravær-fanen", 2, "13.2")
    body(doc, (
        "Registrér når en vogn er ude af drift (værksted, reparation m.m.). Klik "
        "'Meld materielt fravær' (kræver 'Redigér dagsplan') og angiv vogn, 'Fra dato' (default: "
        "fanens valgte dato), en valgfri 'Til dato' (tom betyder étdags-fravær) samt en kommentar. "
        "Tabellen nedenfor viser dagens meldte fravær med en slet-knap."
    ))

    # ── 14. Vagtplan ─────────────────────────────────────────────────────
    doc.add_page_break()
    heading(doc, "Vagtplan", 1, "14")
    body(doc, (
        "Klik på '🗓️ Vagtplan' i venstre menu for at se en 4-ugers oversigt over alle "
        "medarbejderes fravær og kommentarer, med ugenummer i kolonneoverskriften. Kræver "
        "rettigheden 'Se vagtplan'; redigering kræver desuden enten 'Redigér egen linje i "
        "vagtplan' (kun din egen række) eller 'Redigér alle linjer i vagtplan'."
    ))

    heading(doc, "Registrering", 2, "14.1")
    body(doc, "Klik på en tom celle for at registrere fravær eller en kommentar for medarbejderen den dag:")
    bullet(doc, "Vælg en almindelig fraværstype (ferie, sygdom osv.) for at oprette en rigtig aktivitet – nøjagtig samme modal som i Aktivitetsoversigten (kapitel 6).")
    bullet(doc, "Vælg 'Ingen (kun kommentar)' for blot at skrive en fri tekstnote uden at oprette nogen aktivitet – bruges fx til 'ringer ind kl. 10' eller lignende driftsnoter.")
    body(doc, "Klik på en udfyldt celle for at se/redigere den. Fraværsaktiviteter åbner samme aktivitetsdetalje som i Aktivitetsoversigten; rene kommentarer åbner en lille rediger/slet-boks.")

    heading(doc, "Filtrering og 'Fravær i morgen'", 2, "14.2")
    body(doc, (
        "Afdelingsfiltret er en flervalgsliste (klik for at vælge flere grupper ad gangen; "
        "klik 'Vælg alle' først for kun at isolere én gruppe). Knappen 'Fravær i morgen' åbner "
        "en hurtig opsummering af alle medarbejdere (inden for det valgte filter) der har "
        "fravær eller en kommentar registreret på dagen efter i dag – uden at du behøver bladre "
        "en hel uge frem."
    ))
    note_box(doc,
        "Vagtplan og Aktivitetsoversigten viser samme underliggende data – opretter du en "
        "fraværsaktivitet i Vagtplan, ses den også i Aktivitetsoversigten, og omvendt.",
        "GODT AT VIDE"
    )

    # ── 15. Fraværsoversigt ──────────────────────────────────────────────
    doc.add_page_break()
    heading(doc, "Fraværsoversigt", 1, "15")
    body(doc, (
        "Klik på '📊 Fraværsoversigt' i venstre menu for et samlet overblik over fravær pr. "
        "medarbejder og pr. fraværstype over en valgfri periode – uafhængig af de faste "
        "14-dages lønperioder. Kræver rettigheden 'Fraværsoversigt'."
    ))
    bullet(doc, "Vælg en fra- og til-dato for den ønskede periode.")
    bullet(doc, "Tabellen viser fraværstimer/-dage summeret pr. medarbejder og pr. fraværstype, samt en sats i kr/time pr. række.")
    note_box(doc,
        "Satsen der vises her, opdateres IKKE nødvendigvis, hvis I ændrer satser i Stamdata. "
        "Særligt §56-satsen kan afvige fra den aktuelle værdi i Stamdata → Tillæg, og fraværstyper "
        "som Ferie, Feriefri og Afspadsering vises med 0 kr/t her, selvom de udbetales i den "
        "faktiske lønkørsel. Brug Lønafregning (kapitel 12) eller den endelige Danløn-eksport som "
        "facit for hvad der reelt udbetales – Fraværsoversigtens sats-kolonne er kun vejledende.",
        "BEMÆRK"
    )

    heading(doc, "Eksport", 2, "15.1")
    body(doc, "To eksportknapper downloader Excel-filer med samme datointerval som den valgte visning:")
    bullet(doc, "Eksporterer én række pr. kalenderdag med fravær, valgfrit afgrænset til alle medarbejdere, én disponentgruppe eller én enkelt medarbejder.", "Eksportér pr. medarbejder: ")
    bullet(doc, "Eksporterer summeret pr. fraværstype – vælg i en afkrydsningsliste hvilke fraværstyper der skal med (eller markér 'alle').", "Eksportér pr. fraværstype: ")

    # ── 16. Vognpark ─────────────────────────────────────────────────────
    doc.add_page_break()
    heading(doc, "Vognpark", 1, "16")
    body(doc, (
        "Klik på '🚛 Vognpark' i venstre menu for at se og redigere køretøjer. Kræver mindst "
        "'Se vognpark'; opret/rediger/slet kræver 'Tilføj vogn'."
    ))
    header_table(doc,
        ["Felt", "Beskrivelse"],
        [
            ["Nummerplade",     "Registreringsnummer, fx 'DF67671'."],
            ["Vognnummer",      "Internt vognnummer."],
            ["Beskrivelse",     "Fri tekst, vises som ekstra kolonne i Dagsplan (kapitel 13)."],
            ["Disponentgruppe", "Valgfri – knytter vognen til en afdeling."],
            ["Vognpark",        "Afkryds for at vognen skal vises i Dagsplans vognkolonne og kunne vælges som 'Fast bil' på en medarbejder (se nedenfor)."],
        ]
    )
    body(doc, (
        "Siden har to underfaner: 'Vognpark' viser kun de vogne der har fluebenet 'Vognpark' "
        "sat – det er dem der reelt kører gods og indgår i Dagsplan og 'Fast bil'-valget. 'Alle' "
        "viser samtlige oprettede vogne, inklusive interne poster/afdelinger der ikke skal med i "
        "den daglige vognfordeling."
    ))
    note_box(doc,
        "Nyoprettede vogne har som udgangspunkt IKKE fluebenet 'Vognpark' sat og vises derfor "
        "ikke i Dagsplan, før du aktivt går ind under fanen 'Alle' og krydser feltet af. "
        "'Meld materielt fravær' (kapitel 13.2) og medarbejder-modalens 'Fast bil'-søgning viser "
        "i øvrigt alle vogne uanset dette flueben.",
        "BEMÆRK"
    )

    # ── 17. Auto-godkendelse ─────────────────────────────────────────────
    doc.add_page_break()
    heading(doc, "Auto-godkendelse", 1, "17")
    body(doc, (
        "Systemet kan automatisk godkende kørselsdage der er importeret fra tachografen "
        "(.ddd-filer), hvis de ligner medarbejderens sædvanlige mønster for den pågældende "
        "ugedag. Dette er UAFHÆNGIGT af 'Auto-godkend ved oprettelse'-rettigheden (kapitel 6), "
        "som handler om manuelt oprettede aktiviteter – de to må ikke forveksles."
    ))
    note_box(doc,
        "Kun kørselsdage fra tachografimport kan blive auto-godkendt af denne funktion. Manuelt "
        "oprettede aktiviteter og fraværstyper er slet ikke i spil her.",
        "BEMÆRK"
    )

    heading(doc, "Hvordan afgøres det?", 2, "17.1")
    body(doc, (
        "For hver medarbejder og ugedag (mandag til søndag hver for sig) husker systemet det "
        "typiske mønster – gennemsnitlig varighed og starttidspunkt, baseret på tidligere "
        "godkendte dage. En ny kørselsdag godkendes automatisk, hvis BÅDE varighed og starttid "
        "ligger tæt nok på dette mønster. Er der endnu ikke registreret mindst 5 tidligere dage "
        "for den ugedag, godkendes dagen ikke automatisk ('Ikke nok data')."
    ))
    body(doc, (
        "Afviger dagen for meget, bliver den IKKE auto-godkendt – den forbliver 'Afventer' som "
        "normalt, og skal godkendes manuelt ligesom hidtil. Årsagen til afvisningen vises i "
        "aktivitetsdetaljen under 'Afvigelser registreret (ikke auto-godkendt)' (afsnit 5.1), så "
        "du kan se præcis hvad der afveg."
    ))

    heading(doc, "Sådan ser du det i praksis", 2, "17.2")
    two_col_table(doc, [
        ["Lille prik ved klokkeslættet", "Aktiviteten er auto-godkendt (status 'Godkendt' uden manuel handling)."],
        ["'Autogodkend aktiviteter'-knap", "I aktivitetstabellens værktøjslinje – gennemgår alle afventende kørselsdage i den viste periode og godkender dem der matcher mønsteret. Resten flages til manuel gennemgang. Vises kun når funktionen er slået til (se nedenfor)."],
        ["'Afvigelser registreret'",       "I aktivitetsdetaljen for en dag der IKKE blev auto-godkendt – forklarer hvorfor (afsnit 5.1)."],
    ])

    heading(doc, "Global til/fra-kontakt", 2, "17.3")
    body(doc, (
        "Under Stamdata → 'Auto-godkendelse' kan brugere med rettigheden 'Slå auto-godkendelse "
        "til/fra' se status og slå hele funktionen til eller fra for alle medarbejdere på én "
        "gang. Er den slået fra, godkendes intet automatisk – hverken ved import eller via "
        "'Autogodkend aktiviteter'-knappen (som så også er skjult), og alle kørselsdage skal "
        "godkendes manuelt som før funktionen fandtes."
    ))
    note_box(doc,
        "Kontakten påvirker KUN denne statistiske auto-godkendelse. Den har ingen indflydelse på "
        "'Auto-godkend ved oprettelse' (manuelle aktiviteter, kapitel 6) eller på fraværstypers "
        "uændrede automatiske godkendelse ved oprettelse.",
        "BEMÆRK"
    )

    doc.save(OUT / "Brugervejledning.docx")
    print("Brugervejledning.docx gemt.")


if __name__ == "__main__":
    build_teknisk()
    build_bruger()
    print("Begge dokumenter er gemt i docs/-mappen.")
