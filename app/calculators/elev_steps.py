"""
Elevløn-trin (Lærlingeoverenskomsten 2025-2028, § 8 stk. 1) – rene regler, ingen database.

Lønnen regnes "baglæns" fra lærekontraktens slutdato:
- sidste år        = de sidste 12 måneder før slutdatoen
- næstsidste år    = de 12 måneder før det
- tredjesidste år  = alt før det (overenskomsten har intet fjerdesidste trin)

Skifter eleven trin inde i en lønperiode, gælder den nye sats HELE perioden
(besluttet 2026-10-06) → trinnet for en periode = trinnet på periodens sidste dag.
Voksenlærlinge (§ 8 stk. 4) får almindelig overenskomstløn og har ingen trin.
"""
import calendar
from datetime import date, timedelta
from typing import Optional

STEP_THIRD_LAST = "tredjesidste"
STEP_SECOND_LAST = "naestsidste"
STEP_LAST = "sidste"

# Navnene skal matche overenskomsttyperne i Stamdata præcist (stavefejlene er bevidst bevaret).
STEP_AGREEMENT_TYPES = {
    STEP_THIRD_LAST: "Lærling (EUD) Tredjesidste år af lærerkontrakt",
    STEP_SECOND_LAST: "Lærling (EUD) Næstsidsteår af lærerkontrakt",
    STEP_LAST: "Lærling (EUD) Sidste år af lærerkontrakt",
}

STEP_LABELS = {
    STEP_THIRD_LAST: "tredjesidste",
    STEP_SECOND_LAST: "næstsidste",
    STEP_LAST: "sidste",
}


def _years_before(d: date, years: int) -> date:
    return date(d.year - years, d.month, min(d.day, calendar.monthrange(d.year - years, d.month)[1]))


def step_starts(end_date: date) -> dict:
    """Første dag i næstsidste og sidste år af kontrakten."""
    return {
        STEP_SECOND_LAST: _years_before(end_date, 2) + timedelta(days=1),
        STEP_LAST: _years_before(end_date, 1) + timedelta(days=1),
    }


def step_on(start_date: Optional[date], end_date: date, d: date) -> Optional[str]:
    """Trinnet på dagen d, eller None uden for kontrakten."""
    if d > end_date or (start_date and d < start_date):
        return None
    starts = step_starts(end_date)
    if d >= starts[STEP_LAST]:
        return STEP_LAST
    if d >= starts[STEP_SECOND_LAST]:
        return STEP_SECOND_LAST
    return STEP_THIRD_LAST


def step_for_period(start_date: Optional[date], end_date: date,
                    period_start: date, period_end: date) -> Optional[str]:
    """Trinnet for en lønperiode: trinnet på periodens sidste dag (hele perioden
    får den nye sats). Slutter kontrakten inde i perioden, bruges sidste dag i kontrakten."""
    if period_end < (start_date or period_end) or period_start > end_date:
        return None
    return step_on(start_date, end_date, min(period_end, end_date))


def step_changes(start_date: Optional[date], end_date: date) -> list:
    """[(dato, fra_trin, til_trin)] for trinskift der ligger inden for kontrakten."""
    out = []
    starts = step_starts(end_date)
    for new_step, prev_step in ((STEP_SECOND_LAST, STEP_THIRD_LAST), (STEP_LAST, STEP_SECOND_LAST)):
        when = starts[new_step]
        if start_date is None or when > start_date:
            out.append((when, prev_step, new_step))
    return out
