# Udvidet medarbejderregister – implementeringsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Udvid medarbejderregisteret med lønnummer-generator, nye felter (stilling, CPR, anciennitetsdato, elev, personaleforening, natarbejdetillæg), stamdata-fane for stillinger, tre nye advarsler, telefonsøgning, nye filtre, tabelvisning og Excel-eksport.

**Architecture:** FastAPI + SQLAlchemy (SQLite) backend, vanilla JS-frontend i én fil (`app/static/js/app.js`) og én Jinja-skabelon (`app/templates/index.html`). Rene regler (lønnummer, CPR, advarselsvinduer) samles i et nyt, rent modul `app/utils/employee_rules.py`, der kan unit-testes uden database. Endpoints følger de eksisterende mønstre i `app/routers/employees.py` og `app/routers/stamdata.py`.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy, Pydantic v2, openpyxl, pytest, vanilla JS.

**Spec:** `docs/superpowers/specs/2026-10-01-medarbejderregister.md` – læs den før du starter.

## Global Constraints

- **Ingen git-handlinger.** Brugeren stager, committer og pusher selv i VS Code (push = deploy til produktion). Hvert task slutter med "Stop – brugeren committer", ikke en commit-kommando.
- Kør alle tests fra projektroden: `python -m pytest tests -q`. Udgangspunkt 2026-10-01: **494 passed**. Antallet må kun stige.
- "Funktionær" = `agreement_kind == "funktionaer"`. "Chauffør" = enhver anden `agreement_kind`.
- Brandfarver: primary `#317423`, accent `#78b21a`, lys tint `#d4edcc`. Elev-farve: celle `#fff3b8`, avatar `#e0a800`. Afløser beholder `#d4edcc` / `var(--accent)`.
- Al bruger-synlig tekst er dansk.
- Al HTML bygget i JS escapes med den eksisterende `h()`-funktion. Værdier i `onclick`-attributter bruger `jq()`.
- Påkrævede felter skal håndhæves både i klienten (`confirmEmployee()`) og på serveren.
- Gamle medarbejdere må ikke blive ugyldige. På serveren håndhæves påkrævede felter **kun for felter, der sendes med** i en PATCH. Klienten sender altid hele formularen, så reglerne slår igennem "næste gang medarbejderen gemmes".
- CPR's sidste fire cifre må aldrig sendes til en bruger uden rettigheden `view_cpr`, hverken i API-svar, tabel eller Excel.
- Nye rettigheder: `view_cpr`, `jubilee_alert`, `elev_alert`, `birthday_alert`, `employee_table_view`, `employee_export`. Kun admin har dem fra start (admin har implicit alle via `Role.is_system`), så der skal **ikke** laves `_grant_permissions_once`-kald.
- Cache-busting af `app.js` sker automatisk (`?v={{ app_js_mtime }}`). Der er intet at gøre.

---

## Filoversigt

| Fil | Ansvar | Ny/ændret |
|---|---|---|
| `app/utils/employee_rules.py` | Rene regler: næste lønnummer, CPR (validering, fødselsdato, maskering), advarselsvinduer | **Ny** |
| `app/database/models.py` | `MasterPosition` og nye `Employee`-kolonner | Ændret |
| `app/database/session.py` | `_migrate()` tilføjer kolonnerne til eksisterende DB | Ændret |
| `app/database/schemas.py` | Felter på `EmployeeCreate`/`EmployeeUpdate`/`EmployeeResponse`, `MilestoneAlert`, `MilestoneAlertDismiss`, `EmployeeExportRequest` | Ændret |
| `app/auth.py` | 6 nye rettigheder | Ændret |
| `app/routers/employees.py` | Validering pr. type, CPR, generator, nummertjek, positionsliste, advarsler, eksport | Ændret |
| `app/routers/stamdata.py` | CRUD for Stillinger | Ændret |
| `app/templates/index.html` | Modal-felter, popup for skjulte flag, advarsels-modal, stamdata-fane, værktøjslinje og tabel | Ændret |
| `app/static/js/app.js` | Al frontend | Ændret |
| `app/static/css/style.css` | `elev-highlight` | Ændret |
| `tests/conftest.py` | Seed én `MasterPosition` i `db`-fixturen + `required_employee_fields()` | Ændret |
| `tests/test_employee_rules.py` | Unit tests af reglerne | **Ny** |
| `tests/test_employee_register_fields.py` | Model, migration, create/update-validering, CPR-maskering | **Ny** |
| `tests/test_employee_number_endpoints.py` | Generator og nummertjek | **Ny** |
| `tests/test_stamdata_positions.py` | CRUD for stillinger | **Ny** |
| `tests/test_milestone_alerts.py` | Jubilæum, elev og fødselsdag | **Ny** |
| `tests/test_employee_export.py` | Excel-eksport | **Ny** |
| 6 eksisterende testfiler | Body-hjælpere får de nye påkrævede felter | Ændret |
| `CODEREF.md`, `docs/DATA_MODEL.md`, `docs/build_docs.py` | Dokumentation | Ændret |

---

### Task 1: Rene regler – `employee_rules.py`

**Files:**
- Create: `app/utils/employee_rules.py`
- Test: `tests/test_employee_rules.py`

**Interfaces:**
- Produces:
  - `EMPLOYEE_NUMBER_FLOOR: int = 34000`
  - `next_employee_number(existing: Iterable[str]) -> str`
  - `validate_cpr(cpr: str) -> str` (returnerer den trimmede streng, kaster `ValueError` med dansk besked)
  - `cpr_birthdate(cpr: str) -> date`
  - `mask_cpr(cpr: Optional[str]) -> Optional[str]`
  - `is_masked_cpr(value: Optional[str]) -> bool`
  - `one_month_before(d: date) -> date`
  - `in_alert_window(event: date, today: date) -> bool`
  - `anniversary(start: date, years: int) -> date`
  - `round_birthday_alert(birth: date, today: date) -> Optional[tuple[int, date]]`
  - `jubilee_alert(start: date, today: date) -> Optional[tuple[int, date]]`
  - `JUBILEE_YEARS = (25, 40, 50)`

- [ ] **Step 1: Skriv de fejlende tests**

`tests/test_employee_rules.py`:

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from datetime import date

import pytest

from utils.employee_rules import (
    next_employee_number, validate_cpr, cpr_birthdate, mask_cpr, is_masked_cpr,
    one_month_before, in_alert_window, anniversary, round_birthday_alert, jubilee_alert,
)


# ── Lønnummer ──────────────────────────────────────────────────────────────

def test_next_number_is_highest_plus_one_without_filling_gaps():
    assert next_employee_number(["34637", "34640"]) == "34641"


def test_next_number_ignores_numbers_below_34000_and_non_numeric():
    assert next_employee_number(["33999", "1234", "TEST998", "34001"]) == "34002"


def test_next_number_continues_past_34999():
    assert next_employee_number(["34999"]) == "35000"


def test_next_number_defaults_to_34000():
    assert next_employee_number(["5", "TEST1"]) == "34000"
    assert next_employee_number([]) == "34000"


def test_next_number_ignores_blank_and_whitespace():
    assert next_employee_number(["", None, " 34100 "]) == "34101"


# ── CPR ────────────────────────────────────────────────────────────────────

def test_validate_cpr_accepts_valid():
    assert validate_cpr(" 120385-1234 ") == "120385-1234"


@pytest.mark.parametrize("bad", ["1203851234", "12038-51234", "120385-123", "abcdef-1234", "320185-1234", "120385-12345"])
def test_validate_cpr_rejects_wrong_format_or_date(bad):
    with pytest.raises(ValueError):
        validate_cpr(bad)


@pytest.mark.parametrize("cpr,expected", [
    ("120385-1234", date(1985, 3, 12)),   # 7. ciffer 1 → 1900
    ("120305-4234", date(2005, 3, 12)),   # 7. ciffer 4, år 05 → 2000
    ("120385-4234", date(1985, 3, 12)),   # 7. ciffer 4, år 85 → 1900
    ("120305-5234", date(2005, 3, 12)),   # 7. ciffer 5, år 05 → 2000
    ("120385-5234", date(1885, 3, 12)),   # 7. ciffer 5, år 85 → 1800
    ("120336-9234", date(2036, 3, 12)),   # 7. ciffer 9, år 36 → 2000
    ("120337-9234", date(1937, 3, 12)),   # 7. ciffer 9, år 37 → 1900
])
def test_cpr_birthdate_century_rule(cpr, expected):
    assert cpr_birthdate(cpr) == expected


def test_mask_cpr():
    assert mask_cpr("120385-1234") == "120385-****"
    assert mask_cpr(None) is None
    assert mask_cpr("") == ""


def test_is_masked_cpr():
    assert is_masked_cpr("120385-****") is True
    assert is_masked_cpr("120385-1234") is False
    assert is_masked_cpr(None) is False


# ── Advarselsvinduer ───────────────────────────────────────────────────────

def test_one_month_before_same_day_and_clamped():
    assert one_month_before(date(2026, 11, 15)) == date(2026, 10, 15)
    assert one_month_before(date(2026, 3, 31)) == date(2026, 2, 28)
    assert one_month_before(date(2026, 1, 10)) == date(2025, 12, 10)


def test_in_alert_window_inclusive_both_ends():
    event = date(2026, 11, 15)
    assert in_alert_window(event, date(2026, 10, 14)) is False
    assert in_alert_window(event, date(2026, 10, 15)) is True
    assert in_alert_window(event, date(2026, 11, 15)) is True
    assert in_alert_window(event, date(2026, 11, 16)) is False   # overskredet → ingen popup


def test_anniversary_handles_feb_29():
    assert anniversary(date(2000, 2, 29), 25) == date(2025, 2, 28)
    assert anniversary(date(2001, 6, 1), 25) == date(2026, 6, 1)


def test_round_birthday_alert_inside_window():
    # Fylder 40 den 15/11-2026 → vises fra 15/10-2026
    assert round_birthday_alert(date(1986, 11, 15), date(2026, 10, 20)) == (40, date(2026, 11, 15))


def test_round_birthday_alert_all_tens_including_10_and_20():
    assert round_birthday_alert(date(2016, 11, 15), date(2026, 11, 1)) == (10, date(2026, 11, 15))
    assert round_birthday_alert(date(2006, 11, 15), date(2026, 11, 1)) == (20, date(2026, 11, 15))


def test_round_birthday_alert_none_when_not_round_or_outside_window():
    assert round_birthday_alert(date(1987, 11, 15), date(2026, 11, 1)) is None   # 39 år
    assert round_birthday_alert(date(1986, 11, 15), date(2026, 10, 14)) is None  # for tidligt
    assert round_birthday_alert(date(1986, 11, 15), date(2026, 11, 16)) is None  # overskredet


def test_round_birthday_alert_across_new_year():
    # Fylder 50 den 5/1-2027, i dag 10/12-2026 → i vinduet (fra 5/12-2026)
    assert round_birthday_alert(date(1977, 1, 5), date(2026, 12, 10)) == (50, date(2027, 1, 5))


def test_jubilee_alert_25_40_50_only():
    assert jubilee_alert(date(2001, 11, 15), date(2026, 11, 1)) == (25, date(2026, 11, 15))
    assert jubilee_alert(date(1986, 11, 15), date(2026, 11, 1)) == (40, date(2026, 11, 15))
    assert jubilee_alert(date(1976, 11, 15), date(2026, 11, 1)) == (50, date(2026, 11, 15))
    assert jubilee_alert(date(1996, 11, 15), date(2026, 11, 1)) is None   # 30 år – ikke jubilæum
    assert jubilee_alert(date(2001, 11, 15), date(2026, 11, 16)) is None  # overskredet
```

- [ ] **Step 2: Kør testen og se den fejle**

Run: `python -m pytest tests/test_employee_rules.py -q`
Expected: FAIL med `ModuleNotFoundError: No module named 'utils.employee_rules'`

- [ ] **Step 3: Implementér modulet**

`app/utils/employee_rules.py`:

```python
"""Rene regler for medarbejderregisteret (ingen database) – se
docs/superpowers/specs/2026-10-01-medarbejderregister.md."""
import calendar
import re
from datetime import date
from typing import Iterable, Optional

EMPLOYEE_NUMBER_FLOOR = 34000
JUBILEE_YEARS = (25, 40, 50)

_CPR_RE = re.compile(r"^(\d{2})(\d{2})(\d{2})-(\d{4})$")


def next_employee_number(existing: Iterable[Optional[str]]) -> str:
    """Højeste numeriske lønnummer >= 34000 plus 1. Huller udfyldes ikke."""
    numbers = []
    for raw in existing:
        s = (raw or "").strip()
        if s.isdigit() and int(s) >= EMPLOYEE_NUMBER_FLOOR:
            numbers.append(int(s))
    return str(max(numbers) + 1) if numbers else str(EMPLOYEE_NUMBER_FLOOR)


def _century(year2: int, digit7: int) -> int:
    if digit7 <= 3:
        return 1900
    if digit7 in (4, 9):
        return 2000 if year2 <= 36 else 1900
    return 2000 if year2 <= 57 else 1800


def cpr_birthdate(cpr: str) -> date:
    m = _CPR_RE.match(cpr.strip())
    if not m:
        raise ValueError("CPR-nummer skal have formatet ddmmåå-xxxx")
    dd, mm, yy, tail = m.groups()
    year = _century(int(yy), int(tail[0])) + int(yy)
    return date(year, int(mm), int(dd))


def validate_cpr(cpr: str) -> str:
    s = (cpr or "").strip()
    if not _CPR_RE.match(s):
        raise ValueError("CPR-nummer skal have formatet ddmmåå-xxxx")
    try:
        cpr_birthdate(s)
    except ValueError:
        raise ValueError("CPR-nummerets første 6 cifre er ikke en gyldig dato")
    return s


def mask_cpr(cpr: Optional[str]) -> Optional[str]:
    if not cpr:
        return cpr
    return cpr[:7] + "****"


def is_masked_cpr(value: Optional[str]) -> bool:
    return bool(value) and value.endswith("****")


def _clamp(year: int, month: int, day: int) -> date:
    return date(year, month, min(day, calendar.monthrange(year, month)[1]))


def one_month_before(d: date) -> date:
    year, month = (d.year - 1, 12) if d.month == 1 else (d.year, d.month - 1)
    return _clamp(year, month, d.day)


def in_alert_window(event: date, today: date) -> bool:
    """Fra og med samme dato måneden før til og med selve dagen."""
    return one_month_before(event) <= today <= event


def anniversary(start: date, years: int) -> date:
    return _clamp(start.year + years, start.month, start.day)


def round_birthday_alert(birth: date, today: date) -> Optional[tuple]:
    """(alder, dato) hvis en rund fødselsdag (10, 20, 30 …) ligger i advarselsvinduet."""
    for year in (today.year, today.year + 1):
        age = year - birth.year
        if age <= 0 or age % 10:
            continue
        event = anniversary(birth, age)
        if in_alert_window(event, today):
            return age, event
    return None


def jubilee_alert(start: date, today: date) -> Optional[tuple]:
    """(år, dato) hvis 25-, 40- eller 50-års jubilæum ligger i advarselsvinduet."""
    for years in JUBILEE_YEARS:
        event = anniversary(start, years)
        if in_alert_window(event, today):
            return years, event
    return None
```

- [ ] **Step 4: Kør testen og se den bestå**

Run: `python -m pytest tests/test_employee_rules.py -q`
Expected: alle PASS

- [ ] **Step 5: Stop – brugeren committer**

---

### Task 2: Datamodel, migration og schemaer

**Files:**
- Modify: `app/database/models.py` (`Employee` ca. linje 58-107; ny klasse lige før `class Employee`)
- Modify: `app/database/session.py` (`_migrate()`, efter blokken `if "absence_vehicle_id" not in emp_cols3:` ca. linje 270-272)
- Modify: `app/database/schemas.py` (`EmployeeCreate` linje 33, `EmployeeUpdate` linje 63, `EmployeeResponse` ca. linje 93, efter `Paragraf56AlertDismiss` ca. linje 306)
- Modify: `app/routers/employees.py` (`_to_response`, linje 77-117)
- Modify: `tests/conftest.py`
- Test: `tests/test_employee_register_fields.py`

**Interfaces:**
- Produces:
  - `MasterPosition(id, name)`, tabel `master_positions`
  - `Employee`-kolonner: `position_id`, `position` (relationship), `seniority_date`, `cpr_number`, `elev`, `elev_start_date`, `elev_end_date`, `personaleforening`, `natarbejde_tillaeg`
  - `EmployeeResponse`: `position_id`, `position_name`, `seniority_date`, `cpr_number`, `elev`, `elev_start_date`, `elev_end_date`, `personaleforening`, `natarbejde_tillaeg`
  - `conftest.required_employee_fields(employee_number: str) -> dict`, plus en `MasterPosition(id=1, name="Testchauffør")` i hver `db`
  - Schemaer `MilestoneAlert`, `MilestoneAlertDismiss`, `EmployeeExportRequest` (bruges i task 5 og 6)

- [ ] **Step 1: Skriv de fejlende tests**

`tests/test_employee_register_fields.py`:

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

import sqlite3
from datetime import date

from database.models import Employee, MasterPosition


def test_new_employee_defaults(db):
    emp = Employee(employee_number="34001", first_name="A", last_name="B",
                   agreement_type="X", hire_date=date(2026, 1, 1))
    db.add(emp)
    db.commit()
    db.refresh(emp)
    assert emp.personaleforening is True
    assert emp.elev is False
    assert emp.natarbejde_tillaeg is False
    assert emp.position_id is None and emp.cpr_number is None and emp.seniority_date is None


def test_db_fixture_seeds_test_position(db):
    pos = db.query(MasterPosition).get(1)
    assert pos.name == "Testchauffør"


def test_to_response_includes_new_fields(db, employee):
    from routers.employees import _to_response
    employee.position_id = 1
    employee.seniority_date = date(2001, 5, 1)
    employee.cpr_number = "120385-1234"
    employee.elev = True
    employee.elev_start_date = date(2026, 8, 1)
    employee.elev_end_date = date(2029, 7, 31)
    employee.natarbejde_tillaeg = True
    db.commit()
    resp = _to_response(employee, db)
    assert resp.position_id == 1 and resp.position_name == "Testchauffør"
    assert resp.seniority_date == date(2001, 5, 1)
    assert resp.cpr_number == "120385-1234"
    assert resp.elev is True and resp.elev_end_date == date(2029, 7, 31)
    assert resp.personaleforening is True and resp.natarbejde_tillaeg is True


def test_migrate_adds_columns_and_existing_rows_are_not_members(tmp_path, monkeypatch):
    """Eksisterende medarbejdere sættes IKKE som medlem af personaleforeningen."""
    from sqlalchemy import create_engine
    from database.models import Base
    import database.session as session_mod

    db_file = tmp_path / "old.db"
    engine = create_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(engine)
    engine.dispose()
    new_cols = ["position_id", "seniority_date", "cpr_number", "elev", "elev_start_date",
                "elev_end_date", "personaleforening", "natarbejde_tillaeg"]
    with sqlite3.connect(db_file) as conn:
        # Genskab en "gammel" employees-tabel uden de nye kolonner. DROP COLUMN kan
        # ikke bruges, fordi position_id indgår i en FOREIGN KEY.
        old_cols = [r[1] for r in conn.execute("PRAGMA table_info(employees)") if r[1] not in new_cols]
        conn.execute(f"CREATE TABLE employees_old AS SELECT {', '.join(old_cols)} FROM employees")
        conn.execute("DROP TABLE employees")
        conn.execute("ALTER TABLE employees_old RENAME TO employees")
        conn.execute(
            "INSERT INTO employees (employee_number, first_name, last_name, agreement_kind, agreement_type, "
            "fuldloennet, active, hire_date, termination_date, work_schedule, paragraf_56, afloeser, "
            "ot_extra_alle_timer, fast_bil) VALUES ('34001','A','B','hourly_fixed','X',1,1,'2026-01-01',"
            "'9999-12-31','{}',0,0,0,0)"
        )
        conn.commit()

    monkeypatch.setattr(session_mod, "DB_PATH", db_file)
    session_mod._migrate()

    with sqlite3.connect(db_file) as conn:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(employees)")}
        assert set(new_cols) <= cols
        assert conn.execute("SELECT personaleforening, elev, natarbejde_tillaeg FROM employees").fetchone() == (0, 0, 0)
```

- [ ] **Step 2: Kør testen og se den fejle**

Run: `python -m pytest tests/test_employee_register_fields.py -q`
Expected: FAIL med `ImportError: cannot import name 'MasterPosition'`

- [ ] **Step 3: Tilføj model**

I `app/database/models.py`, indsæt lige før `class Employee(Base):`:

```python
class MasterPosition(Base):
    """Stilling – valgmuligheder til medarbejderens Stilling-felt (Stamdata → Stillinger)."""
    __tablename__ = "master_positions"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True, nullable=False)
```

I `class Employee`, indsæt efter linjen `absence_vehicle = relationship("Vehicle", foreign_keys=[absence_vehicle_id])`:

```python
    # Medarbejderregister-udvidelse 2026-10-01 (se docs/superpowers/specs/2026-10-01-medarbejderregister.md)
    position_id = Column(Integer, ForeignKey("master_positions.id"), nullable=True)
    position = relationship("MasterPosition")
    seniority_date = Column(Date, nullable=True)      # Anciennitetsdato – kun til jubilæumsadvarsel
    cpr_number = Column(String(11), nullable=True)    # ddmmåå-xxxx – maskeres uden 'view_cpr'
    elev = Column(Boolean, default=False, nullable=False)
    elev_start_date = Column(Date, nullable=True)
    elev_end_date = Column(Date, nullable=True)
    personaleforening = Column(Boolean, default=True, nullable=False)
    natarbejde_tillaeg = Column(Boolean, default=False, nullable=False)  # kun til filtrering
```

- [ ] **Step 4: Tilføj migration**

I `app/database/session.py` → `_migrate()`, indsæt lige efter blokken

```python
        if "absence_vehicle_id" not in emp_cols3:
            conn.execute("ALTER TABLE employees ADD COLUMN absence_vehicle_id INTEGER")
            conn.commit()
```

følgende:

```python
        for col, ddl in (
            ("position_id", "INTEGER"),
            ("seniority_date", "DATE"),
            ("cpr_number", "VARCHAR(11)"),
            ("elev", "BOOLEAN NOT NULL DEFAULT 0"),
            ("elev_start_date", "DATE"),
            ("elev_end_date", "DATE"),
            # Eksisterende medarbejdere sættes bevidst IKKE som medlem (besluttet 2026-10-01);
            # nye medarbejdere får modellens default True.
            ("personaleforening", "BOOLEAN NOT NULL DEFAULT 0"),
            ("natarbejde_tillaeg", "BOOLEAN NOT NULL DEFAULT 0"),
        ):
            if col not in emp_cols3:
                conn.execute(f"ALTER TABLE employees ADD COLUMN {col} {ddl}")
                conn.commit()
```

`master_positions` oprettes af `Base.metadata.create_all`, som kører før `_migrate()`.

- [ ] **Step 5: Udvid schemaer**

I `app/database/schemas.py`, `EmployeeCreate`: tilføj efter `absence_vehicle_id: Optional[int] = None`:

```python
    position_id: Optional[int] = None
    seniority_date: Optional[date] = None
    cpr_number: Optional[str] = None
    elev: bool = False
    elev_start_date: Optional[date] = None
    elev_end_date: Optional[date] = None
    personaleforening: bool = True
    natarbejde_tillaeg: bool = False
```

`EmployeeUpdate`: tilføj efter `absence_vehicle_id: Optional[int] = None`:

```python
    position_id: Optional[int] = None
    seniority_date: Optional[date] = None
    cpr_number: Optional[str] = None
    elev: Optional[bool] = None
    elev_start_date: Optional[date] = None
    elev_end_date: Optional[date] = None
    personaleforening: Optional[bool] = None
    natarbejde_tillaeg: Optional[bool] = None
```

`EmployeeResponse`: tilføj efter `absence_vehicle_number: Optional[str] = None`:

```python
    position_id: Optional[int] = None
    position_name: Optional[str] = None
    seniority_date: Optional[date] = None
    cpr_number: Optional[str] = None
    elev: bool = False
    elev_start_date: Optional[date] = None
    elev_end_date: Optional[date] = None
    personaleforening: bool = True
    natarbejde_tillaeg: bool = False
```

Efter `class Paragraf56AlertDismiss` tilføjes:

```python
class MilestoneAlert(BaseModel):
    employee_id: int
    employee_name: str
    employee_number: str
    kind: str          # "birthday" | "jubilee" | "elev"
    alert_key: str     # fx "birthday_40", "jubilee_25", "elev_2029-07-31"
    event_date: date
    label: str         # dansk tekst til popup'en


class MilestoneAlertDismiss(BaseModel):
    alert_key: str


class EmployeeExportRequest(BaseModel):
    employee_ids: list[int]   # i den rækkefølge tabellen viser dem
```

- [ ] **Step 6: Udvid `_to_response`**

I `app/routers/employees.py` → `_to_response`, tilføj efter `absence_vehicle_number=…,`:

```python
        position_id=emp.position_id,
        position_name=emp.position.name if emp.position else None,
        seniority_date=emp.seniority_date,
        cpr_number=emp.cpr_number,
        elev=emp.elev,
        elev_start_date=emp.elev_start_date,
        elev_end_date=emp.elev_end_date,
        personaleforening=emp.personaleforening,
        natarbejde_tillaeg=emp.natarbejde_tillaeg,
```

- [ ] **Step 7: Seed testposition og hjælper i conftest**

I `tests/conftest.py`, udskift `db`-fixturen med:

```python
@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    from database.models import MasterPosition
    session.add(MasterPosition(id=1, name="Testchauffør"))
    session.commit()
    yield session
    session.close()
    Base.metadata.drop_all(engine)


def required_employee_fields(employee_number: str) -> dict:
    """Felter der er påkrævede ved oprettelse af en chauffør (2026-10-01).
    Førerkortnummeret afledes af lønnummeret, så det er unikt pr. medarbejder."""
    return {
        "position_id": 1,
        "email": "test@example.dk",
        "tachograph_card_number": f"DKTEST{employee_number}",
    }
```

- [ ] **Step 8: Kør testene**

Run: `python -m pytest tests/test_employee_register_fields.py -q`
Expected: 4 PASS

Run: `python -m pytest tests -q`
Expected: alle PASS (de eksisterende tests rammes ikke endnu, da serveren ikke kræver felterne før task 3).

- [ ] **Step 9: Stop – brugeren committer**

---

### Task 3: Servervalidering pr. type, CPR-håndtering og opdatering af eksisterende tests

**Files:**
- Modify: `app/routers/employees.py` (`create_employee` linje 209-238, `update_employee` linje 354-415, `_CLEARABLE_EMPLOYEE_FIELDS` linje 342, `_visible_response` linje 133, `_PRIVATE_EMPLOYEE_FIELDS` linje 127)
- Modify: `app/auth.py` (`ALL_PERMISSIONS`)
- Modify: `tests/test_dispatcher_group_single.py`, `tests/test_employee_absence_vehicle.py`, `tests/test_employee_agreement_kind_validation.py`, `tests/test_employee_fast_bil_endpoint.py`, `tests/test_employee_ot_extra_alle_timer_endpoint.py`, `tests/test_paragraf_56.py`, `tests/test_vagtplan.py`
- Test: `tests/test_employee_register_fields.py` (udvides)

**Interfaces:**
- Consumes: `validate_cpr`, `mask_cpr`, `is_masked_cpr` (task 1); nye kolonner og schemafelter (task 2)
- Produces:
  - `_validate_employee_fields(db, kind: str, values: dict, check: set[str]) -> None` (kaster 400)
  - `_apply_cpr_mask(resp, db, user) -> EmployeeResponse`
  - Rettigheder i `ALL_PERMISSIONS`: `view_cpr`, `jubilee_alert`, `elev_alert`, `birthday_alert`, `employee_table_view`, `employee_export`

- [ ] **Step 1: Skriv de fejlende tests**

Tilføj nederst i `tests/test_employee_register_fields.py`:

```python
import pytest
from decimal import Decimal
from fastapi import HTTPException

from conftest import required_employee_fields
from database.models import AppUser, MasterAgreementKind, MasterAgreementType, Role
from database.schemas import EmployeeCreate, EmployeeUpdate, WorkSchedule


def _seed(db):
    db.add(MasterAgreementType(name="Standardoverenskomst", hourly_rate=Decimal("150.00")))
    db.add(MasterAgreementKind(key="hourly_fixed", label="Timelønnet", is_active=True,
                               is_user_created=False, requires_agreement_type=True, sort_order=1))
    db.add(MasterAgreementKind(key="funktionaer", label="Funktionær", is_active=True,
                               is_user_created=False, requires_agreement_type=False, sort_order=2))
    db.commit()


def _user(db, name, perms):
    db.add(Role(name=name, display_name=name, is_system=False, permissions=perms))
    u = AppUser(name=name, initials=name[:3].upper(), role=name, password_hash="x", active=True)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _driver_body(**overrides):
    data = dict(employee_number="34500", first_name="Ny", last_name="Chauffør",
                agreement_kind="hourly_fixed", agreement_type="Standardoverenskomst",
                hire_date=date(2026, 1, 1), work_schedule=WorkSchedule())
    data.update(overrides)
    data = {**required_employee_fields(data["employee_number"]), **data}
    return EmployeeCreate(**data)


def _office_body(**overrides):
    data = dict(employee_number="34600", first_name="Ny", last_name="Funktionær",
                agreement_kind="funktionaer", agreement_type="", initials="NYF",
                position_id=1, email="ny@poulschou.dk",
                hire_date=date(2026, 1, 1), work_schedule=WorkSchedule())
    data.update(overrides)
    return EmployeeCreate(**data)


@pytest.mark.parametrize("field,label", [
    ("position_id", "Stilling"), ("email", "Email"), ("tachograph_card_number", "Førerkortnummer"),
])
def test_create_driver_requires_fields(db, field, label):
    from routers.employees import create_employee
    _seed(db)
    with pytest.raises(HTTPException) as exc:
        create_employee(_driver_body(**{field: None}), current_user=_user(db, "a", ["manage_employees"]), db=db)
    assert exc.value.status_code == 400 and label in exc.value.detail


def test_create_office_requires_initials_but_not_card(db):
    from routers.employees import create_employee
    _seed(db)
    user = _user(db, "a", ["manage_employees"])
    resp = create_employee(_office_body(), current_user=user, db=db)
    assert resp.tachograph_card_number is None
    with pytest.raises(HTTPException) as exc:
        create_employee(_office_body(employee_number="34601", initials=None), current_user=user, db=db)
    assert "Initialer" in exc.value.detail


def test_create_rejects_unknown_position(db):
    from routers.employees import create_employee
    _seed(db)
    with pytest.raises(HTTPException) as exc:
        create_employee(_driver_body(position_id=999), current_user=_user(db, "a", ["manage_employees"]), db=db)
    assert exc.value.status_code == 400


def test_elev_requires_dates_for_driver(db):
    from routers.employees import create_employee
    _seed(db)
    user = _user(db, "a", ["manage_employees"])
    with pytest.raises(HTTPException):
        create_employee(_driver_body(elev=True), current_user=user, db=db)
    with pytest.raises(HTTPException):
        create_employee(_driver_body(elev=True, elev_start_date=date(2026, 8, 1),
                                     elev_end_date=date(2026, 7, 1)), current_user=user, db=db)
    resp = create_employee(_driver_body(elev=True, elev_start_date=date(2026, 8, 1),
                                        elev_end_date=date(2029, 7, 31)), current_user=user, db=db)
    assert resp.elev is True


def test_elev_dates_not_required_for_office(db):
    """Skjulte påkrævede felter er ikke påkrævede – og værdien bevares."""
    from routers.employees import create_employee
    _seed(db)
    resp = create_employee(_office_body(elev=True), current_user=_user(db, "a", ["manage_employees"]), db=db)
    assert resp.elev is True


def test_create_rejects_invalid_cpr(db):
    from routers.employees import create_employee
    _seed(db)
    with pytest.raises(HTTPException) as exc:
        create_employee(_driver_body(cpr_number="1203851234"), current_user=_user(db, "a", ["manage_employees"]), db=db)
    assert "CPR" in exc.value.detail


def test_cpr_masked_without_view_cpr_and_full_with(db):
    from routers.employees import create_employee, get_employee
    _seed(db)
    creator = _user(db, "a", ["manage_employees"])
    resp = create_employee(_driver_body(cpr_number="120385-1234"), current_user=creator, db=db)
    assert resp.cpr_number == "120385-****"
    viewer = _user(db, "b", ["view_employees", "view_cpr"])
    assert get_employee(resp.id, current_user=viewer, db=db).cpr_number == "120385-1234"
    assert get_employee(resp.id, current_user=_user(db, "c", ["view_employees"]), db=db).cpr_number == "120385-****"
    assert get_employee(resp.id, current_user=_user(db, "d", ["view_calendar"]), db=db).cpr_number is None


def test_update_with_masked_cpr_keeps_stored_value(db):
    from routers.employees import create_employee, update_employee
    _seed(db)
    user = _user(db, "a", ["manage_employees"])
    resp = create_employee(_driver_body(cpr_number="120385-1234"), current_user=user, db=db)
    update_employee(resp.id, EmployeeUpdate(cpr_number="120385-****"), current_user=user, db=db)
    assert db.query(Employee).get(resp.id).cpr_number == "120385-1234"
    update_employee(resp.id, EmployeeUpdate(cpr_number="010190-4321"), current_user=user, db=db)
    assert db.query(Employee).get(resp.id).cpr_number == "010190-4321"
    update_employee(resp.id, EmployeeUpdate(cpr_number=None), current_user=user, db=db)
    assert db.query(Employee).get(resp.id).cpr_number is None


def test_update_old_employee_without_new_fields_still_allowed_for_partial_patch(db, employee):
    """Gamle medarbejdere uden stilling/email kan stadig PATCH'es på andre felter."""
    from routers.employees import update_employee
    _seed(db)
    resp = update_employee(employee.id, EmployeeUpdate(afloeser=True),
                           current_user=_user(db, "a", ["manage_employees"]), db=db)
    assert resp.afloeser is True


def test_update_cannot_blank_required_field(db, employee):
    from routers.employees import update_employee
    _seed(db)
    with pytest.raises(HTTPException) as exc:
        update_employee(employee.id, EmployeeUpdate(email=None),
                        current_user=_user(db, "a", ["manage_employees"]), db=db)
    assert "Email" in exc.value.detail


def test_update_rejects_duplicate_employee_number(db, employee):
    from routers.employees import create_employee, update_employee
    _seed(db)
    user = _user(db, "a", ["manage_employees"])
    other = create_employee(_driver_body(), current_user=user, db=db)
    with pytest.raises(HTTPException) as exc:
        update_employee(other.id, EmployeeUpdate(employee_number=employee.employee_number), current_user=user, db=db)
    assert exc.value.status_code == 400


def test_switch_to_office_keeps_hidden_values(db):
    from routers.employees import create_employee, update_employee
    _seed(db)
    user = _user(db, "a", ["manage_employees"])
    resp = create_employee(_driver_body(afloeser=True, natarbejde_tillaeg=True), current_user=user, db=db)
    out = update_employee(resp.id, EmployeeUpdate(agreement_kind="funktionaer", initials="ABC",
                                                  tachograph_card_number=resp.tachograph_card_number),
                          current_user=user, db=db)
    assert out.afloeser is True and out.natarbejde_tillaeg is True
    assert out.tachograph_card_number == resp.tachograph_card_number


def test_paragraf56_change_does_not_wipe_milestone_dismissals(db, employee):
    from routers.employees import update_employee
    from database.models import Paragraf56AlertDismissal
    _seed(db)
    user = _user(db, "a", ["manage_employees"])
    db.add(Paragraf56AlertDismissal(employee_id=employee.id, user_id=user.id, alert_type="birthday_40"))
    db.add(Paragraf56AlertDismissal(employee_id=employee.id, user_id=user.id, alert_type="upcoming"))
    db.commit()
    update_employee(employee.id, EmployeeUpdate(paragraf_56=True, paragraf_56_start_date=date(2026, 1, 1),
                                                paragraf_56_end_date=date(2026, 12, 1)),
                    current_user=user, db=db)
    types = {d.alert_type for d in db.query(Paragraf56AlertDismissal).all()}
    assert types == {"birthday_40"}
```

- [ ] **Step 2: Kør testen og se den fejle**

Run: `python -m pytest tests/test_employee_register_fields.py -q`
Expected: de nye tests FAIL (fx "DID NOT RAISE" ved manglende påkrævede felter)

- [ ] **Step 3: Tilføj rettigheder**

I `app/auth.py` → `ALL_PERMISSIONS`, tilføj efter `"dagsplan_edit": …,`:

```python
    "view_cpr":            "Se CPR-nummer",
    "jubilee_alert":       "Jubilæumsadvarsel",
    "elev_alert":          "Elevadvarsel",
    "birthday_alert":      "Fødselsdagsadvarsel",
    "employee_table_view": "Tabelvisning af medarbejdere",
    "employee_export":     "Eksportér medarbejderregister",
```

- [ ] **Step 4: Implementér validering og CPR i `employees.py`**

Opdatér importen øverst:

```python
from auth import get_current_user, require_any_permission, require_permission, user_has_any_permission, user_has_permission
from database.models import AppUser, DispatcherGroup, Employee, MasterAgreementKind, MasterPosition, Paragraf56AlertDismissal, Vehicle
from utils.employee_rules import is_masked_cpr, mask_cpr, validate_cpr
```

Tilføj `"cpr_number"` til `_PRIVATE_EMPLOYEE_FIELDS`:

```python
_PRIVATE_EMPLOYEE_FIELDS = (
    "tachograph_card_number", "address", "postal_code", "email", "phone", "mobile",
    "hourly_rate", "cvr_number", "cpr_number",
)
```

Erstat `_visible_response` med:

```python
def _apply_cpr_mask(resp: EmployeeResponse, db, current_user: AppUser) -> EmployeeResponse:
    """De sidste fire cifre i CPR sendes kun til brugere med 'Se CPR-nummer'."""
    if resp.cpr_number and not user_has_permission(db, current_user, "view_cpr"):
        resp.cpr_number = mask_cpr(resp.cpr_number)
    return resp


def _visible_response(emp: Employee, db, current_user: AppUser) -> EmployeeResponse:
    """Fuld stamdata kun med 'Se medarbejdere'/'Tilføj medarbejdere' – ellers
    udelades kontakt-, løn-, førerkort- og CPR-oplysninger. CPR maskeres desuden
    uden 'Se CPR-nummer'."""
    resp = _to_response(emp, db)
    if not user_has_any_permission(db, current_user, "view_employees", "manage_employees"):
        for field in _PRIVATE_EMPLOYEE_FIELDS:
            setattr(resp, field, None)
        return resp
    return _apply_cpr_mask(resp, db, current_user)
```

Tilføj lige før `@router.post("", …)` (create_employee):

```python
FUNKTIONAER = "funktionaer"


def _blank(v) -> bool:
    return v is None or (isinstance(v, str) and not v.strip())


def _validate_employee_fields(db: Session, kind: str, values: dict, check: set) -> None:
    """Påkrævede felter pr. medarbejdertype (spec afsnit 3). Kun felter i `check`
    kontrolleres – ved PATCH er det de felter, der sendes med, så gamle
    medarbejdere først skal udfylde dem næste gang hele formularen gemmes.
    Skjulte felter (fx førerkort for funktionærer) er aldrig påkrævede."""
    is_office = kind == FUNKTIONAER
    required = {"position_id": "Stilling", "email": "Email"}
    if is_office:
        required["initials"] = "Initialer"
    else:
        required["tachograph_card_number"] = "Førerkortnummer"
    missing = [label for field, label in required.items() if field in check and _blank(values.get(field))]
    if missing:
        raise HTTPException(400, f"Påkrævede felter mangler: {', '.join(missing)}")
    if "position_id" in check and values.get("position_id") is not None:
        if not db.query(MasterPosition).filter(MasterPosition.id == values["position_id"]).first():
            raise HTTPException(400, f"Ukendt stilling-id: {values['position_id']}")
    if not is_office and values.get("elev") and ({"elev", "elev_start_date", "elev_end_date"} & check):
        start, end = values.get("elev_start_date"), values.get("elev_end_date")
        if not start or not end:
            raise HTTPException(400, "Start- og slutdato for elev skal udfyldes")
        if end < start:
            raise HTTPException(400, "Elev slutdato skal være efter startdato")


def _clean_cpr(value: Optional[str]) -> Optional[str]:
    if _blank(value):
        return None
    try:
        return validate_cpr(value)
    except ValueError as e:
        raise HTTPException(400, str(e))
```

I `create_employee`, lige efter `_validate_paragraf_56(...)`-kaldet (før `data = body.model_dump(...)`), indsæt:

```python
    body.cpr_number = _clean_cpr(body.cpr_number)
    _validate_employee_fields(db, body.agreement_kind, body.model_dump(), set(EmployeeCreate.model_fields))
```

og erstat slutningen `return _to_response(emp, db)` i `create_employee` med:

```python
    return _apply_cpr_mask(_to_response(emp, db), db, current_user)
```

Udvid `_CLEARABLE_EMPLOYEE_FIELDS`:

```python
_CLEARABLE_EMPLOYEE_FIELDS = (
    "tachograph_card_number", "initials", "address", "postal_code",
    "email", "phone", "mobile", "seniority_date", "elev_start_date", "elev_end_date",
    "position_id",
)
```

I `update_employee`, lige efter `if not emp: raise HTTPException(404, …)`, indsæt:

```python
    if body.employee_number and body.employee_number != emp.employee_number:
        if db.query(Employee).filter(Employee.employee_number == body.employee_number,
                                     Employee.id != emp.id).first():
            raise HTTPException(400, "Lønnummer eksisterer allerede")
    sent = set(body.model_fields_set)
    # CPR: maskeret værdi (fra en bruger uden 'Se CPR-nummer') betyder "uændret"
    cpr_sent = "cpr_number" in sent and not is_masked_cpr(body.cpr_number)
    new_cpr = _clean_cpr(body.cpr_number) if cpr_sent else emp.cpr_number
    sent.discard("cpr_number")
    effective = {
        c: (getattr(body, c) if c in sent else getattr(emp, c))
        for c in ("position_id", "email", "initials", "tachograph_card_number",
                  "elev", "elev_start_date", "elev_end_date")
    }
    _validate_employee_fields(db, body.agreement_kind or emp.agreement_kind, effective, sent)
```

Tilføj `"cpr_number"` til `_paragraf56_excludes`-sættet, så den ikke sættes af den generelle løkke:

```python
    _paragraf56_excludes = {"dispatcher_group_id", "fast_bil_vehicle_id", "absence_vehicle_id",
                            "paragraf_56", "paragraf_56_start_date", "paragraf_56_end_date",
                            "cpr_number"}
```

Efter løkken `for field_name in _CLEARABLE_EMPLOYEE_FIELDS: …` indsæt:

```python
    if cpr_sent:
        emp.cpr_number = new_cpr
```

Begræns sletningen af §56-afvisninger til §56-typerne (ellers forsvinder afviste fødselsdage/jubilæer). Erstat:

```python
        if end != emp.paragraf_56_end_date:
            db.query(Paragraf56AlertDismissal).filter(
                Paragraf56AlertDismissal.employee_id == emp.id
            ).delete()
```

med:

```python
        if end != emp.paragraf_56_end_date:
            db.query(Paragraf56AlertDismissal).filter(
                Paragraf56AlertDismissal.employee_id == emp.id,
                Paragraf56AlertDismissal.alert_type.in_(("upcoming", "expired")),
            ).delete(synchronize_session=False)
```

Erstat til sidst `return _to_response(emp, db)` i `update_employee` med:

```python
    return _apply_cpr_mask(_to_response(emp, db), db, current_user)
```

- [ ] **Step 5: Kør de nye tests**

Run: `python -m pytest tests/test_employee_register_fields.py -q`
Expected: alle PASS

- [ ] **Step 6: Kør hele suiten og se de eksisterende create-tests fejle**

Run: `python -m pytest tests -q`
Expected: FAIL i de 7 filer, der kalder `create_employee` uden de nye påkrævede felter ("Påkrævede felter mangler")

- [ ] **Step 7: Opdatér de eksisterende test-hjælpere**

Hvert sted tilføjes `from conftest import required_employee_fields` til filens imports. Body-hjælperne flettes, så overrides stadig vinder:

`tests/test_dispatcher_group_single.py` → `_employee_body`, erstat de to sidste linjer:
```python
    data.update(overrides)
    data = {**required_employee_fields(data["employee_number"]), **data}
    return EmployeeCreate(**data)
```

`tests/test_employee_absence_vehicle.py` → `_base_employee_body`, erstat de to sidste linjer:
```python
    data.update(overrides)
    data = {**required_employee_fields(data["employee_number"]), **data}
    return EmployeeCreate(**data)
```

`tests/test_employee_agreement_kind_validation.py` → `_base_employee_body`, erstat de to sidste linjer:
```python
    data.update(overrides)
    data = {**required_employee_fields(data["employee_number"]), **data}
    return EmployeeCreate(**data)
```

`tests/test_employee_fast_bil_endpoint.py` → `_base_employee_body`, erstat de to sidste linjer:
```python
    data.update(overrides)
    data = {**required_employee_fields(data["employee_number"]), **data}
    return EmployeeCreate(**data)
```

`tests/test_employee_ot_extra_alle_timer_endpoint.py` → `_base_employee_body`, erstat de to sidste linjer:
```python
    data.update(overrides)
    data = {**required_employee_fields(data["employee_number"]), **data}
    return EmployeeCreate(**data)
```

`tests/test_paragraf_56.py` → body-hjælperen ved linje 27-38, erstat de to sidste linjer:
```python
    data.update(overrides)
    data = {**required_employee_fields(data["employee_number"]), **data}
    return EmployeeCreate(**data)
```

`tests/test_vagtplan.py` linje 30-37, erstat `body = EmployeeCreate(...)` med:
```python
    body = EmployeeCreate(
        employee_number="9999",
        first_name="Ny",
        last_name="Person",
        agreement_type="Standardoverenskomst",
        hire_date=date(2026, 1, 1),
        initials="NYP",
        **required_employee_fields("9999"),
    )
```

Hvis en hjælper i en af filerne ikke ender med præcis `data.update(overrides)` + `return EmployeeCreate(**data)`, så indsæt fletningen umiddelbart før `return EmployeeCreate(**data)` – det er det samme princip.

- [ ] **Step 8: Kør hele suiten**

Run: `python -m pytest tests -q`
Expected: alle PASS (494 + de nye)

- [ ] **Step 9: Stop – brugeren committer**

---

### Task 4: Lønnummer-generator, nummertjek og positionsliste

**Files:**
- Modify: `app/routers/employees.py` (nye endpoints – skal stå **før** `@router.get("/{employee_id}")`, ellers matcher FastAPI `/{employee_id}` først)
- Test: `tests/test_employee_number_endpoints.py`

**Interfaces:**
- Consumes: `next_employee_number` (task 1), `MasterPosition` (task 2)
- Produces:
  - `GET /api/employees/next-employee-number` → `{"suggestion": str}` – funktion `next_number(current_user, db)`
  - `GET /api/employees/check-number?number=&exclude_id=` → `{"taken": bool, "employee_name": Optional[str]}` – funktion `check_number(number, exclude_id, current_user, db)`
  - `GET /api/employees/positions` → `[{"id": int, "name": str}]` alfabetisk – funktion `list_positions(current_user, db)`

- [ ] **Step 1: Skriv de fejlende tests**

`tests/test_employee_number_endpoints.py`:

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from datetime import date

from database.models import AppUser, Employee, MasterPosition


def _admin():
    return AppUser(name="Admin", initials="ADM", role="admin", password_hash="x")


def _emp(db, number, first="A", last="B"):
    db.add(Employee(employee_number=number, first_name=first, last_name=last,
                    agreement_type="X", hire_date=date(2026, 1, 1), active=False))
    db.commit()


def test_next_number_uses_highest_including_inactive(db):
    from routers.employees import next_number
    _emp(db, "34637")
    _emp(db, "34640")
    _emp(db, "TEST999")
    assert next_number(current_user=_admin(), db=db) == {"suggestion": "34641"}


def test_check_number_taken_and_exclude_self(db):
    from routers.employees import check_number
    _emp(db, "34625", "Alexander B.", "Knudsen")
    emp_id = db.query(Employee).first().id
    assert check_number(number="34625", exclude_id=None, current_user=_admin(), db=db) == \
        {"taken": True, "employee_name": "Alexander B. Knudsen"}
    assert check_number(number="34625", exclude_id=emp_id, current_user=_admin(), db=db) == \
        {"taken": False, "employee_name": None}
    assert check_number(number=" 34626 ", exclude_id=None, current_user=_admin(), db=db)["taken"] is False


def test_list_positions_alphabetical(db):
    from routers.employees import list_positions
    db.add(MasterPosition(name="Disponent"))
    db.add(MasterPosition(name="Bogholder"))
    db.commit()
    names = [p["name"] for p in list_positions(current_user=_admin(), db=db)]
    assert names == ["Bogholder", "Disponent", "Testchauffør"]
```

- [ ] **Step 2: Kør testen og se den fejle**

Run: `python -m pytest tests/test_employee_number_endpoints.py -q`
Expected: FAIL med `ImportError: cannot import name 'next_number'`

- [ ] **Step 3: Implementér endpoints**

I `app/routers/employees.py`, tilføj import:

```python
from utils.employee_rules import is_masked_cpr, mask_cpr, next_employee_number, validate_cpr
```

Indsæt lige før `@router.get("/anciennitet-alerts", …)`:

```python
@router.get("/next-employee-number")
def next_number(current_user: AppUser = Depends(require_permission("manage_employees")),
                db: Session = Depends(get_db)):
    """Forslag til lønnummer: højeste numeriske lønnummer >= 34000 plus 1 (aktive og inaktive)."""
    numbers = [n for (n,) in db.query(Employee.employee_number).all()]
    return {"suggestion": next_employee_number(numbers)}


@router.get("/check-number")
def check_number(number: str, exclude_id: Optional[int] = None,
                 current_user: AppUser = Depends(require_permission("manage_employees")),
                 db: Session = Depends(get_db)):
    q = db.query(Employee).filter(Employee.employee_number == number.strip())
    if exclude_id is not None:
        q = q.filter(Employee.id != exclude_id)
    emp = q.first()
    return {"taken": emp is not None, "employee_name": emp.name if emp else None}


@router.get("/positions")
def list_positions(current_user: AppUser = Depends(_employee_list_access),
                   db: Session = Depends(get_db)):
    """Stillinger til medarbejder-modalens dropdown og registerets filter."""
    rows = db.query(MasterPosition).all()
    return [{"id": r.id, "name": r.name} for r in sorted(rows, key=lambda r: r.name.lower())]
```

- [ ] **Step 4: Kør testen og se den bestå**

Run: `python -m pytest tests/test_employee_number_endpoints.py -q`
Expected: 3 PASS

- [ ] **Step 5: Stop – brugeren committer**

---

### Task 5: Stamdata-CRUD for stillinger

**Files:**
- Modify: `app/routers/stamdata.py` (import + ny sektion efter fraværstyper, før `# ── Aftaletyper`)
- Test: `tests/test_stamdata_positions.py`

**Interfaces:**
- Consumes: `MasterPosition` (task 2)
- Produces: `list_positions_stamdata`, `create_position(body: PositionBody)`, `update_position(position_id, body)`, `delete_position(position_id)` på `/api/stamdata/positions`

- [ ] **Step 1: Skriv de fejlende tests**

`tests/test_stamdata_positions.py`:

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from datetime import date

import pytest
from fastapi import HTTPException

from database.models import AppUser, Employee, MasterPosition


def _admin(db):
    u = AppUser(name="Admin", initials="ADM", role="admin", password_hash="x")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def test_create_update_list_delete_position(db):
    from routers.stamdata import (PositionBody, create_position, delete_position,
                                  list_positions_stamdata, update_position)
    user = _admin(db)
    row = create_position(PositionBody(name="  Disponent "), current_user=user, db=db)
    assert row["name"] == "Disponent"
    update_position(row["id"], PositionBody(name="Disponent (dag)"), current_user=user, db=db)
    names = [r["name"] for r in list_positions_stamdata(current_user=user, db=db)]
    assert names == ["Disponent (dag)", "Testchauffør"]
    assert any(r["employee_count"] == 0 for r in list_positions_stamdata(current_user=user, db=db))
    delete_position(row["id"], current_user=user, db=db)
    assert db.query(MasterPosition).filter(MasterPosition.id == row["id"]).first() is None


def test_duplicate_and_blank_name_rejected(db):
    from routers.stamdata import PositionBody, create_position
    user = _admin(db)
    with pytest.raises(HTTPException):
        create_position(PositionBody(name="testchauffør"), current_user=user, db=db)
    with pytest.raises(HTTPException):
        create_position(PositionBody(name="   "), current_user=user, db=db)


def test_delete_rejected_when_in_use(db):
    from routers.stamdata import delete_position
    user = _admin(db)
    db.add(Employee(employee_number="34001", first_name="A", last_name="B", agreement_type="X",
                    hire_date=date(2026, 1, 1), position_id=1))
    db.commit()
    with pytest.raises(HTTPException) as exc:
        delete_position(1, current_user=user, db=db)
    assert exc.value.status_code == 400 and "1 medarbejder" in exc.value.detail
```

- [ ] **Step 2: Kør testen og se den fejle**

Run: `python -m pytest tests/test_stamdata_positions.py -q`
Expected: FAIL med `ImportError: cannot import name 'PositionBody'`

- [ ] **Step 3: Implementér**

I `app/routers/stamdata.py`, tilføj `MasterPosition` til importen fra `database.models`. Indsæt før `# ── Aftaletyper ───`:

```python
# ── Stillinger ────────────────────────────────────────────────────────────

class PositionBody(BaseModel):
    name: str


def _position_row(db: Session, r: MasterPosition) -> dict:
    count = db.query(Employee).filter(Employee.position_id == r.id).count()
    return {"id": r.id, "name": r.name, "employee_count": count}


def _clean_position_name(db: Session, name: str, exclude_id: Optional[int] = None) -> str:
    clean = (name or "").strip()
    if not clean:
        raise HTTPException(400, "Navn er påkrævet")
    for other in db.query(MasterPosition).all():
        if other.id != exclude_id and other.name.lower() == clean.lower():
            raise HTTPException(400, "En stilling med dette navn eksisterer allerede")
    return clean


@router.get("/positions")
def list_positions_stamdata(current_user: AppUser = Depends(_access), db: Session = Depends(get_db)):
    rows = sorted(db.query(MasterPosition).all(), key=lambda r: r.name.lower())
    return [_position_row(db, r) for r in rows]


@router.post("/positions", status_code=201)
def create_position(body: PositionBody, current_user: AppUser = Depends(_access),
                    db: Session = Depends(get_db)):
    row = MasterPosition(name=_clean_position_name(db, body.name))
    db.add(row)
    db.commit()
    db.refresh(row)
    log_action(db, current_user, "stamdata_create", "position", row.id, f"Oprettet stilling: {row.name}")
    db.commit()
    return _position_row(db, row)


@router.patch("/positions/{position_id}")
def update_position(position_id: int, body: PositionBody, current_user: AppUser = Depends(_access),
                    db: Session = Depends(get_db)):
    row = db.query(MasterPosition).filter(MasterPosition.id == position_id).first()
    if not row:
        raise HTTPException(404, "Ikke fundet")
    row.name = _clean_position_name(db, body.name, exclude_id=position_id)
    db.commit()
    log_action(db, current_user, "stamdata_update", "position", row.id, f"Stilling omdøbt: {row.name}")
    db.commit()
    return _position_row(db, row)


@router.delete("/positions/{position_id}", status_code=204)
def delete_position(position_id: int, current_user: AppUser = Depends(_access),
                    db: Session = Depends(get_db)):
    row = db.query(MasterPosition).filter(MasterPosition.id == position_id).first()
    if not row:
        raise HTTPException(404, "Ikke fundet")
    in_use = db.query(Employee).filter(Employee.position_id == position_id).count()
    if in_use:
        raise HTTPException(400, f"Stillingen bruges af {in_use} medarbejder(e) og kan ikke slettes")
    log_action(db, current_user, "stamdata_delete", "position", row.id, f"Slettet stilling: {row.name}")
    db.delete(row)
    db.commit()
```

- [ ] **Step 4: Kør testen og se den bestå**

Run: `python -m pytest tests/test_stamdata_positions.py -q`
Expected: 3 PASS

- [ ] **Step 5: Stop – brugeren committer**

---

### Task 6: Advarsler – jubilæum, elev og fødselsdag

**Files:**
- Modify: `app/routers/employees.py` (endpoints før `@router.get("/{employee_id}")`)
- Test: `tests/test_milestone_alerts.py`

**Interfaces:**
- Consumes: `cpr_birthdate`, `round_birthday_alert`, `jubilee_alert`, `in_alert_window` (task 1). `MilestoneAlert`, `MilestoneAlertDismiss` (task 2). Rettighederne (task 3).
- Produces:
  - `GET /api/employees/milestone-alerts` → `list[MilestoneAlert]` – funktion `milestone_alerts(current_user, db, today: Optional[date] = None)`. `today` bruges kun af tests. Den bliver en valgfri query-parameter, som frontenden aldrig sender, og den er harmløs.
  - `POST /api/employees/{employee_id}/dismiss-milestone-alert` body `{"alert_key": str}` → 204 – funktion `dismiss_milestone_alert(employee_id, body, current_user, db)`

Afvisninger gemmes pr. bruger i `paragraf_56_alert_dismissals` med `alert_type = alert_key` (fx `birthday_40`, `jubilee_25`, `elev_2029-07-31`).

- [ ] **Step 1: Skriv de fejlende tests**

`tests/test_milestone_alerts.py`:

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from datetime import date

import pytest
from fastapi import HTTPException

from database.models import AppUser, Role
from database.schemas import MilestoneAlertDismiss

TODAY = date(2026, 11, 1)


def _user(db, name, perms):
    db.add(Role(name=name, display_name=name, is_system=False, permissions=perms))
    u = AppUser(name=name, initials=name[:3].upper(), role=name, password_hash="x", active=True)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


ALL = ["birthday_alert", "jubilee_alert", "elev_alert"]


def test_birthday_from_cpr(db, employee):
    from routers.employees import milestone_alerts
    employee.cpr_number = "151186-1234"   # fylder 40 den 15/11-2026
    db.commit()
    alerts = milestone_alerts(current_user=_user(db, "a", ALL), db=db, today=TODAY)
    assert [(a.kind, a.alert_key, a.event_date) for a in alerts] == [("birthday", "birthday_40", date(2026, 11, 15))]
    assert "40" in alerts[0].label


def test_jubilee_uses_seniority_date_before_hire_date(db, employee):
    from routers.employees import milestone_alerts
    employee.hire_date = date(2010, 1, 1)
    employee.seniority_date = date(2001, 11, 20)  # 25 år den 20/11-2026
    db.commit()
    alerts = milestone_alerts(current_user=_user(db, "a", ALL), db=db, today=TODAY)
    assert [a.alert_key for a in alerts] == ["jubilee_25"]


def test_jubilee_falls_back_to_hire_date(db, employee):
    from routers.employees import milestone_alerts
    employee.hire_date = date(1986, 11, 10)  # 40 år
    db.commit()
    assert [a.alert_key for a in milestone_alerts(current_user=_user(db, "a", ALL), db=db, today=TODAY)] == ["jubilee_40"]


def test_elev_alert_only_for_driver_with_elev(db, employee):
    from routers.employees import milestone_alerts
    employee.elev = True
    employee.elev_start_date = date(2023, 8, 1)
    employee.elev_end_date = date(2026, 11, 30)
    db.commit()
    user = _user(db, "a", ALL)
    assert [a.alert_key for a in milestone_alerts(current_user=user, db=db, today=TODAY)] == ["elev_2026-11-30"]
    employee.agreement_kind = "funktionaer"
    db.commit()
    assert milestone_alerts(current_user=user, db=db, today=TODAY) == []


def test_each_kind_requires_its_own_permission(db, employee):
    from routers.employees import milestone_alerts
    employee.cpr_number = "151186-1234"
    employee.hire_date = date(1986, 11, 10)
    db.commit()
    keys = [a.alert_key for a in milestone_alerts(current_user=_user(db, "a", ["jubilee_alert"]), db=db, today=TODAY)]
    assert keys == ["jubilee_40"]


def test_inactive_employees_and_passed_dates_ignored(db, employee):
    from routers.employees import milestone_alerts
    employee.cpr_number = "151186-1234"
    db.commit()
    user = _user(db, "a", ALL)
    assert milestone_alerts(current_user=user, db=db, today=date(2026, 11, 16)) == []
    employee.active = False
    db.commit()
    assert milestone_alerts(current_user=user, db=db, today=TODAY) == []


def test_dismiss_is_per_user_and_per_event(db, employee):
    from routers.employees import dismiss_milestone_alert, milestone_alerts
    employee.cpr_number = "151186-1234"
    db.commit()
    a, b = _user(db, "a", ALL), _user(db, "b", ALL)
    dismiss_milestone_alert(employee.id, MilestoneAlertDismiss(alert_key="birthday_40"), current_user=a, db=db)
    dismiss_milestone_alert(employee.id, MilestoneAlertDismiss(alert_key="birthday_40"), current_user=a, db=db)  # idempotent
    assert milestone_alerts(current_user=a, db=db, today=TODAY) == []
    assert len(milestone_alerts(current_user=b, db=db, today=TODAY)) == 1


def test_dismiss_rejects_unknown_key_or_missing_permission(db, employee):
    from routers.employees import dismiss_milestone_alert
    with pytest.raises(HTTPException) as exc:
        dismiss_milestone_alert(employee.id, MilestoneAlertDismiss(alert_key="upcoming"),
                                current_user=_user(db, "a", ALL), db=db)
    assert exc.value.status_code == 400
    with pytest.raises(HTTPException) as exc:
        dismiss_milestone_alert(employee.id, MilestoneAlertDismiss(alert_key="birthday_40"),
                                current_user=_user(db, "b", ["elev_alert"]), db=db)
    assert exc.value.status_code == 403
```

- [ ] **Step 2: Kør testen og se den fejle**

Run: `python -m pytest tests/test_milestone_alerts.py -q`
Expected: FAIL med `ImportError: cannot import name 'milestone_alerts'`

- [ ] **Step 3: Implementér**

Opdatér importerne i `app/routers/employees.py`:

```python
from utils.employee_rules import (
    cpr_birthdate, in_alert_window, is_masked_cpr, jubilee_alert, mask_cpr,
    next_employee_number, round_birthday_alert, validate_cpr,
)
```

og tilføj `MilestoneAlert, MilestoneAlertDismiss` til importen fra `database.schemas`.

Indsæt efter `dismiss_paragraf56_alert` (før `@router.get("/{employee_id}")`):

```python
_MILESTONE_PERMS = {"birthday": "birthday_alert", "jubilee": "jubilee_alert", "elev": "elev_alert"}


def _milestone_alerts_for(emp: Employee, today: date) -> list:
    """Alle aktuelle jubilæums-/elev-/fødselsdagsadvarsler for én medarbejder."""
    out = []
    if emp.cpr_number:
        try:
            hit = round_birthday_alert(cpr_birthdate(emp.cpr_number), today)
        except ValueError:
            hit = None
        if hit:
            age, when = hit
            out.append(("birthday", f"birthday_{age}", when, f"fylder {age} år"))
    hit = jubilee_alert(emp.seniority_date or emp.hire_date, today)
    if hit:
        years, when = hit
        out.append(("jubilee", f"jubilee_{years}", when, f"har {years} års jubilæum"))
    if (emp.agreement_kind != FUNKTIONAER and emp.elev and emp.elev_end_date
            and in_alert_window(emp.elev_end_date, today)):
        out.append(("elev", f"elev_{emp.elev_end_date.isoformat()}", emp.elev_end_date, "afslutter elevtiden"))
    return out


@router.get("/milestone-alerts", response_model=list[MilestoneAlert])
def milestone_alerts(current_user: AppUser = Depends(require_any_permission(*_MILESTONE_PERMS.values())),
                     db: Session = Depends(get_db), today: Optional[date] = None):
    """Jubilæum (25/40/50 år), elev slutter og rund fødselsdag – fra en måned før til og
    med dagen. Hver type kræver sin egen rettighed. Afvisning er pr. bruger."""
    today = today or date.today()
    allowed = {k for k, perm in _MILESTONE_PERMS.items() if user_has_permission(db, current_user, perm)}
    dismissed = {
        (d.employee_id, d.alert_type)
        for d in db.query(Paragraf56AlertDismissal).filter(
            Paragraf56AlertDismissal.user_id == current_user.id
        ).all()
    }
    alerts = []
    for emp in db.query(Employee).filter(Employee.active == True).all():
        for kind, key, when, label in _milestone_alerts_for(emp, today):
            if kind in allowed and (emp.id, key) not in dismissed:
                alerts.append(MilestoneAlert(
                    employee_id=emp.id, employee_name=emp.name, employee_number=emp.employee_number,
                    kind=kind, alert_key=key, event_date=when, label=label,
                ))
    return sorted(alerts, key=lambda a: (a.event_date, a.employee_name))


@router.post("/{employee_id}/dismiss-milestone-alert", status_code=204)
def dismiss_milestone_alert(employee_id: int, body: MilestoneAlertDismiss,
                            current_user: AppUser = Depends(require_any_permission(*_MILESTONE_PERMS.values())),
                            db: Session = Depends(get_db)):
    """'OK' i popup'en – advarslen kommer ikke igen for DENNE bruger og DENNE begivenhed."""
    kind = body.alert_key.split("_", 1)[0]
    if kind not in _MILESTONE_PERMS or "_" not in body.alert_key:
        raise HTTPException(400, f"Ukendt advarsel: {body.alert_key}")
    if not user_has_permission(db, current_user, _MILESTONE_PERMS[kind]):
        raise HTTPException(403, "Ingen adgang")
    exists = db.query(Paragraf56AlertDismissal).filter(
        Paragraf56AlertDismissal.employee_id == employee_id,
        Paragraf56AlertDismissal.user_id == current_user.id,
        Paragraf56AlertDismissal.alert_type == body.alert_key,
    ).first()
    if not exists:
        db.add(Paragraf56AlertDismissal(employee_id=employee_id, user_id=current_user.id,
                                        alert_type=body.alert_key))
        db.commit()
```

Ret kommentaren på `Paragraf56AlertDismissal.alert_type` i `app/database/models.py` til:

```python
    alert_type = Column(String(20), nullable=False)  # "upcoming" | "expired" | "birthday_40" | "jubilee_25" | "elev_ÅÅÅÅ-MM-DD"
```

- [ ] **Step 4: Kør testen og se den bestå**

Run: `python -m pytest tests/test_milestone_alerts.py -q`
Expected: 8 PASS

- [ ] **Step 5: Stop – brugeren committer**

---

### Task 7: Excel-eksport

**Files:**
- Modify: `app/routers/employees.py` (endpoint før `@router.get("/{employee_id}")`)
- Test: `tests/test_employee_export.py`

**Interfaces:**
- Consumes: `EmployeeExportRequest` (task 2), rettigheden `employee_export` (task 3)
- Produces: `POST /api/employees/export-xlsx` body `{"employee_ids": [..]}` → xlsx-fil. Funktion `export_employees_xlsx(body, current_user, db)`. Kolonnerne står i `EXPORT_HEADERS`.

Klienten sender id'erne i den rækkefølge tabellen viser dem (efter filtre, søgning og sortering). Så skal serveren ikke kende filterlogikken.

- [ ] **Step 1: Skriv de fejlende tests**

`tests/test_employee_export.py`:

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

import io
from datetime import date

import openpyxl

from database.models import AppUser, AuditLog, DispatcherGroup, Employee
from database.schemas import EmployeeExportRequest


def _user(db):
    u = AppUser(name="Admin", initials="ADM", role="admin", password_hash="x")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


async def _read(resp):
    chunks = [c async for c in resp.body_iterator]
    return openpyxl.load_workbook(io.BytesIO(b"".join(chunks))).active


def _emp(db, number, **kw):
    e = Employee(employee_number=number, first_name="Fornavn" + number, last_name="Efternavn",
                 agreement_type="X", hire_date=date(2020, 5, 1), **kw)
    db.add(e)
    db.commit()
    return e


def test_export_columns_order_and_no_cpr(db):
    import asyncio
    from routers.employees import EXPORT_HEADERS, export_employees_xlsx
    group = DispatcherGroup(name="2 - Kran")
    db.add(group)
    db.commit()
    a = _emp(db, "34001", phone="11223344", mobile="55667788", email="a@x.dk", position_id=1,
             dispatcher_group_id=group.id, cpr_number="120385-1234", fuldloennet=True, natarbejde_tillaeg=True,
             elev=True, elev_start_date=date(2026, 8, 1), elev_end_date=date(2029, 7, 31))
    b = _emp(db, "34002", fuldloennet=False)
    resp = export_employees_xlsx(EmployeeExportRequest(employee_ids=[b.id, a.id]), current_user=_user(db), db=db)
    ws = asyncio.run(_read(resp))
    rows = list(ws.iter_rows(values_only=True))
    assert list(rows[0]) == EXPORT_HEADERS
    assert rows[1][0] == "34002"           # klientens rækkefølge bevares
    assert rows[2][:7] == ("34001", "Fornavn34001 Efternavn", "Ja", "Ja", "Testchauffør", "2 - Kran", "01-05-2020")
    assert rows[2][7:] == ("11223344", "55667788", "a@x.dk", "Ja", "01-08-2026", "31-07-2029")
    assert rows[1][3] == "Nej" and rows[1][10] == "Nej" and rows[1][11] is None
    flat = " ".join(str(v) for r in rows for v in r if v)
    assert "1234" not in flat and "120385" not in flat


def test_export_is_audit_logged(db):
    from routers.employees import export_employees_xlsx
    a = _emp(db, "34001")
    user = _user(db)
    export_employees_xlsx(EmployeeExportRequest(employee_ids=[a.id]), current_user=user, db=db)
    assert db.query(AuditLog).filter(AuditLog.action == "employee_export").count() == 1
```

- [ ] **Step 2: Kør testen og se den fejle**

Run: `python -m pytest tests/test_employee_export.py -q`
Expected: FAIL med `ImportError: cannot import name 'EXPORT_HEADERS'`

- [ ] **Step 3: Implementér**

Tilføj imports i `app/routers/employees.py`:

```python
import io
import openpyxl
from openpyxl.styles import Font, PatternFill
from fastapi.responses import StreamingResponse
from auth import log_action
```

(`log_action` kan tilføjes til den eksisterende `from auth import …`-linje.) Tilføj også `EmployeeExportRequest` til importen fra `database.schemas`.

Indsæt før `@router.get("/{employee_id}")`:

```python
EXPORT_HEADERS = [
    "Lønnummer", "Navn", "Fuldlønnet", "Natarbejdetillæg", "Stilling", "Disponentgruppe",
    "Ansættelsesdato", "Telefon", "Mobil", "Email", "Elev", "Elev start", "Elev slut",
]


def _dk_date(d: Optional[date]) -> Optional[str]:
    return d.strftime("%d-%m-%Y") if d else None


@router.post("/export-xlsx")
def export_employees_xlsx(body: EmployeeExportRequest,
                          current_user: AppUser = Depends(require_permission("employee_export")),
                          db: Session = Depends(get_db)):
    """Medarbejderregisterets tabelvisning som Excel. Rækkefølgen er klientens
    (efter filtre/søgning/sortering). CPR kommer aldrig med."""
    by_id = {e.id: e for e in db.query(Employee).filter(Employee.id.in_(body.employee_ids)).all()}
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Medarbejderregister"
    ws.append(EXPORT_HEADERS)
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill(start_color="317423", end_color="317423", fill_type="solid")
    for emp_id in body.employee_ids:
        e = by_id.get(emp_id)
        if not e:
            continue
        is_elev = bool(e.elev) and e.agreement_kind != FUNKTIONAER
        ws.append([
            e.employee_number, e.name,
            "Ja" if e.fuldloennet else "Nej",
            "Ja" if e.natarbejde_tillaeg else "Nej",
            e.position.name if e.position else None,
            e.dispatcher_group.name if e.dispatcher_group else None,
            _dk_date(e.hire_date), e.phone, e.mobile, e.email,
            "Ja" if is_elev else "Nej",
            _dk_date(e.elev_start_date) if is_elev else None,
            _dk_date(e.elev_end_date) if is_elev else None,
        ])
    for col in ws.columns:
        ws.column_dimensions[col[0].column_letter].width = max(12, max(len(str(c.value or "")) for c in col) + 2)
    log_action(db, current_user, "employee_export", "employee", None,
               f"Eksporteret medarbejderregister ({len(by_id)} medarbejdere)")
    db.commit()
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    filename = f"Medarbejderregister_{date.today().isoformat()}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
```

- [ ] **Step 4: Kør testen og se den bestå**

Run: `python -m pytest tests/test_employee_export.py -q`
Expected: 2 PASS

Run: `python -m pytest tests -q`
Expected: alle PASS

- [ ] **Step 5: Stop – brugeren committer**

---

### Task 8: Frontend – medarbejder-modal

**Files:**
- Modify: `app/templates/index.html` (`#modal-employee` linje 1424-1613; ny modal `#modal-emp-hidden-flags` lige efter `#modal-employee`)
- Modify: `app/static/js/app.js` (`onAgreementKindChange` ca. linje 3516, `openNewEmployeeModal` ca. 3561, `openEditEmployee` ca. 3595, `confirmEmployee` ca. 3648, `_saveEmployee`)

**Interfaces:**
- Consumes: `GET /api/employees/next-employee-number`, `GET /api/employees/check-number`, `GET /api/employees/positions` (task 4). Nye felter på `EmployeeCreate`/`EmployeeUpdate`/`EmployeeResponse` (task 2).
- Produces (bruges i task 10):
  - `state.positions: [{id, name}]`
  - `loadPositions(): Promise<void>`
  - `isElev(e): boolean` = `!!e.elev && e.agreement_kind !== "funktionaer"`

Ingen automatiske frontend-tests i projektet. Verifikation sker manuelt i browseren (step 6).

- [ ] **Step 1: HTML – nye felter i modalen**

I `#modal-employee`:

a) Erstat Lønnummer/Førerkort/Initialer-rækken (linje 1469-1483) med:

```html
      <div class="form-row">
        <div class="form-group">
          <label>Lønnummer <span style="color:var(--danger)">*</span></label>
          <input type="text" id="emp-number" placeholder="Fx 34629" inputmode="numeric" onblur="checkEmployeeNumber()">
          <div id="emp-number-error" class="form-hint" style="display:none;color:var(--danger)"></div>
        </div>
        <div class="form-group" id="emp-card-group">
          <label>Førerkortnummer <span id="emp-card-star" style="color:var(--danger)">*</span></label>
          <input type="text" id="emp-card" placeholder="DK00000000000000">
        </div>
        <div class="form-group">
          <label>Initialer <span id="emp-initials-star" style="color:var(--danger);display:none">*</span></label>
          <input type="text" id="emp-initials" placeholder="Fx ABC" maxlength="10" style="text-transform:uppercase"
                 title="Bruges til at matche medarbejderen mod en login-bruger for 'redigér egen linje' i Vagtplan">
        </div>
      </div>

      <div class="form-group">
        <label>Stilling <span style="color:var(--danger)">*</span></label>
        <select id="emp-position"></select>
      </div>
```

b) Erstat E-mail-blokken (linje 1507-1510) med:

```html
      <div class="form-group">
        <label><span id="emp-email-label">Email</span> <span style="color:var(--danger)">*</span></label>
        <input type="text" id="emp-email" placeholder="navn@firma.dk">
      </div>
```

c) Erstat Ansættelses-/Fratrædelsesrækken (linje 1523-1533) med:

```html
      <div class="form-row">
        <div class="form-group">
          <label>Ansættelsesdato <span style="color:var(--danger)">*</span></label>
          <div id="emp-hire"></div>
        </div>
        <div class="form-group">
          <label>Fratrædelsesdato</label>
          <div id="emp-termination"></div>
          <div class="form-hint">Udfyldes først ved fratrædelse (default 31-12-9999)</div>
        </div>
      </div>

      <div class="form-row">
        <div class="form-group">
          <label>Anciennitetsdato</label>
          <div id="emp-seniority"></div>
          <div class="form-hint">Må være tom – bruges kun til jubilæumsadvarsel</div>
        </div>
        <div class="form-group">
          <label>CPR-nummer</label>
          <input type="text" id="emp-cpr" placeholder="ddmmåå-xxxx" maxlength="11" autocomplete="off">
          <div class="form-hint" id="emp-cpr-hint" style="display:none">Maskeret – skriv et nyt fuldt CPR-nummer for at ændre det</div>
        </div>
      </div>
```

d) Erstat afkrydsningsrækken og særaftale-rækken (linje 1535-1569) med:

```html
      <div class="form-row" style="grid-template-columns:1fr 1fr 1fr 1fr">
        <div class="form-group">
          <label style="display:flex;align-items:center;gap:8px;cursor:pointer">
            <input type="checkbox" id="emp-active" checked> Aktiv
          </label>
        </div>
        <div class="form-group">
          <label style="display:flex;align-items:center;gap:8px;cursor:pointer">
            <input type="checkbox" id="emp-fuldloennet" checked> Fuldlønnet
          </label>
        </div>
        <div class="form-group">
          <label style="display:flex;align-items:center;gap:8px;cursor:pointer">
            <input type="checkbox" id="emp-paragraf56" onchange="onParagraf56Change()"> §56
          </label>
        </div>
        <div class="form-group">
          <label style="display:flex;align-items:center;gap:8px;cursor:pointer">
            <input type="checkbox" id="emp-personaleforening" checked> Medlem af Personaleforening
          </label>
        </div>
        <div class="form-group emp-driver-only">
          <label style="display:flex;align-items:center;gap:8px;cursor:pointer">
            <input type="checkbox" id="emp-elev" onchange="onElevChange()"> Elev
          </label>
        </div>
        <div class="form-group emp-driver-only">
          <label style="display:flex;align-items:center;gap:8px;cursor:pointer">
            <input type="checkbox" id="emp-afloeser"> Afløser
          </label>
        </div>
        <div class="form-group emp-driver-only">
          <label style="display:flex;align-items:center;gap:8px;cursor:pointer">
            <input type="checkbox" id="emp-fast-bil" onchange="onFastBilChange()"> Fast bil
          </label>
        </div>
        <div class="form-group emp-driver-only">
          <label style="display:flex;align-items:center;gap:8px;cursor:pointer">
            <input type="checkbox" id="emp-natarbejde"> Natarbejdetillæg
          </label>
        </div>
      </div>

      <div class="form-row emp-driver-only">
        <div class="form-group">
          <label style="display:flex;align-items:center;gap:8px;cursor:pointer">
            <input type="checkbox" id="emp-ot-extra-alle-timer"> Særaftale: Øvrig overtid for alle timer
          </label>
        </div>
      </div>

      <div class="form-row" id="emp-elev-dates" style="display:none">
        <div class="form-group">
          <label>Elev startdato <span style="color:var(--danger)">*</span></label>
          <div id="emp-elev-start"></div>
        </div>
        <div class="form-group">
          <label>Elev slutdato <span style="color:var(--danger)">*</span></label>
          <div id="emp-elev-end"></div>
        </div>
      </div>
```

e) Tilføj klassen `emp-driver-only` på `#emp-fast-bil-vehicle-row` (`<div class="form-row emp-driver-only" id="emp-fast-bil-vehicle-row" style="display:none">`).

f) Indsæt lige efter `#modal-employee`s afsluttende `</div>` (efter linje 1613):

```html
<!-- Skjulte chauffør-markeringer ved skift til funktionær -->
<div id="modal-emp-hidden-flags" class="modal-overlay">
  <div class="modal" style="width:480px">
    <div class="modal-header">
      <h2>Markeringer fra chauffør-tiden</h2>
      <button class="modal-close" onclick="closeModal('modal-emp-hidden-flags')">&#215;</button>
    </div>
    <div class="modal-body" id="emp-hidden-flags-body"></div>
    <div class="modal-footer">
      <button class="btn btn-secondary" onclick="closeModal('modal-emp-hidden-flags')">Annuller</button>
      <button class="btn btn-primary" onclick="confirmEmpHiddenFlags()">Gem</button>
    </div>
  </div>
</div>
```

- [ ] **Step 2: JS – type-skift, elev, stillinger, nummertjek**

Erstat hele `onAgreementKindChange()` med:

```js
const FUNKTIONAER = "funktionaer";
let _empOriginalKind = null;   // aftaletype ved åbning af modalen (null = ny medarbejder)

function isElev(e) {
  return !!e.elev && e.agreement_kind !== FUNKTIONAER;
}

function onAgreementKindChange() {
  const key = document.getElementById("emp-agreement-kind").value;
  const kind = state.agreementKinds.find(k => k.key === key);
  const requires = kind ? kind.requires_agreement_type : true;
  document.getElementById("emp-agreement-type-required-star").style.display = requires ? "" : "none";

  document.getElementById("emp-agreement-type-group").style.display = requires ? "" : "none";
  if (!requires) document.getElementById("emp-agreement-type").value = "";

  // Felter der ikke gælder for typen skjules kun – værdierne bevares (spec 3.3)
  const isFunktionaer = key === FUNKTIONAER;
  document.getElementById("emp-card-group").style.display = isFunktionaer ? "none" : "";
  document.getElementById("emp-initials-star").style.display = isFunktionaer ? "" : "none";
  document.getElementById("emp-email-label").textContent = isFunktionaer ? "Email (Poulschou)" : "Email (Privat)";
  document.querySelectorAll("#modal-employee .emp-driver-only").forEach(el => {
    el.style.display = isFunktionaer ? "none" : "";
  });
  if (!isFunktionaer) {
    onFastBilChange();
  }
  onElevChange();

  const isNewEmployee = !document.getElementById("emp-id").value;
  if (isNewEmployee && isFunktionaer) {
    const sel = document.getElementById("emp-dispatcher-group");
    if (!sel.value) {
      const kontorGroup = state.dispatcherGroups.find(g => /^0\b/.test(g.name.trim()) && /kontor/i.test(g.name));
      if (kontorGroup) sel.value = String(kontorGroup.id);
    }
  }
}

function onElevChange() {
  const isFunktionaer = document.getElementById("emp-agreement-kind").value === FUNKTIONAER;
  const checked = document.getElementById("emp-elev").checked;
  document.getElementById("emp-elev-dates").style.display = checked && !isFunktionaer ? "" : "none";
}

async function loadPositions() {
  try { state.positions = await GET("/api/employees/positions"); }
  catch (_) { state.positions = state.positions || []; }
}

function fillPositionSelect(selectedId = null) {
  const sel = document.getElementById("emp-position");
  sel.innerHTML = `<option value="">[Vælg stilling]</option>` + (state.positions || [])
    .map(p => `<option value="${p.id}" ${p.id === selectedId ? "selected" : ""}>${h(p.name)}</option>`)
    .join("");
}

async function checkEmployeeNumber() {
  const input = document.getElementById("emp-number");
  const err = document.getElementById("emp-number-error");
  const number = input.value.trim();
  err.style.display = "none";
  if (!number) return true;
  const id = document.getElementById("emp-id").value;
  try {
    const qs = new URLSearchParams({ number });
    if (id) qs.set("exclude_id", id);
    const r = await GET(`/api/employees/check-number?${qs}`);
    if (r.taken) {
      err.textContent = `Lønnummer ${number} bruges allerede af ${r.employee_name}`;
      err.style.display = "";
      return false;
    }
  } catch (_) { /* serveren afviser alligevel en dublet ved gem */ }
  return true;
}
```

Tilføj `positions: [],` til `state`-objektets definition (søg efter `const state = {` øverst i `app.js`).

- [ ] **Step 3: JS – åbn modal (ny og redigér)**

I `openNewEmployeeModal()`:
- tilføj `await loadPositions();` efter `await loadAgreementKinds();`
- udvid id-listen der nulstilles med `"emp-cpr"`:
  ```js
  ["emp-number","emp-card","emp-initials","emp-firstname","emp-lastname","emp-address","emp-postal",
   "emp-email","emp-phone","emp-mobile","emp-cpr"].forEach(id => document.getElementById(id).value = "");
  ```
- indsæt lige før `buildScheduleTable(null);`:
  ```js
  _empOriginalKind = null;
  fillPositionSelect(null);
  buildDatePicker("emp-seniority", "");
  document.getElementById("emp-cpr-hint").style.display = "none";
  document.getElementById("emp-personaleforening").checked = true;
  document.getElementById("emp-elev").checked = false;
  document.getElementById("emp-natarbejde").checked = false;
  buildDatePicker("emp-elev-start", "");
  buildDatePicker("emp-elev-end", "");
  document.getElementById("emp-number-error").style.display = "none";
  try {
    const { suggestion } = await GET("/api/employees/next-employee-number");
    document.getElementById("emp-number").value = suggestion;
  } catch (_) { /* forslag er en hjælp – modalen virker uden */ }
  onAgreementKindChange();
  ```

I `openEditEmployee(id)`:
- tilføj `await loadPositions();` efter `await loadAgreementKinds();`
- indsæt lige før `buildScheduleTable(e.work_schedule);`:
  ```js
  _empOriginalKind = e.agreement_kind;
  fillPositionSelect(e.position_id ?? null);
  buildDatePicker("emp-seniority", e.seniority_date || "");
  document.getElementById("emp-cpr").value = e.cpr_number || "";
  document.getElementById("emp-cpr-hint").style.display = (e.cpr_number || "").endsWith("****") ? "" : "none";
  document.getElementById("emp-personaleforening").checked = e.personaleforening;
  document.getElementById("emp-elev").checked = e.elev;
  document.getElementById("emp-natarbejde").checked = e.natarbejde_tillaeg;
  buildDatePicker("emp-elev-start", e.elev_start_date || "");
  buildDatePicker("emp-elev-end", e.elev_end_date || "");
  document.getElementById("emp-number-error").style.display = "none";
  onAgreementKindChange();
  ```

- [ ] **Step 4: JS – gem med validering og popup for skjulte flag**

I `confirmEmployee()`, tilføj til `body`-objektet efter `absence_vehicle_id: …,`:

```js
    position_id: document.getElementById("emp-position").value
      ? parseInt(document.getElementById("emp-position").value) : null,
    seniority_date: readDatePicker("emp-seniority") || null,
    cpr_number: document.getElementById("emp-cpr").value.trim() || null,
    personaleforening: document.getElementById("emp-personaleforening").checked,
    elev: document.getElementById("emp-elev").checked,
    elev_start_date: document.getElementById("emp-elev").checked ? (readDatePicker("emp-elev-start") || null) : null,
    elev_end_date: document.getElementById("emp-elev").checked ? (readDatePicker("emp-elev-end") || null) : null,
    natarbejde_tillaeg: document.getElementById("emp-natarbejde").checked,
```

Erstat valideringsblokken fra `if (!body.employee_number || …` til og med §56-tjekkene med:

```js
  const isFunktionaer = body.agreement_kind === FUNKTIONAER;
  const missing = [];
  if (!body.employee_number) missing.push("Lønnummer");
  if (!body.first_name) missing.push("Fornavn");
  if (!body.last_name) missing.push("Efternavn");
  if (!body.hire_date) missing.push("Ansættelsesdato");
  if (!body.position_id) missing.push("Stilling");
  if (!body.email) missing.push("Email");
  if (isFunktionaer && !body.initials) missing.push("Initialer");
  if (!isFunktionaer && !body.tachograph_card_number) missing.push("Førerkortnummer");
  if (missing.length) {
    toast(`Udfyld: ${missing.join(", ")}`, "error");
    return;
  }
  if (!body.absence_vehicle_id) {
    toast("Vælg et vognnummer ved fravær fra listen", "error");
    return;
  }
  if (body.cpr_number && !body.cpr_number.endsWith("****") && !/^\d{6}-\d{4}$/.test(body.cpr_number)) {
    toast("CPR-nummer skal have formatet ddmmåå-xxxx", "error");
    return;
  }
  if (body.paragraf_56 && (!body.paragraf_56_start_date || !body.paragraf_56_end_date)) {
    toast("Udfyld start- og slutdato for §56", "error");
    return;
  }
  if (body.paragraf_56 && body.paragraf_56_end_date < body.paragraf_56_start_date) {
    toast("§56 slutdato skal være efter startdato", "error");
    return;
  }
  if (!isFunktionaer && body.elev && (!body.elev_start_date || !body.elev_end_date)) {
    toast("Udfyld start- og slutdato for elev", "error");
    return;
  }
  if (!isFunktionaer && body.elev && body.elev_end_date < body.elev_start_date) {
    toast("Elev slutdato skal være efter startdato", "error");
    return;
  }
  if (!(await checkEmployeeNumber())) {
    toast("Lønnummeret er allerede i brug", "error");
    return;
  }
```

Lige før `if (!id) {` (dublet-tjekket) indsæt:

```js
  // Skift fra chauffør til funktionær med skjulte markeringer: spørg pr. markering (spec 3.3)
  const switchedToOffice = isFunktionaer && _empOriginalKind !== FUNKTIONAER;
  const hiddenFlags = [
    ["afloeser", "Afløser"], ["fast_bil", "Fast bil"], ["ot_extra_alle_timer", "Særaftale: Øvrig overtid for alle timer"],
  ].filter(([key]) => body[key]);
  if (switchedToOffice && hiddenFlags.length) {
    _showEmpHiddenFlags(id, body, hiddenFlags);
    return;
  }
```

Flyt dublet-tjekket og `_saveEmployee`-kaldet ud i en hjælpefunktion, så popup'en kan fortsætte samme flow. Erstat resten af `confirmEmployee()` (fra `if (!id) {` til slutningen) med:

```js
  await _continueSaveEmployee(id, body);
}

async function _continueSaveEmployee(id, body) {
  if (!id) {
    try {
      const all = await GET("/api/employees?active_only=false");
      const nameMatches = all.filter(e =>
        e.first_name.trim().toLowerCase() === body.first_name.toLowerCase() &&
        e.last_name.trim().toLowerCase() === body.last_name.toLowerCase());
      const cardMatches = body.tachograph_card_number
        ? all.filter(e => (e.tachograph_card_number || "").trim().toLowerCase() === body.tachograph_card_number.toLowerCase())
        : [];
      if (nameMatches.length || cardMatches.length) {
        _showEmployeeDuplicateWarning(body, nameMatches, cardMatches);
        return;
      }
    } catch (_) { /* duplikat-tjek må ikke blokere oprettelse hvis den fejler */ }
  }
  await _saveEmployee(id, body);
}

let _pendingHiddenFlags = null;

function _showEmpHiddenFlags(id, body, flags) {
  _pendingHiddenFlags = { id, body, flags };
  const name = `${body.first_name} ${body.last_name}`;
  document.getElementById("emp-hidden-flags-body").innerHTML = `
    <p style="font-size:14px;margin-bottom:12px">
      <strong>${h(name)}</strong> har stadig følgende markeringer fra chauffør-tiden. Vælg for hver, om den skal beholdes eller fjernes.
    </p>
    ${flags.map(([key, label]) => `
      <div style="display:flex;align-items:center;justify-content:space-between;padding:8px 0;border-top:1px solid var(--border)">
        <span style="font-size:13px">${h(label)}</span>
        <span style="display:flex;gap:14px;font-size:13px">
          <label style="display:flex;gap:4px;align-items:center;cursor:pointer"><input type="radio" name="hf-${key}" value="keep" checked> Behold</label>
          <label style="display:flex;gap:4px;align-items:center;cursor:pointer"><input type="radio" name="hf-${key}" value="remove"> Fjern</label>
        </span>
      </div>`).join("")}
  `;
  openModal("modal-emp-hidden-flags");
}

async function confirmEmpHiddenFlags() {
  if (!_pendingHiddenFlags) return;
  const { id, body, flags } = _pendingHiddenFlags;
  for (const [key] of flags) {
    if (document.querySelector(`input[name="hf-${key}"]:checked`)?.value === "remove") {
      body[key] = false;
      if (key === "fast_bil") body.fast_bil_vehicle_id = null;
    }
  }
  _pendingHiddenFlags = null;
  closeModal("modal-emp-hidden-flags");
  await _continueSaveEmployee(id, body);
}
```

Sørg for, at den første del af `confirmEmployee()` (body-opbygning + validering + popup-tjek) står uændret over `await _continueSaveEmployee(id, body);`.

- [ ] **Step 5: Kør backend-tests (sikkerhedsnet)**

Run: `python -m pytest tests -q`
Expected: alle PASS

- [ ] **Step 6: Manuel verifikation i browseren**

Start app'en med `preview_start` (launch-konfiguration i `.claude/launch.json`). Brugeren logger selv ind. Tjek:
1. "+ Opret medarbejder" udfylder lønnummer med højeste + 1.
2. Et eksisterende lønnummer giver en rød besked, når feltet forlades, og der kan ikke gemmes.
3. Aftale = Funktionær: Førerkort, Elev, Afløser, Fast bil, Natarbejdetillæg og Særaftale skjules. Label "Email (Poulschou)", Initialer får *. "0 - Kontor" forvælges.
4. Aftale = chauffør-type: label "Email (Privat)", Førerkort får *. Elev viser datofelter.
5. Gem uden Stilling/Email giver en toast med de manglende felter.
6. Redigér en chauffør med Afløser, skift til Funktionær og gem: popup med Behold/Fjern. Fjern → genåbn og bekræft, at Afløser er fjernet.
7. CPR gemmes og vises fuldt for admin.
8. `read_console_messages` – ingen JS-fejl.

- [ ] **Step 7: Stop – brugeren committer**

---

### Task 9: Frontend – stamdata-fanen "Stillinger"

**Files:**
- Modify: `app/templates/index.html` (tab-knap efter `sd-tab-agreementkind`, pane efter `sd-pane-absence`, "+ Tilføj"-knap ved siden af `btn-stamdata-add-absence`, modal efter `#modal-stamdata-absence`)
- Modify: `app/static/js/app.js` (`switchStamdataTab`, `loadStamdata`, nye funktioner efter `deleteStamdataAbsence`)

**Interfaces:**
- Consumes: `/api/stamdata/positions` CRUD (task 5)
- Produces: `loadStamdataPositions()`, `openStamdataPositionModal(id, name)`, `confirmStamdataPosition()`, `deleteStamdataPosition(id, name)`

- [ ] **Step 1: HTML**

Find knappen `id="btn-stamdata-add-absence"` (`grep -n btn-stamdata-add-absence app/templates/index.html`) og indsæt lige efter den:

```html
        <button class="btn btn-primary" id="btn-stamdata-add-position" style="display:none" onclick="openStamdataPositionModal()">+ Tilføj stilling</button>
```

Efter tab-knappen `sd-tab-agreementkind`:

```html
        <button id="sd-tab-position" onclick="switchStamdataTab('position')"
                style="padding:7px 18px;border:none;border-bottom:2px solid transparent;margin-bottom:-2px;background:transparent;font-size:13px;font-weight:600;color:var(--text-light);cursor:pointer">
          Stillinger
        </button>
```

Efter `sd-pane-absence`s afsluttende `</div>`:

```html
        <!-- Stillinger -->
        <div id="sd-pane-position" style="display:none">
          <table style="width:100%;border-collapse:collapse;font-size:14px;background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,.08)">
            <thead>
              <tr style="background:var(--primary);color:#fff">
                <th style="padding:10px 14px;text-align:left;font-weight:600">Navn</th>
                <th style="padding:10px 14px;text-align:center;font-weight:600">Medarbejdere</th>
                <th style="padding:10px 14px;text-align:center;font-weight:600">Handlinger</th>
              </tr>
            </thead>
            <tbody id="stamdata-position-tbody">
              <tr><td colspan="3" style="padding:24px;text-align:center;color:var(--text-light)">Indlæser...</td></tr>
            </tbody>
          </table>
        </div>
```

Efter `#modal-stamdata-absence`s afsluttende `</div>`:

```html
<div id="modal-stamdata-position" class="modal-overlay">
  <div class="modal" style="width:420px">
    <div class="modal-header">
      <h2 id="stamdata-position-title">Stilling</h2>
      <button class="modal-close" onclick="closeModal('modal-stamdata-position')">&#215;</button>
    </div>
    <div class="modal-body">
      <input type="hidden" id="stamdata-position-id">
      <div class="form-group">
        <label>Navn</label>
        <input type="text" id="stamdata-position-name" placeholder="fx Chauffør">
      </div>
    </div>
    <div class="modal-footer">
      <button class="btn btn-secondary" onclick="closeModal('modal-stamdata-position')">Annuller</button>
      <button class="btn btn-primary" onclick="confirmStamdataPosition()">Gem</button>
    </div>
  </div>
</div>
```

- [ ] **Step 2: JS**

I `switchStamdataTab`: tilføj `"position"` til fane-arrayet (efter `"agreementkind"`) og tilføj nederst:

```js
  document.getElementById("btn-stamdata-add-position").style.display = tab === "position" ? "" : "none";
```

I `loadStamdata`: tilføj `loadStamdataPositions(),` i `Promise.all`-listen.

Efter `deleteStamdataAbsence` indsæt:

```js
// ── Stillinger (stamdata) ─────────────────────────────────────────────────

async function loadStamdataPositions() {
  const tbody = document.getElementById("stamdata-position-tbody");
  if (!tbody) return;
  try {
    const rows = await GET("/api/stamdata/positions");
    tbody.innerHTML = rows.length ? rows.map(r => `
      <tr style="border-bottom:1px solid var(--border);background:#fff">
        <td style="padding:10px 14px">${h(r.name)}</td>
        <td style="padding:10px 14px;text-align:center">${r.employee_count}</td>
        <td style="padding:10px 14px;text-align:center">
          <button class="btn btn-secondary" style="font-size:12px;padding:4px 10px;margin-right:4px"
                  onclick="openStamdataPositionModal(${r.id},${jq(r.name)})">Rediger</button>
          <button class="btn btn-danger" style="font-size:12px;padding:4px 10px"
                  onclick="deleteStamdataPosition(${r.id},${jq(r.name)})">Slet</button>
        </td>
      </tr>`).join("")
      : `<tr><td colspan="3" style="padding:24px;text-align:center;color:var(--text-light)">Ingen stillinger endnu</td></tr>`;
  } catch (e) { tbody.innerHTML = `<tr><td colspan="3" style="padding:24px;text-align:center;color:var(--danger)">${h(e.message)}</td></tr>`; }
}

function openStamdataPositionModal(id, name) {
  document.getElementById("stamdata-position-id").value = id || "";
  document.getElementById("stamdata-position-name").value = name || "";
  document.getElementById("stamdata-position-title").textContent = id ? "Rediger stilling" : "Ny stilling";
  openModal("modal-stamdata-position");
}

async function confirmStamdataPosition() {
  const id = document.getElementById("stamdata-position-id").value;
  const name = document.getElementById("stamdata-position-name").value.trim();
  if (!name) { toast("Navn er påkrævet", "error"); return; }
  try {
    if (id) {
      await PATCH(`/api/stamdata/positions/${id}`, { name });
      toast("Stilling opdateret");
    } else {
      await POST("/api/stamdata/positions", { name });
      toast("Stilling oprettet");
    }
    closeModal("modal-stamdata-position");
    await loadStamdataPositions();
  } catch (e) { toast(e.message, "error"); }
}

async function deleteStamdataPosition(id, name) {
  if (!confirm(`Slet stillingen "${name}"?`)) return;
  try {
    await DEL(`/api/stamdata/positions/${id}`);
    toast("Stilling slettet");
    await loadStamdataPositions();
  } catch (e) { toast(e.message, "error"); }
}
```

- [ ] **Step 3: Manuel verifikation**

I browseren: Stamdata → Stillinger. Opret "Chauffør" og "Disponent", omdøb, og slet en ubrugt. Sæt en stilling på en medarbejder og prøv at slette den: fejlbesked med antal. Stillingerne vises alfabetisk i medarbejder-modalens dropdown. Ingen konsolfejl.

- [ ] **Step 4: Stop – brugeren committer**

---

### Task 10: Frontend – liste, søgning, filtre, tabel, eksport og elev-farve

**Files:**
- Modify: `app/templates/index.html` (værktøjslinjen i `data-view="employees"` linje 361-377)
- Modify: `app/static/js/app.js` (`loadEmployees`, `renderEmployeeList`, `init` ca. linje 6494, vagtplan-celle ca. linje 423, aktivitetskalender-celle ca. linje 998)
- Modify: `app/static/css/style.css` (efter `.afloeser-highlight` linje 304)

**Interfaces:**
- Consumes: `state.positions`, `loadPositions()`, `isElev(e)` (task 8). `POST /api/employees/export-xlsx` (task 7). Den eksisterende `downloadFile(path, body, fallbackFilename)`.
- Produces: `renderEmployeeList()` (liste eller tabel), `_filteredEmployees(): Employee[]`, `exportEmployeesXlsx()`, `toggleEmployeeView()`

- [ ] **Step 1: CSS**

I `app/static/css/style.css`, lige efter `.grid-table tbody td.emp-cell.afloeser-highlight { background: #d4edcc; }`:

```css
/* Elev (2026-10-01) – gul, så den kan skelnes fra afløser. Elev vinder over afløser. */
.grid-table tbody td.emp-cell.elev-highlight { background: #fff3b8; }
.emp-table { width:100%; border-collapse:collapse; font-size:13px; background:#fff; border-radius:8px; overflow:hidden; box-shadow:0 1px 4px rgba(0,0,0,.08); }
.emp-table th { background:var(--primary); color:#fff; padding:9px 10px; text-align:left; font-weight:600; cursor:pointer; white-space:nowrap; user-select:none; }
.emp-table td { padding:8px 10px; border-bottom:1px solid var(--border); white-space:nowrap; }
.emp-table tr.elev-row td { background:#fff3b8; }
.emp-table tbody tr { cursor:pointer; }
```

- [ ] **Step 2: HTML – værktøjslinje og tabel-container**

Erstat værktøjslinjen i `data-view="employees"` (linje 362-375) med:

```html
      <div class="toolbar" style="flex-wrap:wrap;gap:8px">
        <h2 style="font-size:16px;font-weight:600">Medarbejdere</h2>
        <div class="spacer"></div>
        <button class="btn btn-primary" onclick="openParagraf56ListModal()">§56</button>
        <button class="btn btn-secondary" id="btn-employee-view-toggle" data-perm-require="employee_table_view" onclick="toggleEmployeeView()">Tabel</button>
        <button class="btn btn-secondary" id="btn-employee-export" data-perm-require="employee_export" style="display:none" onclick="exportEmployeesXlsx()">Eksportér til Excel</button>
        <input type="text" id="employee-search" placeholder="Søg navn, lønnr. eller telefon…"
               style="padding:6px 10px;border:1px solid var(--border);border-radius:6px;font-size:13px;width:220px">
        <select id="employee-filter-dispatcher-group" style="padding:6px 10px;border:1px solid var(--border);border-radius:6px;font-size:13px;width:170px">
          <option value="">Alle afdelinger</option>
        </select>
        <select id="employee-filter-position" style="padding:6px 10px;border:1px solid var(--border);border-radius:6px;font-size:13px;width:160px">
          <option value="">Alle stillinger</option>
        </select>
        <select id="employee-filter-personaleforening" style="padding:6px 10px;border:1px solid var(--border);border-radius:6px;font-size:13px;width:150px">
          <option value="">Personaleforening</option>
          <option value="1">Medlem</option>
          <option value="0">Ikke medlem</option>
        </select>
        <select id="employee-filter-natarbejde" style="padding:6px 10px;border:1px solid var(--border);border-radius:6px;font-size:13px;width:150px">
          <option value="">Natarbejdetillæg</option>
          <option value="1">Ja</option>
          <option value="0">Nej</option>
        </select>
        <select id="employee-filter-elev" style="padding:6px 10px;border:1px solid var(--border);border-radius:6px;font-size:13px;width:120px">
          <option value="">Elev</option>
          <option value="1">Elev</option>
          <option value="0">Ikke elev</option>
        </select>
        <label style="display:flex;align-items:center;gap:6px;font-size:13px;cursor:pointer">
          <input type="checkbox" id="show-inactive"> Vis inaktive
        </label>
        <button class="btn btn-primary" data-perm-require="manage_employees" onclick="openNewEmployeeModal()">+ Opret medarbejder</button>
      </div>
```

`#employee-list` (linje 376) beholdes uændret – både liste og tabel renderes heri.

- [ ] **Step 3: JS – filtrering, liste, tabel og eksport**

Erstat `loadEmployees()` og `renderEmployeeList()` med:

```js
async function loadEmployees() {
  setLoading(true);
  try {
    const showInactive = document.getElementById("show-inactive")?.checked;
    const [emps] = await Promise.all([GET(`/api/employees?active_only=${!showInactive}`), loadPositions()]);
    state.employees = emps;
    fillEmployeePositionFilter();
    renderEmployeeList();
  } catch (e) { toast(e.message, "error"); }
  finally { setLoading(false); }
}

function fillEmployeePositionFilter() {
  const sel = document.getElementById("employee-filter-position");
  if (!sel) return;
  const cur = sel.value;
  sel.innerHTML = `<option value="">Alle stillinger</option><option value="none">Ingen stilling</option>` +
    (state.positions || []).map(p => `<option value="${p.id}">${h(p.name)}</option>`).join("");
  if ([...sel.options].some(o => o.value === cur)) sel.value = cur;
}

// Telefonsøgning: mellemrum, bindestreger og +45/0045 ignoreres
function _normalizePhone(s) {
  let d = String(s || "").replace(/\D/g, "");
  if (d.startsWith("0045")) d = d.slice(4);
  else if (d.length === 10 && d.startsWith("45")) d = d.slice(2);
  return d;
}

function _boolFilter(id, value) {
  const v = document.getElementById(id)?.value || "";
  return v === "" || (v === "1") === !!value;
}

function _filteredEmployees() {
  const query = (document.getElementById("employee-search")?.value || "").toLowerCase().trim();
  const phoneQuery = _normalizePhone(query);
  let emps = state.employees;
  if (query) {
    emps = emps.filter(e =>
      e.name.toLowerCase().includes(query) ||
      String(e.employee_number).toLowerCase().includes(query) ||
      (phoneQuery.length >= 3 && [e.phone, e.mobile].some(p => _normalizePhone(p).includes(phoneQuery)))
    );
  }
  const groupFilter = document.getElementById("employee-filter-dispatcher-group")?.value || "";
  if (groupFilter === "none") emps = emps.filter(e => !e.dispatcher_group);
  else if (groupFilter) emps = emps.filter(e => e.dispatcher_group?.id === parseInt(groupFilter));
  const posFilter = document.getElementById("employee-filter-position")?.value || "";
  if (posFilter === "none") emps = emps.filter(e => !e.position_id);
  else if (posFilter) emps = emps.filter(e => e.position_id === parseInt(posFilter));
  emps = emps.filter(e =>
    _boolFilter("employee-filter-personaleforening", e.personaleforening) &&
    _boolFilter("employee-filter-natarbejde", e.natarbejde_tillaeg) &&
    _boolFilter("employee-filter-elev", isElev(e)));
  return emps;
}

const _EMP_TABLE_COLUMNS = [
  { key: "employee_number", label: "Lønnummer", value: e => e.employee_number, sort: e => e.employee_number },
  { key: "name",            label: "Navn",      value: e => e.name, sort: e => e.name },
  { key: "fuldloennet",     label: "Fuldlønnet", value: e => e.fuldloennet ? "✓" : "–", sort: e => e.fuldloennet ? 1 : 0 },
  { key: "natarbejde",      label: "Natarbejdetillæg", value: e => e.natarbejde_tillaeg ? "✓" : "–", sort: e => e.natarbejde_tillaeg ? 1 : 0 },
  { key: "position",        label: "Stilling",  value: e => e.position_name || "", sort: e => e.position_name || "" },
  { key: "group",           label: "Disponentgruppe", value: e => e.dispatcher_group?.name || "", sort: e => e.dispatcher_group?.name || "" },
  { key: "hire_date",       label: "Ansættelsesdato", value: e => formatDateShort(e.hire_date), sort: e => e.hire_date },
  { key: "phone",           label: "Telefon",   value: e => e.phone || "", sort: e => e.phone || "" },
  { key: "mobile",          label: "Mobil",     value: e => e.mobile || "", sort: e => e.mobile || "" },
  { key: "email",           label: "Email",     value: e => e.email || "", sort: e => e.email || "" },
  { key: "elev",            label: "Elev",
    value: e => isElev(e) ? `Ja (${formatDateShort(e.elev_start_date)}–${formatDateShort(e.elev_end_date)})` : "Nej",
    sort: e => isElev(e) ? (e.elev_end_date || "") : "" },
];

function _employeeViewMode() {
  if (!_hasPerm("employee_table_view")) return "list";
  try { return localStorage.getItem("employeeViewMode") === "table" ? "table" : "list"; }
  catch (_) { return "list"; }
}

function toggleEmployeeView() {
  const next = _employeeViewMode() === "table" ? "list" : "table";
  try { localStorage.setItem("employeeViewMode", next); } catch (_) {}
  renderEmployeeList();
}

function sortEmployeeTable(key) {
  const cur = state.employeeSort || { key: "name", dir: 1 };
  state.employeeSort = { key, dir: cur.key === key ? -cur.dir : 1 };
  renderEmployeeList();
}

function _sortedForTable(emps) {
  const { key, dir } = state.employeeSort || { key: "name", dir: 1 };
  const col = _EMP_TABLE_COLUMNS.find(c => c.key === key) || _EMP_TABLE_COLUMNS[1];
  return emps.slice().sort((a, b) => {
    const va = col.sort(a), vb = col.sort(b);
    const cmp = typeof va === "number" ? va - vb : naturalCompare(String(va), String(vb));
    return cmp * dir;
  });
}

function renderEmployeeList() {
  const container = document.getElementById("employee-list");
  container.innerHTML = "";
  const mode = _employeeViewMode();
  const toggleBtn = document.getElementById("btn-employee-view-toggle");
  if (toggleBtn) toggleBtn.textContent = mode === "table" ? "Liste" : "Tabel";
  const exportBtn = document.getElementById("btn-employee-export");
  if (exportBtn) exportBtn.style.display = mode === "table" && _hasPerm("employee_export") ? "" : "none";

  const emps = _filteredEmployees();
  if (emps.length === 0) {
    container.innerHTML = `<div class="empty-state"><div class="icon">👤</div><h3>Ingen medarbejdere</h3></div>`;
    return;
  }
  const canEdit = _hasPerm("manage_employees");

  if (mode === "table") {
    const sorted = _sortedForTable(emps);
    const { key, dir } = state.employeeSort || { key: "name", dir: 1 };
    container.innerHTML = `
      <div style="overflow-x:auto">
        <table class="emp-table">
          <thead><tr>${_EMP_TABLE_COLUMNS.map(c =>
            `<th onclick="sortEmployeeTable(${jq(c.key)})">${h(c.label)}${c.key === key ? (dir > 0 ? " ▲" : " ▼") : ""}</th>`).join("")}</tr></thead>
          <tbody>${sorted.map(e => `
            <tr class="${isElev(e) ? "elev-row" : ""}" ${canEdit ? `onclick="openEditEmployee(${e.id})"` : ""}>
              ${_EMP_TABLE_COLUMNS.map(c => `<td>${h(c.value(e))}</td>`).join("")}
            </tr>`).join("")}
          </tbody>
        </table>
      </div>`;
    return;
  }

  for (const e of emps.slice().sort((a, b) => a.name.localeCompare(b.name, "da"))) {
    const initials = `${e.first_name[0] || ""}${e.last_name[0] || ""}`.toUpperCase();
    const avatarStyle = isElev(e) ? "background:#e0a800" : (e.afloeser ? "background:var(--accent)" : "");
    const div = document.createElement("div");
    div.className = "emp-card";
    div.style.cursor = "pointer";
    div.innerHTML = `
      <div class="emp-avatar" style="${avatarStyle}">${h(initials)}</div>
      <div class="emp-info">
        <div class="emp-name">${h(e.name)}</div>
        <div class="emp-sub">Lønnr. ${h(e.employee_number)}${e.position_name ? ` · ${h(e.position_name)}` : ""}</div>
      </div>
      ${e.active ? "" : `<span class="badge" style="background:#fee2e2;color:#dc2626">Inaktiv</span>`}
      ${canEdit ? `<button class="btn btn-secondary btn-sm" onclick="event.stopPropagation(); openEditEmployee(${e.id})">Rediger</button>` : ""}
    `;
    div.addEventListener("click", () => { if (canEdit) openEditEmployee(e.id); });
    container.appendChild(div);
  }
}

async function exportEmployeesXlsx() {
  const ids = _sortedForTable(_filteredEmployees()).map(e => e.id);
  if (!ids.length) { toast("Ingen medarbejdere at eksportere", "error"); return; }
  try {
    await downloadFile("/api/employees/export-xlsx", { employee_ids: ids }, "Medarbejderregister.xlsx");
  } catch (e) { toast(e.message, "error"); }
}
```

Tilføj `employeeSort: { key: "name", dir: 1 },` til `state`-objektet.

I `init()`, lige efter linjen `document.getElementById("employee-filter-dispatcher-group")?.addEventListener("change", renderEmployeeList);` tilføjes:

```js
  ["employee-filter-position", "employee-filter-personaleforening", "employee-filter-natarbejde", "employee-filter-elev"]
    .forEach(id => document.getElementById(id)?.addEventListener("change", renderEmployeeList));
```

- [ ] **Step 4: JS – elev-farve i Vagtplan og Aktivitetskalender**

Linje ca. 423 (vagtplan) og ca. 998 (aktivitetskalender) indeholder begge:

```js
`<td class="emp-cell${emp.afloeser ? " afloeser-highlight" : ""}" …
```

Tilføj en hjælper lige over `function isElev` (fra task 8):

```js
// Navnecellens markering: elev (gul) vinder over afløser (grøn)
function empCellHighlight(emp) {
  if (isElev(emp)) return " elev-highlight";
  return emp.afloeser ? " afloeser-highlight" : "";
}
```

Erstat `${emp.afloeser ? " afloeser-highlight" : ""}` med `${empCellHighlight(emp)}` begge steder.

- [ ] **Step 5: Manuel verifikation**

I browseren som admin:
1. Listen viser "Lønnr. 34625 · Chauffør".
2. En elev har gul avatar, en afløser grøn.
3. En søgning på et telefonnummer med og uden mellemrum finder medarbejderen.
4. Hvert filter virker, også kombineret med søgning.
5. "Tabel" viser de 11 kolonner. Klik på en overskrift sorterer, og et klik mere vender rækkefølgen. Elev-rækker er gule. Valget huskes efter genindlæsning.
6. "Eksportér til Excel" henter `Medarbejderregister_ÅÅÅÅ-MM-DD.xlsx` med samme rækker og rækkefølge og uden CPR.
7. I Vagtplan og Aktivitetskalenderen er elevens navnecelle gul.
8. En bruger uden `employee_table_view` ser ikke Tabel-knappen.
9. Ingen konsolfejl.

- [ ] **Step 6: Stop – brugeren committer**

---

### Task 11: Frontend – advarselspopup og rettighedslabels

**Files:**
- Modify: `app/templates/index.html` (ny modal efter `#modal-paragraf56-alert` ca. linje 822)
- Modify: `app/static/js/app.js` (`PERMISSION_LABELS` linje 46-74, `PERMISSION_DESCRIPTIONS` linje 76-104, efter `checkParagraf56Alerts`, kaldet efter login ca. linje 6449)

**Interfaces:**
- Consumes: `GET /api/employees/milestone-alerts`, `POST /api/employees/{id}/dismiss-milestone-alert` (task 6)
- Produces: `checkMilestoneAlerts()`, `dismissMilestoneAlert(employeeId, alertKey)`

- [ ] **Step 1: Rettighedslabels**

I `PERMISSION_LABELS`, efter `dagsplan_edit: …,`:

```js
  view_cpr:            "Se CPR-nummer",
  jubilee_alert:       "Jubilæumsadvarsel",
  elev_alert:          "Elevadvarsel",
  birthday_alert:      "Fødselsdagsadvarsel",
  employee_table_view: "Tabelvisning af medarbejdere",
  employee_export:     "Eksportér medarbejderregister",
```

I `PERMISSION_DESCRIPTIONS`, efter `dagsplan_edit: …,`:

```js
  view_cpr:            "Kan se hele CPR-nummeret. Uden rettigheden vises de sidste fire cifre som ****.",
  jubilee_alert:       "Får en popup en måned før en medarbejders 25-, 40- og 50-års jubilæum.",
  elev_alert:          "Får en popup en måned før en elevs slutdato.",
  birthday_alert:      "Får en popup en måned før en medarbejders runde fødselsdag (10, 20, 30 …).",
  employee_table_view: "Kan skifte medarbejderregisteret til tabelvisning.",
  employee_export:     "Kan eksportere medarbejderregisterets tabel til Excel.",
```

- [ ] **Step 2: HTML – modal**

Efter `#modal-paragraf56-alert`:

```html
<div id="modal-milestone-alert" class="modal-overlay">
  <div class="modal" style="width:460px">
    <div class="modal-header">
      <h2 id="milestone-alert-title">&#128197; Mærkedag</h2>
      <button class="modal-close" onclick="closeModal('modal-milestone-alert')">&#215;</button>
    </div>
    <div class="modal-body" id="milestone-alert-body"></div>
    <div class="modal-footer">
      <button class="btn btn-secondary" onclick="closeModal('modal-milestone-alert')">Luk</button>
      <button class="btn btn-warning" id="btn-milestone-alert-ok">OK</button>
      <button class="btn btn-primary" id="btn-goto-employee-milestone">Gå til medarbejder</button>
    </div>
  </div>
</div>
```

- [ ] **Step 3: JS**

Efter `checkParagraf56Alerts()` indsæt:

```js
// ── Jubilæum / elev / fødselsdag ───────────────────────────────────────────
const _MILESTONE_TITLES = {
  birthday: "&#127874; Rund fødselsdag",
  jubilee:  "&#127942; Jubilæum",
  elev:     "&#127891; Elevtid slutter",
};

async function dismissMilestoneAlert(employeeId, alertKey) {
  try {
    await POST(`/api/employees/${employeeId}/dismiss-milestone-alert`, { alert_key: alertKey });
  } catch (e) {
    console.error("Kunne ikke gemme afvisning af advarsel:", e);
  }
  closeModal("modal-milestone-alert");
}

async function checkMilestoneAlerts() {
  if (!["birthday_alert", "jubilee_alert", "elev_alert"].some(_hasPerm)) return;
  try {
    const alerts = await GET("/api/employees/milestone-alerts");
    if (alerts.length === 0) return;
    const a = alerts[0];
    document.getElementById("milestone-alert-title").innerHTML = _MILESTONE_TITLES[a.kind] || "&#128197; Mærkedag";
    document.getElementById("milestone-alert-body").innerHTML = `
      <p style="font-size:14px;margin-bottom:8px">
        Medarbejder <strong>${h(a.employee_name)} (${h(a.employee_number)})</strong> ${h(a.label)}
        den ${formatDateShort(a.event_date)}.
      </p>
      ${alerts.length > 1 ? `<p style="font-size:12px;color:var(--text-light);margin-top:8px">+ ${alerts.length - 1} flere.</p>` : ""}
    `;
    document.getElementById("btn-goto-employee-milestone").onclick = async () => {
      closeModal("modal-milestone-alert");
      setView("employees");
      await loadEmployees();
      openEditEmployee(a.employee_id);
    };
    document.getElementById("btn-milestone-alert-ok").onclick = () => dismissMilestoneAlert(a.employee_id, a.alert_key);
    openModal("modal-milestone-alert");
  } catch (e) {
    console.error("Mærkedags-advarsel check fejlede:", e);
  }
}
```

Efter `await checkParagraf56Alerts();` i login-flowet (ca. linje 6449):

```js
  await checkMilestoneAlerts();
```

- [ ] **Step 4: Manuel verifikation**

1. Sæt en testmedarbejders CPR til en dato, der giver rund fødselsdag om ca. 2 uger, og genindlæs som admin: popup "Rund fødselsdag" vises.
2. "OK" → genindlæs → popup'en kommer ikke igen. "Luk" → den kommer igen ved næste login.
3. Brugerstyring → redigér en rolle: de 6 nye rettigheder vises med label og beskrivelse.
4. En bruger uden rettighederne får ingen popup.
5. Ingen konsolfejl.

Ryd testdata bagefter (fjern test-CPR).

- [ ] **Step 5: Stop – brugeren committer**

---

### Task 12: Dokumentation

**Files:**
- Modify: `CODEREF.md`
- Modify: `docs/DATA_MODEL.md`
- Modify: `docs/build_docs.py`
- Modify: `docs/superpowers/specs/2026-10-01-medarbejderregister.md` (status → IMPLEMENTERET)

- [ ] **Step 1: DATA_MODEL.md**

Find afsnittet for `employees` (`grep -n "employees" docs/DATA_MODEL.md`) og tilføj rækker for kolonnerne:

| Kolonne | Type | Beskrivelse |
|---|---|---|
| `position_id` | INTEGER FK → `master_positions.id` | Stilling (påkrævet ved næste gem) |
| `seniority_date` | DATE NULL | Anciennitetsdato – kun til jubilæumsadvarsel |
| `cpr_number` | VARCHAR(11) NULL | `ddmmåå-xxxx`; maskeres i API uden `view_cpr` |
| `elev` | BOOLEAN | Kun chauffører |
| `elev_start_date` / `elev_end_date` | DATE NULL | Påkrævet når `elev` (chauffør) |
| `personaleforening` | BOOLEAN | Default True for nye; eksisterende migreret til False |
| `natarbejde_tillaeg` | BOOLEAN | Kun til filtrering |

Tilføj et nyt afsnit for tabellen `master_positions(id, name UNIQUE)`. Tilføj under `paragraf_56_alert_dismissals`, at `alert_type` også kan være `birthday_<alder>`, `jubilee_<år>` og `elev_<ÅÅÅÅ-MM-DD>`.

- [ ] **Step 2: CODEREF.md**

Tilføj under medarbejder-sektionen (`grep -n "_visible_response\|_employee_list_access" CODEREF.md`):

```markdown
- **Medarbejderregister-udvidelse (2026-10-01)** – spec `docs/superpowers/specs/2026-10-01-medarbejderregister.md`.
  - Rene regler i `app/utils/employee_rules.py`: `next_employee_number`, `validate_cpr`, `cpr_birthdate`, `mask_cpr`, `round_birthday_alert`, `jubilee_alert`, `in_alert_window`.
  - `employees.py`:
    - `_validate_employee_fields()` håndhæver påkrævede felter pr. type. Ved PATCH gælder det kun de felter, der sendes med.
    - `_apply_cpr_mask()` maskerer CPR uden `view_cpr`.
    - Endpoints: `GET /next-employee-number`, `GET /check-number`, `GET /positions`, `GET /milestone-alerts`, `POST /{id}/dismiss-milestone-alert`, `POST /export-xlsx`. Afvisninger af mærkedage genbruger `Paragraf56AlertDismissal` med `alert_type` = `alert_key`.
  - `stamdata.py`: `/api/stamdata/positions` CRUD.
  - Frontend:
    - `isElev()` og `empCellHighlight()`: elev er gul og vinder over afløser i Vagtplan og Aktivitetskalender.
    - `_filteredEmployees()` deles af liste, tabel og eksport.
    - `_continueSaveEmployee()` og `modal-emp-hidden-flags`: Behold/Fjern for Afløser, Fast bil og Særaftale ved skift til funktionær.
    - `checkMilestoneAlerts()` efter `checkParagraf56Alerts()`.
```

- [ ] **Step 3: build_docs.py**

Find medarbejder-afsnittene i `docs/build_docs.py` (`grep -n "Medarbejder\|Afløser" docs/build_docs.py`) og opdatér brugervejledningen og den tekniske dokumentation med de samme fakta, i samme stil som de eksisterende afsnit:
- nye felter og hvornår de er påkrævede
- Stamdata → Stillinger
- de tre nye advarsler og rettigheder
- tabelvisning og eksport
- elev-farve

Kør derefter:

Run: `python docs/build_docs.py`
Expected: `docs/Brugervejledning.docx` og `docs/Teknisk dokumentation.docx` genereres uden fejl.

- [ ] **Step 4: Spec-status**

I spec'en: erstat `**Status:** GODKENDT 2026-10-01 – ikke implementeret. …` med `**Status:** IMPLEMENTERET (se plan docs/superpowers/plans/2026-10-01-medarbejderregister.md).`

- [ ] **Step 5: Fuld testkørsel**

Run: `python -m pytest tests -q`
Expected: alle PASS

- [ ] **Step 6: Stop – brugeren committer**
