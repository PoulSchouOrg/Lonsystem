import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))
sys.path.insert(0, os.path.dirname(__file__))

from conftest import required_employee_fields

from datetime import date

import pytest
from fastapi import HTTPException

from database.models import AppUser, Vehicle
from database.schemas import EmployeeCreate, EmployeeUpdate, WorkSchedule


def _admin():
    return AppUser(name="Admin", initials="ADM", role="admin", password_hash="x")


def _seed_agreement(db):
    from database.models import MasterAgreementType, MasterAgreementKind
    from decimal import Decimal
    db.add(MasterAgreementType(name="Standardoverenskomst", hourly_rate=Decimal("150.00")))
    db.add(MasterAgreementKind(
        key="hourly_fixed", label="Timelønnet, fast arbejdstid",
        is_active=True, is_user_created=False,
        requires_agreement_type=True, sort_order=1,
    ))
    db.commit()


def _base_employee_body(**overrides):
    data = dict(
        employee_number="3001", first_name="Test", last_name="Fravaersbil",
        agreement_kind="hourly_fixed", agreement_type="Standardoverenskomst",
        hire_date=date(2020, 1, 1), work_schedule=WorkSchedule(),
    )
    data.update(overrides)
    data = {**required_employee_fields(data["employee_number"]), **data}
    return EmployeeCreate(**data)


def _vehicle(db, reg="BN47449", num="52"):
    v = Vehicle(registration_number=reg, vehicle_number=num)
    db.add(v)
    db.commit()
    return v


def test_create_employee_with_absence_vehicle(db):
    from routers.employees import create_employee
    _seed_agreement(db)
    v = _vehicle(db)
    resp = create_employee(_base_employee_body(absence_vehicle_id=v.id), current_user=_admin(), db=db)
    assert resp.absence_vehicle_id == v.id
    assert resp.absence_vehicle_number == "52"


def test_create_employee_rejects_unknown_absence_vehicle(db):
    from routers.employees import create_employee
    _seed_agreement(db)
    with pytest.raises(HTTPException) as exc:
        create_employee(_base_employee_body(absence_vehicle_id=999999), current_user=_admin(), db=db)
    assert exc.value.status_code == 400


def test_absence_vehicle_is_independent_of_fast_bil(db):
    from routers.employees import create_employee
    _seed_agreement(db)
    v1 = _vehicle(db, "AA11111", "10")
    v2 = _vehicle(db, "BB22222", "20")
    resp = create_employee(
        _base_employee_body(fast_bil=True, fast_bil_vehicle_id=v1.id, absence_vehicle_id=v2.id),
        current_user=_admin(), db=db,
    )
    assert resp.fast_bil_vehicle_number == "10"
    assert resp.absence_vehicle_number == "20"


def test_update_employee_absence_vehicle(db, employee):
    from routers.employees import update_employee
    _seed_agreement(db)
    v = _vehicle(db)
    resp = update_employee(employee.id, EmployeeUpdate(absence_vehicle_id=v.id), current_user=_admin(), db=db)
    assert resp.absence_vehicle_number == "52"

    unchanged = update_employee(employee.id, EmployeeUpdate(first_name="Nyt"), current_user=_admin(), db=db)
    assert unchanged.absence_vehicle_id == v.id
