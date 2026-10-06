"""
Elevløn-trin (2026-10-06): elevoversigt (opstartstjek), indstillinger, popups,
godkend / behold / annullér. Reglerne: calculators/elev_steps.py og elev_agreement.py.

Popups vises kun for roller hvor 'elev_wage_approve' er sat EKSPLICIT – en systemrolle
(admin) har adgang til siderne, men får ikke advarslerne.
"""
from datetime import date, datetime, timedelta
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth import log_action, require_any_permission, require_permission
from calculators.elev_agreement import (
    PERIOD_DAYS, agreement_type_for_period, apply_due_changes, has_elev_steps, is_elev,
    mismatch_reason, mismatches, step_event_date, upcoming_changes,
)
from calculators.elev_steps import STEP_AGREEMENT_TYPES, step_for_period
from calculators.pay_period import period_start_for_date
from database.models import (
    AppUser, ElevStepDecision, Employee, MasterAgreementType, Paragraf56AlertDismissal,
    PayPeriod, PayPeriodStatus, Role, SystemSettings,
)
from database.session import get_db

router = APIRouter(prefix="/api/elev", tags=["elev"])

PERM = "elev_wage_approve"
_view_access = require_any_permission(PERM, "stamdata")


def _settings(db: Session) -> SystemSettings:
    s = db.query(SystemSettings).filter(SystemSettings.id == 1).first()
    if s is None:
        s = SystemSettings(id=1, auto_approval_enabled=True)
        db.add(s)
        db.commit()
    return s


def _explicit_permission(db: Session, user: AppUser, perm: str) -> bool:
    """Rettigheden er sat på rollen – systemrollens 'alle rettigheder' tæller ikke."""
    role = db.query(Role).filter(Role.name == user.role).first()
    return bool(role and perm in (role.permissions or []))


def _logger(db: Session, user: AppUser):
    return lambda action, etype, eid, details: log_action(db, user, action, etype, eid, details)


def _dk(d: Optional[date]) -> str:
    return d.strftime("%d.%m.%Y") if d else "–"


# ── Indstillinger ─────────────────────────────────────────────────────────────

def _settings_out(s: SystemSettings) -> dict:
    return {"enabled": s.elev_alerts_enabled, "notice_days": s.elev_notice_days,
            "remind_days": s.elev_remind_days}


@router.get("/settings")
def get_settings(current_user: AppUser = Depends(_view_access), db: Session = Depends(get_db)):
    return _settings_out(_settings(db))


class SettingsBody(BaseModel):
    notice_days: int = Field(ge=1, le=365)
    remind_days: Optional[int] = Field(default=None, ge=0, le=365)   # None = Aldrig


@router.put("/settings")
def put_settings(body: SettingsBody, current_user: AppUser = Depends(require_permission("stamdata")),
                 db: Session = Depends(get_db)):
    if body.remind_days is not None and body.remind_days >= body.notice_days:
        raise HTTPException(400, "'Påmind igen' skal være færre dage før end 'Varsel'")
    s = _settings(db)
    old = (s.elev_notice_days, s.elev_remind_days)
    s.elev_notice_days, s.elev_remind_days = body.notice_days, body.remind_days
    s.updated_by, s.updated_at = current_user.initials, datetime.now()
    log_action(db, current_user, "elev_settings_update", "system_settings", 1,
               f"Elevadvarsler: varsel {old[0]} → {body.notice_days} dage før, "
               f"påmind igen {old[1] if old[1] is not None else 'aldrig'} → "
               f"{body.remind_days if body.remind_days is not None else 'aldrig'} dage før")
    db.commit()
    return _settings_out(s)


@router.post("/enable")
def enable_alerts(current_user: AppUser = Depends(require_permission(PERM)), db: Session = Depends(get_db)):
    """Opstartstjek: elevoversigten er gennemgået – advarslerne kan starte."""
    s = _settings(db)
    if not s.elev_alerts_enabled:
        s.elev_alerts_enabled = True
        log_action(db, current_user, "elev_alerts_enabled", "system_settings", 1,
                   "Elevoversigt gennemgået – elevløn-advarsler slået til")
        db.commit()
    return _settings_out(s)


# ── Elevoversigt (opstartstjek) ───────────────────────────────────────────────

@router.get("/overview")
def overview(current_user: AppUser = Depends(_view_access), db: Session = Depends(get_db),
             today: Optional[date] = None):
    today = today or date.today()
    known_types = {t.name for t in db.query(MasterAgreementType).all()}
    p_start = period_start_for_date(today)
    p_end = p_start + timedelta(days=PERIOD_DAYS - 1)
    rows = []
    for emp in db.query(Employee).filter(Employee.active == True, Employee.elev == True).all():  # noqa: E712
        if not is_elev(emp):
            continue
        current_type = agreement_type_for_period(db, emp, p_start)
        row = {
            "employee_id": emp.id, "employee_name": emp.name, "employee_number": emp.employee_number,
            "elev_start_date": emp.elev_start_date, "elev_end_date": emp.elev_end_date,
            "voksenelev": emp.voksenelev, "current_type": current_type,
            "expected_type": None, "status": "", "next_change": None, "scheduled": None,
        }
        if emp.voksenelev:
            row["status"] = "voksenelev"            # almindelig løn, ingen trin
        elif not has_elev_steps(emp):
            row["status"] = "ingen_trin"            # fx EGU, disponent eller forkert type
        else:
            step = step_for_period(emp.elev_start_date, emp.elev_end_date, p_start, p_end)
            if step:
                row["expected_type"] = STEP_AGREEMENT_TYPES[step]
                row["expected_event_date"] = step_event_date(emp, step)
                row["status"] = "ok" if current_type == row["expected_type"] else "afviger"
                if row["status"] == "afviger":
                    row["mismatch_reason"] = mismatch_reason(emp, step, current_type, p_start, today)
            else:
                row["status"] = "uden_for_kontrakt"
            ups = upcoming_changes(db, emp, today)
            if ups:
                u = ups[0]
                row["next_change"] = {"event_date": u["event_date"], "effective_from": u["effective_from"],
                                      "to_type": u["to_type"]}
        sched = (db.query(ElevStepDecision)
                 .filter(ElevStepDecision.employee_id == emp.id, ElevStepDecision.decision == "approve",
                         ElevStepDecision.applied_at.is_(None))
                 .order_by(ElevStepDecision.effective_from).first())
        if sched:
            row["scheduled"] = {"id": sched.id, "to_type": sched.to_type, "effective_from": sched.effective_from}
        row["type_unknown"] = current_type not in known_types
        rows.append(row)
    rows.sort(key=lambda r: (r["elev_end_date"] or date.max, r["employee_name"]))
    missing_types = [t for t in STEP_AGREEMENT_TYPES.values() if t not in known_types]
    return {"settings": _settings_out(_settings(db)), "period_start": p_start, "period_end": p_end,
            "rows": rows, "missing_step_types": missing_types}


# ── Popups ───────────────────────────────────────────────────────────────────

def _dismissals(db: Session, user: AppUser) -> dict:
    return {(d.employee_id, d.alert_type): d.dismissed_at for d in db.query(Paragraf56AlertDismissal)
            .filter(Paragraf56AlertDismissal.user_id == user.id).all()}


def _upcoming_visible(u: dict, s: SystemSettings, dismissed: dict, today: date) -> bool:
    if today < u["effective_from"] - timedelta(days=s.elev_notice_days):
        return False
    eid, key = u["employee_id"], u["event_date"].isoformat()
    if (eid, f"elevno_{key}") in dismissed:
        return False
    snoozed_at = dismissed.get((eid, f"elevup_{key}"))
    if snoozed_at is None:
        return True
    if s.elev_remind_days is None:
        return False
    remind_on = u["effective_from"] - timedelta(days=s.elev_remind_days)
    return today >= remind_on and snoozed_at.date() < remind_on


@router.get("/alerts")
def alerts(current_user: AppUser = Depends(require_permission(PERM)), db: Session = Depends(get_db),
           today: Optional[date] = None):
    today = today or date.today()
    s = _settings(db)
    empty = {"upcoming": [], "applied": [], "mismatches": []}
    if not s.elev_alerts_enabled or not _explicit_permission(db, current_user, PERM):
        return empty
    apply_due_changes(db, today, _logger(db, current_user))
    dismissed = _dismissals(db, current_user)
    upcoming = []
    for emp in db.query(Employee).filter(Employee.active == True, Employee.elev == True).all():  # noqa: E712
        for u in upcoming_changes(db, emp, today):
            if _upcoming_visible(u, s, dismissed, today):
                upcoming.append(u)
    applied = []
    for d in (db.query(ElevStepDecision)
              .filter(ElevStepDecision.decision == "approve", ElevStepDecision.applied_at.isnot(None),
                      ElevStepDecision.effective_from <= today,
                      ElevStepDecision.effective_from > today - timedelta(days=3 * PERIOD_DAYS)).all()):
        if (d.employee_id, f"elevfx_{d.id}") in dismissed:
            continue
        emp = d.employee
        applied.append({
            "decision_id": d.id, "employee_id": emp.id, "employee_name": emp.name,
            "employee_number": emp.employee_number, "to_type": d.to_type, "from_type": d.from_type,
            "effective_from": d.effective_from,
            "effective_to": d.effective_from + timedelta(days=PERIOD_DAYS - 1),
            "took_effect": emp.agreement_type == d.to_type,
        })
    return {"upcoming": sorted(upcoming, key=lambda u: u["effective_from"]), "applied": applied,
            "mismatches": mismatches(db, today)}


class SnoozeBody(BaseModel):
    employee_id: int
    event_date: date
    mode: Literal["later", "never"]


@router.post("/snooze", status_code=204)
def snooze(body: SnoozeBody, current_user: AppUser = Depends(require_permission(PERM)),
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
def ack_applied(decision_id: int, current_user: AppUser = Depends(require_permission(PERM)),
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
    employee_id: int
    event_date: date
    decision: Literal["approve", "keep"]
    to_type: Optional[str] = None
    effective_from: Optional[date] = None   # en dag i den lønperiode skiftet skal gælde fra
    note: Optional[str] = None


@router.post("/decisions", status_code=201)
def create_decision(body: DecisionBody, current_user: AppUser = Depends(require_permission(PERM)),
                    db: Session = Depends(get_db), today: Optional[date] = None):
    today = today or date.today()
    emp = db.query(Employee).filter(Employee.id == body.employee_id).first()
    if not emp:
        raise HTTPException(404, "Medarbejder ikke fundet")
    note = (body.note or "").strip() or None
    if body.decision == "keep":
        if not note:
            raise HTTPException(400, "Skriv en bemærkning om hvorfor satsen bevares")
        d = ElevStepDecision(employee_id=emp.id, event_date=body.event_date, decision="keep",
                             from_type=emp.agreement_type, to_type=body.to_type, note=note,
                             decided_by=current_user.initials)
        db.add(d)
        db.flush()
        log_action(db, current_user, "elev_step_keep", "employee", emp.id,
                   f"{emp.name}: overenskomsttype '{emp.agreement_type}' bevares i stedet for "
                   f"'{body.to_type or '–'}' (trin fra {_dk(body.event_date)}). Bemærkning: {note}")
        db.commit()
        return {"id": d.id}

    if not body.to_type or not db.query(MasterAgreementType).filter(MasterAgreementType.name == body.to_type).first():
        raise HTTPException(400, "Vælg en gyldig overenskomsttype")
    effective = period_start_for_date(body.effective_from or body.event_date)
    period = db.query(PayPeriod).filter(PayPeriod.start_date == effective).first()
    if period and period.status == PayPeriodStatus.closed:
        raise HTTPException(400, "Lønperioden er låst (eksporteret) – vælg en senere periode")
    from_type = agreement_type_for_period(db, emp, effective - timedelta(days=PERIOD_DAYS))
    d = ElevStepDecision(employee_id=emp.id, event_date=body.event_date, decision="approve",
                         from_type=from_type, to_type=body.to_type, effective_from=effective,
                         note=note, decided_by=current_user.initials)
    db.add(d)
    db.flush()
    log_action(db, current_user, "elev_step_approve", "employee", emp.id,
               f"{emp.name}: overenskomsttype '{from_type}' → '{body.to_type}' fra lønperioden "
               f"{_dk(effective)}–{_dk(effective + timedelta(days=PERIOD_DAYS - 1))}"
               + (f". Bemærkning: {note}" if note else ""))
    db.commit()
    if effective <= today:
        apply_due_changes(db, today, _logger(db, current_user))
    return {"id": d.id}


class CancelBody(BaseModel):
    note: Optional[str] = None


@router.delete("/decisions/{decision_id}", status_code=204)
def cancel_decision(decision_id: int, body: Optional[CancelBody] = None,
                    current_user: AppUser = Depends(require_permission(PERM)), db: Session = Depends(get_db)):
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
