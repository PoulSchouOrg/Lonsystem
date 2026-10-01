import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))
sys.path.insert(0, os.path.dirname(__file__))

from conftest import required_employee_fields

from datetime import date

from database.models import AppUser
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
        employee_number="3001", first_name="Test", last_name="Saeraftale",
        agreement_kind="hourly_fixed", agreement_type="Standardoverenskomst",
        hire_date=date(2020, 1, 1), work_schedule=WorkSchedule(),
    )
    data.update(overrides)
    data = {**required_employee_fields(data["employee_number"]), **data}
    return EmployeeCreate(**data)


def test_create_employee_with_ot_extra_alle_timer(db):
    from routers.employees import create_employee
    _seed_agreement(db)
    resp = create_employee(_base_employee_body(ot_extra_alle_timer=True),
                            current_user=_admin(), db=db)
    assert resp.ot_extra_alle_timer is True


def test_employee_defaults_to_ot_extra_alle_timer_false(db):
    from routers.employees import create_employee
    _seed_agreement(db)
    resp = create_employee(_base_employee_body(), current_user=_admin(), db=db)
    assert resp.ot_extra_alle_timer is False


def test_update_employee_ot_extra_alle_timer(db, employee):
    from routers.employees import update_employee
    _seed_agreement(db)
    resp = update_employee(employee.id, EmployeeUpdate(ot_extra_alle_timer=True),
                            current_user=_admin(), db=db)
    assert resp.ot_extra_alle_timer is True
