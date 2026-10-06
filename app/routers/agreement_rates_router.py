"""
Fremtidige overenskomstsatser (2026-10-06): Stamdata-boksen "Fremtidige satser" og den
fælles advarsel før nye satser træder i kraft. Beregningen: calculators/agreement_rates.py.
"""
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth import log_action, require_permission
from calculators.agreement_rates import apply_due_rates
from calculators.pay_period import period_start_for_date
from database.models import (
    AppUser, Employee, MasterAgreementType, MasterAgreementTypeRate, PayPeriod, PayPeriodStatus, Role,
    SystemSettings, UserAlertDismissal,
)
from database.session import get_db

router = APIRouter(prefix="/api/agreement-rates", tags=["agreement-rates"])
_access = require_permission("stamdata")


def _out(r: MasterAgreementTypeRate) -> dict:
    return {"id": r.id, "agreement_type_id": r.agreement_type_id, "agreement_type": r.agreement_type.name,
            "valid_from": r.valid_from, "hourly_rate": float(r.hourly_rate),
            "old_rate": float(r.old_rate) if r.old_rate is not None else None,
            "current_rate": float(r.agreement_type.hourly_rate), "applied": r.applied_at is not None,
            "note": r.note}


def _describe(r: MasterAgreementTypeRate) -> str:
    return (f"'{r.agreement_type.name}' {Decimal(str(r.hourly_rate)):.2f} kr fra {r.valid_from.strftime('%d.%m.%Y')}"
            + (f" (begrundelse: {r.note})" if r.note else ""))


@router.get("")
def list_rates(history: bool = False, current_user: AppUser = Depends(_access), db: Session = Depends(get_db)):
    """Fremtidige satser (og med history=true også dem der er trådt i kraft)."""
    apply_due_rates(db, date.today())
    q = db.query(MasterAgreementTypeRate)
    if not history:
        q = q.filter(MasterAgreementTypeRate.applied_at.is_(None))
    rows = q.order_by(MasterAgreementTypeRate.valid_from, MasterAgreementTypeRate.agreement_type_id).all()
    return [_out(r) for r in rows]


class RateBody(BaseModel):
    agreement_type_id: int
    valid_from: date
    hourly_rate: float = Field(gt=0)
    note: Optional[str] = Field(default=None, max_length=300)


def _validate(db: Session, body: RateBody, rate_id: Optional[int] = None) -> MasterAgreementType:
    t = db.query(MasterAgreementType).filter(MasterAgreementType.id == body.agreement_type_id).first()
    if not t:
        raise HTTPException(400, "Vælg en overenskomsttype fra listen")
    dup = db.query(MasterAgreementTypeRate).filter(
        MasterAgreementTypeRate.agreement_type_id == t.id, MasterAgreementTypeRate.valid_from == body.valid_from,
        MasterAgreementTypeRate.id != (rate_id or 0)).first()
    if dup:
        raise HTTPException(400, "Der findes allerede en sats for typen på den dato")
    period = db.query(PayPeriod).filter(PayPeriod.start_date == period_start_for_date(body.valid_from)).first()
    if period and period.status == PayPeriodStatus.closed:
        raise HTTPException(400, "Lønperioden for datoen er låst (eksporteret) – vælg en senere dato")
    return t


@router.post("", status_code=201)
def create_rate(body: RateBody, current_user: AppUser = Depends(_access), db: Session = Depends(get_db)):
    _validate(db, body)
    r = MasterAgreementTypeRate(agreement_type_id=body.agreement_type_id, valid_from=body.valid_from,
                                hourly_rate=Decimal(str(body.hourly_rate)), created_by=current_user.initials,
                                note=(body.note or "").strip() or None)
    db.add(r)
    db.flush()
    log_action(db, current_user, "stamdata_create", "agreement_rate", r.id, f"Fremtidig sats oprettet: {_describe(r)}")
    db.commit()
    apply_due_rates(db, date.today())   # en dato i dag/fortiden træder i kraft med det samme
    db.refresh(r)
    return _out(r)


@router.patch("/{rate_id}")
def update_rate(rate_id: int, body: RateBody, current_user: AppUser = Depends(_access), db: Session = Depends(get_db)):
    r = db.query(MasterAgreementTypeRate).filter(MasterAgreementTypeRate.id == rate_id).first()
    if not r:
        raise HTTPException(404, "Ikke fundet")
    if r.applied_at is not None:
        raise HTTPException(400, "Satsen er trådt i kraft og kan ikke ændres – ret den nuværende sats i stedet")
    _validate(db, body, rate_id)
    before = _describe(r)
    r.agreement_type_id, r.valid_from, r.hourly_rate = body.agreement_type_id, body.valid_from, Decimal(str(body.hourly_rate))
    r.note = (body.note or "").strip() or None
    db.flush()
    db.refresh(r)
    log_action(db, current_user, "stamdata_update", "agreement_rate", r.id, f"Fremtidig sats ændret: {before} → {_describe(r)}")
    db.commit()
    apply_due_rates(db, date.today())
    db.refresh(r)
    return _out(r)


@router.delete("/{rate_id}", status_code=204)
def delete_rate(rate_id: int, current_user: AppUser = Depends(_access), db: Session = Depends(get_db)):
    r = db.query(MasterAgreementTypeRate).filter(MasterAgreementTypeRate.id == rate_id).first()
    if not r:
        raise HTTPException(404, "Ikke fundet")
    if r.applied_at is not None:
        raise HTTPException(400, "Satsen er trådt i kraft og indgår i historikken – den kan ikke slettes")
    # Hele rækken logges, så en fejlslettet sats kan genskabes fra hændelsesloggen
    log_action(db, current_user, "stamdata_delete", "agreement_rate", r.id, f"Fremtidig sats slettet: {_describe(r)}")
    db.delete(r)
    db.commit()


# ── Fælles advarsel: nye satser træder snart i kraft ──────────────────────────

def _explicit(db: Session, user: AppUser, perm: str) -> bool:
    role = db.query(Role).filter(Role.name == user.role).first()
    return bool(role and perm in (role.permissions or []))


@router.get("/alerts")
def rate_alerts(current_user: AppUser = Depends(require_permission("payroll")), db: Session = Depends(get_db),
                today: Optional[date] = None):
    """Til roller med 'Lønkørsel' sat eksplicit: nye satser der træder i kraft inden for
    varslet (samme 'Varsel'-indstilling som elevløn). Én advarsel pr. dato."""
    today = today or date.today()
    if not _explicit(db, current_user, "payroll"):
        return []
    s = db.query(SystemSettings).filter(SystemSettings.id == 1).first()
    notice = s.elev_notice_days if s else 30
    dismissed = {d.key for d in db.query(UserAlertDismissal).filter(UserAlertDismissal.user_id == current_user.id).all()}
    groups: dict = {}
    for r in db.query(MasterAgreementTypeRate).filter(MasterAgreementTypeRate.applied_at.is_(None)).all():
        p_start = period_start_for_date(r.valid_from)
        if not (p_start - timedelta(days=notice) <= today < r.valid_from) or f"rates_{r.valid_from}" in dismissed:
            continue
        g = groups.setdefault(r.valid_from, {"valid_from": r.valid_from, "period_start": p_start,
                                             "period_end": p_start + timedelta(days=13), "rates": []})
        employees = (db.query(Employee).filter(Employee.active == True,  # noqa: E712
                                               Employee.agreement_type == r.agreement_type.name)
                     .order_by(Employee.first_name, Employee.last_name).all())
        g["rates"].append({"agreement_type": r.agreement_type.name, "current_rate": float(r.agreement_type.hourly_rate),
                           "new_rate": float(r.hourly_rate), "note": r.note,
                           "employees": [e.name for e in employees]})
    return sorted(groups.values(), key=lambda g: g["valid_from"])


class DismissBody(BaseModel):
    valid_from: date


@router.post("/alerts/dismiss", status_code=204)
def dismiss_rate_alert(body: DismissBody, current_user: AppUser = Depends(require_permission("payroll")),
                       db: Session = Depends(get_db)):
    key = f"rates_{body.valid_from}"
    if not db.query(UserAlertDismissal).filter(UserAlertDismissal.user_id == current_user.id,
                                               UserAlertDismissal.key == key).first():
        db.add(UserAlertDismissal(user_id=current_user.id, key=key))
        db.commit()
