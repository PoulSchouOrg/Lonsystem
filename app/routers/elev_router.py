"""
Lønstigninger (2026-10-06): elevløn-trin og 9 måneders anciennitet – advarsler,
godkend / behold / annullér, lås. Reglerne: calculators/elev_steps.py og elev_agreement.py.

Popups vises kun for roller hvor 'elev_wage_approve' er sat EKSPLICIT – en systemrolle
(admin) har adgang til siderne, men får ikke advarslerne.
"""
from datetime import date, datetime, timedelta
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from auth import get_current_user, log_action, require_any_permission, user_has_permission
from calculators.elev_agreement import (
    PERIOD_DAYS, _periods_to_check, active_claim, agreement_type_for_period, apply_due_changes,
    has_elev_steps, locked_backpay, mismatches, upcoming_changes,
)
from calculators import anciennitet_steps
from calculators.elev_steps import dk_period, step_changes
from calculators.pay_period import period_start_for_date
from database.models import (
    AppUser, ElevStepClaim, ElevStepDecision, Employee, UserAlertSettings, MasterAgreementType, Paragraf56AlertDismissal,
    PayPeriod, PayPeriodStatus, Role,
)
from database.session import get_db

router = APIRouter(prefix="/api/elev", tags=["elev"])

PERM = "elev_wage_approve"
ANC_PERM = "anciennitet_alert"
_raise_access = require_any_permission(PERM, ANC_PERM)   # elevløn eller anciennitet
_view_access = require_any_permission(PERM, "stamdata")


def _explicit_permission(db: Session, user: AppUser, perm: str) -> bool:
    """Rettigheden er sat på rollen – systemrollens 'alle rettigheder' tæller ikke."""
    role = db.query(Role).filter(Role.name == user.role).first()
    return bool(role and perm in (role.permissions or []))


def _logger(db: Session, user: AppUser):
    return lambda action, etype, eid, details: log_action(db, user, action, etype, eid, details)


def _dk(d: Optional[date]) -> str:
    return d.strftime("%d.%m.%Y") if d else "–"


# ── Popups ───────────────────────────────────────────────────────────────────

def _dismissals(db: Session, user: AppUser) -> dict:
    return {(d.employee_id, d.alert_type): d.dismissed_at for d in db.query(Paragraf56AlertDismissal)
            .filter(Paragraf56AlertDismissal.user_id == user.id).all()}


# Varsel: dage før lønperioden med skiftet; påmind igen: dage før (None = aldrig).
NOTICE_DAYS, REMIND_DAYS = 30, 7


def notice_settings(db: Session, user: AppUser) -> tuple:
    """(varsel, påmind igen) for brugeren – egne indstillinger, ellers standard."""
    st = db.get(UserAlertSettings, user.id)
    return (st.raise_notice_days, st.raise_remind_days) if st else (NOTICE_DAYS, REMIND_DAYS)


def _may(db: Session, user: AppUser, kind: str) -> bool:
    """Elevløn kræver rettigheden sat eksplicit på rollen; anciennitet som hidtil."""
    return _explicit_permission(db, user, PERM) if kind == "elev" else user_has_permission(db, user, ANC_PERM)


def _upcoming_visible(u: dict, notice: tuple, dismissed: dict, today: date) -> bool:
    notice_days, remind_days = notice
    if today < u["effective_from"] - timedelta(days=notice_days):
        return False
    eid, key = u["employee_id"], u["event_date"].isoformat()
    if (eid, f"elevno_{key}") in dismissed:
        return False
    snoozed_at = dismissed.get((eid, f"elevup_{key}"))
    if snoozed_at is None:
        return True
    if remind_days is None:
        return False
    remind_on = u["effective_from"] - timedelta(days=remind_days)
    return today >= remind_on and snoozed_at.date() < remind_on


@router.get("/alerts")
def alerts(current_user: AppUser = Depends(_raise_access), db: Session = Depends(get_db),
           today: Optional[date] = None):
    today = today or date.today()
    empty = {"upcoming": [], "applied": [], "mismatches": []}
    show = {k for k in ("elev", "anciennitet") if _may(db, current_user, k)}
    if not show:
        return empty
    notice = notice_settings(db, current_user)
    apply_due_changes(db, today, _logger(db, current_user))
    dismissed = _dismissals(db, current_user)
    candidates = []
    if "elev" in show:
        for emp in db.query(Employee).filter(Employee.active == True, Employee.elev == True).all():  # noqa: E712
            candidates += upcoming_changes(db, emp, today)
    if "anciennitet" in show:
        candidates += anciennitet_steps.upcoming(db, today)
    upcoming = [u for u in candidates if _upcoming_visible(u, notice, dismissed, today)]
    applied = []
    for d in (db.query(ElevStepDecision)
              .filter(ElevStepDecision.decision == "approve", ElevStepDecision.applied_at.isnot(None),
                      ElevStepDecision.effective_from <= today,
                      ElevStepDecision.effective_from > today - timedelta(days=3 * PERIOD_DAYS)).all()):
        if (d.employee_id, f"elevfx_{d.id}") in dismissed or d.kind not in show:
            continue
        emp = d.employee
        applied.append({
            "decision_id": d.id, "kind": d.kind, "employee_id": emp.id, "employee_name": emp.name,
            "employee_number": emp.employee_number, "to_type": d.to_type, "from_type": d.from_type,
            "effective_from": d.effective_from,
            "effective_to": d.effective_from + timedelta(days=PERIOD_DAYS - 1),
            "took_effect": emp.agreement_type == d.to_type,
        })
    mm = mismatches(db, today) if "elev" in show else []
    if "anciennitet" in show:
        mm += anciennitet_steps.mismatches(db, today, _periods_to_check(db, today))
    for item in upcoming + mm:
        _annotate_claim(db, item, current_user)
    return {"upcoming": sorted(upcoming, key=lambda u: u["effective_from"]), "applied": applied,
            "mismatches": mm}


def _annotate_claim(db: Session, item: dict, user: AppUser) -> None:
    c = active_claim(db, item["employee_id"], item["event_date"]) if item.get("event_date") else None
    item["claimed_by"] = c.initials if c and c.user_id != user.id else None
    item["claimed_at"] = c.claimed_at if c and c.user_id != user.id else None


# ── Lås: "Behandles af ..." ───────────────────────────────────────────────────

class ClaimBody(BaseModel):
    employee_id: int
    event_date: date


def _take_claim(db: Session, user: AppUser, employee_id: int, event_date: date) -> None:
    """Giver brugeren låsen, eller 409 hvis en anden er i gang (låsen udløber efter
    CLAIM_MINUTES minutter, fx hvis browseren lukkes midt i)."""
    c = active_claim(db, employee_id, event_date)
    if c and c.user_id != user.id:
        raise HTTPException(409, f"Behandles allerede af {c.initials} (siden kl. {c.claimed_at.strftime('%H.%M')})")
    if c:
        c.claimed_at = datetime.now()
        db.commit()
        return
    db.add(ElevStepClaim(employee_id=employee_id, event_date=event_date, user_id=user.id,
                         initials=user.initials, claimed_at=datetime.now()))
    try:
        db.commit()
    except IntegrityError:          # en anden nåede det samme øjeblik
        db.rollback()
        c = active_claim(db, employee_id, event_date)
        raise HTTPException(409, f"Behandles allerede af {c.initials if c else 'en anden'}")


def _release_claim(db: Session, user: AppUser, employee_id: int, event_date: date) -> None:
    db.query(ElevStepClaim).filter(ElevStepClaim.employee_id == employee_id,
                                   ElevStepClaim.event_date == event_date,
                                   ElevStepClaim.user_id == user.id).delete(synchronize_session=False)
    db.commit()


@router.get("/claims/{employee_id}")
def claims_for_employee(employee_id: int, current_user: AppUser = Depends(get_current_user),
                        db: Session = Depends(get_db)):
    """Til medarbejderformularen: 'LB behandler elevløn for denne medarbejder'."""
    out = []
    for c in db.query(ElevStepClaim).filter(ElevStepClaim.employee_id == employee_id).all():
        c = active_claim(db, c.employee_id, c.event_date)
        if c and c.user_id != current_user.id:
            out.append({"initials": c.initials, "claimed_at": c.claimed_at})
    return out


@router.post("/claim", status_code=204)
def claim(body: ClaimBody, current_user: AppUser = Depends(_raise_access), db: Session = Depends(get_db)):
    _take_claim(db, current_user, body.employee_id, body.event_date)


@router.post("/claim/release", status_code=204)
def release_claim(body: ClaimBody, current_user: AppUser = Depends(_raise_access),
                  db: Session = Depends(get_db)):
    _release_claim(db, current_user, body.employee_id, body.event_date)


class SnoozeBody(BaseModel):
    employee_id: int
    event_date: date
    mode: Literal["later", "never"]


@router.post("/snooze", status_code=204)
def snooze(body: SnoozeBody, current_user: AppUser = Depends(_raise_access),
           db: Session = Depends(get_db)):
    """'Påmind igen' (vises igen X dage før) eller 'Påmind mig ikke igen' – kun for denne bruger."""
    key = f"{'elevup' if body.mode == 'later' else 'elevno'}_{body.event_date.isoformat()}"
    row = db.query(Paragraf56AlertDismissal).filter(
        Paragraf56AlertDismissal.employee_id == body.employee_id,
        Paragraf56AlertDismissal.user_id == current_user.id,
        Paragraf56AlertDismissal.alert_type == key).first()
    if row:
        row.dismissed_at = datetime.now()
    else:
        db.add(Paragraf56AlertDismissal(employee_id=body.employee_id, user_id=current_user.id, alert_type=key))
    db.commit()


@router.post("/applied/{decision_id}/ack", status_code=204)
def ack_applied(decision_id: int, current_user: AppUser = Depends(_raise_access),
                db: Session = Depends(get_db)):
    d = db.query(ElevStepDecision).filter(ElevStepDecision.id == decision_id).first()
    if not d:
        raise HTTPException(404, "Ikke fundet")
    key = f"elevfx_{d.id}"
    if not db.query(Paragraf56AlertDismissal).filter(
            Paragraf56AlertDismissal.employee_id == d.employee_id,
            Paragraf56AlertDismissal.user_id == current_user.id,
            Paragraf56AlertDismissal.alert_type == key).first():
        db.add(Paragraf56AlertDismissal(employee_id=d.employee_id, user_id=current_user.id, alert_type=key))
        db.commit()


# ── Godkend / behold / annullér ──────────────────────────────────────────────

class DecisionBody(BaseModel):
    kind: Literal["elev", "anciennitet"] = "elev"
    employee_id: int
    event_date: date
    decision: Literal["approve", "keep"]
    to_type: Optional[str] = None
    effective_from: Optional[date] = None   # en dag i den lønperiode skiftet skal gælde fra
    note: Optional[str] = None


@router.post("/decisions", status_code=201)
def create_decision(body: DecisionBody, current_user: AppUser = Depends(_raise_access),
                    db: Session = Depends(get_db), today: Optional[date] = None):
    today = today or date.today()
    emp = db.query(Employee).filter(Employee.id == body.employee_id).first()
    if not emp:
        raise HTTPException(404, "Medarbejder ikke fundet")
    note = (body.note or "").strip() or None
    if body.decision == "keep" and not note:
        raise HTTPException(400, "Skriv en bemærkning om hvorfor satsen bevares")
    # Er lærekontrakten ændret (fx af en kollega i medarbejderformularen), mens dialogen
    # var åben, hører beslutningen til gamle datoer → afvis.
    if not _may(db, current_user, body.kind):
        raise HTTPException(403, "Ingen adgang")
    if body.kind == "elev":
        valid_events = {emp.elev_start_date} | {c[0] for c in step_changes(emp.elev_start_date, emp.elev_end_date)} \
            if has_elev_steps(emp) else set()
    else:
        valid_events = {anciennitet_steps.event_date(emp)}
    if body.event_date not in valid_events:
        _release_claim(db, current_user, emp.id, body.event_date)
        raise HTTPException(409, "Medarbejderens datoer er ændret, mens du behandlede ændringen. Luk og åbn igen.")
    _take_claim(db, current_user, emp.id, body.event_date)
    existing = (db.query(ElevStepDecision)
                .filter(ElevStepDecision.employee_id == emp.id, ElevStepDecision.event_date == body.event_date,
                        ElevStepDecision.applied_at.is_(None)).first())
    if existing:
        _release_claim(db, current_user, emp.id, body.event_date)
        raise HTTPException(409, f"Allerede behandlet af {existing.decided_by} – annullér den først for at ændre")
    if body.decision == "keep":
        d = ElevStepDecision(employee_id=emp.id, kind=body.kind, event_date=body.event_date, decision="keep",
                             from_type=emp.agreement_type, to_type=body.to_type, note=note,
                             decided_by=current_user.initials)
        db.add(d)
        db.flush()
        log_action(db, current_user, "elev_step_keep", "employee", emp.id,
                   f"{emp.name}: overenskomsttype '{emp.agreement_type}' bevares i stedet for "
                   f"'{body.to_type or '–'}' (trin fra {_dk(body.event_date)}). Bemærkning: {note}")
        db.commit()
        _release_claim(db, current_user, emp.id, body.event_date)
        return {"id": d.id}

    if not body.to_type or not db.query(MasterAgreementType).filter(MasterAgreementType.name == body.to_type).first():
        raise HTTPException(400, "Vælg en gyldig overenskomsttype")
    effective = period_start_for_date(body.effective_from or body.event_date)
    period = db.query(PayPeriod).filter(PayPeriod.start_date == effective).first()
    if period and period.status == PayPeriodStatus.closed:
        _release_claim(db, current_user, emp.id, body.event_date)
        raise HTTPException(400, "Lønperioden er låst (eksporteret) – vælg en senere periode")
    backpay = locked_backpay(db, emp, period_start_for_date(body.event_date), effective, body.to_type)
    from_type = agreement_type_for_period(db, emp, effective - timedelta(days=PERIOD_DAYS))
    d = ElevStepDecision(employee_id=emp.id, kind=body.kind, event_date=body.event_date, decision="approve",
                         from_type=from_type, to_type=body.to_type, effective_from=effective,
                         note=note, decided_by=current_user.initials)
    db.add(d)
    db.flush()
    log_action(db, current_user, "elev_step_approve", "employee", emp.id,
               f"{emp.name}: overenskomsttype '{from_type}' → '{body.to_type}' fra lønperioden "
               f"{dk_period(effective, effective + timedelta(days=PERIOD_DAYS - 1))}"
               + (f". Bemærkning: {note}" if note else "")
               + "".join(f" {b['text']}" for b in backpay))
    db.commit()
    _release_claim(db, current_user, emp.id, body.event_date)
    if effective <= today:
        apply_due_changes(db, today, _logger(db, current_user))
    return {"id": d.id, "backpay": backpay}


class CancelBody(BaseModel):
    note: Optional[str] = None


@router.delete("/decisions/{decision_id}", status_code=204)
def cancel_decision(decision_id: int, body: Optional[CancelBody] = None,
                    current_user: AppUser = Depends(_raise_access), db: Session = Depends(get_db)):
    """Annullér en godkendelse der endnu ikke er trådt i kraft, eller en 'behold'-beslutning
    (så advarslen kommer igen)."""
    d = db.query(ElevStepDecision).filter(ElevStepDecision.id == decision_id).first()
    if not d:
        raise HTTPException(404, "Ikke fundet")
    if d.applied_at is not None:
        raise HTTPException(400, "Skiftet er allerede trådt i kraft – ret overenskomsttypen på medarbejderen")
    emp = d.employee
    what = (f"godkendt skift '{d.from_type}' → '{d.to_type}' fra {_dk(d.effective_from)}"
            if d.decision == "approve" else f"'behold {d.from_type}' (bemærkning: {d.note})")
    note = (body.note or "").strip() if body else ""
    log_action(db, current_user, "elev_step_cancel", "employee", emp.id,
               f"{emp.name}: annulleret {what}" + (f". Bemærkning: {note}" if note else ""))
    db.delete(d)
    db.commit()


@router.get("/decisions/{employee_id}")
def list_decisions(employee_id: int, current_user: AppUser = Depends(_view_access),
                   db: Session = Depends(get_db)):
    return [{
        "id": d.id, "event_date": d.event_date, "decision": d.decision, "from_type": d.from_type,
        "to_type": d.to_type, "effective_from": d.effective_from, "note": d.note,
        "decided_by": d.decided_by, "decided_at": d.decided_at, "applied_at": d.applied_at,
    } for d in db.query(ElevStepDecision).filter(ElevStepDecision.employee_id == employee_id)
        .order_by(ElevStepDecision.event_date).all()]
