"""Låst lønperiode gælder kun medarbejdere der er med i Aktivitetsoversigten
(disponentgruppe med visible_in_activity_overview). For alle andre kan fravær og
Vagtplan-kommentarer oprettes/rettes/slettes bagud i låste perioder; normal tid er
stadig låst (bekræftet af bruger 2026-10-08)."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from datetime import date, datetime

import pytest
from fastapi import HTTPException

from conftest import make_activity
from database.models import (
    ActivitySource, AppUser, DispatcherGroup, PayPeriodStatus, Role, VagtplanComment,
)
from database.schemas import ActivityCreate, ActivityDeactivate, VagtplanCommentCreate, VagtplanSeriesCreate
from calculators.pay_period import get_or_create_period_for_date

D = date(2026, 10, 13)


def _admin(db):
    if not db.query(Role).filter(Role.name == "admin").first():
        db.add(Role(name="admin", display_name="Administrator", is_system=True, permissions=[]))
        db.commit()
    return AppUser(name="Test", initials="TST", role="admin", password_hash="x")


def _lock(db, d=D):
    p = get_or_create_period_for_date(d, db)
    p.status = PayPeriodStatus.closed
    db.commit()


def _in_overview(db, employee, visible=True):
    g = DispatcherGroup(name=f"G{visible}", visible_in_activity_overview=visible)
    db.add(g)
    db.commit()
    employee.dispatcher_group_id = g.id
    db.commit()
    db.refresh(employee)


def _ferie_body(employee, activity_type="ferie"):
    return ActivityCreate(employee_id=employee.id, activity_type=activity_type,
                          start_time=datetime(2026, 10, 13, 6), end_time=datetime(2026, 10, 13, 14),
                          vehicle_number="1234", source="vagtplan")


def test_lock_applies_helper(db, employee):
    from routers.activities import _lock_applies
    assert _lock_applies(employee, "ferie") is False          # ingen disponentgruppe
    assert _lock_applies(employee, "normal") is True           # normal tid altid låst
    _in_overview(db, employee, visible=False)
    assert _lock_applies(employee, "ferie") is False
    _in_overview(db, employee, visible=True)
    assert _lock_applies(employee, "ferie") is True


def test_create_absence_in_locked_period_outside_overview(db, employee):
    from routers.activities import create_manual_activity
    _lock(db)
    resp = create_manual_activity(_ferie_body(employee), current_user=_admin(db), db=db)
    assert resp.activity_type == "ferie"
    assert resp.period_closed is False


def test_create_absence_in_locked_period_in_overview_rejected(db, employee):
    from routers.activities import create_manual_activity
    _in_overview(db, employee)
    _lock(db)
    with pytest.raises(HTTPException) as e:
        create_manual_activity(_ferie_body(employee), current_user=_admin(db), db=db)
    assert e.value.status_code == 400


def test_normal_time_still_locked_outside_overview(db, employee):
    from routers.activities import create_manual_activity
    _lock(db)
    body = ActivityCreate(employee_id=employee.id, activity_type="normal",
                          start_time=datetime(2026, 10, 13, 6), end_time=datetime(2026, 10, 13, 14),
                          vehicle_number="1234")
    with pytest.raises(HTTPException):
        create_manual_activity(body, current_user=_admin(db), db=db)


def test_delete_and_deactivate_absence_outside_overview(db, employee):
    from routers.activities import delete_activity, deactivate_activity, _to_response
    a1 = make_activity(db, employee, datetime(2026, 10, 13, 6), datetime(2026, 10, 13, 14),
                       activity_type="ferie", source=ActivitySource.vagtplan)
    a2 = make_activity(db, employee, datetime(2026, 10, 14, 6), datetime(2026, 10, 14, 14),
                       activity_type="ferie", source=ActivitySource.vagtplan)
    _lock(db)
    db.refresh(a1)
    assert _to_response(a1).period_closed is False
    delete_activity(a1.id, current_user=_admin(db), db=db)
    deactivate_activity(a2.id, ActivityDeactivate(comment=None), current_user=_admin(db), db=db)


def test_delete_absence_in_overview_still_locked(db, employee):
    from routers.activities import delete_activity, _to_response
    _in_overview(db, employee)
    a = make_activity(db, employee, datetime(2026, 10, 13, 6), datetime(2026, 10, 13, 14),
                      activity_type="ferie", source=ActivitySource.vagtplan)
    _lock(db)
    db.refresh(a)
    assert _to_response(a).period_closed is True
    with pytest.raises(HTTPException):
        delete_activity(a.id, current_user=_admin(db), db=db)


def test_locked_dates_endpoint_respects_employee(db, employee):
    from routers.activities import locked_dates
    _lock(db)
    assert D in locked_dates(D, D, current_user=_admin(db), db=db)
    assert locked_dates(D, D, employee_id=employee.id, activity_type="ferie",
                        current_user=_admin(db), db=db) == []
    assert D in locked_dates(D, D, employee_id=employee.id, activity_type="normal",
                             current_user=_admin(db), db=db)
    _in_overview(db, employee)
    assert D in locked_dates(D, D, employee_id=employee.id, activity_type="ferie",
                             current_user=_admin(db), db=db)


def test_comments_in_locked_period_outside_overview(db, employee):
    from routers.vagtplan_comments import create_comment, delete_comment
    _lock(db)
    c = create_comment(VagtplanCommentCreate(employee_id=employee.id, date=D, text="x"),
                       current_user=_admin(db), db=db)
    delete_comment(c.id, current_user=_admin(db), db=db)
    assert db.query(VagtplanComment).count() == 0


def test_comments_in_locked_period_in_overview_rejected(db, employee):
    from routers.vagtplan_comments import create_comment
    _in_overview(db, employee)
    _lock(db)
    with pytest.raises(HTTPException):
        create_comment(VagtplanCommentCreate(employee_id=employee.id, date=D, text="x"),
                       current_user=_admin(db), db=db)


def test_series_in_locked_period_outside_overview(db, employee):
    from routers.vagtplan_series import create_series, preview_series, delete_series
    _lock(db)
    body = VagtplanSeriesCreate(employee_id=employee.id, activity_type="ferie", vehicle_number="1234",
                                freq="weekly", weekdays=[1], start_date=D, end_mode="count", end_count=2)
    assert preview_series(body, current_user=_admin(db), db=db).locked_dates == []
    res = create_series(body, current_user=_admin(db), db=db)
    assert res.created == 2
    r = delete_series(res.series.id, current_user=_admin(db), db=db)
    assert r.deleted == 2 and r.kept_locked == 0


def test_series_in_locked_period_in_overview_rejected(db, employee):
    from routers.vagtplan_series import create_series
    _in_overview(db, employee)
    _lock(db)
    body = VagtplanSeriesCreate(employee_id=employee.id, activity_type="ferie", vehicle_number="1234",
                                freq="weekly", weekdays=[1], start_date=D, end_mode="count", end_count=2)
    with pytest.raises(HTTPException):
        create_series(body, current_user=_admin(db), db=db)


def test_absence_group_patch_outside_overview(db, employee):
    from routers.activities import create_manual_activity, update_absence_group_dates
    from database.schemas import AbsenceGroupDatesUpdate
    body = _ferie_body(employee)
    body.absence_group_id = "grp-1"
    create_manual_activity(body, current_user=_admin(db), db=db)
    _lock(db)
    # Udvid perioden ind i låst periode og forkort igen – tilladt uden for oversigten
    update_absence_group_dates("grp-1", AbsenceGroupDatesUpdate(new_start_date=D, new_end_date=date(2026, 10, 15)),
                               current_user=_admin(db), db=db)
    update_absence_group_dates("grp-1", AbsenceGroupDatesUpdate(new_start_date=D, new_end_date=D),
                               current_user=_admin(db), db=db)
