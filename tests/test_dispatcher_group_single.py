import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))
sys.path.insert(0, os.path.dirname(__file__))

from conftest import required_employee_fields

from database.models import DispatcherGroup, Employee, Vehicle


def test_employee_dispatcher_group_defaults_to_none(db, employee):
    assert employee.dispatcher_group_id is None
    assert employee.dispatcher_group is None


def test_employee_can_be_assigned_a_single_dispatcher_group(db, employee):
    group = DispatcherGroup(name="Testgruppe")
    db.add(group)
    db.commit()
    db.refresh(group)

    employee.dispatcher_group = group
    db.commit()
    db.refresh(employee)

    assert employee.dispatcher_group_id == group.id
    assert employee.dispatcher_group.name == "Testgruppe"


def test_employee_no_longer_has_a_many_to_many_dispatcher_groups_relationship():
    assert not hasattr(Employee, "dispatcher_groups")


def test_dispatcher_group_vehicle_number_is_none_without_vehicle(db):
    group = DispatcherGroup(name="Uden vogn")
    db.add(group)
    db.commit()
    db.refresh(group)
    assert group.vehicle_number is None


def test_dispatcher_group_vehicle_number_reads_linked_vehicle(db):
    vehicle = Vehicle(registration_number="AB12345", vehicle_number="99")
    db.add(vehicle)
    db.commit()
    db.refresh(vehicle)

    group = DispatcherGroup(name="Med vogn", vehicle_id=vehicle.id)
    db.add(group)
    db.commit()
    db.refresh(group)

    assert group.vehicle_number == "99"


from database.models import AppUser
from database.schemas import EmployeeUpdate, WorkSchedule
from datetime import date
from fastapi import HTTPException
import pytest


def _dummy_user():
    return AppUser(name="Test", initials="TST", role="admin", password_hash="x")


def _employee_body(**overrides):
    from database.schemas import EmployeeCreate
    data = dict(
        employee_number="9201",
        first_name="Ny",
        last_name="Person",
        agreement_kind="hourly_fixed",
        agreement_type="Standardoverenskomst",
        hire_date=date(2026, 1, 1),
        work_schedule=WorkSchedule(),
    )
    data.update(overrides)
    data = {**required_employee_fields(data["employee_number"]), **data}
    return EmployeeCreate(**data)


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


def test_create_employee_with_dispatcher_group(db):
    from routers.employees import create_employee
    _seed_agreement(db)
    group = DispatcherGroup(name="Ny Gruppe")
    db.add(group)
    db.commit()
    db.refresh(group)

    resp = create_employee(_employee_body(dispatcher_group_id=group.id), current_user=_dummy_user(), db=db)
    assert resp.dispatcher_group.id == group.id
    assert resp.dispatcher_group.name == "Ny Gruppe"


def test_create_employee_without_dispatcher_group(db):
    from routers.employees import create_employee
    _seed_agreement(db)
    resp = create_employee(_employee_body(), current_user=_dummy_user(), db=db)
    assert resp.dispatcher_group is None


def test_create_employee_rejects_unknown_dispatcher_group(db):
    from routers.employees import create_employee
    _seed_agreement(db)
    with pytest.raises(HTTPException) as exc:
        create_employee(_employee_body(dispatcher_group_id=999999), current_user=_dummy_user(), db=db)
    assert exc.value.status_code == 400


def test_update_employee_can_set_and_clear_dispatcher_group(db, employee):
    from routers.employees import update_employee
    _seed_agreement(db)
    group = DispatcherGroup(name="Skiftegruppe")
    db.add(group)
    db.commit()
    db.refresh(group)

    updated = update_employee(employee.id, EmployeeUpdate(dispatcher_group_id=group.id), current_user=_dummy_user(), db=db)
    assert updated.dispatcher_group.id == group.id

    cleared = update_employee(employee.id, EmployeeUpdate(dispatcher_group_id=None), current_user=_dummy_user(), db=db)
    assert cleared.dispatcher_group is None


def test_update_employee_without_dispatcher_group_field_leaves_it_unchanged(db, employee):
    from routers.employees import update_employee
    _seed_agreement(db)
    group = DispatcherGroup(name="Uændret-gruppe")
    db.add(group)
    db.commit()
    db.refresh(group)
    employee.dispatcher_group = group
    db.commit()

    updated = update_employee(employee.id, EmployeeUpdate(first_name="Nytnavn"), current_user=_dummy_user(), db=db)
    assert updated.dispatcher_group.id == group.id


def test_active_employees_excludes_employee_without_dispatcher_group(db, employee):
    from routers.payroll_router import _active_employees
    result = _active_employees(db)
    assert employee.id not in [e.id for e in result]


def test_active_employees_includes_employee_with_visible_group(db, employee):
    from routers.payroll_router import _active_employees
    group = DispatcherGroup(name="Synlig gruppe", visible_in_activity_overview=True)
    db.add(group)
    db.commit()
    employee.dispatcher_group = group
    db.commit()

    result = _active_employees(db)
    assert employee.id in [e.id for e in result]


def test_active_employees_excludes_employee_with_hidden_group(db, employee):
    from routers.payroll_router import _active_employees
    group = DispatcherGroup(name="Skjult gruppe", visible_in_activity_overview=False)
    db.add(group)
    db.commit()
    employee.dispatcher_group = group
    db.commit()

    result = _active_employees(db)
    assert employee.id not in [e.id for e in result]
