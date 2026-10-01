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
