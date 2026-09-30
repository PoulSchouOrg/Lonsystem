"""Se-rettigheder håndhæves i backend (2026-09-30): medarbejder-/vognlisten,
aktiviteter, vagtplan-kommentarer og advarsler."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from database.models import AppUser, Role


def _user(db, name, perms):
    db.add(Role(name=name, display_name=name, is_system=False, permissions=perms))
    u = AppUser(name=name, initials=name[:3].upper(), role=name, password_hash="x", active=True)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _call_checker(checker, db, user):
    return checker(SimpleNamespace(session={"user_id": user.id}), db=db)


def test_require_any_permission_accepts_one_of(db):
    from auth import require_any_permission
    user = _user(db, "vagt", ["vagtplan_view"])
    assert _call_checker(require_any_permission("view_calendar", "vagtplan_view"), db, user).id == user.id


def test_require_any_permission_rejects_none_of(db):
    from auth import require_any_permission
    user = _user(db, "ingen", ["payroll"])
    with pytest.raises(HTTPException) as exc:
        _call_checker(require_any_permission("view_calendar", "vagtplan_view"), db, user)
    assert exc.value.status_code == 403


def test_employee_list_hides_private_fields_without_view_employees(db, employee):
    from routers.employees import list_employees
    employee.email, employee.phone, employee.address = "a@b.dk", "1234", "Vej 1"
    employee.tachograph_card_number = "DK000000000001"
    db.commit()
    user = _user(db, "disponent", ["view_calendar"])
    resp = list_employees(active_only=True, current_user=user, db=db)[0]
    assert resp.name == employee.name
    assert resp.email is None and resp.phone is None and resp.address is None
    assert resp.tachograph_card_number is None
    assert resp.hourly_rate is None


def test_employee_list_shows_private_fields_with_view_employees(db, employee):
    from routers.employees import list_employees
    employee.email = "a@b.dk"
    db.commit()
    user = _user(db, "hr", ["view_employees"])
    resp = list_employees(active_only=True, current_user=user, db=db)[0]
    assert resp.email == "a@b.dk"


def test_employee_list_requires_a_screen_permission(db):
    from routers.employees import _employee_list_access
    user = _user(db, "tom", ["import_ddd"])
    with pytest.raises(HTTPException) as exc:
        _call_checker(_employee_list_access, db, user)
    assert exc.value.status_code == 403


def test_hide_from_vagtplan_requires_vagtplan_edit(db, employee):
    from datetime import datetime
    from database.models import Activity, ActivitySource, ActivityStatus
    from database.schemas import VagtplanHideBody
    from calculators.pay_period import get_or_create_period_for_date
    from routers.activities import hide_from_vagtplan
    period = get_or_create_period_for_date(datetime(2026, 1, 5).date(), db)
    a = Activity(employee_id=employee.id, pay_period_id=period.id, source=ActivitySource.vagtplan,
                 activity_type="ferie", start_time=datetime(2026, 1, 5, 6, 0),
                 end_time=datetime(2026, 1, 5, 14, 0), status=ActivityStatus.approved,
                 pause_intervals=[], segments=[])
    db.add(a)
    db.commit()
    user = _user(db, "se", ["vagtplan_view"])
    with pytest.raises(HTTPException) as exc:
        hide_from_vagtplan(a.id, VagtplanHideBody(hidden=True), current_user=user, db=db)
    assert exc.value.status_code == 403
