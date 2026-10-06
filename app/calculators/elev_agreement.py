"""
Elevløn-trin mod databasen (2026-10-06): hvilken overenskomsttype gælder i en
lønperiode, godkendte skift der skal træde i kraft, kommende skift og afvigelser.
Reglerne for selve trinnene ligger i calculators/elev_steps.py.
"""
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from calculators.elev_steps import (
    STEP_AGREEMENT_TYPES, STEP_LABELS, step_changes, step_for_period, step_starts,
    STEP_THIRD_LAST,
)
from calculators.pay_period import period_start_for_date
from database.models import ElevStepDecision, Employee, PayPeriod, PayPeriodStatus

FUNKTIONAER = "funktionaer"
PERIOD_DAYS = 14


def is_elev(emp: Employee) -> bool:
    return bool(emp.active and emp.elev and emp.elev_end_date and emp.agreement_kind != FUNKTIONAER)


def has_elev_steps(emp: Employee) -> bool:
    """Elever med løntrin: EUD-lærlinge på en af de tre trin-typer. Voksenlærlinge,
    EGU-elever og disponentspecialet har ingen trin (de vises stadig i elevoversigten)."""
    return bool(is_elev(emp) and not emp.voksenelev
                and emp.agreement_type in STEP_AGREEMENT_TYPES.values())


def _approved(db: Session, employee_id: int) -> list:
    return (db.query(ElevStepDecision)
            .filter(ElevStepDecision.employee_id == employee_id,
                    ElevStepDecision.decision == "approve")
            .order_by(ElevStepDecision.effective_from).all())


def agreement_type_for_period(db: Session, emp: Employee, period_start: date) -> str:
    """Overenskomsttypen der gælder for lønperioden der starter period_start.
    Uden godkendte elevskift er det altid medarbejderens nuværende type."""
    decisions = _approved(db, emp.id)
    if not decisions:
        return emp.agreement_type
    later = [d for d in decisions if d.effective_from > period_start]
    if later:
        # Ældre periode: typen fra før det første senere skift
        return later[0].from_type or emp.agreement_type
    due = decisions[-1]
    if due.applied_at is None:
        return due.to_type
    return emp.agreement_type


def apply_due_changes(db: Session, today: date, log=None) -> list:
    """Skifter medarbejderens type når et godkendt skift træder i kraft.
    Er typen ændret manuelt i mellemtiden, overskrives den ikke (afvigelsen vises)."""
    applied = []
    pending = (db.query(ElevStepDecision)
               .filter(ElevStepDecision.decision == "approve",
                       ElevStepDecision.applied_at.is_(None),
                       ElevStepDecision.effective_from <= today).all())
    for d in pending:
        emp = d.employee
        old = emp.agreement_type
        if old == d.from_type:
            emp.agreement_type = d.to_type
            detail = f"Elevløn-trin trådt i kraft for {emp.name}: '{old}' → '{d.to_type}' fra {d.effective_from}"
        else:
            detail = (f"Elevløn-trin for {emp.name} ikke anvendt: typen er ændret manuelt "
                      f"til '{old}' (godkendt: '{d.from_type}' → '{d.to_type}')")
        d.applied_at = datetime.now()
        if log:
            log("elev_step_applied", "employee", emp.id, detail)
        applied.append(d)
    if applied:
        db.commit()
    return applied


def _reason(emp: Employee, when: date, from_step: str, to_step: str) -> str:
    return (f"{emp.name} går fra {STEP_LABELS[from_step]} ind i {STEP_LABELS[to_step]} "
            f"år af sin lærekontrakt den {when.strftime('%d.%m.%Y')}.")


def upcoming_changes(db: Session, emp: Employee, today: date) -> list:
    """Trinskift der endnu ikke er behandlet og hvis lønperiode ikke er startet."""
    if not has_elev_steps(emp):
        return []
    decided = {d.event_date for d in db.query(ElevStepDecision)
               .filter(ElevStepDecision.employee_id == emp.id).all()}
    out = []
    for when, from_step, to_step in step_changes(emp.elev_start_date, emp.elev_end_date):
        effective = period_start_for_date(when)
        if when in decided or effective <= today:
            continue
        out.append({
            "employee_id": emp.id, "employee_name": emp.name, "employee_number": emp.employee_number,
            "event_date": when, "effective_from": effective,
            "effective_to": effective + timedelta(days=PERIOD_DAYS - 1),
            "from_type": emp.agreement_type, "to_type": STEP_AGREEMENT_TYPES[to_step],
            "reason": _reason(emp, when, from_step, to_step),
        })
    return out


def step_event_date(emp: Employee, step: str) -> Optional[date]:
    """Dagen trinnet begyndte (kontraktstart for tredjesidste år)."""
    if step == STEP_THIRD_LAST:
        return emp.elev_start_date
    return step_starts(emp.elev_end_date)[step]


def _periods_to_check(db: Session, today: date) -> list:
    """Den aktuelle lønperiode + ældre perioder der stadig er åbne."""
    current = period_start_for_date(today)
    starts = {current}
    for p in db.query(PayPeriod).filter(PayPeriod.status == PayPeriodStatus.open,
                                        PayPeriod.start_date < current).all():
        starts.add(p.start_date)
    return sorted(starts)


def mismatches(db: Session, today: date, period_starts: Optional[list] = None) -> list:
    """Elever hvis overenskomsttype i en åben periode ikke svarer til trinnet,
    og hvor lønbogholderen ikke bevidst har valgt at beholde typen."""
    starts = period_starts or _periods_to_check(db, today)
    out = []
    for emp in db.query(Employee).filter(Employee.active == True, Employee.elev == True).all():  # noqa: E712
        if not has_elev_steps(emp):
            continue
        kept = {d.event_date for d in db.query(ElevStepDecision)
                .filter(ElevStepDecision.employee_id == emp.id, ElevStepDecision.decision == "keep").all()}
        for p_start in starts:
            p_end = p_start + timedelta(days=PERIOD_DAYS - 1)
            step = step_for_period(emp.elev_start_date, emp.elev_end_date, p_start, p_end)
            if step is None:
                continue
            expected = STEP_AGREEMENT_TYPES[step]
            actual = agreement_type_for_period(db, emp, p_start)
            event = step_event_date(emp, step)
            if actual == expected or event in kept:
                continue
            out.append({
                "employee_id": emp.id, "employee_name": emp.name, "employee_number": emp.employee_number,
                "period_start": p_start, "period_end": p_end, "event_date": event,
                "elev_end_date": emp.elev_end_date, "effective_from": period_start_for_date(event) if event else None,
                "current_type": actual, "expected_type": expected,
                "reason": mismatch_reason(emp, step, actual, p_start, today),
            })
    return out


def mismatch_reason(emp: Employee, step: str, actual: str, period_start: date, today: date) -> str:
    """Fx: 'Jonas Elevsen gik ind i sidste år af sin lærekontrakt den 27.09.2026 (lærekontrakten
    slutter 26.09.2027). Den nye sats gælder fra lønperioden 21.09.–04.10.2026, men i lønperioden
    05.10.–18.10.2026 er overenskomsttypen stadig '...'.'"""
    dk = lambda d: d.strftime("%d.%m.%Y")  # noqa: E731
    event = step_event_date(emp, step)
    p_end = period_start + timedelta(days=PERIOD_DAYS - 1)
    if step == STEP_THIRD_LAST:
        when = f"startede sin lærekontrakt den {dk(event)}" if event else "er i tredjesidste år af sin lærekontrakt"
    else:
        verb = "går" if event > today else "gik"
        when = f"{verb} ind i {STEP_LABELS[step]} år af sin lærekontrakt den {dk(event)}"
    text = f"{emp.name} {when} (lærekontrakten slutter {dk(emp.elev_end_date)})."
    if event:
        effective = period_start_for_date(event)
        text += (f" Den nye sats gælder fra lønperioden {effective.strftime('%d.%m.')}–"
                 f"{dk(effective + timedelta(days=PERIOD_DAYS - 1))}, men")
        if effective != period_start:
            text += f" i lønperioden {period_start.strftime('%d.%m.')}–{dk(p_end)}"
        text += f" er overenskomsttypen stadig '{actual}'."
    else:
        text += f" Overenskomsttypen er '{actual}'."
    return text
