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
    STEP_THIRD_LAST, dk_date, dk_period,
)
from calculators.pay_period import period_start_for_date
from database.models import ElevStepClaim, ElevStepDecision, Employee, PayPeriod, PayPeriodStatus

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


def rate_for(db: Session, type_name: str, period_start: date) -> Optional[float]:
    """Timesatsen for typen i lønperioden (til beskederne) – inkl. fremtidige satser."""
    from calculators.agreement_rates import agreement_rate_for_period
    rate = agreement_rate_for_period(db, type_name, period_start, period_start + timedelta(days=PERIOD_DAYS - 1))
    return float(rate) if rate else None


def _kr(v: Optional[float]) -> str:
    return "?" if v is None else f"{v:,.2f} kr".replace(",", "X").replace(".", ",").replace("X", ".")


def _reason(db: Session, emp: Employee, when: date, from_step: str, to_step: str) -> str:
    """Fx: 'Fra lønperioden 2. november til 15. november 2026 stiger Nanna Elevsens timesats fra
    105,75 kr til 119,17 kr, fordi Nanna går fra næstsidste ind i sidste år af sin lærekontrakt
    den 6. november 2026 (lærekontrakten slutter 5. november 2027).'"""
    p_start = period_start_for_date(when)
    old = rate_for(db, STEP_AGREEMENT_TYPES[from_step], p_start)
    new = rate_for(db, STEP_AGREEMENT_TYPES[to_step], p_start)
    return (f"Fra lønperioden {dk_period(p_start, p_start + timedelta(days=PERIOD_DAYS - 1))} stiger "
            f"{emp.name}s timesats fra {_kr(old)} til {_kr(new)}, fordi {emp.first_name} går fra "
            f"{STEP_LABELS[from_step]} ind i {STEP_LABELS[to_step]} år af sin lærekontrakt den {dk_date(when)} "
            f"(lærekontrakten slutter {dk_date(emp.elev_end_date)}).")


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
            "reason": _reason(db, emp, when, from_step, to_step),
        })
    return out


def step_event_date(emp: Employee, step: str) -> Optional[date]:
    """Dagen trinnet begyndte (kontraktstart for tredjesidste år)."""
    if step == STEP_THIRD_LAST:
        return emp.elev_start_date
    return step_starts(emp.elev_end_date)[step]


def is_closed(db: Session, period_start: date) -> bool:
    p = db.query(PayPeriod).filter(PayPeriod.start_date == period_start).first()
    return bool(p and p.status == PayPeriodStatus.closed)


def _periods_to_check(db: Session, today: date) -> list:
    """Den aktuelle lønperiode, perioden der lige er slut (den køres typisk nu) og
    ældre perioder der stadig er åbne – låste perioder kan ikke rettes."""
    current = period_start_for_date(today)
    starts = {current}
    previous = current - timedelta(days=PERIOD_DAYS)
    if not is_closed(db, previous):
        starts.add(previous)
    for p in db.query(PayPeriod).filter(PayPeriod.status == PayPeriodStatus.open,
                                        PayPeriod.start_date < current).all():
        starts.add(p.start_date)
    return sorted(starts)


def first_open_period(db: Session, start: date) -> date:
    """Første lønperiode fra og med start, der ikke er låst."""
    p = start
    while is_closed(db, p):
        p += timedelta(days=PERIOD_DAYS)
    return p


def backpay(db: Session, emp: Employee, period_start: date, expected_type: str) -> dict:
    """Beløbet eleven mangler i en (låst) periode, hvis den var regnet med den rigtige
    type – samme beregning som Lønkørsel/Lønafregning ('I alt')."""
    from routers.payroll_router import _calculate_employee
    from routers.payroll_settlement_router import settlement_total_kr
    p_end = period_start + timedelta(days=PERIOD_DAYS - 1)
    actual = _calculate_employee(emp, period_start, p_end, db)
    expected = _calculate_employee(emp, period_start, p_end, db, agreement_type=expected_type)
    diff = settlement_total_kr(expected) - settlement_total_kr(actual)
    return {"period_start": period_start, "period_end": p_end, "hours": actual["total_hours"],
            "actual_type": actual["agreement_type"], "amount": float(round(diff, 2)),
            "text": f"Lønperioden {dk_period(period_start, p_end)} er låst: mangler {dk_kr(diff)} (skal efterreguleres)."}


def dk_kr(amount) -> str:
    """1.105,50 kr"""
    return f"{float(amount):,.2f} kr".replace(",", "X").replace(".", ",").replace("X", ".")


def locked_backpay(db: Session, emp: Employee, from_period: date, until_period: date, expected_type: str) -> list:
    """Låste perioder fra trinnets start og frem til (ikke med) den første åbne periode,
    hvor eleven er regnet med en forkert type."""
    out = []
    p = from_period
    while p < until_period:
        if is_closed(db, p) and agreement_type_for_period(db, emp, p) != expected_type:
            out.append(backpay(db, emp, p, expected_type))
        p += timedelta(days=PERIOD_DAYS)
    return out


def cancel_open_decisions(db: Session, emp: Employee, changed: str, log=None) -> int:
    """Elevens datoer/type er ændret: godkendelser der ikke er trådt i kraft og
    'behold'-beslutninger annulleres (logges), så advarslen kommer igen."""
    rows = (db.query(ElevStepDecision)
            .filter(ElevStepDecision.employee_id == emp.id, ElevStepDecision.applied_at.is_(None)).all())
    for d in rows:
        what = (f"godkendt skift '{d.from_type}' → '{d.to_type}' fra {dk_date(d.effective_from)}"
                if d.decision == "approve" else f"'behold {d.from_type}' (bemærkning: {d.note})")
        if log:
            log("elev_step_cancel", "employee", emp.id,
                f"{emp.name}: {what} annulleret automatisk, fordi {changed} er ændret")
        db.delete(d)
    db.query(ElevStepClaim).filter(ElevStepClaim.employee_id == emp.id).delete(synchronize_session=False)
    return len(rows)


# ── Lås: "Behandles af ..." ───────────────────────────────────────────────────
CLAIM_MINUTES = 15


def active_claim(db: Session, employee_id: int, event_date: date) -> Optional[ElevStepClaim]:
    c = (db.query(ElevStepClaim)
         .filter(ElevStepClaim.employee_id == employee_id, ElevStepClaim.event_date == event_date).first())
    if c and c.claimed_at < datetime.now() - timedelta(minutes=CLAIM_MINUTES):
        db.delete(c)       # udløbet (fx lukket browser)
        db.commit()
        return None
    return c


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
        for p_start in starts:   # én advarsel pr. elev: den tidligste periode med fejl
            p_end = p_start + timedelta(days=PERIOD_DAYS - 1)
            step = step_for_period(emp.elev_start_date, emp.elev_end_date, p_start, p_end)
            if step is None:
                continue
            expected = STEP_AGREEMENT_TYPES[step]
            actual = agreement_type_for_period(db, emp, p_start)
            event = step_event_date(emp, step)
            if actual == expected or event in kept:
                continue
            effective = period_start_for_date(event) if event else p_start
            suggested = first_open_period(db, effective)
            out.append({
                "employee_id": emp.id, "employee_name": emp.name, "employee_number": emp.employee_number,
                "period_start": p_start, "period_end": p_end, "event_date": event,
                "elev_end_date": emp.elev_end_date, "effective_from": effective,
                "suggested_from": suggested,
                "current_type": actual, "expected_type": expected,
                "locked_periods": locked_backpay(db, emp, effective, suggested, expected),
                "reason": mismatch_reason(emp, step, actual, p_start, today, db),
            })
            break
    return out


def mismatch_reason(emp: Employee, step: str, actual: str, period_start: date, today: date,
                    db: Optional[Session] = None) -> str:
    """Fx: 'Jonas Elevsen gik ind i sidste år af sin lærekontrakt den 27. september 2026
    (lærekontrakten slutter 26. september 2027). Den nye sats gælder fra lønperioden 21. september
    til 4. oktober 2026, men i lønperioden 5. oktober til 18. oktober 2026 er overenskomsttypen stadig '...'.'"""
    dk = dk_date
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
        text += (f" Den nye sats gælder fra lønperioden "
                 f"{dk_period(effective, effective + timedelta(days=PERIOD_DAYS - 1))}, men")
        if effective != period_start:
            text += f" i lønperioden {dk_period(period_start, p_end)}"
        text += f" er overenskomsttypen stadig '{actual}'."
        if db is not None:
            text += (f" Timesatsen er {_kr(rate_for(db, actual, period_start))} – den skulle være "
                     f"{_kr(rate_for(db, STEP_AGREEMENT_TYPES[step], period_start))}.")
    else:
        text += f" Overenskomsttypen er '{actual}'."
    return text
