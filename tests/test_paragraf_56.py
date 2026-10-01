import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))
sys.path.insert(0, os.path.dirname(__file__))

from conftest import required_employee_fields

from datetime import date
import pytest
from fastapi import HTTPException

from database.models import AppUser, MasterAgreementType, MasterAgreementKind
from database.schemas import EmployeeCreate, EmployeeUpdate, WorkSchedule


def _dummy_user():
    return AppUser(name="Test", initials="TST", role="admin", password_hash="x")


def _seed_agreement(db):
    from decimal import Decimal
    db.add(MasterAgreementType(name="Standardoverenskomst", hourly_rate=Decimal("150.00")))
    db.add(MasterAgreementKind(
        key="hourly_fixed", label="Timelønnet, fast arbejdstid",
        is_active=True, is_user_created=False,
        requires_agreement_type=True, sort_order=1,
    ))
    db.commit()


def _employee_body(**overrides):
    data = dict(
        employee_number="9301",
        first_name="Ny",
        last_name="Paragraf",
        agreement_kind="hourly_fixed",
        agreement_type="Standardoverenskomst",
        hire_date=date(2026, 1, 1),
        work_schedule=WorkSchedule(),
    )
    data.update(overrides)
    data = {**required_employee_fields(data["employee_number"]), **data}
    return EmployeeCreate(**data)


def test_employee_paragraf_56_defaults_to_false(db, employee):
    assert employee.paragraf_56 is False
    assert employee.paragraf_56_start_date is None
    assert employee.paragraf_56_end_date is None


def test_create_employee_with_paragraf_56_requires_start_date(db):
    from routers.employees import create_employee
    _seed_agreement(db)
    with pytest.raises(HTTPException) as exc:
        create_employee(
            _employee_body(paragraf_56=True, paragraf_56_end_date=date(2026, 6, 1)),
            current_user=_dummy_user(), db=db,
        )
    assert exc.value.status_code == 400


def test_create_employee_with_paragraf_56_requires_end_date(db):
    from routers.employees import create_employee
    _seed_agreement(db)
    with pytest.raises(HTTPException) as exc:
        create_employee(
            _employee_body(paragraf_56=True, paragraf_56_start_date=date(2026, 1, 1)),
            current_user=_dummy_user(), db=db,
        )
    assert exc.value.status_code == 400


def test_create_employee_with_paragraf_56_rejects_end_before_start(db):
    from routers.employees import create_employee
    _seed_agreement(db)
    with pytest.raises(HTTPException) as exc:
        create_employee(
            _employee_body(
                paragraf_56=True,
                paragraf_56_start_date=date(2026, 6, 1),
                paragraf_56_end_date=date(2026, 1, 1),
            ),
            current_user=_dummy_user(), db=db,
        )
    assert exc.value.status_code == 400


def test_create_employee_with_valid_paragraf_56_dates_is_saved(db):
    from routers.employees import create_employee
    _seed_agreement(db)
    resp = create_employee(
        _employee_body(
            paragraf_56=True,
            paragraf_56_start_date=date(2026, 1, 1),
            paragraf_56_end_date=date(2026, 6, 1),
        ),
        current_user=_dummy_user(), db=db,
    )
    assert resp.paragraf_56 is True
    assert resp.paragraf_56_start_date == date(2026, 1, 1)
    assert resp.paragraf_56_end_date == date(2026, 6, 1)


def test_create_employee_without_paragraf_56_ignores_stray_dates(db):
    from routers.employees import create_employee
    _seed_agreement(db)
    resp = create_employee(
        _employee_body(paragraf_56=False, paragraf_56_start_date=date(2026, 1, 1)),
        current_user=_dummy_user(), db=db,
    )
    assert resp.paragraf_56 is False
    assert resp.paragraf_56_start_date is None
    assert resp.paragraf_56_end_date is None


def test_update_employee_can_set_paragraf_56(db, employee):
    from routers.employees import update_employee
    _seed_agreement(db)
    updated = update_employee(
        employee.id,
        EmployeeUpdate(paragraf_56=True, paragraf_56_start_date=date(2026, 2, 1), paragraf_56_end_date=date(2026, 8, 1)),
        current_user=_dummy_user(), db=db,
    )
    assert updated.paragraf_56 is True
    assert updated.paragraf_56_start_date == date(2026, 2, 1)
    assert updated.paragraf_56_end_date == date(2026, 8, 1)


def test_update_employee_can_clear_paragraf_56_and_dates(db, employee):
    from routers.employees import update_employee
    _seed_agreement(db)
    update_employee(
        employee.id,
        EmployeeUpdate(paragraf_56=True, paragraf_56_start_date=date(2026, 2, 1), paragraf_56_end_date=date(2026, 8, 1)),
        current_user=_dummy_user(), db=db,
    )
    cleared = update_employee(
        employee.id,
        EmployeeUpdate(paragraf_56=False),
        current_user=_dummy_user(), db=db,
    )
    assert cleared.paragraf_56 is False
    assert cleared.paragraf_56_start_date is None
    assert cleared.paragraf_56_end_date is None


def test_update_employee_without_paragraf_56_field_leaves_it_unchanged(db, employee):
    from routers.employees import update_employee
    _seed_agreement(db)
    update_employee(
        employee.id,
        EmployeeUpdate(paragraf_56=True, paragraf_56_start_date=date(2026, 2, 1), paragraf_56_end_date=date(2026, 8, 1)),
        current_user=_dummy_user(), db=db,
    )
    updated = update_employee(
        employee.id,
        EmployeeUpdate(first_name="Nytnavn"),
        current_user=_dummy_user(), db=db,
    )
    assert updated.paragraf_56 is True
    assert updated.paragraf_56_start_date == date(2026, 2, 1)
    assert updated.paragraf_56_end_date == date(2026, 8, 1)
