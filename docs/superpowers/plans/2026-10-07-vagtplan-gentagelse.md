# Gentagelse i Vagtplan – implementeringsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fravær og kommentarer i Vagtplan kan oprettes som en gentagelse (ugentligt på valgte ugedage eller månedligt på "N. ugedag"), med antal eller slutdato, som senere kan rettes eller slettes samlet fra en vilkårlig forekomst.

**Architecture:** En ren beregningsfunktion (`calculators/recurrence.py`) udregner forekomstdatoer. En ny tabel `vagtplan_series` gemmer reglen; hver forekomst er en almindelig `Activity`/`VagtplanComment` med `series_id`. En ny router (`routers/vagtplan_series.py`) opretter/forlænger/forkorter/sletter serier server-side i én transaktion og genbruger oprettelseslogikken fra `create_manual_activity` via en udtrukket hjælpefunktion. Frontend (`app.js`/`index.html`) får gentagelsesfelter i opret-modalen og en serie-sektion i aktivitetsdetaljen og kommentarboksen.

**Tech Stack:** Python 3.11 / FastAPI / SQLAlchemy / SQLite, Pydantic v2, pytest; Vanilla JS + Jinja2-HTML.

**Spec:** `docs/superpowers/specs/2026-10-07-vagtplan-gentagelse-design.md`

## Global Constraints

- **Claude må ALDRIG stage, committe eller pushe.** Brugeren håndterer git selv (push = deploy til produktion). Planens "commit"-trin er derfor erstattet af "Ingen commit".
- Alle brugervendte tekster på dansk.
- Forekomst = altid én dag. Ingen perioder pr. forekomst.
- Grænser: maks. 1 år fra seriens startdato (`one_year_after(start_date)`, inklusiv) og maks. 100 forekomster i alt.
- Helligdage (alle rækker i tabellen `holidays`) springes over for serier med fraværstype; serier der kun er kommentar oprettes også på helligdage.
- Antal = antal oprettede forekomstdage (helligdage erstattes af næste dag i mønstret).
- Månedligt = samme ugedag i måneden udledt af startdatoen; 5. forekomst → "sidste <ugedag>".
- Dage i en låst lønperiode: oprettelse og ændring af slut afvises helt (alt-eller-intet). "Slet hele serien" bevarer låste forekomster.
- Rettighed: `_has_vagtplan_edit_access(db, user, emp)` (fra `routers/activities.py`) for alle skrivende serie-endpoints.
- Kør tests fra projektroden: `python -m pytest tests/<fil> -q`.
- Ugedage indekseres 0 = mandag … 6 = søndag (Python `date.weekday()`).

## Filoversigt

| Fil | Ansvar |
|---|---|
| `app/calculators/recurrence.py` (ny) | Ren datoberegning + mønsterbeskrivelse. Ingen DB. |
| `app/database/models.py` | `VagtplanSeries`-model; `series_id` på `Activity` og `VagtplanComment`. |
| `app/database/session.py` | Migration: `series_id`-kolonner + indeks på eksisterende DB. |
| `app/database/schemas.py` | Serie-schemas; `series_id` på `ActivityResponse`/`VagtplanCommentResponse`. |
| `app/routers/activities.py` | Udtræk `_create_manual_activity_row()`; `series_id` i `_to_response`. |
| `app/routers/vagtplan_comments.py` | Intet funktionelt – `series_id` følger med via response-schemaet. |
| `app/routers/vagtplan_series.py` (ny) | Preview/opret/hent/ret slut/slet serie/slet forekomst. |
| `app/main.py` | Registrér routeren. |
| `app/templates/index.html` | Gentagelsesfelter i opret-modalen; serie-container i kommentarboksen. |
| `app/static/js/app.js` | Oprettelse via serie-API; serie-sektion i detalje/kommentar. |
| `tests/test_recurrence.py` (ny) | Tests af beregningen. |
| `tests/test_vagtplan_series.py` (ny) | Tests af model, router og rettigheder. |
| `CODEREF.md`, `docs/build_docs.py` | Dokumentation. |

---

### Task 1: Beregningsmodul `recurrence.py`

**Files:**
- Create: `app/calculators/recurrence.py`
- Test: `tests/test_recurrence.py`

**Interfaces:**
- Produces:
  - `MAX_OCCURRENCES: int = 100`
  - `one_year_after(d: date) -> date`
  - `occurrence_dates(freq: str, weekdays: list[int], start_date: date, end_mode: str, end_count: int | None, end_date: date | None, holidays: set[date], skip_holidays: bool, after: date | None = None, existing_count: int = 0) -> list[date]`
  - `describe(freq: str, weekdays: list[int], start_date: date) -> str`

- [ ] **Step 1: Skriv de fejlende tests**

```python
# tests/test_recurrence.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from datetime import date
from calculators.recurrence import occurrence_dates, describe, one_year_after, MAX_OCCURRENCES


def _weekly(weekdays, start, **kw):
    args = dict(end_mode="count", end_count=None, end_date=None, holidays=set(), skip_holidays=True)
    args.update(kw)
    return occurrence_dates("weekly", weekdays, start, **args)


def test_weekly_single_day_count():
    # Tirsdag 13-10-2026, hver tirsdag, 3 gange
    assert _weekly([1], date(2026, 10, 13), end_count=3) == [
        date(2026, 10, 13), date(2026, 10, 20), date(2026, 10, 27)]


def test_weekly_multiple_days_count_counts_days():
    # Mandag 12-10-2026, hver mandag og torsdag, 4 gange → man, tors, man, tors
    assert _weekly([0, 3], date(2026, 10, 12), end_count=4) == [
        date(2026, 10, 12), date(2026, 10, 15), date(2026, 10, 19), date(2026, 10, 22)]


def test_start_date_not_in_pattern_is_not_an_occurrence():
    # Startdato onsdag, mønster kun mandag
    assert _weekly([0], date(2026, 10, 14), end_count=2) == [date(2026, 10, 19), date(2026, 10, 26)]


def test_weekly_end_date_inclusive():
    assert _weekly([1], date(2026, 10, 13), end_mode="date", end_date=date(2026, 10, 27)) == [
        date(2026, 10, 13), date(2026, 10, 20), date(2026, 10, 27)]


def test_holiday_skipped_and_replaced_when_counting():
    hol = {date(2026, 10, 20)}
    assert _weekly([1], date(2026, 10, 13), end_count=3, holidays=hol) == [
        date(2026, 10, 13), date(2026, 10, 27), date(2026, 11, 3)]


def test_holiday_not_skipped_for_comment_only():
    hol = {date(2026, 10, 20)}
    assert _weekly([1], date(2026, 10, 13), end_count=2, holidays=hol, skip_holidays=False) == [
        date(2026, 10, 13), date(2026, 10, 20)]


def test_monthly_nth_weekday():
    # 13-10-2026 er 2. tirsdag i oktober
    got = occurrence_dates("monthly", [], date(2026, 10, 13), "count", 3, None, set(), True)
    assert got == [date(2026, 10, 13), date(2026, 11, 10), date(2026, 12, 8)]


def test_monthly_fifth_weekday_means_last():
    # 29-10-2026 er 5. torsdag i oktober → sidste torsdag hver måned
    got = occurrence_dates("monthly", [], date(2026, 10, 29), "count", 3, None, set(), True)
    assert got == [date(2026, 10, 29), date(2026, 11, 26), date(2026, 12, 31)]


def test_limit_one_year():
    got = _weekly([0], date(2026, 10, 12), end_mode="date", end_date=date(2028, 1, 1))
    assert got[-1] <= one_year_after(date(2026, 10, 12))
    assert got[-1] == date(2027, 10, 11)


def test_limit_100_occurrences():
    got = _weekly([0, 1, 2, 3, 4], date(2026, 10, 12), end_count=500)
    assert len(got) == MAX_OCCURRENCES


def test_after_and_existing_count_extend_from_end():
    # Serie med 3 eksisterende (sidste 27-10), forlæng til 5 i alt
    got = _weekly([1], date(2026, 10, 13), end_count=5, after=date(2026, 10, 27), existing_count=3)
    assert got == [date(2026, 11, 3), date(2026, 11, 10)]


def test_existing_count_respects_global_max():
    got = _weekly([1], date(2026, 10, 13), end_mode="date", end_date=date(2027, 10, 1),
                  after=date(2026, 10, 13), existing_count=99)
    assert len(got) == 1


def test_one_year_after_leap_day():
    assert one_year_after(date(2028, 2, 29)) == date(2029, 2, 28)


def test_describe_weekly():
    assert describe("weekly", [0, 3], date(2026, 10, 12)) == "Hver mandag og torsdag"
    assert describe("weekly", [0, 2, 4], date(2026, 10, 12)) == "Hver mandag, onsdag og fredag"
    assert describe("weekly", [1], date(2026, 10, 13)) == "Hver tirsdag"


def test_describe_monthly():
    assert describe("monthly", [], date(2026, 10, 13)) == "Hver 2. tirsdag i måneden"
    assert describe("monthly", [], date(2026, 10, 29)) == "Sidste torsdag i måneden"
```

- [ ] **Step 2: Kør testene og se dem fejle**

Run: `python -m pytest tests/test_recurrence.py -q`
Expected: FAIL – `ModuleNotFoundError: No module named 'calculators.recurrence'`

- [ ] **Step 3: Implementér modulet**

```python
# app/calculators/recurrence.py
"""Datoberegning for gentagelser i Vagtplan (spec 2026-10-07-vagtplan-gentagelse).
Ren logik uden DB-afhængighed – kaldes af routers/vagtplan_series.py."""
from datetime import date, timedelta
from typing import Iterator, Optional

MAX_OCCURRENCES = 100

_WEEKDAY_NAMES = ["mandag", "tirsdag", "onsdag", "torsdag", "fredag", "lørdag", "søndag"]


def one_year_after(d: date) -> date:
    """Samme dato ét år senere (29/2 → 28/2). Seriens sidste tilladte dato (inklusiv)."""
    try:
        return d.replace(year=d.year + 1)
    except ValueError:
        return d.replace(year=d.year + 1, day=28)


def _nth_of_month(start_date: date) -> int:
    """1-4 = N. forekomst af ugedagen i måneden; 5 = sidste."""
    return (start_date.day - 1) // 7 + 1


def _monthly_date(year: int, month: int, weekday: int, nth: int) -> date:
    if nth >= 5:
        # Sidste <ugedag> i måneden
        next_month = date(year + (month == 12), month % 12 + 1, 1)
        d = next_month - timedelta(days=1)
        while d.weekday() != weekday:
            d -= timedelta(days=1)
        return d
    first = date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    return first + timedelta(days=offset + 7 * (nth - 1))


def _candidates(freq: str, weekdays: list[int], start_date: date) -> Iterator[date]:
    if freq == "weekly":
        wanted = set(weekdays)
        d = start_date
        while True:
            if d.weekday() in wanted:
                yield d
            d += timedelta(days=1)
    elif freq == "monthly":
        nth = _nth_of_month(start_date)
        weekday = start_date.weekday()
        year, month = start_date.year, start_date.month
        while True:
            d = _monthly_date(year, month, weekday, nth)
            if d >= start_date:
                yield d
            year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    else:
        raise ValueError(f"Ukendt frekvens: {freq}")


def occurrence_dates(freq: str, weekdays: list[int], start_date: date,
                     end_mode: str, end_count: Optional[int], end_date: Optional[date],
                     holidays: set[date], skip_holidays: bool,
                     after: Optional[date] = None, existing_count: int = 0) -> list[date]:
    """Forekomstdatoer i kronologisk rækkefølge.

    after: kun datoer EFTER denne dato (forlængelse fra seriens sidste forekomst).
    existing_count: antal forekomster der allerede findes – tæller med i end_count
    og i MAX_OCCURRENCES. Helligdage springes over (og erstattes) når skip_holidays."""
    limit_date = one_year_after(start_date)
    last_allowed = min(end_date, limit_date) if end_mode == "date" else limit_date
    total = MAX_OCCURRENCES if end_mode == "date" else min(end_count or 0, MAX_OCCURRENCES)
    remaining = total - existing_count
    result: list[date] = []
    if remaining <= 0:
        return result
    for d in _candidates(freq, weekdays, start_date):
        if d > last_allowed:
            break
        if after is not None and d <= after:
            continue
        if skip_holidays and d in holidays:
            continue
        result.append(d)
        if len(result) >= remaining:
            break
    return result


def _join_da(names: list[str]) -> str:
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " og " + names[-1]


def describe(freq: str, weekdays: list[int], start_date: date) -> str:
    """Brugervendt mønsterbeskrivelse, fx 'Hver mandag og torsdag' / 'Hver 2. tirsdag i måneden'."""
    if freq == "weekly":
        return "Hver " + _join_da([_WEEKDAY_NAMES[w] for w in sorted(set(weekdays))])
    nth = _nth_of_month(start_date)
    day = _WEEKDAY_NAMES[start_date.weekday()]
    return f"Sidste {day} i måneden" if nth >= 5 else f"Hver {nth}. {day} i måneden"
```

- [ ] **Step 4: Kør testene**

Run: `python -m pytest tests/test_recurrence.py -q`
Expected: `15 passed`

- [ ] **Step 5: Ingen commit** (brugeren committer selv).

---

### Task 2: Datamodel, migration og response-felter

**Files:**
- Modify: `app/database/models.py` (`Activity` ~linje 219, `VagtplanComment` ~linje 268, ny klasse efter `VagtplanComment`)
- Modify: `app/database/session.py` (`_migrate()` ~linje 178 og indeks-blokken ~linje 215)
- Modify: `app/database/schemas.py` (`ActivityResponse` linje 161, `VagtplanCommentResponse` linje 485)
- Modify: `app/routers/activities.py` (`_to_response`, linje ~335)
- Test: `tests/test_vagtplan_series.py`

**Interfaces:**
- Produces:
  - Model `VagtplanSeries` (tabel `vagtplan_series`) med felterne: `id, employee_id, activity_type, comment_text, vehicle_number, terminsdato, freq, weekdays (String "0,3"), start_date, end_mode, end_count, end_date, created_by, created_at` + property `weekday_list -> list[int]`.
  - `Activity.series_id`, `VagtplanComment.series_id` (Integer FK → `vagtplan_series.id`, nullable, indekseret).
  - `ActivityResponse.series_id: Optional[int] = None`, `VagtplanCommentResponse.series_id: Optional[int] = None`.

- [ ] **Step 1: Skriv den fejlende test**

```python
# tests/test_vagtplan_series.py
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from datetime import date, datetime

import pytest
from fastapi import HTTPException

from conftest import make_activity
from database.models import (
    Activity, ActivitySource, ActivityStatus, AppUser, Holiday, PayPeriodStatus, Role,
    VagtplanComment, VagtplanSeries,
)
from calculators.pay_period import get_or_create_period_for_date


def _admin(db, initials="TST"):
    if not db.query(Role).filter(Role.name == "admin").first():
        db.add(Role(name="admin", display_name="Administrator", is_system=True, permissions=[]))
        db.commit()
    return AppUser(name="Test", initials=initials, role="admin", password_hash="x")


def _lock(db, d: date):
    p = get_or_create_period_for_date(d, db)
    p.status = PayPeriodStatus.closed
    db.commit()


def test_series_model_and_series_id_on_activity_and_comment(db, employee):
    s = VagtplanSeries(employee_id=employee.id, activity_type="ferie", freq="weekly",
                       weekdays="1,3", start_date=date(2026, 10, 13), end_mode="count", end_count=2,
                       created_by="TST")
    db.add(s)
    db.commit()
    assert s.weekday_list == [1, 3]
    a = make_activity(db, employee, datetime(2026, 10, 13, 6), datetime(2026, 10, 13, 14),
                      activity_type="ferie", source=ActivitySource.vagtplan)
    a.series_id = s.id
    c = VagtplanComment(employee_id=employee.id, date=date(2026, 10, 13), text="x", series_id=s.id)
    db.add(c)
    db.commit()
    from routers.activities import _to_response
    from database.schemas import VagtplanCommentResponse
    assert _to_response(a).series_id == s.id
    assert VagtplanCommentResponse.model_validate(c).series_id == s.id
```

- [ ] **Step 2: Kør testen og se den fejle**

Run: `python -m pytest tests/test_vagtplan_series.py -q`
Expected: FAIL – `ImportError: cannot import name 'VagtplanSeries'`

- [ ] **Step 3: Tilføj model og kolonner i `models.py`**

I `class Activity` lige efter `absence_group_id = Column(String(36), nullable=True)`:

```python
    # Gentagelse i Vagtplan (2026-10-07): forekomstens serie, ellers null.
    series_id = Column(Integer, ForeignKey("vagtplan_series.id"), nullable=True)
```

og tilføj i `Activity.__table_args__` efter `Index("ix_activities_absence_group", "absence_group_id"),`:

```python
        Index("ix_activities_series", "series_id"),
```

I `class VagtplanComment` efter `created_at`:

```python
    series_id = Column(Integer, ForeignKey("vagtplan_series.id"), nullable=True, index=True)
```

Ny klasse lige efter `VagtplanComment`:

```python
class VagtplanSeries(Base):
    """Gentagelsesregel i Vagtplan (spec 2026-10-07). Forekomsterne er almindelige
    Activity-/VagtplanComment-rækker med series_id. Månedligt mønster ('N. ugedag i
    måneden') udledes af start_date og gemmes ikke separat."""
    __tablename__ = "vagtplan_series"

    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    activity_type = Column(String(50), nullable=True)      # null = kun kommentar
    comment_text = Column(String(1000), nullable=True)     # null = ingen kommentar
    vehicle_number = Column(String(50), nullable=True)
    terminsdato = Column(Date, nullable=True)
    freq = Column(String(10), nullable=False)              # weekly / monthly
    weekdays = Column(String(20), nullable=True)           # "0,3" (0 = mandag), kun weekly
    start_date = Column(Date, nullable=False)
    end_mode = Column(String(10), nullable=False)          # count / date
    end_count = Column(Integer, nullable=True)
    end_date = Column(Date, nullable=True)
    created_by = Column(String(10), nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    employee = relationship("Employee")

    @property
    def weekday_list(self) -> list[int]:
        return [int(x) for x in self.weekdays.split(",") if x != ""] if self.weekdays else []
```

- [ ] **Step 4: Migration i `session.py`**

I `_migrate()` efter blokken `if "absence_group_id" not in act_cols2: ...`:

```python
        if "series_id" not in act_cols2:
            conn.execute("ALTER TABLE activities ADD COLUMN series_id INTEGER REFERENCES vagtplan_series(id)")
            conn.commit()
        vc_cols = {row[1] for row in conn.execute("PRAGMA table_info(vagtplan_comments)")}
        if vc_cols and "series_id" not in vc_cols:
            conn.execute("ALTER TABLE vagtplan_comments ADD COLUMN series_id INTEGER REFERENCES vagtplan_series(id)")
            conn.commit()
        conn.execute("CREATE INDEX IF NOT EXISTS ix_vagtplan_comments_series_id ON vagtplan_comments(series_id)")
        conn.commit()
```

og efter blokken `if "ix_activities_absence_group" not in existing_indexes: ...`:

```python
        if "ix_activities_series" not in existing_indexes:
            conn.execute("CREATE INDEX ix_activities_series ON activities(series_id)")
            conn.commit()
```

Tabellen `vagtplan_series` oprettes af `Base.metadata.create_all()` i `init_db()` (kører før `_migrate()` – verificér rækkefølgen i `init_db()` linje 60-62; den skal være `create_all` → `_migrate`).

- [ ] **Step 5: Response-felter**

`schemas.py` – i `ActivityResponse` efter `absence_group_id`-feltet:

```python
    series_id: Optional[int] = None
```

i `VagtplanCommentResponse` efter `created_by`:

```python
    series_id: Optional[int] = None
```

`activities.py` – i `_to_response()` efter `absence_group_id=a.absence_group_id,`:

```python
        series_id=a.series_id,
```

- [ ] **Step 6: Kør testene**

Run: `python -m pytest tests/test_vagtplan_series.py tests/test_vagtplan.py tests/test_absence_group_model.py -q`
Expected: alle PASS.

- [ ] **Step 7: Ingen commit.**

---

### Task 3: Udtræk oprettelseslogik fra `create_manual_activity`

**Files:**
- Modify: `app/routers/activities.py` (`create_manual_activity`, linje ~595-675)
- Test: eksisterende tests + `tests/test_vagtplan_series.py`

**Interfaces:**
- Produces: `_create_manual_activity_row(db: Session, current_user: AppUser, emp: Employee, body: ActivityCreate, source: ActivitySource, series_id: Optional[int] = None) -> Activity` – validerer type, omklassificerer (sygdom ≤8 uger, barn_1sygedag, barsel), sætter vogn for normal, afviser låst dato, opretter + `flush()` + godkender fravær/auto-godkendelse. Hverken rettighedstjek, `log_action` eller `commit`.

- [ ] **Step 1: Skriv testen**

Tilføj i `tests/test_vagtplan_series.py`:

```python
def test_create_manual_activity_row_reclassifies_and_sets_series(db, employee):
    from routers.activities import _create_manual_activity_row
    from database.schemas import ActivityCreate
    employee.hire_date = date(2026, 10, 1)  # ansat < 8 uger
    db.commit()
    body = ActivityCreate(employee_id=employee.id, activity_type="sygdom",
                          start_time=datetime(2026, 10, 13, 6), end_time=datetime(2026, 10, 13, 14),
                          source="vagtplan")
    a = _create_manual_activity_row(db, _admin(db), employee, body, ActivitySource.vagtplan, series_id=None)
    db.commit()
    assert a.activity_type == "sygdom_u_8uger"
    assert a.status == ActivityStatus.approved
    assert a.source == ActivitySource.vagtplan
```

- [ ] **Step 2: Kør testen og se den fejle**

Run: `python -m pytest tests/test_vagtplan_series.py::test_create_manual_activity_row_reclassifies_and_sets_series -q`
Expected: FAIL – `ImportError: cannot import name '_create_manual_activity_row'`

- [ ] **Step 3: Refaktorér**

Erstat hele `create_manual_activity` med (adfærden er uændret – kun opdelt):

```python
def _create_manual_activity_row(db: Session, current_user: AppUser, emp: Employee,
                                body: ActivityCreate, source: ActivitySource,
                                series_id: Optional[int] = None) -> Activity:
    """Fælles oprettelse af en manuel aktivitet (enkeltdag via POST /api/activities og
    forekomster i Vagtplan-serier). Rettighedstjek, log_action og commit ligger hos
    kalderen."""
    activity_type = body.activity_type

    if activity_type in _BACKEND_ONLY_TYPES:
        raise HTTPException(400, "Denne aktivitetstype tildeles automatisk og kan ikke angives manuelt")

    # Sygdom: 8 uger eller under → uden løn
    if activity_type == "sygdom":
        employed_days = (body.start_time.date() - emp.hire_date).days
        if employed_days <= _EIGHT_WEEKS:
            activity_type = "sygdom_u_8uger"

    # Barn 1.sygedag: under 9 måneder → dagpengesats
    if activity_type == "barn_1sygedag":
        if _months_between(emp.hire_date, body.start_time.date()) < _NINE_MONTHS:
            activity_type = "barn_1sygedag_u_8uger"

    # Anciennitetskontrol for barsel: terminsdato skal være min. 9 måneder efter ansættelse
    if activity_type == "barsel":
        if body.terminsdato is None:
            raise HTTPException(400, "Terminsdato er påkrævet for barsel")
        if _months_between(emp.hire_date, body.terminsdato) < _NINE_MONTHS:
            activity_type = "barsel_u_loen"
        # Husk seneste terminsdato på medarbejderen, så den foreslås ved næste barsel-oprettelse
        emp.terminsdato = body.terminsdato

    vehicle_number = body.vehicle_number
    if activity_type == "normal" and not vehicle_number:
        vehicle = effective_vehicle_for_employee(db, body.employee_id, body.start_time.date())
        if vehicle:
            vehicle_number = vehicle.vehicle_number

    period = _forbid_date_in_closed_period(body.start_time.date(), db)
    is_absence = activity_type != "normal"
    can_auto_approve = user_has_permission(db, current_user, "auto_approve_manual_activities")
    activity = Activity(
        employee_id=body.employee_id,
        pay_period_id=period.id,
        source=source,
        created_by=current_user.initials,
        activity_type=activity_type,
        start_time=body.start_time,
        end_time=body.end_time,
        loading_minutes=body.loading_minutes,
        unloading_minutes=body.unloading_minutes,
        comment=body.comment,
        vehicle_number=vehicle_number,
        km_start=body.km_start,
        km_end=body.km_end,
        salt_supplement=body.salt_supplement,
        pause_intervals=body.pause_intervals,
        status=ActivityStatus.pending,
        absence_group_id=body.absence_group_id,
        series_id=series_id,
    )
    db.add(activity)
    db.flush()

    if is_absence or can_auto_approve:
        activity.status = ActivityStatus.approved
        activity.approved_by = current_user.initials
        activity.approved_at = datetime.utcnow()

        if can_auto_approve and not activity.comment:
            dur = _duration_minutes(activity)
            if dur < FOUR_HOURS and not _day_reaches_4h_with_approved(activity, dur):
                activity.comment = current_user.initials
    return activity


@router.post("", response_model=ActivityResponse, status_code=201)
def create_manual_activity(body: ActivityCreate,
                            current_user: AppUser = Depends(get_current_user),
                            db: Session = Depends(get_db)):
    emp = db.query(Employee).filter(Employee.id == body.employee_id).first()
    if not emp:
        raise HTTPException(404, "Medarbejder ikke fundet")

    activity_source = ActivitySource.manual
    if body.source == "vagtplan":
        if not _has_vagtplan_edit_access(db, current_user, emp):
            raise HTTPException(403, "Ingen redigeringsret til Vagtplan for denne medarbejder")
        activity_source = ActivitySource.vagtplan
    elif not _has_activity_permission(db, current_user, "edit_activities"):
        raise HTTPException(403, "Ingen adgang – kræver rettigheden 'Redigér aktiviteter'")

    activity = _create_manual_activity_row(db, current_user, emp, body, activity_source)
    log_action(db, current_user, "create_activity", "activity", activity.id,
               f"Manuelt oprettet for {emp.name}")
    db.commit()
    db.refresh(activity)
    return _to_response(activity)
```

Bevar alle eksisterende kommentarer fra den oprindelige funktion (de er kopieret ovenfor). Funktionen `_create_manual_activity_row` placeres lige over `@router.post("")`-dekoratoren.

- [ ] **Step 4: Kør hele testsuiten** (refaktoreringen må intet ændre)

Run: `python -m pytest tests -q`
Expected: alle PASS (samme antal som før + den nye test).

- [ ] **Step 5: Ingen commit.**

---

### Task 4: Serie-router – schemas, preview og oprettelse

**Files:**
- Modify: `app/database/schemas.py` (tilføj efter `VagtplanCommentResponse`)
- Create: `app/routers/vagtplan_series.py`
- Modify: `app/main.py` (import + `app.include_router(vagtplan_series.router)` efter `vagtplan_comments`)
- Test: `tests/test_vagtplan_series.py`

**Interfaces:**
- Consumes: `occurrence_dates`, `describe`, `one_year_after` (Task 1); `VagtplanSeries`, `series_id` (Task 2); `_create_manual_activity_row`, `_has_vagtplan_edit_access`, `_range_day_defaults`, `_COUNT_BASED_RANGE_TYPES`, `_HIDDEN_FROM_TYPE_PICKER` fra `routers.activities` (Task 3).
- Produces:
  - Schemas: `VagtplanSeriesCreate`, `VagtplanSeriesPreview`, `VagtplanSeriesResponse`, `VagtplanSeriesCreateResult`, `VagtplanSeriesEndUpdate`, `VagtplanSeriesUpdateResult`, `VagtplanSeriesDeleteResult`.
  - Router-funktioner: `preview_series(body, current_user, db) -> VagtplanSeriesPreview`, `create_series(body, current_user, db) -> VagtplanSeriesCreateResult`.
  - Hjælpere (bruges i Task 5-6): `_holidays(db) -> set[date]`, `_occurrence_dates_of(db, series) -> list[date]`, `_series_response(db, series) -> VagtplanSeriesResponse`, `_materialize(db, user, emp, series, dates) -> tuple[int, list[date], list[date]]` (created, skipped_comments, skipped_no_hours), `_is_locked(db, d) -> bool`, `_load_series_with_access(db, user, series_id) -> tuple[VagtplanSeries, Employee]`.

- [ ] **Step 1: Skriv de fejlende tests**

Tilføj i `tests/test_vagtplan_series.py`:

```python
from database.schemas import VagtplanSeriesCreate


def _ferie_weekly(employee, **kw):
    data = dict(employee_id=employee.id, activity_type="ferie", comment_text=None,
                vehicle_number="1234", freq="weekly", weekdays=[1],
                start_date=date(2026, 10, 13), end_mode="count", end_count=3)
    data.update(kw)
    return VagtplanSeriesCreate(**data)


def test_create_weekly_ferie_series_creates_activities(db, employee):
    from routers.vagtplan_series import create_series
    res = create_series(_ferie_weekly(employee), current_user=_admin(db), db=db)
    acts = db.query(Activity).filter(Activity.series_id == res.series.id).order_by(Activity.start_time).all()
    assert [a.start_time for a in acts] == [datetime(2026, 10, 13, 6), datetime(2026, 10, 20, 6), datetime(2026, 10, 27, 6)]
    assert all(a.end_time.hour == 14 for a in acts)  # 8 t fra arbejdsplanen
    assert all(a.source == ActivitySource.vagtplan for a in acts)
    assert res.created == 3
    assert res.series.description == "Hver tirsdag"
    assert res.series.occurrence_count == 3


def test_create_skips_holiday_for_absence(db, employee):
    from routers.vagtplan_series import create_series
    db.add(Holiday(date=date(2026, 10, 20), name="Testhelligdag"))
    db.commit()
    res = create_series(_ferie_weekly(employee), current_user=_admin(db), db=db)
    dates = [a.start_time.date() for a in db.query(Activity).filter(Activity.series_id == res.series.id)]
    assert sorted(dates) == [date(2026, 10, 13), date(2026, 10, 27), date(2026, 11, 3)]


def test_comment_only_series_ignores_holidays_and_skips_existing_comment(db, employee):
    from routers.vagtplan_series import create_series
    db.add(Holiday(date=date(2026, 10, 20), name="Testhelligdag"))
    db.add(VagtplanComment(employee_id=employee.id, date=date(2026, 10, 27), text="findes"))
    db.commit()
    body = _ferie_weekly(employee, activity_type=None, comment_text="Ringer kl. 10", vehicle_number=None)
    res = create_series(body, current_user=_admin(db), db=db)
    rows = db.query(VagtplanComment).filter(VagtplanComment.series_id == res.series.id).all()
    assert sorted(c.date for c in rows) == [date(2026, 10, 13), date(2026, 10, 20)]
    assert res.skipped_comments == [date(2026, 10, 27)]
    existing = db.query(VagtplanComment).filter(VagtplanComment.date == date(2026, 10, 27)).one()
    assert existing.text == "findes"


def test_absence_plus_comment_creates_both(db, employee):
    from routers.vagtplan_series import create_series
    res = create_series(_ferie_weekly(employee, comment_text="Ferie", end_count=2),
                        current_user=_admin(db), db=db)
    assert db.query(Activity).filter(Activity.series_id == res.series.id).count() == 2
    assert db.query(VagtplanComment).filter(VagtplanComment.series_id == res.series.id).count() == 2


def test_create_rejected_when_any_date_locked(db, employee):
    from routers.vagtplan_series import create_series
    _lock(db, date(2026, 10, 27))
    with pytest.raises(HTTPException) as e:
        create_series(_ferie_weekly(employee), current_user=_admin(db), db=db)
    assert e.value.status_code == 400
    assert "27-10-2026" in e.value.detail
    assert db.query(Activity).count() == 0
    assert db.query(VagtplanSeries).count() == 0


def test_preview_reports_conflicts(db, employee):
    from routers.vagtplan_series import preview_series
    make_activity(db, employee, datetime(2026, 10, 20, 6), datetime(2026, 10, 20, 15))  # kørsel
    db.add(VagtplanComment(employee_id=employee.id, date=date(2026, 10, 27), text="findes"))
    db.commit()
    _lock(db, date(2026, 10, 13))
    p = preview_series(_ferie_weekly(employee, comment_text="x"), current_user=_admin(db), db=db)
    assert p.dates == [date(2026, 10, 13), date(2026, 10, 20), date(2026, 10, 27)]
    assert p.locked_dates == [date(2026, 10, 13)]
    assert p.driving_conflicts == [date(2026, 10, 20)]
    assert p.comment_conflicts == [date(2026, 10, 27)]
    assert p.description == "Hver tirsdag"


def test_preview_reports_no_hours_for_afspadsering(db, employee):
    from routers.vagtplan_series import preview_series
    p = preview_series(_ferie_weekly(employee, activity_type="afspadsering", weekdays=[5], start_date=date(2026, 10, 17), end_count=2),
                       current_user=_admin(db), db=db)
    assert p.skipped_no_hours == [date(2026, 10, 17), date(2026, 10, 24)]


def test_series_schema_validation():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        VagtplanSeriesCreate(employee_id=1, activity_type=None, comment_text=None, freq="weekly",
                             weekdays=[1], start_date=date(2026, 10, 13), end_mode="count", end_count=2)
    with pytest.raises(ValidationError):
        VagtplanSeriesCreate(employee_id=1, activity_type="ferie", freq="weekly", weekdays=[],
                             start_date=date(2026, 10, 13), end_mode="count", end_count=2)
    with pytest.raises(ValidationError):
        VagtplanSeriesCreate(employee_id=1, activity_type="ferie", freq="weekly", weekdays=[1],
                             start_date=date(2026, 10, 13), end_mode="count", end_count=101)
    with pytest.raises(ValidationError):
        VagtplanSeriesCreate(employee_id=1, activity_type="ferie", freq="weekly", weekdays=[1],
                             start_date=date(2026, 10, 13), end_mode="date", end_date=date(2026, 10, 1))


def test_create_rejects_normal_type(db, employee):
    from routers.vagtplan_series import create_series
    with pytest.raises(HTTPException) as e:
        create_series(_ferie_weekly(employee, activity_type="normal"), current_user=_admin(db), db=db)
    assert e.value.status_code == 400


def test_create_requires_vagtplan_edit_access(db, employee):
    from routers.vagtplan_series import create_series
    db.add(Role(name="kontor", display_name="Kontor", is_system=False, permissions=["vagtplan_view", "vagtplan_edit_own"]))
    db.commit()
    other = AppUser(name="Anden", initials="XYZ", role="kontor", password_hash="x")
    with pytest.raises(HTTPException) as e:
        create_series(_ferie_weekly(employee), current_user=other, db=db)
    assert e.value.status_code == 403
    employee.initials = "XYZ"
    db.commit()
    res = create_series(_ferie_weekly(employee), current_user=other, db=db)
    assert res.created == 3
```

- [ ] **Step 2: Kør testene og se dem fejle**

Run: `python -m pytest tests/test_vagtplan_series.py -q`
Expected: FAIL – `ImportError: cannot import name 'VagtplanSeriesCreate'`

- [ ] **Step 3: Schemas** – tilføj i `schemas.py` efter `VagtplanCommentResponse` (`Literal` importeres fra `typing` hvis ikke allerede):

```python
class VagtplanSeriesCreate(BaseModel):
    employee_id: int
    activity_type: Optional[str] = None          # null = kun kommentar
    comment_text: Optional[str] = Field(default=None, max_length=1000)
    vehicle_number: Optional[str] = Field(default=None, max_length=50)
    terminsdato: Optional[date] = None
    freq: Literal["weekly", "monthly"]
    weekdays: list[int] = Field(default_factory=list)
    start_date: date
    end_mode: Literal["count", "date"]
    end_count: Optional[int] = Field(default=None, ge=1, le=100)
    end_date: Optional[date] = None

    @model_validator(mode="after")
    def _validate(self):
        if self.comment_text is not None and not self.comment_text.strip():
            self.comment_text = None
        if not self.activity_type and not self.comment_text:
            raise ValueError("Vælg en fraværstype eller skriv en kommentar")
        if self.freq == "weekly":
            if not self.weekdays:
                raise ValueError("Vælg mindst én ugedag")
            if any(w < 0 or w > 6 for w in self.weekdays):
                raise ValueError("Ugyldig ugedag")
        if self.end_mode == "count" and self.end_count is None:
            raise ValueError("Angiv antal gentagelser")
        if self.end_mode == "date":
            if self.end_date is None:
                raise ValueError("Angiv slutdato")
            if self.end_date < self.start_date:
                raise ValueError("Slutdato skal være på eller efter startdatoen")
        return self


class VagtplanSeriesPreview(BaseModel):
    dates: list[date]
    locked_dates: list[date]
    comment_conflicts: list[date]
    driving_conflicts: list[date]
    skipped_no_hours: list[date]
    description: str


class VagtplanSeriesResponse(BaseModel):
    id: int
    employee_id: int
    activity_type: Optional[str] = None
    comment_text: Optional[str] = None
    freq: str
    weekdays: list[int]
    start_date: date
    end_mode: str
    end_count: Optional[int] = None
    end_date: Optional[date] = None
    description: str
    occurrence_count: int
    first_date: Optional[date] = None
    last_date: Optional[date] = None


class VagtplanSeriesCreateResult(BaseModel):
    series: VagtplanSeriesResponse
    created: int
    skipped_comments: list[date]
    skipped_no_hours: list[date]


class VagtplanSeriesEndUpdate(BaseModel):
    end_mode: Literal["count", "date"]
    end_count: Optional[int] = Field(default=None, ge=1, le=100)
    end_date: Optional[date] = None

    @model_validator(mode="after")
    def _validate(self):
        if self.end_mode == "count" and self.end_count is None:
            raise ValueError("Angiv antal gentagelser")
        if self.end_mode == "date" and self.end_date is None:
            raise ValueError("Angiv slutdato")
        return self


class VagtplanSeriesUpdateResult(BaseModel):
    series: VagtplanSeriesResponse
    added: int
    removed: int
    skipped_comments: list[date]
    skipped_no_hours: list[date]


class VagtplanSeriesDeleteResult(BaseModel):
    deleted: int
    kept_locked: int
    kept_split: int
```

- [ ] **Step 4: Router** – opret `app/routers/vagtplan_series.py`:

```python
"""Gentagelse i Vagtplan (spec 2026-10-07-vagtplan-gentagelse). Serier oprettes,
forlænges/forkortes (kun i enden) og slettes samlet server-side. Hver forekomst er en
almindelig Activity (source=vagtplan) og/eller VagtplanComment med series_id."""
from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from auth import get_current_user, log_action, require_any_permission
from calculators.pay_period import get_or_create_period_for_date
from calculators.recurrence import describe, occurrence_dates, one_year_after
from database.models import (
    Activity, ActivitySource, ActivityStatus, AppUser, Employee, Holiday, PayPeriodStatus,
    VagtplanComment, VagtplanSeries,
)
from database.schemas import (
    ActivityCreate, VagtplanSeriesCreate, VagtplanSeriesCreateResult, VagtplanSeriesDeleteResult,
    VagtplanSeriesEndUpdate, VagtplanSeriesPreview, VagtplanSeriesResponse, VagtplanSeriesUpdateResult,
)
from database.session import get_db
from routers.activities import (
    _BACKEND_ONLY_TYPES, _COUNT_BASED_RANGE_TYPES, _HIDDEN_FROM_TYPE_PICKER,
    _create_manual_activity_row, _has_vagtplan_edit_access, _range_day_defaults,
)

router = APIRouter(prefix="/api/vagtplan-series", tags=["vagtplan-series"])

_view_access = require_any_permission("view_calendar", "vagtplan_view")


def _fmt(d: date) -> str:
    return d.strftime("%d-%m-%Y")


def _holidays(db: Session) -> set[date]:
    return {h.date for h in db.query(Holiday).all()}


def _is_locked(db: Session, d: date) -> bool:
    # Opretter også perioden hvis den mangler (get_or_create committer) – derfor
    # kaldes dette for ALLE datoer FØR noget oprettes, så senere opslag ikke committer
    # en halvt oprettet serie.
    return get_or_create_period_for_date(d, db).status == PayPeriodStatus.closed


def _employee_with_access(db: Session, user: AppUser, employee_id: int) -> Employee:
    emp = db.query(Employee).filter(Employee.id == employee_id).first()
    if not emp:
        raise HTTPException(404, "Medarbejder ikke fundet")
    if not _has_vagtplan_edit_access(db, user, emp):
        raise HTTPException(403, "Ingen redigeringsret til Vagtplan for denne medarbejder")
    return emp


def _load_series_with_access(db: Session, user: AppUser, series_id: int) -> tuple[VagtplanSeries, Employee]:
    series = db.query(VagtplanSeries).filter(VagtplanSeries.id == series_id).first()
    if not series:
        raise HTTPException(404, "Gentagelse ikke fundet")
    return series, _employee_with_access(db, user, series.employee_id)


def _validate_type(activity_type):
    if activity_type is None:
        return
    if activity_type == "normal":
        raise HTTPException(400, "Normal tid kan ikke gentages fra Vagtplan")
    if activity_type in _BACKEND_ONLY_TYPES or activity_type in _HIDDEN_FROM_TYPE_PICKER:
        raise HTTPException(400, "Denne aktivitetstype kan ikke angives manuelt")


def _occurrence_dates_of(db: Session, series: VagtplanSeries) -> list[date]:
    """Datoer der i dag har en forekomst (aktivitet og/eller kommentar) i serien."""
    act_dates = {a.start_time.date() for a in db.query(Activity).filter(Activity.series_id == series.id)}
    com_dates = {c.date for c in db.query(VagtplanComment).filter(VagtplanComment.series_id == series.id)}
    return sorted(act_dates | com_dates)


def _series_response(db: Session, series: VagtplanSeries) -> VagtplanSeriesResponse:
    dates = _occurrence_dates_of(db, series)
    return VagtplanSeriesResponse(
        id=series.id, employee_id=series.employee_id, activity_type=series.activity_type,
        comment_text=series.comment_text, freq=series.freq, weekdays=series.weekday_list,
        start_date=series.start_date, end_mode=series.end_mode, end_count=series.end_count,
        end_date=series.end_date, description=describe(series.freq, series.weekday_list, series.start_date),
        occurrence_count=len(dates), first_date=dates[0] if dates else None,
        last_date=dates[-1] if dates else None,
    )


def _day_hours(activity_type: str, d: date, emp: Employee):
    """(start, slut) for fraværsforekomsten eller None hvis dagen springes over (ingen
    garanterede timer). Samme regler som oprettelse af en fraværsperiode."""
    if activity_type in _COUNT_BASED_RANGE_TYPES:
        start = datetime.combine(d, time(0, 0))
        return start, start
    hours = _range_day_defaults(activity_type, d, emp)
    if hours is None:
        return None
    start = datetime.combine(d, time(6, 0))
    return start, start + timedelta(minutes=round(hours * 60))


def _materialize(db: Session, user: AppUser, emp: Employee, series: VagtplanSeries,
                 dates: list[date]) -> tuple[int, list[date], list[date]]:
    """Opretter forekomster på datoerne. Returnerer (antal dage med noget oprettet,
    kommentar-konflikter, dage uden garanterede timer). Hverken log eller commit."""
    created, skipped_comments, skipped_no_hours = 0, [], []
    for d in dates:
        made = False
        if series.activity_type:
            times = _day_hours(series.activity_type, d, emp)
            if times is None:
                skipped_no_hours.append(d)
                continue
            body = ActivityCreate(
                employee_id=emp.id, activity_type=series.activity_type,
                start_time=times[0], end_time=times[1], terminsdato=series.terminsdato,
                vehicle_number=series.vehicle_number, source="vagtplan",
            )
            _create_manual_activity_row(db, user, emp, body, ActivitySource.vagtplan, series_id=series.id)
            made = True
        if series.comment_text:
            exists = db.query(VagtplanComment).filter(
                VagtplanComment.employee_id == emp.id, VagtplanComment.date == d).first()
            if exists:
                skipped_comments.append(d)
            else:
                db.add(VagtplanComment(employee_id=emp.id, date=d, text=series.comment_text,
                                       created_by=user.initials, series_id=series.id))
                made = True
        created += int(made)
    return created, skipped_comments, skipped_no_hours


def _plan(db: Session, body: VagtplanSeriesCreate, emp: Employee) -> VagtplanSeriesPreview:
    _validate_type(body.activity_type)
    if body.end_mode == "date" and body.end_date > one_year_after(body.start_date):
        raise HTTPException(400, f"Slutdato må højst være {_fmt(one_year_after(body.start_date))} (1 år frem)")
    dates = occurrence_dates(body.freq, body.weekdays, body.start_date, body.end_mode,
                             body.end_count, body.end_date, _holidays(db),
                             skip_holidays=bool(body.activity_type))
    if not dates:
        raise HTTPException(400, "Ingen forekomster i den valgte periode")
    locked = [d for d in dates if _is_locked(db, d)]
    comment_conflicts = []
    if body.comment_text:
        existing = {c.date for c in db.query(VagtplanComment).filter(
            VagtplanComment.employee_id == emp.id,
            VagtplanComment.date >= dates[0], VagtplanComment.date <= dates[-1])}
        comment_conflicts = [d for d in dates if d in existing]
    driving, no_hours = [], []
    if body.activity_type:
        normal_dates = {a.start_time.date() for a in db.query(Activity).filter(
            Activity.employee_id == emp.id, Activity.activity_type == "normal",
            Activity.status != ActivityStatus.deactivated,
            Activity.start_time >= datetime.combine(dates[0], time(0, 0)),
            Activity.start_time < datetime.combine(dates[-1] + timedelta(days=1), time(0, 0)))}
        driving = [d for d in dates if d in normal_dates]
        no_hours = [d for d in dates if _day_hours(body.activity_type, d, emp) is None]
    return VagtplanSeriesPreview(
        dates=dates, locked_dates=locked, comment_conflicts=comment_conflicts,
        driving_conflicts=driving, skipped_no_hours=no_hours,
        description=describe(body.freq, body.weekdays, body.start_date),
    )


@router.post("/preview", response_model=VagtplanSeriesPreview)
def preview_series(body: VagtplanSeriesCreate,
                   current_user: AppUser = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    emp = _employee_with_access(db, current_user, body.employee_id)
    return _plan(db, body, emp)


@router.post("", response_model=VagtplanSeriesCreateResult, status_code=201)
def create_series(body: VagtplanSeriesCreate,
                  current_user: AppUser = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    emp = _employee_with_access(db, current_user, body.employee_id)
    plan = _plan(db, body, emp)
    if plan.locked_dates:
        raise HTTPException(400, "Kan ikke oprette – lønperioden er låst for: "
                            + ", ".join(_fmt(d) for d in plan.locked_dates))
    if body.activity_type == "barsel" and body.terminsdato is None:
        raise HTTPException(400, "Terminsdato er påkrævet for barsel")
    series = VagtplanSeries(
        employee_id=emp.id, activity_type=body.activity_type, comment_text=body.comment_text,
        vehicle_number=body.vehicle_number, terminsdato=body.terminsdato, freq=body.freq,
        weekdays=",".join(str(w) for w in sorted(set(body.weekdays))) if body.freq == "weekly" else None,
        start_date=body.start_date, end_mode=body.end_mode,
        end_count=body.end_count if body.end_mode == "count" else None,
        end_date=body.end_date if body.end_mode == "date" else None,
        created_by=current_user.initials,
    )
    db.add(series)
    db.flush()
    created, skipped_comments, skipped_no_hours = _materialize(db, current_user, emp, series, plan.dates)
    if created == 0:
        db.rollback()
        raise HTTPException(400, "Ingen forekomster blev oprettet")
    log_action(db, current_user, "create_vagtplan_series", "vagtplan_series", series.id,
               f"{emp.name}: {plan.description}, {created} forekomster fra {_fmt(plan.dates[0])}")
    db.commit()
    db.refresh(series)
    return VagtplanSeriesCreateResult(series=_series_response(db, series), created=created,
                                      skipped_comments=skipped_comments, skipped_no_hours=skipped_no_hours)
```

Kontrollér at `require_any_permission` findes i `auth.py` (bruges allerede i `activities.py` linje 13). `ActivityStatus` bruges i `_plan`.

- [ ] **Step 5: Registrér routeren i `main.py`** – linje 15 bliver:

```python
from routers import import_ddd, employees, activities, payroll_router, vehicles, employee_supplements, vagtplan_comments, vagtplan_series, payroll_settlement_router
```

og efter `app.include_router(vagtplan_comments.router)` (linje 107):

```python
app.include_router(vagtplan_series.router)
```

- [ ] **Step 6: Kør testene**

Run: `python -m pytest tests/test_vagtplan_series.py -q`
Expected: alle PASS.

- [ ] **Step 7: Ingen commit.**

---

### Task 5: Hent serie og ret slutdato/antal (PATCH)

**Files:**
- Modify: `app/routers/vagtplan_series.py`
- Test: `tests/test_vagtplan_series.py`

**Interfaces:**
- Consumes: hjælperne fra Task 4.
- Produces: `get_series(series_id, current_user, db) -> VagtplanSeriesResponse`, `update_series_end(series_id, body: VagtplanSeriesEndUpdate, current_user, db) -> VagtplanSeriesUpdateResult`, samt hjælperne `_delete_occurrence_rows(db, series, d: date) -> None` og `_assert_removable(db, series, d: date) -> None` (bruges også i Task 6).

- [ ] **Step 1: Skriv de fejlende tests**

```python
from database.schemas import VagtplanSeriesEndUpdate


def _make_series(db, employee, **kw):
    from routers.vagtplan_series import create_series
    return create_series(_ferie_weekly(employee, **kw), current_user=_admin(db), db=db).series


def _series_dates(db, sid):
    return sorted(a.start_time.date() for a in db.query(Activity).filter(Activity.series_id == sid))


def test_get_series(db, employee):
    from routers.vagtplan_series import get_series
    s = _make_series(db, employee)
    r = get_series(s.id, current_user=_admin(db), db=db)
    assert r.occurrence_count == 3 and r.last_date == date(2026, 10, 27)


def test_extend_by_count_adds_after_last(db, employee):
    from routers.vagtplan_series import update_series_end
    s = _make_series(db, employee)
    r = update_series_end(s.id, VagtplanSeriesEndUpdate(end_mode="count", end_count=5),
                          current_user=_admin(db), db=db)
    assert r.added == 2 and r.removed == 0
    assert _series_dates(db, s.id)[-2:] == [date(2026, 11, 3), date(2026, 11, 10)]
    assert r.series.end_count == 5


def test_deleted_occurrence_is_not_recreated_on_extend(db, employee):
    from routers.vagtplan_series import update_series_end
    s = _make_series(db, employee)
    mid = db.query(Activity).filter(Activity.series_id == s.id,
                                    Activity.start_time == datetime(2026, 10, 20, 6)).one()
    db.delete(mid)
    db.commit()
    update_series_end(s.id, VagtplanSeriesEndUpdate(end_mode="count", end_count=4),
                      current_user=_admin(db), db=db)
    assert _series_dates(db, s.id) == [date(2026, 10, 13), date(2026, 10, 27), date(2026, 11, 3), date(2026, 11, 10)]


def test_shorten_by_date_deletes_approved_tail(db, employee):
    from routers.vagtplan_series import update_series_end
    s = _make_series(db, employee)
    r = update_series_end(s.id, VagtplanSeriesEndUpdate(end_mode="date", end_date=date(2026, 10, 20)),
                          current_user=_admin(db), db=db)
    assert r.removed == 1
    assert _series_dates(db, s.id) == [date(2026, 10, 13), date(2026, 10, 20)]
    assert r.series.end_mode == "date" and r.series.end_count is None


def test_shorten_by_count(db, employee):
    from routers.vagtplan_series import update_series_end
    s = _make_series(db, employee)
    update_series_end(s.id, VagtplanSeriesEndUpdate(end_mode="count", end_count=1),
                      current_user=_admin(db), db=db)
    assert _series_dates(db, s.id) == [date(2026, 10, 13)]


def test_change_rejected_when_removed_day_locked(db, employee):
    from routers.vagtplan_series import update_series_end
    s = _make_series(db, employee)
    _lock(db, date(2026, 10, 27))
    with pytest.raises(HTTPException) as e:
        update_series_end(s.id, VagtplanSeriesEndUpdate(end_mode="count", end_count=1),
                          current_user=_admin(db), db=db)
    # 20/10 og 27/10 ligger i samme lønperiode (19/10–1/11) → første blokerende dato nævnes
    assert "lønperioden er låst" in e.value.detail
    assert len(_series_dates(db, s.id)) == 3


def test_change_rejected_when_added_day_locked(db, employee):
    from routers.vagtplan_series import update_series_end
    s = _make_series(db, employee)
    _lock(db, date(2026, 11, 3))
    with pytest.raises(HTTPException):
        update_series_end(s.id, VagtplanSeriesEndUpdate(end_mode="count", end_count=4),
                          current_user=_admin(db), db=db)
    assert len(_series_dates(db, s.id)) == 3


def test_cannot_remove_all_occurrences(db, employee):
    from routers.vagtplan_series import update_series_end
    s = _make_series(db, employee)
    update_series_end(s.id, VagtplanSeriesEndUpdate(end_mode="date", end_date=date(2026, 10, 13)),
                      current_user=_admin(db), db=db)
    assert _series_dates(db, s.id) == [date(2026, 10, 13)]
    with pytest.raises(HTTPException) as e:
        update_series_end(s.id, VagtplanSeriesEndUpdate(end_mode="date", end_date=date(2026, 10, 12)),
                          current_user=_admin(db), db=db)
    assert "mindst én forekomst" in e.value.detail
```

- [ ] **Step 2: Kør testene og se dem fejle**

Run: `python -m pytest tests/test_vagtplan_series.py -q`
Expected: FAIL – `ImportError: cannot import name 'get_series'`

- [ ] **Step 3: Implementér** – tilføj i `vagtplan_series.py`:

```python
@router.get("/{series_id}", response_model=VagtplanSeriesResponse)
def get_series(series_id: int,
               current_user: AppUser = Depends(_view_access),
               db: Session = Depends(get_db)):
    series = db.query(VagtplanSeries).filter(VagtplanSeries.id == series_id).first()
    if not series:
        raise HTTPException(404, "Gentagelse ikke fundet")
    return _series_response(db, series)


def _delete_occurrence_rows(db: Session, series: VagtplanSeries, d: date) -> None:
    start = datetime.combine(d, time(0, 0))
    for a in db.query(Activity).filter(Activity.series_id == series.id,
                                       Activity.start_time >= start,
                                       Activity.start_time < start + timedelta(days=1)):
        db.delete(a)
    for c in db.query(VagtplanComment).filter(VagtplanComment.series_id == series.id,
                                              VagtplanComment.date == d):
        db.delete(c)


def _assert_removable(db: Session, series: VagtplanSeries, d: date) -> None:
    if _is_locked(db, d):
        raise HTTPException(400, f"Kan ikke fjerne {_fmt(d)} – lønperioden er låst")
    start = datetime.combine(d, time(0, 0))
    for a in db.query(Activity).filter(Activity.series_id == series.id,
                                       Activity.start_time >= start,
                                       Activity.start_time < start + timedelta(days=1)):
        if a.split_children:
            raise HTTPException(400, f"Kan ikke fjerne {_fmt(d)} – aktiviteten er splittet, fortryd splittet først")


@router.patch("/{series_id}", response_model=VagtplanSeriesUpdateResult)
def update_series_end(series_id: int, body: VagtplanSeriesEndUpdate,
                      current_user: AppUser = Depends(get_current_user),
                      db: Session = Depends(get_db)):
    """Ændrer seriens slutning – kun i enden: tilføjer efter sidste forekomst eller
    fjerner fra enden. Alt-eller-intet ved låste dage."""
    series, emp = _load_series_with_access(db, current_user, series_id)
    existing = _occurrence_dates_of(db, series)
    if not existing:
        raise HTTPException(400, "Serien har ingen forekomster")
    last = existing[-1]
    limit = one_year_after(series.start_date)

    if body.end_mode == "count":
        to_remove = existing[body.end_count:] if body.end_count < len(existing) else []
    else:
        if body.end_date > limit:
            raise HTTPException(400, f"Slutdato må højst være {_fmt(limit)} (1 år fra seriens start)")
        to_remove = [d for d in existing if d > body.end_date]
    if len(to_remove) == len(existing):
        raise HTTPException(400, "Serien skal have mindst én forekomst – brug 'Slet hele serien'")

    to_add: list[date] = []
    if not to_remove:
        to_add = occurrence_dates(series.freq, series.weekday_list, series.start_date, body.end_mode,
                                  body.end_count, body.end_date, _holidays(db),
                                  skip_holidays=bool(series.activity_type),
                                  after=last, existing_count=len(existing))

    # Validér ALT før noget ændres
    for d in to_remove:
        _assert_removable(db, series, d)
    locked_add = [d for d in to_add if _is_locked(db, d)]
    if locked_add:
        raise HTTPException(400, "Kan ikke forlænge – lønperioden er låst for: "
                            + ", ".join(_fmt(d) for d in locked_add))

    for d in to_remove:
        _delete_occurrence_rows(db, series, d)
    added, skipped_comments, skipped_no_hours = _materialize(db, current_user, emp, series, to_add)

    series.end_mode = body.end_mode
    series.end_count = body.end_count if body.end_mode == "count" else None
    series.end_date = body.end_date if body.end_mode == "date" else None
    log_action(db, current_user, "update_vagtplan_series", "vagtplan_series", series.id,
               f"{emp.name}: slutning ændret ({added} tilføjet, {len(to_remove)} fjernet)")
    db.commit()
    db.refresh(series)
    return VagtplanSeriesUpdateResult(series=_series_response(db, series), added=added,
                                      removed=len(to_remove), skipped_comments=skipped_comments,
                                      skipped_no_hours=skipped_no_hours)
```

- [ ] **Step 4: Kør testene**

Run: `python -m pytest tests/test_vagtplan_series.py -q`
Expected: alle PASS.

- [ ] **Step 5: Ingen commit.**

---

### Task 6: Slet hele serien og slet én forekomst

**Files:**
- Modify: `app/routers/vagtplan_series.py`
- Test: `tests/test_vagtplan_series.py`

**Interfaces:**
- Produces: `delete_series(series_id, current_user, db) -> VagtplanSeriesDeleteResult` (`DELETE /api/vagtplan-series/{id}`), `delete_occurrence(series_id, occurrence_date: date, current_user, db) -> None` (`DELETE /api/vagtplan-series/{id}/occurrences/{occurrence_date}`, 204). "Slet denne forekomst" sletter både aktivitet og kommentar for datoen i serien.

- [ ] **Step 1: Skriv de fejlende tests**

```python
def test_delete_series_keeps_locked(db, employee):
    from routers.vagtplan_series import delete_series
    s = _make_series(db, employee, comment_text="Ferie")
    _lock(db, date(2026, 10, 13))
    r = delete_series(s.id, current_user=_admin(db), db=db)
    assert r.deleted == 2 and r.kept_locked == 1 and r.kept_split == 0
    assert _series_dates(db, s.id) == [date(2026, 10, 13)]
    assert db.query(VagtplanComment).filter(VagtplanComment.series_id == s.id).count() == 1
    assert db.query(VagtplanSeries).filter(VagtplanSeries.id == s.id).count() == 1


def test_delete_series_removes_series_row_when_empty(db, employee):
    from routers.vagtplan_series import delete_series
    s = _make_series(db, employee)
    r = delete_series(s.id, current_user=_admin(db), db=db)
    assert r.deleted == 3
    assert db.query(VagtplanSeries).count() == 0
    assert db.query(Activity).count() == 0


def test_delete_occurrence_removes_activity_and_comment(db, employee):
    from routers.vagtplan_series import delete_occurrence
    s = _make_series(db, employee, comment_text="Ferie")
    delete_occurrence(s.id, date(2026, 10, 20), current_user=_admin(db), db=db)
    assert _series_dates(db, s.id) == [date(2026, 10, 13), date(2026, 10, 27)]
    assert sorted(c.date for c in db.query(VagtplanComment).filter(VagtplanComment.series_id == s.id)) == [
        date(2026, 10, 13), date(2026, 10, 27)]


def test_delete_occurrence_locked_rejected(db, employee):
    from routers.vagtplan_series import delete_occurrence
    s = _make_series(db, employee)
    _lock(db, date(2026, 10, 20))
    with pytest.raises(HTTPException) as e:
        delete_occurrence(s.id, date(2026, 10, 20), current_user=_admin(db), db=db)
    assert e.value.status_code == 400


def test_delete_series_requires_access(db, employee):
    from routers.vagtplan_series import delete_series
    s = _make_series(db, employee)
    db.add(Role(name="laeser", display_name="Læser", is_system=False, permissions=["vagtplan_view"]))
    db.commit()
    with pytest.raises(HTTPException) as e:
        delete_series(s.id, current_user=AppUser(name="L", initials="LLL", role="laeser", password_hash="x"), db=db)
    assert e.value.status_code == 403
```

- [ ] **Step 2: Kør testene og se dem fejle**

Run: `python -m pytest tests/test_vagtplan_series.py -q`
Expected: FAIL – `ImportError: cannot import name 'delete_series'`

- [ ] **Step 3: Implementér** – tilføj i `vagtplan_series.py`:

```python
@router.delete("/{series_id}", response_model=VagtplanSeriesDeleteResult)
def delete_series(series_id: int,
                  current_user: AppUser = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    """Sletter alle forekomster permanent, undtagen dem i låste lønperioder (og
    splittede aktiviteter). Serierækken slettes når intet er tilbage."""
    series, emp = _load_series_with_access(db, current_user, series_id)
    dates = _occurrence_dates_of(db, series)
    locked = {d for d in dates if _is_locked(db, d)}
    deleted, kept_split = 0, 0
    for d in dates:
        if d in locked:
            continue
        start = datetime.combine(d, time(0, 0))
        acts = db.query(Activity).filter(Activity.series_id == series.id,
                                         Activity.start_time >= start,
                                         Activity.start_time < start + timedelta(days=1)).all()
        if any(a.split_children for a in acts):
            kept_split += 1
            continue
        _delete_occurrence_rows(db, series, d)
        deleted += 1
    db.flush()
    if not _occurrence_dates_of(db, series):
        db.delete(series)
    log_action(db, current_user, "delete_vagtplan_series", "vagtplan_series", series_id,
               f"{emp.name}: {deleted} forekomster slettet, {len(locked)} bevaret (låst), {kept_split} bevaret (splittet)")
    db.commit()
    return VagtplanSeriesDeleteResult(deleted=deleted, kept_locked=len(locked), kept_split=kept_split)


@router.delete("/{series_id}/occurrences/{occurrence_date}", status_code=204)
def delete_occurrence(series_id: int, occurrence_date: date,
                      current_user: AppUser = Depends(get_current_user),
                      db: Session = Depends(get_db)):
    """'Slet denne forekomst': fjerner dagens aktivitet og kommentar i serien. Dagen
    genopstår ikke ved forlængelse (forlængelse sker kun efter sidste forekomst)."""
    series, emp = _load_series_with_access(db, current_user, series_id)
    if occurrence_date not in _occurrence_dates_of(db, series):
        raise HTTPException(404, "Forekomsten findes ikke i serien")
    _assert_removable(db, series, occurrence_date)
    _delete_occurrence_rows(db, series, occurrence_date)
    db.flush()
    if not _occurrence_dates_of(db, series):
        db.delete(series)
    log_action(db, current_user, "delete_vagtplan_series_occurrence", "vagtplan_series", series_id,
               f"{emp.name}: forekomst {_fmt(occurrence_date)} slettet")
    db.commit()
```

Bemærk rækkefølgen: `/{series_id}/occurrences/{occurrence_date}` og `/{series_id}` kolliderer ikke (forskelligt antal path-segmenter).

- [ ] **Step 4: Kør hele testsuiten**

Run: `python -m pytest tests -q`
Expected: alle PASS.

- [ ] **Step 5: Ingen commit.**

---

### Task 7: Frontend – gentagelsesfelter og oprettelse

**Files:**
- Modify: `app/templates/index.html` (efter `manual-til-dato-group`, ~linje 1067)
- Modify: `app/static/js/app.js` (`openManualActivityModal` ~linje 2775, `updateManualTypeVisibility` ~linje 2320, `confirmManualActivity` ~linje 2975)

**Interfaces:**
- Consumes: `POST /api/vagtplan-series/preview`, `POST /api/vagtplan-series` (Task 4).
- Produces (JS): `_isRepeatOn() -> boolean`, `_readRepeatRule() -> {freq, weekdays, end_mode, end_count, end_date} | null` (viser toast og returnerer null ved fejl), `_updateRepeatUi()`, `_createVagtplanSeries(empId, actType, startDate)`, `_monthlyLabel(dateIso) -> string`.

- [ ] **Step 1: HTML** – indsæt lige efter `</div>` der lukker `manual-til-dato-group`:

```html
      <div class="form-group" id="manual-repeat-group" style="display:none">
        <label style="display:flex;align-items:center;gap:8px;cursor:pointer;font-weight:500">
          <input type="checkbox" id="manual-repeat" style="width:16px;height:16px;cursor:pointer">
          Gentagelse
        </label>
        <div id="manual-repeat-fields" style="display:none;margin-top:8px;padding:10px;background:var(--bg);border-radius:var(--radius)">
          <div style="display:flex;gap:16px;margin-bottom:8px">
            <label style="display:flex;align-items:center;gap:6px;cursor:pointer"><input type="radio" name="manual-repeat-freq" value="weekly" checked> Ugentligt</label>
            <label style="display:flex;align-items:center;gap:6px;cursor:pointer"><input type="radio" name="manual-repeat-freq" value="monthly"> Månedligt</label>
          </div>
          <div id="manual-repeat-weekdays" style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:8px">
            <label><input type="checkbox" class="manual-repeat-wd" value="0"> Man</label>
            <label><input type="checkbox" class="manual-repeat-wd" value="1"> Tir</label>
            <label><input type="checkbox" class="manual-repeat-wd" value="2"> Ons</label>
            <label><input type="checkbox" class="manual-repeat-wd" value="3"> Tor</label>
            <label><input type="checkbox" class="manual-repeat-wd" value="4"> Fre</label>
            <label><input type="checkbox" class="manual-repeat-wd" value="5"> Lør</label>
            <label><input type="checkbox" class="manual-repeat-wd" value="6"> Søn</label>
          </div>
          <div id="manual-repeat-monthly-label" style="display:none;font-size:13px;margin-bottom:8px"></div>
          <div style="display:flex;flex-direction:column;gap:6px">
            <label style="display:flex;align-items:center;gap:6px">
              <input type="radio" name="manual-repeat-end" value="count" checked> Efter
              <input type="number" id="manual-repeat-count" min="1" max="100" value="4" style="width:70px"> gange
            </label>
            <label style="display:flex;align-items:center;gap:6px">
              <input type="radio" name="manual-repeat-end" value="date"> Den
              <input type="date" id="manual-repeat-end-date" style="width:170px">
            </label>
          </div>
        </div>
      </div>
```

- [ ] **Step 2: JS-hjælpere** – tilføj lige før `async function openManualActivityModal(`:

```js
// ── Gentagelse i Vagtplan (spec 2026-10-07) ─────────────────────────────────
const _WEEKDAY_NAMES_DA = ["mandag", "tirsdag", "onsdag", "torsdag", "fredag", "lørdag", "søndag"];

function _isRepeatOn() {
  return _manualActivityContext.vagtplan && document.getElementById("manual-repeat").checked;
}

// Spejler calculators/recurrence.py:describe() for månedligt mønster.
function _monthlyLabel(dateIso) {
  if (!dateIso) return "";
  const d = new Date(dateIso + "T12:00:00");
  const nth = Math.floor((d.getDate() - 1) / 7) + 1;
  const day = _WEEKDAY_NAMES_DA[(d.getDay() + 6) % 7];
  return nth >= 5 ? `Sidste ${day} i måneden` : `Hver ${nth}. ${day} i måneden`;
}

function _manualStartDateIso() {
  return document.getElementById("manual-start")?.querySelector(".dt-date")?.value || "";
}

function _updateRepeatUi() {
  const on = _isRepeatOn();
  document.getElementById("manual-repeat-fields").style.display = on ? "" : "none";
  const freq = document.querySelector('input[name="manual-repeat-freq"]:checked').value;
  document.getElementById("manual-repeat-weekdays").style.display = freq === "weekly" ? "flex" : "none";
  const lbl = document.getElementById("manual-repeat-monthly-label");
  lbl.style.display = freq === "monthly" ? "" : "none";
  lbl.textContent = _monthlyLabel(_manualStartDateIso());
  const startIso = _manualStartDateIso();
  const endDate = document.getElementById("manual-repeat-end-date");
  endDate.min = startIso;
  if (startIso) {
    const max = new Date(startIso + "T12:00:00");
    max.setFullYear(max.getFullYear() + 1);
    endDate.max = _isoOfDate(max);
  }
  updateManualTypeVisibility();
}

// Forvælg startdatoens ugedag (kun når ingen ugedag er valgt endnu).
function _preselectRepeatWeekday() {
  const iso = _manualStartDateIso();
  const boxes = [...document.querySelectorAll(".manual-repeat-wd")];
  if (!iso || boxes.some(b => b.checked)) return;
  const idx = (new Date(iso + "T12:00:00").getDay() + 6) % 7;
  boxes[idx].checked = true;
}

function _readRepeatRule() {
  const freq = document.querySelector('input[name="manual-repeat-freq"]:checked').value;
  const weekdays = [...document.querySelectorAll(".manual-repeat-wd:checked")].map(b => parseInt(b.value));
  if (freq === "weekly" && weekdays.length === 0) { toast("Vælg mindst én ugedag", "error"); return null; }
  const end_mode = document.querySelector('input[name="manual-repeat-end"]:checked').value;
  const rule = { freq, weekdays: freq === "weekly" ? weekdays : [], end_mode, end_count: null, end_date: null };
  if (end_mode === "count") {
    const n = parseInt(document.getElementById("manual-repeat-count").value);
    if (!(n >= 1 && n <= 100)) { toast("Antal gentagelser skal være 1–100", "error"); return null; }
    rule.end_count = n;
  } else {
    const d = document.getElementById("manual-repeat-end-date").value;
    if (!d) { toast("Angiv slutdato for gentagelsen", "error"); return null; }
    rule.end_date = d;
  }
  return rule;
}

async function _createVagtplanSeries(empId, actType, startDate) {
  const rule = _readRepeatRule();
  if (!rule) return;
  const commentText = document.getElementById("manual-vagtplan-comment").value.trim() || null;
  const isCommentOnly = actType === "__none__";
  if (isCommentOnly && !commentText) { toast("Skriv en kommentar", "error"); return; }
  let vehicleNumber = null;
  if (!isCommentOnly && actType !== "overnatning") {
    const regInput = document.getElementById("manual-reg").value.trim().toUpperCase();
    if (!regInput) { toast("Registreringsnummer / Vognnummer er påkrævet", "error"); return; }
    const v = state.vehicles.find(x => x.registration_number.toUpperCase() === regInput || x.vehicle_number.toUpperCase() === regInput);
    if (!v) { openModal("modal-reg-error"); return; }
    vehicleNumber = v.vehicle_number;
  }
  const terminsdato = document.getElementById("manual-terminsdato").value || null;
  if (actType === "barsel" && !terminsdato) { toast("Angiv terminsdato for barsel", "error"); return; }
  const payload = {
    employee_id: empId,
    activity_type: isCommentOnly ? null : actType,
    comment_text: commentText,
    vehicle_number: vehicleNumber,
    terminsdato,
    start_date: startDate,
    ...rule,
  };
  const fmt = d => { const [y, m, day] = d.split("-"); return `${day}-${m}-${y}`; };
  let preview;
  try { preview = await POST("/api/vagtplan-series/preview", payload); }
  catch (e) { toast(e.message, "error"); return; }
  if (preview.locked_dates.length) {
    toast(`Kan ikke oprette – lønperioden er låst for: ${preview.locked_dates.map(fmt).join(", ")}`, "error");
    return;
  }
  const lines = [`${preview.description}: ${preview.dates.length} forekomster (${fmt(preview.dates[0])} – ${fmt(preview.dates[preview.dates.length - 1])}).`];
  if (preview.driving_conflicts.length) lines.push(`Der er registreret kørsel på: ${preview.driving_conflicts.map(fmt).join(", ")}.`);
  if (preview.comment_conflicts.length) lines.push(`Der findes allerede en kommentar på: ${preview.comment_conflicts.map(fmt).join(", ")} – den overskrives ikke.`);
  if (preview.skipped_no_hours.length) lines.push(`Springes over (ingen garanterede timer): ${preview.skipped_no_hours.map(fmt).join(", ")}.`);
  if (!window.confirm(lines.join("\n\n") + "\n\nOpret gentagelsen?")) return;
  try {
    const res = await POST("/api/vagtplan-series", payload);
    toast(`${res.created} forekomster oprettet`, "success");
    closeModal("modal-manual-activity");
    await loadVagtplan();
  } catch (e) { toast(e.message, "error"); }
}
```

- [ ] **Step 3: Nulstil og bind felterne i `openManualActivityModal()`** – lige efter linjen `document.getElementById("manual-vagtplan-comment-group").style.display = _manualActivityContext.vagtplan ? "" : "none";`:

```js
  document.getElementById("manual-repeat-group").style.display = _manualActivityContext.vagtplan ? "" : "none";
  document.getElementById("manual-repeat").checked = false;
  document.querySelector('input[name="manual-repeat-freq"][value="weekly"]').checked = true;
  document.querySelector('input[name="manual-repeat-end"][value="count"]').checked = true;
  document.getElementById("manual-repeat-count").value = "4";
  document.getElementById("manual-repeat-end-date").value = "";
  document.querySelectorAll(".manual-repeat-wd").forEach(b => b.checked = false);
  document.getElementById("manual-repeat").onchange = () => { _preselectRepeatWeekday(); _updateRepeatUi(); };
  document.querySelectorAll('input[name="manual-repeat-freq"]').forEach(r => r.onchange = _updateRepeatUi);
```

og i den eksisterende `document.getElementById("manual-start").addEventListener("change", (e) => { ... })` som sidste linje i callback'en:

```js
    if (_isRepeatOn()) _updateRepeatUi();
```

- [ ] **Step 4: Skjul "Til dato" og tider når Gentagelse er til** – i `updateManualTypeVisibility()` erstattes de fire linjer

```js
  document.getElementById("manual-til-dato-group").style.display = tilDatoFieldVisible ? "" : "none";
  if (!tilDatoFieldVisible) document.getElementById("manual-til-dato").value = "";
  const pauseSection = document.getElementById("manual-pause-section");
  if (pauseSection) pauseSection.style.display = (isDateOnly || isCommentOnly) ? "none" : "";
```

med:

```js
  // Gentagelse (Vagtplan): kun startdato – ingen til-dato, sluttid, pauser eller klokkeslæt.
  // Startdatoen vises også ved "Ingen (kun kommentar)", da den er seriens start.
  const repeatOn = _isRepeatOn();
  document.getElementById("manual-til-dato-group").style.display = (tilDatoFieldVisible && !repeatOn) ? "" : "none";
  if (!tilDatoFieldVisible || repeatOn) document.getElementById("manual-til-dato").value = "";
  const pauseSection = document.getElementById("manual-pause-section");
  if (pauseSection) pauseSection.style.display = (isDateOnly || isCommentOnly || repeatOn) ? "none" : "";
  if (repeatOn) {
    document.getElementById("manual-end-group").style.display = "none";
    document.getElementById("manual-start-group").style.display = "";
    const timeEl = document.getElementById("manual-start")?.querySelector(".dt-time");
    if (timeEl) timeEl.style.display = "none";
    const startLbl = document.querySelector("#manual-start-group label");
    if (startLbl) startLbl.innerHTML = `Startdato <span style="color:var(--danger)">*</span>`;
  }
```

- [ ] **Step 5: Gren i `confirmManualActivity()`** – lige efter linjen `const empId   = parseInt(document.getElementById("manual-employee").value);` (før `if (_manualActivityContext.vagtplan && actType === "__none__")`):

```js
  if (_isRepeatOn()) {
    const startDate = _manualStartDateIso();
    if (!startDate) { toast("Angiv startdato", "error"); return; }
    await _createVagtplanSeries(empId, actType, startDate);
    return;
  }
```

- [ ] **Step 6: Verificér i browseren** – start `preview_start {name: "Lønsystem (Udvikling)"}`. Log-in kræver brugerens egne initialer/adgangskode: bed brugeren logge ind i Browser-panelet (Claude indtaster ALDRIG adgangskoder). Derefter:
  1. Vagtplan → klik tom celle → afkryds Gentagelse → "Til dato" og sluttid forsvinder, ugedagen er forvalgt.
  2. Skift til Månedligt → teksten "Hver N. <ugedag> i måneden" vises.
  3. Ferie, hver tirsdag, 3 gange → bekræftelse → 3 badges i griddet.
  4. "Ingen (kun kommentar)" + tekst + gentagelse → kommentarer i griddet.
  5. `read_console_messages` uden fejl.

- [ ] **Step 7: Ingen commit.**

---

### Task 8: Frontend – serie-sektion ved redigering

**Files:**
- Modify: `app/templates/index.html` (`modal-vagtplan-comment`, ~linje 1145-1151)
- Modify: `app/static/js/app.js` (`openActivityDetail` ~linje 1325-1375, `openVagtplanCommentModal` ~linje 311)

**Interfaces:**
- Consumes: `GET/PATCH/DELETE /api/vagtplan-series/{id}`, `DELETE /api/vagtplan-series/{id}/occurrences/{date}` (Task 5-6); `series_id` på aktivitet/kommentar (Task 2).
- Produces (JS): `_renderSeriesSection(series, occurrenceDate, canEdit) -> string`, `saveSeriesEnd(seriesId)`, `deleteSeriesOccurrence(seriesId, dateIso)`, `deleteWholeSeries(seriesId)`, `_afterSeriesChange()`.

- [ ] **Step 1: HTML** – i `modal-vagtplan-comment` lige efter `</div>` der lukker tekst-`form-group`:

```html
      <div id="vagtplan-comment-series"></div>
```

- [ ] **Step 2: JS-hjælpere** – tilføj efter `_createVagtplanSeries` (Task 7):

```js
function _renderSeriesSection(series, occurrenceDate, canEdit) {
  const isCount = series.end_mode === "count";
  const countVal = series.occurrence_count;
  const dateVal = series.end_date || series.last_date || "";
  const maxD = new Date(series.start_date + "T12:00:00");
  maxD.setFullYear(maxD.getFullYear() + 1);
  const controls = canEdit ? `
      <div style="display:flex;flex-direction:column;gap:6px;margin:8px 0">
        <label style="display:flex;align-items:center;gap:6px">
          <input type="radio" name="series-end-mode" value="count" ${isCount ? "checked" : ""}> Efter
          <input type="number" id="series-end-count" min="1" max="100" value="${countVal}" style="width:70px"> gange
        </label>
        <label style="display:flex;align-items:center;gap:6px">
          <input type="radio" name="series-end-mode" value="date" ${isCount ? "" : "checked"}> Den
          <input type="date" id="series-end-date" value="${dateVal}" min="${series.first_date || series.start_date}" max="${_isoOfDate(maxD)}" style="width:170px">
        </label>
      </div>
      <div style="display:flex;gap:6px;flex-wrap:wrap">
        <button type="button" class="btn btn-secondary" style="font-size:13px;padding:5px 14px" onclick="saveSeriesEnd(${series.id})">Gem for serien</button>
        <button type="button" class="btn btn-secondary" style="font-size:13px;padding:5px 14px" onclick="deleteSeriesOccurrence(${series.id}, '${occurrenceDate}')">Slet denne forekomst</button>
        <button type="button" class="btn btn-danger" style="font-size:13px;padding:5px 14px" onclick="deleteWholeSeries(${series.id})">Slet hele serien</button>
      </div>` : "";
  return `
    <div class="form-group" id="series-section" style="margin-bottom:14px;padding:10px;background:var(--bg);border-radius:var(--radius)">
      <label style="font-weight:500;font-size:12px;text-transform:uppercase;color:var(--text-light);margin-bottom:6px;display:block">Gentagelse</label>
      <div style="font-size:13px">${h(series.description)} – ${series.occurrence_count} forekomster (${formatDate(series.first_date)} – ${formatDate(series.last_date)})</div>
      ${controls}
    </div>`;
}

async function _afterSeriesChange() {
  closeAllModals();
  if (state.currentView === "vagtplan") await loadVagtplan();
  else await refreshActivities();
}

async function saveSeriesEnd(seriesId) {
  const mode = document.querySelector('input[name="series-end-mode"]:checked')?.value;
  const body = { end_mode: mode, end_count: null, end_date: null };
  if (mode === "count") {
    const n = parseInt(document.getElementById("series-end-count").value);
    if (!(n >= 1 && n <= 100)) { toast("Antal gentagelser skal være 1–100", "error"); return; }
    body.end_count = n;
  } else {
    const d = document.getElementById("series-end-date").value;
    if (!d) { toast("Angiv slutdato", "error"); return; }
    body.end_date = d;
  }
  try {
    const r = await PATCH(`/api/vagtplan-series/${seriesId}`, body);
    toast(`Gentagelse opdateret – ${r.added} tilføjet, ${r.removed} fjernet`, "success");
    if (r.skipped_comments.length) toast(`Kommentar ikke oprettet (findes allerede) på ${r.skipped_comments.length} dag(e)`, "warning");
    if (r.skipped_no_hours.length) toast(`${r.skipped_no_hours.length} dag(e) sprunget over – ingen garanterede timer`, "warning");
    await _afterSeriesChange();
  } catch (e) { toast(e.message, "error"); }
}

async function deleteSeriesOccurrence(seriesId, dateIso) {
  if (!window.confirm(`Slet forekomsten d. ${formatDate(dateIso)}?`)) return;
  try {
    await DEL(`/api/vagtplan-series/${seriesId}/occurrences/${dateIso}`);
    toast("Forekomst slettet", "success");
    await _afterSeriesChange();
  } catch (e) { toast(e.message, "error"); }
}

async function deleteWholeSeries(seriesId) {
  if (!window.confirm("Slet hele serien? Alle forekomster slettes permanent (undtagen i låste lønperioder).")) return;
  try {
    const r = await DEL(`/api/vagtplan-series/${seriesId}`);
    const kept = r.kept_locked + r.kept_split;
    toast(kept ? `${r.deleted} forekomster slettet – ${kept} er bevaret (låst lønperiode eller splittet)` : `${r.deleted} forekomster slettet`, "success");
    await _afterSeriesChange();
  } catch (e) { toast(e.message, "error"); }
}
```

Bemærk: `DEL()` returnerer `null` for 204, men `DELETE /api/vagtplan-series/{id}` returnerer 200 med JSON, så `r` er udfyldt. Kontrollér at `formatDate()` accepterer en ren `"YYYY-MM-DD"`-streng (den bruges allerede med `c.date` i `openVagtplanCommentModal`).

- [ ] **Step 3: Aktivitetsdetaljen** – i `openActivityDetail()` lige efter `absencePeriod`-blokken (efter dens `catch`):

```js
  let seriesHtml = "";
  if (a.series_id) {
    try {
      const series = await GET(`/api/vagtplan-series/${a.series_id}`);
      const emp = state.employees.find(e => e.id === a.employee_id);
      const canEdit = _hasVagtplanEditAccess(emp) && !a.period_closed;
      seriesHtml = _renderSeriesSection(series, a.start_time.slice(0, 10), canEdit);
    } catch (e) { /* serien kunne ikke hentes – sektionen udelades */ }
  }
```

og i template-strengen til `modal-activity-body` som det første (før `${absencePeriod && ...`):

```js
    ${seriesHtml}
```

- [ ] **Step 4: Kommentarboksen** – gør `openVagtplanCommentModal` asynkron og tilføj serie-sektionen. Erstat funktionen med:

```js
async function openVagtplanCommentModal(commentId) {
  const c = state.vagtplan.comments.find(x => x.id === commentId);
  if (!c) return;
  const emp = state.employees.find(e => e.id === c.employee_id);
  document.getElementById("vagtplan-comment-id").value = c.id;
  document.getElementById("vagtplan-comment-info").textContent =
    `${emp ? emp.name : "Ukendt medarbejder"} – ${formatDate(c.date)}`;
  document.getElementById("vagtplan-comment-text").value = c.text;
  const seriesEl = document.getElementById("vagtplan-comment-series");
  seriesEl.innerHTML = "";
  openModal("modal-vagtplan-comment");
  if (c.series_id) {
    try {
      const series = await GET(`/api/vagtplan-series/${c.series_id}`);
      seriesEl.innerHTML = _renderSeriesSection(series, c.date, _hasVagtplanEditAccess(emp));
    } catch (e) { /* serien kunne ikke hentes – sektionen udelades */ }
  }
}
```

(Låst periode håndhæves af backend; fejlen vises som toast.)

- [ ] **Step 5: Verificér i browseren** (brugeren logger ind selv):
  1. Åbn en forekomst fra Task 7 → sektionen "Gentagelse" vises med beskrivelse og antal.
  2. Sæt antal til 5 → "Gem for serien" → 2 nye badges efter den sidste.
  3. "Slet denne forekomst" → dagen forsvinder; forlæng igen → dagen kommer ikke tilbage.
  4. Åbn en kommentar-forekomst → samme sektion i kommentarboksen.
  5. "Slet hele serien" → alt forsvinder. Åbn forekomsten fra Aktivitetsoversigten → sektionen vises også der.
  6. `read_console_messages` uden fejl.

- [ ] **Step 6: Ingen commit.**

---

### Task 9: Dokumentation

**Files:**
- Modify: `CODEREF.md` (nyt afsnit sidst i filen)
- Modify: `docs/build_docs.py` (teknisk kapitel 15 "Vagtplan" og brugervejledningens kapitel 14 "Vagtplan")

- [ ] **Step 1: CODEREF.md** – tilføj:

```markdown
## Gentagelse i Vagtplan (2026-10-07, calculators/recurrence.py + routers/vagtplan_series.py + activities.py + app.js)
- **Model:** `VagtplanSeries` (tabel `vagtplan_series`) gemmer reglen (freq weekly/monthly, weekdays "0,3", start_date, end_mode count/date). Forekomster = almindelige `Activity` (source=vagtplan) og/eller `VagtplanComment` med `series_id`. Månedligt = "N. ugedag" udledt af start_date (5. → sidste).
- **Beregning:** `occurrence_dates()` – helligdage (tabellen `holidays`) springes over for fravær og erstattes; maks. 1 år (`one_year_after`) og 100 forekomster (`MAX_OCCURRENCES`). `after`/`existing_count` bruges ved forlængelse.
- **Oprettelse:** `_create_manual_activity_row()` (activities.py) er udtrukket fra `create_manual_activity` og bruges af begge – samme omklassificering/godkendelse/låsetjek. Tider via `_range_day_defaults`.
- **Endpoints:** `POST /api/vagtplan-series/preview`, `POST /api/vagtplan-series`, `GET /{id}` (view_calendar|vagtplan_view), `PATCH /{id}` (slut ændres KUN i enden; alt-eller-intet ved låst dag), `DELETE /{id}` (bevarer låste/splittede), `DELETE /{id}/occurrences/{dato}`. Skriv kræver `_has_vagtplan_edit_access`.
- **Frontend:** Gentagelse-felter i opret-modalen (kun vagtplan-kontekst, `_isRepeatOn()`), serie-sektion i `openActivityDetail()` og `openVagtplanCommentModal()` via `_renderSeriesSection()`.
- Tests: `tests/test_recurrence.py`, `tests/test_vagtplan_series.py`.
```

- [ ] **Step 2: build_docs.py** – i teknisk kapitel 15 (efter afsnit 15.3 "Frontend", før `# ── 16. Fraværsoversigt`) tilføj et afsnit med `heading(doc, "Gentagelse", 2, "15.4")` og `body(...)`-tekst svarende til CODEREF-afsnittet ovenfor. I brugervejledningens kapitel 14 (efter afsnit 14.2, før `# ── 15. Fraværsoversigt`) tilføj `heading(doc, "Gentagelse", 2, "14.3")` med disse bullets:

```python
    heading(doc, "Gentagelse", 2, "14.3")
    body(doc, "Afkryds 'Gentagelse' i registreringsvinduet for at oprette det samme fravær eller den samme kommentar flere gange:")
    bullet(doc, "Ugentligt: vælg en eller flere ugedage (fx hver mandag og torsdag).")
    bullet(doc, "Månedligt: samme ugedag i måneden som startdatoen (fx hver 2. tirsdag – eller sidste fredag).")
    bullet(doc, "Slutter: efter et antal gange (maks. 100) eller på en dato (maks. 1 år frem).")
    bullet(doc, "Fravær springer helligdage over og tager næste dag i stedet; kommentarer oprettes også på helligdage. Findes der allerede en kommentar på en dag, overskrives den ikke.")
    body(doc, "Åbn en vilkårlig forekomst for at ændre antal/slutdato for hele serien, slette kun denne forekomst eller slette hele serien. Forekomster i en låst lønperiode bevares altid.")
```

- [ ] **Step 3: Generér dokumenterne** – `python docs/build_docs.py` (fra projektroden). Expected: ingen fejl; `docs/Brugervejledning.docx` og `docs/Teknisk dokumentation.docx` opdateres.

- [ ] **Step 4: Ingen commit.**
