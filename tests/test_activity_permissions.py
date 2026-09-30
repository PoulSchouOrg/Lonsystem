"""'Godkend aktiviteter' og 'Redigér aktiviteter' håndhæves i backend (2026-09-30)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from datetime import datetime

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import sessionmaker

from database.models import Activity, ActivitySource, ActivityStatus, AppUser, Role
from database.schemas import ActivityApprove, ActivityCreate, ActivityDeactivate, ActivityUpdate
from calculators.pay_period import get_or_create_period_for_date

pytestmark = pytest.mark.real_activity_permissions


def _role(db, name, perms):
    db.add(Role(name=name, display_name=name, is_system=False, permissions=perms))
    db.commit()
    return AppUser(name=name, initials=name[:3].upper(), role=name, password_hash="x")


def _activity(db, employee, source=ActivitySource.manual, activity_type="normal"):
    start, end = datetime(2026, 1, 5, 6, 0), datetime(2026, 1, 5, 14, 0)
    period = get_or_create_period_for_date(start.date(), db)
    a = Activity(
        employee_id=employee.id, pay_period_id=period.id, source=source,
        activity_type=activity_type, start_time=start, end_time=end,
        status=ActivityStatus.pending, pause_intervals=[], segments=[],
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


def test_approve_requires_approve_permission(db, employee):
    from routers.activities import approve_activity
    a = _activity(db, employee)
    user = _role(db, "kontor", ["edit_activities"])
    with pytest.raises(HTTPException) as exc:
        approve_activity(a.id, ActivityApprove(comment="ok"), current_user=user, db=db)
    assert exc.value.status_code == 403


def test_approve_allowed_with_permission(db, employee):
    from routers.activities import approve_activity
    a = _activity(db, employee)
    user = _role(db, "lon", ["approve_activities"])
    approve_activity(a.id, ActivityApprove(comment="ok"), current_user=user, db=db)
    db.refresh(a)
    assert a.status == ActivityStatus.approved


@pytest.mark.parametrize("endpoint", ["deactivate", "delete", "reopen"])
def test_remove_and_reopen_require_approve_permission(db, employee, endpoint):
    import routers.activities as r
    a = _activity(db, employee)
    user = _role(db, "kontor", ["edit_activities"])
    with pytest.raises(HTTPException) as exc:
        if endpoint == "deactivate":
            r.deactivate_activity(a.id, ActivityDeactivate(comment=None), current_user=user, db=db)
        elif endpoint == "delete":
            r.delete_activity(a.id, current_user=user, db=db)
        else:
            r.reopen_activity(a.id, current_user=user, db=db)
    assert exc.value.status_code == 403


def test_update_requires_edit_permission(db, employee):
    from routers.activities import update_activity
    a = _activity(db, employee)
    user = _role(db, "godkender", ["approve_activities"])
    with pytest.raises(HTTPException) as exc:
        update_activity(a.id, ActivityUpdate(km_start=5), current_user=user, db=db)
    assert exc.value.status_code == 403


def test_create_requires_edit_permission(db, employee):
    from routers.activities import create_manual_activity
    user = _role(db, "godkender", ["approve_activities"])
    body = ActivityCreate(employee_id=employee.id, activity_type="overnatning",
                          start_time=datetime(2026, 1, 5, 0, 0), end_time=datetime(2026, 1, 5, 0, 0))
    with pytest.raises(HTTPException) as exc:
        create_manual_activity(body, current_user=user, db=db)
    assert exc.value.status_code == 403


def test_bulk_auto_approve_requires_approve_permission(db, employee):
    from routers.activities import bulk_auto_approve
    user = _role(db, "kontor", ["edit_activities"])
    with pytest.raises(HTTPException) as exc:
        bulk_auto_approve(period_start="2026-01-05", current_user=user, db=db)
    assert exc.value.status_code == 403


def test_vagtplan_editor_can_remove_vagtplan_activity_without_general_permissions(db, employee):
    """Vagtplanen skal fortsat virke for roller uden de generelle aktivitetsrettigheder."""
    from routers.activities import deactivate_activity
    a = _activity(db, employee, source=ActivitySource.vagtplan, activity_type="ferie")
    user = _role(db, "vagt", ["vagtplan_view", "vagtplan_edit_all"])
    deactivate_activity(a.id, ActivityDeactivate(comment=None), current_user=user, db=db)
    db.refresh(a)
    assert a.status == ActivityStatus.deactivated


def test_vagtplan_editor_cannot_touch_non_vagtplan_activity(db, employee):
    from routers.activities import deactivate_activity
    a = _activity(db, employee, source=ActivitySource.tachograph)
    user = _role(db, "vagt", ["vagtplan_view", "vagtplan_edit_all"])
    with pytest.raises(HTTPException) as exc:
        deactivate_activity(a.id, ActivityDeactivate(comment=None), current_user=user, db=db)
    assert exc.value.status_code == 403


def test_edit_activities_granted_once_to_all_roles(db, monkeypatch):
    import database.session as session_module
    monkeypatch.setattr(session_module, "SessionLocal", sessionmaker(bind=db.get_bind()))
    db.add(Role(name="lonbogholder", display_name="L", is_system=False, permissions=[]))
    db.add(Role(name="kontor", display_name="K", is_system=False, permissions=[]))
    db.commit()
    session_module._ensure_edit_activities_permission()
    for role in db.query(Role).all():
        db.refresh(role)
        assert "edit_activities" in role.permissions
    kontor = db.query(Role).filter(Role.name == "kontor").first()
    kontor.permissions = []
    db.commit()
    session_module._ensure_edit_activities_permission()
    db.refresh(kontor)
    assert kontor.permissions == []
