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


def _candidates(freq: str, weekdays: list[int], start_date: date, interval: int = 1) -> Iterator[date]:
    if freq == "weekly":
        # interval = hver N. uge, talt fra startdatoens uge (uge 0).
        wanted = set(weekdays)
        start_monday = start_date - timedelta(days=start_date.weekday())
        d = start_date
        while True:
            week_idx = (d - start_monday).days // 7
            if d.weekday() in wanted and week_idx % interval == 0:
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
                     after: Optional[date] = None, existing_count: int = 0,
                     interval: int = 1) -> list[date]:
    """Forekomstdatoer i kronologisk rækkefølge.

    after: kun datoer EFTER denne dato (forlængelse fra seriens sidste forekomst).
    existing_count: antal forekomster der allerede findes – tæller med i end_count
    og i MAX_OCCURRENCES. Helligdage springes over (og erstattes) når skip_holidays.
    interval: kun weekly – hver N. uge talt fra startdatoens uge."""
    limit_date = one_year_after(start_date)
    last_allowed = min(end_date, limit_date) if end_mode == "date" else limit_date
    total = MAX_OCCURRENCES if end_mode == "date" else min(end_count or 0, MAX_OCCURRENCES)
    remaining = total - existing_count
    result: list[date] = []
    if remaining <= 0:
        return result
    for d in _candidates(freq, weekdays, start_date, interval):
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


def describe(freq: str, weekdays: list[int], start_date: date, interval: int = 1) -> str:
    """Brugervendt mønsterbeskrivelse, fx 'Hver mandag og torsdag' / 'Hver 2. uge: tirsdag' /
    'Hver 2. tirsdag i måneden'."""
    if freq == "weekly":
        days = _join_da([_WEEKDAY_NAMES[w] for w in sorted(set(weekdays))])
        return f"Hver {interval}. uge: {days}" if interval > 1 else f"Hver {days}"
    nth = _nth_of_month(start_date)
    day = _WEEKDAY_NAMES[start_date.weekday()]
    return f"Sidste {day} i måneden" if nth >= 5 else f"Hver {nth}. {day} i måneden"
