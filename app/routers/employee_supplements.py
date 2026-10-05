from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

from auth import log_action, require_permission
from calculators.rates_loader import get_supplements_for_period
from database.models import AppUser, Employee, EmployeeSupplement
from database.schemas import EmployeeSupplementCreate, EmployeeSupplementResponse
from database.session import get_db

router = APIRouter(prefix="/api/employee-supplements", tags=["employee-supplements"])

_supplements_access = require_permission("manage_employee_supplements")

_OPEN_ENDED = date(9999, 12, 31)


def _create_supplement(db: Session, employee_id: int, start_date: date, value: Decimal) -> EmployeeSupplement:
    value = value.quantize(Decimal("0.01"))
    if value <= 0:
        raise HTTPException(400, "Værdien skal være et positivt beløb")
    emp = db.query(Employee).filter(Employee.id == employee_id).first()
    if not emp:
        raise HTTPException(404, "Medarbejder ikke fundet")
    # En medarbejder kan have flere aktive tillæg samtidig (summeres i lønberegningen),
    # så et nyt tillæg lukker IKKE eksisterende – det gøres med "Afslut" (2026-10-05).
    new_row = EmployeeSupplement(employee_id=employee_id, start_date=start_date, value=value)
    db.add(new_row)
    db.commit()
    db.refresh(new_row)
    return new_row


def _to_response(row: EmployeeSupplement) -> EmployeeSupplementResponse:
    today = date.today()
    return EmployeeSupplementResponse(
        id=row.id,
        employee_id=row.employee_id,
        employee_number=row.employee.employee_number,
        employee_name=row.employee.name,
        name=row.name,
        type=row.type,
        value=float(row.value),
        start_date=row.start_date,
        end_date=row.end_date,
        is_active=row.start_date <= today <= row.end_date,
        deactivated=row.deactivated_at is not None,
    )


@router.get("", response_model=list[EmployeeSupplementResponse])
def list_supplements(
    employee_id: Optional[int] = None,
    date_from: Optional[date] = Query(None, alias="from"),
    date_to: Optional[date] = Query(None, alias="to"),
    current_user: AppUser = Depends(_supplements_access),
    db: Session = Depends(get_db),
):
    q = db.query(EmployeeSupplement).options(joinedload(EmployeeSupplement.employee))
    if employee_id is not None:
        if not db.query(Employee).filter(Employee.id == employee_id).first():
            raise HTTPException(404, "Medarbejder ikke fundet")
        q = q.filter(EmployeeSupplement.employee_id == employee_id)
    if date_from is not None:
        q = q.filter(EmployeeSupplement.end_date >= date_from)
    if date_to is not None:
        q = q.filter(EmployeeSupplement.start_date <= date_to)
    rows = q.order_by(EmployeeSupplement.start_date.desc()).all()
    return [_to_response(r) for r in rows]


@router.get("/active/{employee_id}", response_model=list[EmployeeSupplementResponse])
def get_active_supplement(
    employee_id: int,
    current_user: AppUser = Depends(_supplements_access),
    db: Session = Depends(get_db),
):
    if not db.query(Employee).filter(Employee.id == employee_id).first():
        raise HTTPException(404, "Medarbejder ikke fundet")
    today = date.today()
    return [_to_response(r) for r in get_supplements_for_period(db, employee_id, today, today)]


@router.post("", response_model=EmployeeSupplementResponse, status_code=201)
def create_supplement(
    body: EmployeeSupplementCreate,
    current_user: AppUser = Depends(_supplements_access),
    db: Session = Depends(get_db),
):
    row = _create_supplement(db, body.employee_id, body.start_date, Decimal(str(body.value)))
    log_action(db, current_user, "employee_supplement_create", "employee_supplement", row.id,
               f"{row.value} kr/t fra {row.start_date.isoformat()}")
    db.commit()
    return _to_response(row)


@router.post("/{supplement_id}/end", response_model=EmployeeSupplementResponse)
def end_supplement(
    supplement_id: int,
    current_user: AppUser = Depends(_supplements_access),
    db: Session = Depends(get_db),
):
    row = db.query(EmployeeSupplement).filter(EmployeeSupplement.id == supplement_id).first()
    if not row:
        raise HTTPException(404, "Tillæg ikke fundet")
    today = date.today()
    if (row.deactivated_at is not None or row.end_date != _OPEN_ENDED
            or not (row.start_date <= today <= row.end_date)):
        raise HTTPException(400, "Kun aktive tillæg uden slutdato kan afsluttes")
    # Afslut: dags dato er sidste gyldige dag (bekræftet 2026-10-05). Tillægget
    # tæller stadig med i de perioder/dage, hvor det var gyldigt.
    row.deactivated_at = datetime.now()
    row.end_date = today
    db.commit()
    log_action(db, current_user, "employee_supplement_end", "employee_supplement", row.id,
               f"Afsluttet, sidste gyldige dag {today.isoformat()}")
    db.commit()
    db.refresh(row)
    return _to_response(row)
