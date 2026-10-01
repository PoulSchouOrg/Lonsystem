import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from conftest import required_employee_fields
import pytest
from datetime import date
from fastapi import HTTPException

from database.models import AppUser, MasterAgreementKind
from database.schemas import EmployeeCreate, WorkSchedule
from routers.employees import agreement_kinds, create_employee


def _dummy_user():
    return AppUser(name="Test", initials="TST", role="admin", password_hash="x")


def _seed_kinds(db):
    db.add(MasterAgreementKind(
        key="hourly_fixed", label="Timelønnet, fast arbejdstid",
        is_active=True, is_user_created=False,
        requires_agreement_type=True, sort_order=1,
    ))
    db.add(MasterAgreementKind(
        key="ingen_overenskomst", label="Ny type uden krav",
        is_active=True, is_user_created=True,
        requires_agreement_type=False, sort_order=2,
    ))
    db.add(MasterAgreementKind(
        key="skjult", label="Inaktiv type",
        is_active=False, is_user_created=True,
        requires_agreement_type=True, sort_order=3,
    ))
    db.commit()


def _base_employee_body(**overrides):
    data = dict(
        employee_number="9101",
        first_name="Ny",
        last_name="Medarbejder",
        agreement_kind="hourly_fixed",
        agreement_type="Standardoverenskomst",
        hire_date=date(2026, 1, 1),
        work_schedule=WorkSchedule(),
    )
    data.update(overrides)
    data = {**required_employee_fields(data["employee_number"]), **data}
    return EmployeeCreate(**data)


def test_agreement_kinds_endpoint_only_returns_active(db):
    _seed_kinds(db)
    rows = agreement_kinds(current_user=_dummy_user(), db=db)
    keys = {r["key"] for r in rows}
    assert keys == {"hourly_fixed", "ingen_overenskomst"}


def test_create_employee_rejects_unknown_agreement_kind(db):
    _seed_kinds(db)
    body = _base_employee_body(agreement_kind="findes_ikke")
    with pytest.raises(HTTPException) as exc:
        create_employee(body, current_user=_dummy_user(), db=db)
    assert exc.value.status_code == 400


def test_create_employee_requires_agreement_type_when_flagged(db):
    _seed_kinds(db)
    body = _base_employee_body(agreement_kind="hourly_fixed", agreement_type="")
    with pytest.raises(HTTPException) as exc:
        create_employee(body, current_user=_dummy_user(), db=db)
    assert exc.value.status_code == 400


def test_create_employee_allows_empty_agreement_type_when_not_required(db):
    _seed_kinds(db)
    body = _base_employee_body(
        employee_number="9102",
        agreement_kind="ingen_overenskomst",
        agreement_type="",
    )
    result = create_employee(body, current_user=_dummy_user(), db=db)
    assert result.agreement_kind == "ingen_overenskomst"
    assert result.agreement_type == ""
