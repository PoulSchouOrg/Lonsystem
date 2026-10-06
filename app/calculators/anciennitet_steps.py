"""
Anciennitet som lønstigning (2026-10-06): efter 9 måneder skifter en medarbejder fra
'<type>' til '<type>. 9 mdr anciennitet' (højere sats) – samme forløb som elevløn-trin:
varsel før, godkend fra en lønperiode (hele perioden), 'Mulig fejl' hvis det er glemt.

- Tælles fra anciennitetsdatoen, hvis den er udfyldt, ellers fra ansættelsesdatoen (Kasper 2026-10-06).
- Ligger datoen inde i en lønperiode, gælder den nye sats hele perioden (som elever).
- Medarbejdere hvor den gamle anciennitetsadvarsel er afvist (anciennitet_dismissed_at), springes over.
"""
import calendar
from datetime import date, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from calculators.elev_agreement import (
    FUNKTIONAER, PERIOD_DAYS, _kr, agreement_type_for_period, first_open_period, locked_backpay, rate_for,
)
from calculators.elev_steps import dk_date, dk_period
from calculators.pay_period import period_start_for_date
from database.models import ElevStepDecision, Employee, MasterAgreementType

KIND = "anciennitet"
MONTHS = 9
SUFFIX = ". 9 mdr anciennitet"


def _add_months(d: date, months: int) -> date:
    m = d.month - 1 + months
    y, m = d.year + m // 12, m % 12 + 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def start_date(emp: Employee) -> Optional[date]:
    return emp.seniority_date or emp.hire_date


def event_date(emp: Employee) -> Optional[date]:
    s = start_date(emp)
    return _add_months(s, MONTHS) if s else None


def _variant(known: set, type_name: Optional[str]) -> Optional[str]:
    if not type_name or type_name.endswith(SUFFIX):
        return None
    v = f"{type_name}{SUFFIX}"
    return v if v in known else None


def _candidates(db: Session):
    """(medarbejder, basistype, 9-mdr-type, dato) for alle der har en 9-mdr-variant."""
    known = {t.name for t in db.query(MasterAgreementType).all()}
    for emp in db.query(Employee).filter(Employee.active == True).all():  # noqa: E712
        if emp.agreement_kind == FUNKTIONAER or emp.anciennitet_dismissed_at is not None:
            continue
        event = event_date(emp)
        if not event:
            continue
        base = emp.agreement_type
        variant = _variant(known, base)
        if variant:
            yield emp, base, variant, event


def _decided(db: Session, emp: Employee, event: date) -> bool:
    return db.query(ElevStepDecision).filter(ElevStepDecision.employee_id == emp.id,
                                             ElevStepDecision.event_date == event).first() is not None


def _since(emp: Employee) -> str:
    return "anciennitetsdato" if emp.seniority_date else "ansat"


def upcoming(db: Session, today: date) -> list:
    """Anciennitetsstigninger hvis lønperiode ikke er startet og som ikke er behandlet."""
    out = []
    for emp, base, variant, event in _candidates(db):
        effective = period_start_for_date(event)
        if effective <= today or _decided(db, emp, event):
            continue
        old, new = rate_for(db, base, effective), rate_for(db, variant, effective)
        out.append({
            "kind": KIND, "employee_id": emp.id, "employee_name": emp.name, "employee_number": emp.employee_number,
            "event_date": event, "effective_from": effective, "effective_to": effective + timedelta(days=PERIOD_DAYS - 1),
            "from_type": base, "to_type": variant,
            "reason": (f"Fra lønperioden {dk_period(effective, effective + timedelta(days=PERIOD_DAYS - 1))} stiger "
                       f"{emp.name}s timesats fra {_kr(old)} til {_kr(new)}, fordi {emp.first_name} når "
                       f"{MONTHS} måneders anciennitet den {dk_date(event)} "
                       f"({_since(emp)} {dk_date(start_date(emp))})."),
        })
    return out


def mismatches(db: Session, today: date, period_starts: list) -> list:
    """9 måneder er nået (lønperioden er startet), men typen er stadig basistypen og intet er besluttet."""
    out = []
    for emp, base, variant, event in _candidates(db):
        effective = period_start_for_date(event)
        if effective > today or _decided(db, emp, event):
            continue
        open_starts = [p for p in period_starts if p >= effective]
        p_start = next((p for p in open_starts if agreement_type_for_period(db, emp, p) == base), None)
        if p_start is None:
            continue
        suggested = first_open_period(db, max(effective, period_starts[0]))
        verb = "når" if event > today else "nåede"
        text = (f"{emp.name} {verb} {MONTHS} måneders anciennitet den {dk_date(event)} "
                f"({_since(emp)} {dk_date(start_date(emp))}). Den nye sats gælder fra lønperioden "
                f"{dk_period(effective, effective + timedelta(days=PERIOD_DAYS - 1))}, men")
        if p_start != effective:
            text += f" i lønperioden {dk_period(p_start, p_start + timedelta(days=PERIOD_DAYS - 1))}"
        text += (f" er overenskomsttypen stadig '{base}'. Timesatsen er {_kr(rate_for(db, base, p_start))} – "
                 f"den skulle være {_kr(rate_for(db, variant, p_start))}.")
        out.append({
            "kind": KIND, "employee_id": emp.id, "employee_name": emp.name, "employee_number": emp.employee_number,
            "period_start": p_start, "period_end": p_start + timedelta(days=PERIOD_DAYS - 1), "event_date": event,
            "effective_from": effective, "suggested_from": suggested,
            "current_type": base, "expected_type": variant,
            "locked_periods": locked_backpay(db, emp, effective, suggested, variant),
            "reason": text,
        })
    return out
