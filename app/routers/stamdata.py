"""
Stamdata – CRUD for overenskomsttyper, overtidssatser, tillæg og løntypekoder.
Kun tilgængeligt for administratorer (kræver 'stamdata'-tilladelse).
"""
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth import get_current_user, log_action, require_permission
from database.models import (
    AppUser, Employee, DispatcherGroup, Vehicle,
    MasterAgreementType, MasterAgreementKind, MasterOvertimeRate,
    MasterSupplementRate, MasterPayType, MasterAbsenceType, MasterCvrNumber,
    MasterPosition, Holiday,
)
from database.session import get_db
from utils.natural_sort import natural_key

router = APIRouter(prefix="/api/stamdata", tags=["stamdata"])
_access = require_permission("stamdata")


def _normalize_absence_key(label: str) -> str:
    overrides = {"Kursus/Skole": "skole_kursus"}
    if label in overrides:
        return overrides[label]
    s = label.lower()
    s = s.replace("§", "paragraf_")
    s = s.replace("æ", "ae").replace("ø", "oe").replace("å", "aa")
    s = s.replace(" ", "_").replace("/", "_").replace(".", "").replace("-", "_")
    while "__" in s:
        s = s.replace("__", "_")
    return s.strip("_")


# ── Overenskomsttyper ──────────────────────────────────────────────────────


class AgreementTypeBody(BaseModel):
    name: Optional[str] = None
    hourly_rate: Optional[float] = Field(default=None, gt=0)


@router.get("/agreement-types")
def list_agreement_types(
    current_user: AppUser = Depends(_access),
    db: Session = Depends(get_db),
):
    from datetime import date
    from calculators.agreement_rates import apply_due_rates
    apply_due_rates(db, date.today())   # fremtidige satser hvis dato er nået
    rows = db.query(MasterAgreementType).order_by(MasterAgreementType.name).all()
    return [{"id": r.id, "name": r.name, "hourly_rate": float(r.hourly_rate)} for r in rows]


@router.post("/agreement-types", status_code=201)
def create_agreement_type(
    body: AgreementTypeBody,
    current_user: AppUser = Depends(_access),
    db: Session = Depends(get_db),
):
    if not body.name or body.hourly_rate is None:
        raise HTTPException(400, "Navn og timesats er påkrævet")
    if db.query(MasterAgreementType).filter(MasterAgreementType.name == body.name).first():
        raise HTTPException(400, "En overenskomsttype med dette navn eksisterer allerede")
    row = MasterAgreementType(name=body.name.strip(), hourly_rate=Decimal(str(body.hourly_rate)))
    db.add(row)
    db.commit()
    db.refresh(row)
    log_action(db, current_user, "stamdata_create", "agreement_type", row.id,
               f"Oprettet overenskomsttype: {row.name} ({body.hourly_rate} kr/t)")
    db.commit()
    return {"id": row.id, "name": row.name, "hourly_rate": float(row.hourly_rate)}


@router.patch("/agreement-types/{agreement_id}")
def update_agreement_type(
    agreement_id: int,
    body: AgreementTypeBody,
    current_user: AppUser = Depends(_access),
    db: Session = Depends(get_db),
):
    row = db.query(MasterAgreementType).filter(MasterAgreementType.id == agreement_id).first()
    if not row:
        raise HTTPException(404, "Ikke fundet")
    old_name_before = row.name
    if body.name is not None:
        conflict = db.query(MasterAgreementType).filter(
            MasterAgreementType.name == body.name.strip(),
            MasterAgreementType.id != agreement_id,
        ).first()
        if conflict:
            raise HTTPException(400, "Et andet overenskomsttype med dette navn eksisterer allerede")
        row.name = body.name.strip()
    old_name, old_rate = old_name_before, row.hourly_rate
    if body.hourly_rate is not None:
        row.hourly_rate = Decimal(str(body.hourly_rate))
    db.commit()
    log_action(db, current_user, "stamdata_update", "agreement_type", row.id,
               f"Opdateret overenskomsttype: '{old_name}' {Decimal(str(old_rate)):.2f} kr → "
               f"'{row.name}' {Decimal(str(row.hourly_rate)):.2f} kr")
    db.commit()
    return {"id": row.id, "name": row.name, "hourly_rate": float(row.hourly_rate)}


@router.delete("/agreement-types/{agreement_id}", status_code=204)
def delete_agreement_type(
    agreement_id: int,
    current_user: AppUser = Depends(_access),
    db: Session = Depends(get_db),
):
    row = db.query(MasterAgreementType).filter(MasterAgreementType.id == agreement_id).first()
    if not row:
        raise HTTPException(404, "Ikke fundet")
    in_use = db.query(Employee).filter(
        Employee.agreement_type == row.name,
        Employee.active == True,
    ).count()
    if in_use:
        raise HTTPException(
            400,
            f"Kan ikke slettes – {in_use} aktiv(e) medarbejder(e) bruger denne overenskomsttype",
        )
    from database.models import MasterAgreementTypeRate
    rates = db.query(MasterAgreementTypeRate).filter(MasterAgreementTypeRate.agreement_type_id == row.id).all()
    if any(r.applied_at is None for r in rates):
        raise HTTPException(400, "Kan ikke slettes – typen har fremtidige satser. Slet dem først.")
    history = ", ".join(f"{r.valid_from}: {Decimal(str(r.hourly_rate)):.2f}" for r in rates)
    log_action(db, current_user, "stamdata_delete", "agreement_type", row.id,
               f"Slettet overenskomsttype: '{row.name}' ({Decimal(str(row.hourly_rate)):.2f} kr)"
               + (f". Sats-historik: {history}" if history else ""))
    for r in rates:
        db.delete(r)
    db.delete(row)
    db.commit()


# ── Overtidssatser ─────────────────────────────────────────────────────────


class RateBody(BaseModel):
    rate: float = Field(gt=0)


class NewRateBody(BaseModel):
    label: str
    rate: float = Field(gt=0)


@router.get("/overtime-rates")
def list_overtime_rates(
    current_user: AppUser = Depends(_access),
    db: Session = Depends(get_db),
):
    rows = db.query(MasterOvertimeRate).order_by(MasterOvertimeRate.id).all()
    return [{"id": r.id, "label": r.label, "rate": float(r.rate), "is_user_created": r.is_user_created} for r in rows]


@router.post("/overtime-rates", status_code=201)
def create_overtime_rate(
    body: NewRateBody,
    current_user: AppUser = Depends(_access),
    db: Session = Depends(get_db),
):
    label = body.label.strip()
    if not label:
        raise HTTPException(400, "Betegnelse er påkrævet")
    if db.query(MasterOvertimeRate).filter(MasterOvertimeRate.label == label).first():
        raise HTTPException(400, "En overtidssats med dette navn eksisterer allerede")
    row = MasterOvertimeRate(label=label, rate=Decimal(str(body.rate)), is_user_created=True)
    db.add(row)
    db.commit()
    db.refresh(row)
    log_action(db, current_user, "stamdata_create", "overtime_rate", row.id,
               f"Ny overtidssats oprettet: {row.label} = {body.rate}")
    db.commit()
    return {"id": row.id, "label": row.label, "rate": float(row.rate), "is_user_created": row.is_user_created}


@router.patch("/overtime-rates/{rate_id}")
def update_overtime_rate(
    rate_id: int,
    body: RateBody,
    current_user: AppUser = Depends(_access),
    db: Session = Depends(get_db),
):
    row = db.query(MasterOvertimeRate).filter(MasterOvertimeRate.id == rate_id).first()
    if not row:
        raise HTTPException(404, "Ikke fundet")
    row.rate = Decimal(str(body.rate))
    db.commit()
    log_action(db, current_user, "stamdata_update", "overtime_rate", row.id,
               f"Overtidssats opdateret: {row.label} = {body.rate}")
    db.commit()
    return {"id": row.id, "label": row.label, "rate": float(row.rate), "is_user_created": row.is_user_created}


@router.delete("/overtime-rates/{rate_id}", status_code=204)
def delete_overtime_rate(
    rate_id: int,
    current_user: AppUser = Depends(_access),
    db: Session = Depends(get_db),
):
    row = db.query(MasterOvertimeRate).filter(MasterOvertimeRate.id == rate_id).first()
    if not row:
        raise HTTPException(404, "Ikke fundet")
    if not row.is_user_created:
        raise HTTPException(400, "Systemsatser kan ikke slettes")
    in_use = db.query(MasterPayType).filter(MasterPayType.csv_rate_source == f"overtime:{rate_id}").first()
    if in_use:
        raise HTTPException(400, f"Kan ikke slettes – bruges som sats-kilde af løntypekoden '{in_use.label}'")
    log_action(db, current_user, "stamdata_delete", "overtime_rate", row.id,
               f"Slettet overtidssats: {row.label}")
    db.delete(row)
    db.commit()


# ── Tillæg ─────────────────────────────────────────────────────────────────


@router.get("/supplements")
def list_supplements(
    current_user: AppUser = Depends(_access),
    db: Session = Depends(get_db),
):
    rows = db.query(MasterSupplementRate).order_by(MasterSupplementRate.id).all()
    return [{"id": r.id, "label": r.label, "rate": float(r.rate), "is_user_created": r.is_user_created} for r in rows]


@router.post("/supplements", status_code=201)
def create_supplement(
    body: NewRateBody,
    current_user: AppUser = Depends(_access),
    db: Session = Depends(get_db),
):
    label = body.label.strip()
    if not label:
        raise HTTPException(400, "Betegnelse er påkrævet")
    if db.query(MasterSupplementRate).filter(MasterSupplementRate.label == label).first():
        raise HTTPException(400, "Et tillæg med dette navn eksisterer allerede")
    row = MasterSupplementRate(label=label, rate=Decimal(str(body.rate)), is_user_created=True)
    db.add(row)
    db.commit()
    db.refresh(row)
    log_action(db, current_user, "stamdata_create", "supplement_rate", row.id,
               f"Nyt tillæg oprettet: {row.label} = {body.rate}")
    db.commit()
    return {"id": row.id, "label": row.label, "rate": float(row.rate), "is_user_created": row.is_user_created}


@router.patch("/supplements/{supplement_id}")
def update_supplement(
    supplement_id: int,
    body: RateBody,
    current_user: AppUser = Depends(_access),
    db: Session = Depends(get_db),
):
    row = db.query(MasterSupplementRate).filter(MasterSupplementRate.id == supplement_id).first()
    if not row:
        raise HTTPException(404, "Ikke fundet")
    row.rate = Decimal(str(body.rate))
    db.commit()
    log_action(db, current_user, "stamdata_update", "supplement_rate", row.id,
               f"Tillægssats opdateret: {row.label} = {body.rate}")
    db.commit()
    return {"id": row.id, "label": row.label, "rate": float(row.rate), "is_user_created": row.is_user_created}


@router.delete("/supplements/{supplement_id}", status_code=204)
def delete_supplement(
    supplement_id: int,
    current_user: AppUser = Depends(_access),
    db: Session = Depends(get_db),
):
    row = db.query(MasterSupplementRate).filter(MasterSupplementRate.id == supplement_id).first()
    if not row:
        raise HTTPException(404, "Ikke fundet")
    if not row.is_user_created:
        raise HTTPException(400, "Systemtillæg kan ikke slettes")
    in_use = db.query(MasterPayType).filter(MasterPayType.csv_rate_source == f"supplement:{supplement_id}").first()
    if in_use:
        raise HTTPException(400, f"Kan ikke slettes – bruges som sats-kilde af løntypekoden '{in_use.label}'")
    log_action(db, current_user, "stamdata_delete", "supplement_rate", row.id,
               f"Slettet tillæg: {row.label}")
    db.delete(row)
    db.commit()


# ── Løntypekoder ───────────────────────────────────────────────────────────


class PayTypeBody(BaseModel):
    label: Optional[str] = None
    danloen_code: Optional[str] = None
    include_in_csv: Optional[bool] = None
    csv_quantity_type: Optional[str] = None
    csv_rate_source: Optional[str] = None
    csv_include_rate: Optional[bool] = None
    csv_include_total: Optional[bool] = None


def _normalize_pay_type_key(label: str) -> str:
    s = label.lower()
    s = s.replace("æ", "ae").replace("ø", "oe").replace("å", "aa")
    s = s.replace(" ", "_").replace("/", "_").replace(".", "").replace("-", "_")
    while "__" in s:
        s = s.replace("__", "_")
    return s.strip("_")


@router.get("/pay-types")
def list_pay_types(
    current_user: AppUser = Depends(_access),
    db: Session = Depends(get_db),
):
    rows = db.query(MasterPayType).order_by(MasterPayType.sort_order).all()
    return [{
        "id": r.id,
        "code_key": r.code_key,
        "label": r.label,
        "danloen_code": r.danloen_code,
        "include_in_csv": r.include_in_csv,
        "csv_quantity_type": r.csv_quantity_type or "hours",
        "csv_rate_source": r.csv_rate_source or "hourly",
        "csv_include_rate": r.csv_include_rate if r.csv_include_rate is not None else True,
        "csv_include_total": r.csv_include_total or False,
        "is_user_created": r.is_user_created,
    } for r in rows]


class NewPayTypeBody(BaseModel):
    label: str
    danloen_code: str = ""
    include_in_csv: bool = True
    csv_quantity_type: str = "hours"
    csv_rate_source: str = "hourly"
    csv_include_rate: bool = True
    csv_include_total: bool = False


@router.post("/pay-types", status_code=201)
def create_pay_type(
    body: NewPayTypeBody,
    current_user: AppUser = Depends(_access),
    db: Session = Depends(get_db),
):
    label = body.label.strip()
    if not label:
        raise HTTPException(400, "Betegnelse er påkrævet")
    code_key = _normalize_pay_type_key(label)
    if db.query(MasterPayType).filter(MasterPayType.code_key == code_key).first():
        raise HTTPException(400, "En løntypekode med denne betegnelse (eller tilsvarende nøgle) eksisterer allerede")
    max_order = db.query(MasterPayType).count()
    row = MasterPayType(
        code_key=code_key,
        label=label,
        danloen_code=body.danloen_code.strip(),
        include_in_csv=body.include_in_csv,
        csv_quantity_type=body.csv_quantity_type,
        csv_rate_source=body.csv_rate_source,
        csv_include_rate=body.csv_include_rate,
        csv_include_total=body.csv_include_total,
        sort_order=max_order + 1,
        is_user_created=True,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    log_action(db, current_user, "stamdata_create", "pay_type", row.id,
               f"Ny løntypekode oprettet: {row.label} ({row.code_key}) → {row.danloen_code}")
    db.commit()
    return {
        "id": row.id, "code_key": row.code_key, "label": row.label,
        "danloen_code": row.danloen_code, "include_in_csv": row.include_in_csv,
        "csv_quantity_type": row.csv_quantity_type, "csv_rate_source": row.csv_rate_source,
        "csv_include_rate": row.csv_include_rate, "csv_include_total": row.csv_include_total,
        "is_user_created": row.is_user_created,
    }


@router.delete("/pay-types/{pay_type_id}", status_code=204)
def delete_pay_type(
    pay_type_id: int,
    current_user: AppUser = Depends(_access),
    db: Session = Depends(get_db),
):
    row = db.query(MasterPayType).filter(MasterPayType.id == pay_type_id).first()
    if not row:
        raise HTTPException(404, "Ikke fundet")
    log_action(db, current_user, "stamdata_delete", "pay_type", row.id,
               f"Slettet løntypekode: {row.label}")
    db.delete(row)
    db.commit()


@router.patch("/pay-types/{pay_type_id}")
def update_pay_type(
    pay_type_id: int,
    body: PayTypeBody,
    current_user: AppUser = Depends(_access),
    db: Session = Depends(get_db),
):
    row = db.query(MasterPayType).filter(MasterPayType.id == pay_type_id).first()
    if not row:
        raise HTTPException(404, "Ikke fundet")
    if body.label is not None:
        label = body.label.strip()
        if not label:
            raise HTTPException(400, "Type må ikke være tom")
        row.label = label
    if body.danloen_code is not None:
        row.danloen_code = body.danloen_code.strip()
    if body.include_in_csv is not None:
        row.include_in_csv = body.include_in_csv
    if body.csv_quantity_type is not None:
        row.csv_quantity_type = body.csv_quantity_type
    if body.csv_rate_source is not None:
        row.csv_rate_source = body.csv_rate_source
    if body.csv_include_rate is not None:
        row.csv_include_rate = body.csv_include_rate
    if body.csv_include_total is not None:
        row.csv_include_total = body.csv_include_total
    db.commit()
    log_action(db, current_user, "stamdata_update", "pay_type", row.id,
               f"Løntypekode opdateret: {row.label} → kode={row.danloen_code}, CSV={row.include_in_csv}")
    db.commit()
    return {
        "id": row.id,
        "code_key": row.code_key,
        "label": row.label,
        "danloen_code": row.danloen_code,
        "include_in_csv": row.include_in_csv,
        "csv_quantity_type": row.csv_quantity_type,
        "csv_rate_source": row.csv_rate_source,
        "csv_include_rate": row.csv_include_rate,
        "csv_include_total": row.csv_include_total,
    }


# ── Fraværstyper ────────────────────────────────────────────────────────────


class AbsenceTypeBody(BaseModel):
    label: Optional[str] = None
    is_active: Optional[bool] = None


def _absence_row(r) -> dict:
    return {
        "id": r.id,
        "label": r.label,
        "normalized_key": r.normalized_key,
        "is_active": r.is_active,
        "is_user_created": r.is_user_created,
    }


@router.get("/absence-types")
def list_absence_types(
    current_user: AppUser = Depends(_access),
    db: Session = Depends(get_db),
):
    rows = db.query(MasterAbsenceType).order_by(
        MasterAbsenceType.sort_order, MasterAbsenceType.label
    ).all()
    return [_absence_row(r) for r in rows]


@router.post("/absence-types", status_code=201)
def create_absence_type(
    body: AbsenceTypeBody,
    current_user: AppUser = Depends(_access),
    db: Session = Depends(get_db),
):
    if not body.label:
        raise HTTPException(400, "Betegnelse er påkrævet")
    label = body.label.strip()
    key = _normalize_absence_key(label)
    if db.query(MasterAbsenceType).filter(MasterAbsenceType.normalized_key == key).first():
        raise HTTPException(400, "En fraværstype med denne betegnelse (eller tilsvarende nøgle) eksisterer allerede")
    max_order = db.query(MasterAbsenceType).count()
    row = MasterAbsenceType(
        label=label, normalized_key=key,
        is_active=True, is_user_created=True,
        sort_order=max_order + 1,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    log_action(db, current_user, "stamdata_create", "absence_type", row.id,
               f"Oprettet fraværstype: {row.label}")
    db.commit()
    return _absence_row(row)


@router.patch("/absence-types/{absence_id}")
def update_absence_type(
    absence_id: int,
    body: AbsenceTypeBody,
    current_user: AppUser = Depends(_access),
    db: Session = Depends(get_db),
):
    row = db.query(MasterAbsenceType).filter(MasterAbsenceType.id == absence_id).first()
    if not row:
        raise HTTPException(404, "Ikke fundet")
    if body.label is not None:
        label = body.label.strip()
        new_key = _normalize_absence_key(label)
        conflict = db.query(MasterAbsenceType).filter(
            MasterAbsenceType.normalized_key == new_key,
            MasterAbsenceType.id != absence_id,
        ).first()
        if conflict:
            raise HTTPException(400, "En anden fraværstype med denne betegnelse eksisterer allerede")
        row.label = label
        row.normalized_key = new_key
    if body.is_active is not None:
        row.is_active = body.is_active
    db.commit()
    log_action(db, current_user, "stamdata_update", "absence_type", row.id,
               f"Fraværstype opdateret: {row.label}, aktiv={row.is_active}")
    db.commit()
    return _absence_row(row)


@router.delete("/absence-types/{absence_id}", status_code=204)
def delete_absence_type(
    absence_id: int,
    current_user: AppUser = Depends(_access),
    db: Session = Depends(get_db),
):
    row = db.query(MasterAbsenceType).filter(MasterAbsenceType.id == absence_id).first()
    if not row:
        raise HTTPException(404, "Ikke fundet")
    log_action(db, current_user, "stamdata_delete", "absence_type", row.id,
               f"Slettet fraværstype: {row.label}")
    db.delete(row)
    db.commit()


# ── Stillinger ────────────────────────────────────────────────────────────

class PositionBody(BaseModel):
    name: str


def _position_row(db: Session, r: MasterPosition) -> dict:
    count = db.query(Employee).filter(Employee.position_id == r.id).count()
    return {"id": r.id, "name": r.name, "employee_count": count}


def _clean_position_name(db: Session, name: str, exclude_id: Optional[int] = None) -> str:
    clean = (name or "").strip()
    if not clean:
        raise HTTPException(400, "Navn er påkrævet")
    for other in db.query(MasterPosition).all():
        if other.id != exclude_id and other.name.lower() == clean.lower():
            raise HTTPException(400, "En stilling med dette navn eksisterer allerede")
    return clean


@router.get("/positions")
def list_positions_stamdata(current_user: AppUser = Depends(_access), db: Session = Depends(get_db)):
    rows = sorted(db.query(MasterPosition).all(), key=lambda r: r.name.lower())
    return [_position_row(db, r) for r in rows]


@router.post("/positions", status_code=201)
def create_position(body: PositionBody, current_user: AppUser = Depends(_access),
                    db: Session = Depends(get_db)):
    row = MasterPosition(name=_clean_position_name(db, body.name))
    db.add(row)
    db.commit()
    db.refresh(row)
    log_action(db, current_user, "stamdata_create", "position", row.id, f"Oprettet stilling: {row.name}")
    db.commit()
    return _position_row(db, row)


@router.patch("/positions/{position_id}")
def update_position(position_id: int, body: PositionBody, current_user: AppUser = Depends(_access),
                    db: Session = Depends(get_db)):
    row = db.query(MasterPosition).filter(MasterPosition.id == position_id).first()
    if not row:
        raise HTTPException(404, "Ikke fundet")
    row.name = _clean_position_name(db, body.name, exclude_id=position_id)
    db.commit()
    log_action(db, current_user, "stamdata_update", "position", row.id, f"Stilling omdøbt: {row.name}")
    db.commit()
    return _position_row(db, row)


@router.delete("/positions/{position_id}", status_code=204)
def delete_position(position_id: int, current_user: AppUser = Depends(_access),
                    db: Session = Depends(get_db)):
    row = db.query(MasterPosition).filter(MasterPosition.id == position_id).first()
    if not row:
        raise HTTPException(404, "Ikke fundet")
    in_use = db.query(Employee).filter(Employee.position_id == position_id).count()
    if in_use:
        raise HTTPException(400, f"Stillingen bruges af {in_use} medarbejder(e) og kan ikke slettes")
    log_action(db, current_user, "stamdata_delete", "position", row.id, f"Slettet stilling: {row.name}")
    db.delete(row)
    db.commit()


# ── Aftaletyper ───────────────────────────────────────────────────────────


class AgreementKindBody(BaseModel):
    label: Optional[str] = None
    is_active: Optional[bool] = None
    requires_agreement_type: Optional[bool] = None


def _agreement_kind_row(r) -> dict:
    return {
        "id": r.id,
        "key": r.key,
        "label": r.label,
        "is_active": r.is_active,
        "is_user_created": r.is_user_created,
        "requires_agreement_type": r.requires_agreement_type,
    }


@router.get("/agreement-kinds")
def list_agreement_kinds(
    current_user: AppUser = Depends(_access),
    db: Session = Depends(get_db),
):
    rows = db.query(MasterAgreementKind).order_by(
        MasterAgreementKind.sort_order, MasterAgreementKind.label
    ).all()
    return [_agreement_kind_row(r) for r in rows]


@router.post("/agreement-kinds", status_code=201)
def create_agreement_kind(
    body: AgreementKindBody,
    current_user: AppUser = Depends(_access),
    db: Session = Depends(get_db),
):
    if not body.label:
        raise HTTPException(400, "Betegnelse er påkrævet")
    label = body.label.strip()
    key = _normalize_absence_key(label)  # generisk slug-normalisering, trods navnet
    if db.query(MasterAgreementKind).filter(MasterAgreementKind.key == key).first():
        raise HTTPException(400, "En aftaletype med denne betegnelse (eller tilsvarende nøgle) eksisterer allerede")
    max_order = db.query(MasterAgreementKind).count()
    row = MasterAgreementKind(
        key=key, label=label,
        is_active=True, is_user_created=True,
        requires_agreement_type=(
            body.requires_agreement_type if body.requires_agreement_type is not None else True
        ),
        sort_order=max_order + 1,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    log_action(db, current_user, "stamdata_create", "agreement_kind", row.id,
               f"Oprettet aftaletype: {row.label}")
    db.commit()
    return _agreement_kind_row(row)


@router.patch("/agreement-kinds/{kind_id}")
def update_agreement_kind(
    kind_id: int,
    body: AgreementKindBody,
    current_user: AppUser = Depends(_access),
    db: Session = Depends(get_db),
):
    row = db.query(MasterAgreementKind).filter(MasterAgreementKind.id == kind_id).first()
    if not row:
        raise HTTPException(404, "Ikke fundet")
    if body.label is not None:
        row.label = body.label.strip()
    if body.is_active is not None:
        row.is_active = body.is_active
    if body.requires_agreement_type is not None:
        row.requires_agreement_type = body.requires_agreement_type
    db.commit()
    log_action(db, current_user, "stamdata_update", "agreement_kind", row.id,
               f"Aftaletype opdateret: {row.label}, aktiv={row.is_active}")
    db.commit()
    return _agreement_kind_row(row)


@router.delete("/agreement-kinds/{kind_id}", status_code=204)
def delete_agreement_kind(
    kind_id: int,
    current_user: AppUser = Depends(_access),
    db: Session = Depends(get_db),
):
    row = db.query(MasterAgreementKind).filter(MasterAgreementKind.id == kind_id).first()
    if not row:
        raise HTTPException(404, "Ikke fundet")
    if not row.is_user_created:
        raise HTTPException(400, "Systemtyper kan ikke slettes")
    in_use = db.query(Employee).filter(Employee.agreement_kind == row.key).first()
    if in_use:
        raise HTTPException(400, f"Kan ikke slettes – bruges af medarbejderen '{in_use.name}'")
    log_action(db, current_user, "stamdata_delete", "agreement_kind", row.id,
               f"Slettet aftaletype: {row.label}")
    db.delete(row)
    db.commit()


# ── Disponentgrupper ─────────────────────────────────────────────────────────


class DispatcherGroupBody(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    visible_in_activity_overview: Optional[bool] = None
    visible_in_dagsplan: Optional[bool] = None
    vehicle_id: Optional[int] = None


def _dispatcher_group_row(r) -> dict:
    return {
        "id": r.id,
        "name": r.name,
        "description": r.description,
        "employee_count": len(r.employees),
        "visible_in_activity_overview": r.visible_in_activity_overview,
        "visible_in_dagsplan": r.visible_in_dagsplan,
        "vehicle_id": r.vehicle_id,
        "vehicle_number": r.vehicle.vehicle_number if r.vehicle else None,
    }


@router.get("/dispatcher-groups")
def list_dispatcher_groups(
    current_user: AppUser = Depends(_access),
    db: Session = Depends(get_db),
):
    rows = sorted(db.query(DispatcherGroup).all(), key=lambda g: natural_key(g.name))
    return [_dispatcher_group_row(r) for r in rows]


@router.post("/dispatcher-groups", status_code=201)
def create_dispatcher_group(
    body: DispatcherGroupBody,
    current_user: AppUser = Depends(_access),
    db: Session = Depends(get_db),
):
    if not body.name:
        raise HTTPException(400, "Navn er påkrævet")
    name = body.name.strip()
    if db.query(DispatcherGroup).filter(DispatcherGroup.name == name).first():
        raise HTTPException(400, "En disponentgruppe med dette navn eksisterer allerede")
    if body.vehicle_id is not None and not db.query(Vehicle).filter(
        Vehicle.id == body.vehicle_id, Vehicle.deleted_at.is_(None)
    ).first():
        raise HTTPException(400, "Ukendt køretøj")
    row = DispatcherGroup(
        name=name,
        description=(body.description or "").strip() or None,
        visible_in_activity_overview=(
            body.visible_in_activity_overview
            if body.visible_in_activity_overview is not None
            else True
        ),
        visible_in_dagsplan=bool(body.visible_in_dagsplan),
        vehicle_id=body.vehicle_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    log_action(db, current_user, "stamdata_create", "dispatcher_group", row.id,
               f"Oprettet disponentgruppe: {row.name}")
    db.commit()
    return _dispatcher_group_row(row)


@router.patch("/dispatcher-groups/{group_id}")
def update_dispatcher_group(
    group_id: int,
    body: DispatcherGroupBody,
    current_user: AppUser = Depends(_access),
    db: Session = Depends(get_db),
):
    row = db.query(DispatcherGroup).filter(DispatcherGroup.id == group_id).first()
    if not row:
        raise HTTPException(404, "Ikke fundet")
    if body.name is not None:
        name = body.name.strip()
        if not name:
            raise HTTPException(400, "Navn er påkrævet")
        conflict = db.query(DispatcherGroup).filter(
            DispatcherGroup.name == name,
            DispatcherGroup.id != group_id,
        ).first()
        if conflict:
            raise HTTPException(400, "En anden disponentgruppe med dette navn eksisterer allerede")
        row.name = name
    if body.description is not None:
        row.description = body.description.strip() or None
    if body.visible_in_activity_overview is not None:
        row.visible_in_activity_overview = body.visible_in_activity_overview
    if body.visible_in_dagsplan is not None:
        row.visible_in_dagsplan = body.visible_in_dagsplan
    if "vehicle_id" in body.model_fields_set:
        if body.vehicle_id is not None and not db.query(Vehicle).filter(
            Vehicle.id == body.vehicle_id, Vehicle.deleted_at.is_(None)
        ).first():
            raise HTTPException(400, "Ukendt køretøj")
        row.vehicle_id = body.vehicle_id
    db.commit()
    log_action(db, current_user, "stamdata_update", "dispatcher_group", row.id,
               f"Disponentgruppe opdateret: {row.name}")
    db.commit()
    return _dispatcher_group_row(row)


@router.delete("/dispatcher-groups/{group_id}", status_code=204)
def delete_dispatcher_group(
    group_id: int,
    current_user: AppUser = Depends(_access),
    db: Session = Depends(get_db),
):
    row = db.query(DispatcherGroup).filter(DispatcherGroup.id == group_id).first()
    if not row:
        raise HTTPException(404, "Ikke fundet")
    log_action(db, current_user, "stamdata_delete", "dispatcher_group", row.id,
               f"Slettet disponentgruppe: {row.name}")
    row.employees = []
    db.delete(row)
    db.commit()


# ── CVR-numre ────────────────────────────────────────────────────────────────


def _cvr_row(r) -> dict:
    return {
        "id": r.id,
        "cvr_number": r.cvr_number,
        "company_name": r.company_name,
        "is_default": r.is_default,
    }


class CvrBody(BaseModel):
    cvr_number: Optional[str] = None
    company_name: Optional[str] = None


@router.get("/cvr-numbers")
def list_cvr_numbers(
    current_user: AppUser = Depends(_access),
    db: Session = Depends(get_db),
):
    rows = db.query(MasterCvrNumber).order_by(MasterCvrNumber.id).all()
    return [_cvr_row(r) for r in rows]


@router.post("/cvr-numbers", status_code=201)
def create_cvr_number(
    body: CvrBody,
    current_user: AppUser = Depends(_access),
    db: Session = Depends(get_db),
):
    if not body.cvr_number or not body.cvr_number.strip():
        raise HTTPException(400, "CVR-nummer er påkrævet")
    cvr = body.cvr_number.strip()
    if db.query(MasterCvrNumber).filter(MasterCvrNumber.cvr_number == cvr).first():
        raise HTTPException(400, "CVR-nummeret eksisterer allerede")
    row = MasterCvrNumber(
        cvr_number=cvr,
        company_name=(body.company_name or "").strip(),
        is_default=db.query(MasterCvrNumber).count() == 0,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    log_action(db, current_user, "stamdata_create", "cvr_number", row.id,
               f"Oprettet CVR: {cvr}")
    db.commit()
    return _cvr_row(row)


@router.patch("/cvr-numbers/{cvr_id}")
def update_cvr_number(
    cvr_id: int,
    body: CvrBody,
    current_user: AppUser = Depends(_access),
    db: Session = Depends(get_db),
):
    row = db.query(MasterCvrNumber).filter(MasterCvrNumber.id == cvr_id).first()
    if not row:
        raise HTTPException(404, "Ikke fundet")
    if body.cvr_number is not None:
        cvr = body.cvr_number.strip()
        conflict = db.query(MasterCvrNumber).filter(
            MasterCvrNumber.cvr_number == cvr,
            MasterCvrNumber.id != cvr_id,
        ).first()
        if conflict:
            raise HTTPException(400, "CVR-nummeret er allerede i brug")
        row.cvr_number = cvr
    if body.company_name is not None:
        row.company_name = body.company_name.strip()
    db.commit()
    log_action(db, current_user, "stamdata_update", "cvr_number", row.id,
               f"Opdateret CVR: {row.cvr_number}")
    db.commit()
    return _cvr_row(row)


@router.post("/cvr-numbers/{cvr_id}/set-default", status_code=200)
def set_default_cvr(
    cvr_id: int,
    current_user: AppUser = Depends(_access),
    db: Session = Depends(get_db),
):
    row = db.query(MasterCvrNumber).filter(MasterCvrNumber.id == cvr_id).first()
    if not row:
        raise HTTPException(404, "Ikke fundet")
    db.query(MasterCvrNumber).update({"is_default": False})
    row.is_default = True
    db.commit()
    log_action(db, current_user, "stamdata_update", "cvr_number", row.id,
               f"Standard CVR sat til: {row.cvr_number}")
    db.commit()
    return _cvr_row(row)


@router.delete("/cvr-numbers/{cvr_id}", status_code=204)
def delete_cvr_number(
    cvr_id: int,
    current_user: AppUser = Depends(_access),
    db: Session = Depends(get_db),
):
    row = db.query(MasterCvrNumber).filter(MasterCvrNumber.id == cvr_id).first()
    if not row:
        raise HTTPException(404, "Ikke fundet")
    if row.is_default:
        raise HTTPException(400, "Standard CVR-nummeret kan ikke slettes")
    if db.query(Employee).filter(Employee.cvr_number == row.cvr_number).count() > 0:
        raise HTTPException(400, "CVR-nummeret er tilknyttet medarbejdere og kan ikke slettes")
    log_action(db, current_user, "stamdata_delete", "cvr_number", row.id,
               f"Slettet CVR: {row.cvr_number}")
    db.delete(row)
    db.commit()


# ── Helligdage ───────────────────────────────────────────────────────────────

_holidays_mgmt = require_permission("manage_holidays")


def _holiday_row(r) -> dict:
    return {
        "id":                r.id,
        "date":              r.date.isoformat(),
        "name":              r.name,
        "half_day_from":     r.half_day_from,
        "is_auto_generated": r.is_auto_generated,
    }


class HolidayBody(BaseModel):
    date:          str
    name:          str
    half_day_from: Optional[str] = None


@router.get("/holidays")
def list_holidays(
    year: Optional[int] = None,
    # Alle indloggede skal kunne SE helligdagene (markering i aktivitetskalender,
    # vagtplan m.fl.) – kun oprettelse/sletning/generering kræver rettigheder.
    current_user: AppUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from datetime import date as _date
    q = db.query(Holiday).order_by(Holiday.date)
    if year:
        q = q.filter(
            Holiday.date >= _date(year, 1, 1),
            Holiday.date <= _date(year, 12, 31),
        )
    return [_holiday_row(r) for r in q.all()]


@router.post("/holidays", status_code=201)
def create_holiday(
    body: HolidayBody,
    current_user: AppUser = Depends(_holidays_mgmt),
    db: Session = Depends(get_db),
):
    from datetime import date as _date
    try:
        d = _date.fromisoformat(body.date)
    except ValueError:
        raise HTTPException(400, "Ugyldig dato — brug YYYY-MM-DD format")
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "Navn må ikke være tomt")
    if db.query(Holiday).filter(Holiday.date == d).first():
        raise HTTPException(400, "Der er allerede en helligdag på denne dato")
    if body.half_day_from and body.half_day_from not in ("12:00",):
        raise HTTPException(400, "half_day_from skal være '12:00' eller tom")
    row = Holiday(
        date=d,
        name=name,
        half_day_from=body.half_day_from or None,
        is_auto_generated=False,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    log_action(db, current_user, "stamdata_create", "holiday", row.id,
               f"Oprettet helligdag: {row.date} {row.name}")
    db.commit()
    return _holiday_row(row)


@router.delete("/holidays/{holiday_id}", status_code=204)
def delete_holiday(
    holiday_id: int,
    current_user: AppUser = Depends(_holidays_mgmt),
    db: Session = Depends(get_db),
):
    row = db.query(Holiday).filter(Holiday.id == holiday_id).first()
    if not row:
        raise HTTPException(404, "Helligdag ikke fundet")
    log_action(db, current_user, "stamdata_delete", "holiday", row.id,
               f"Slettet helligdag: {row.date} {row.name}")
    db.delete(row)
    db.commit()


@router.post("/holidays/generate/{year}", status_code=200)
def generate_holidays_for_year(
    year: int,
    current_user: AppUser = Depends(_holidays_mgmt),
    db: Session = Depends(get_db),
):
    from calculators.holidays import get_holidays_for_year
    if year < 2020 or year > 2100:
        raise HTTPException(400, "Årstal skal være mellem 2020 og 2100")
    added = 0
    try:
        for h in get_holidays_for_year(year):
            if not db.query(Holiday).filter(Holiday.date == h["date"]).first():
                db.add(Holiday(
                    date=h["date"],
                    name=h["name"],
                    half_day_from=h["half_day_from"],
                    is_auto_generated=True,
                ))
                added += 1
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"Fejl ved generering af helligdage: {e}")
    log_action(db, current_user, "stamdata_create", "holiday", None,
               f"Genereret {added} helligdage for {year}")
    db.commit()
    return {"year": year, "added": added}
