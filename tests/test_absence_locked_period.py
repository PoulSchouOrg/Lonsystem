import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException

from database.models import Activity, ActivitySource, ActivityStatus, AppUser, PayPeriodStatus
from database.schemas import ActivityDeactivate
from calculators.pay_period import get_or_create_period_for_date


def _user():
    return AppUser(name="Test", initials="LB1", role="lonbogholder", password_hash="x")


def _activity(db, employee, activity_type, closed):
    start = datetime(2026, 1, 5, 6, 0)
    period = get_or_create_period_for_date(start.date(), db)
    period.status = PayPeriodStatus.closed if closed else PayPeriodStatus.open
    a = Activity(
        employee_id=employee.id, pay_period_id=period.id, source=ActivitySource.vagtplan,
        activity_type=activity_type, start_time=start, end_time=datetime(2026, 1, 5, 13, 24),
        status=ActivityStatus.pending, pause_intervals=[], segments=[],
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


def test_cannot_delete_absence_in_closed_period(db, employee):
    from routers.activities import delete_activity
    a = _activity(db, employee, "ferie", closed=True)
    with pytest.raises(HTTPException) as exc:
        delete_activity(a.id, current_user=_user(), db=db)
    assert exc.value.status_code == 400
    assert db.query(Activity).filter(Activity.id == a.id).first() is not None


def test_cannot_deactivate_absence_in_closed_period(db, employee):
    from routers.activities import deactivate_activity
    a = _activity(db, employee, "sygdom", closed=True)
    with pytest.raises(HTTPException):
        deactivate_activity(a.id, ActivityDeactivate(comment=None), current_user=_user(), db=db)
    db.refresh(a)
    assert a.status == ActivityStatus.pending


def test_can_delete_absence_in_open_period(db, employee):
    from routers.activities import delete_activity
    a = _activity(db, employee, "ferie", closed=False)
    delete_activity(a.id, current_user=_user(), db=db)
    assert db.query(Activity).filter(Activity.id == a.id).first() is None


@pytest.mark.parametrize("activity_type", ["normal", "ferie"])
def test_cannot_reopen_in_closed_period(db, employee, activity_type):
    from routers.activities import reopen_activity
    a = _activity(db, employee, activity_type, closed=True)
    a.status = ActivityStatus.approved
    db.commit()
    with pytest.raises(HTTPException) as exc:
        reopen_activity(a.id, current_user=_user(), db=db)
    assert exc.value.status_code == 400
    db.refresh(a)
    assert a.status == ActivityStatus.approved


def test_can_reopen_in_open_period(db, employee):
    from routers.activities import reopen_activity
    a = _activity(db, employee, "normal", closed=False)
    a.status = ActivityStatus.approved
    db.commit()
    assert reopen_activity(a.id, current_user=_user(), db=db).status == ActivityStatus.pending


@pytest.mark.parametrize("activity_type", ["normal", "ferie"])
def test_cannot_save_changes_in_closed_period(db, employee, activity_type):
    from routers.activities import update_activity
    from database.schemas import ActivityUpdate
    a = _activity(db, employee, activity_type, closed=True)
    with pytest.raises(HTTPException) as exc:
        update_activity(a.id, ActivityUpdate(start_time=datetime(2026, 3, 2, 6, 0),
                                             end_time=datetime(2026, 3, 2, 14, 0)),
                        current_user=_user(), db=db)
    assert exc.value.status_code == 400
    db.refresh(a)
    assert a.start_time == datetime(2026, 1, 5, 6, 0)


def test_cannot_undo_split_in_closed_period(db, employee):
    from routers.activities import undo_split
    parent = _activity(db, employee, "normal", closed=True)
    parent.status = ActivityStatus.deactivated
    child = Activity(
        employee_id=employee.id, pay_period_id=parent.pay_period_id, source=ActivitySource.manual,
        activity_type="normal", start_time=parent.start_time, end_time=datetime(2026, 1, 5, 10, 0),
        status=ActivityStatus.approved, pause_intervals=[], segments=[],
        parent_activity_id=parent.id,
    )
    db.add(child)
    db.commit()
    with pytest.raises(HTTPException) as exc:
        undo_split(child.id, current_user=_user(), db=db)
    assert exc.value.status_code == 400
    assert db.query(Activity).filter(Activity.id == child.id).first() is not None


@pytest.mark.parametrize("endpoint", ["undo_edit", "correct_all_segments"])
def test_other_edits_blocked_in_closed_period(db, employee, endpoint):
    import routers.activities as r
    a = _activity(db, employee, "normal", closed=True)
    a.original_start_time = a.start_time
    a.original_end_time = a.end_time
    db.commit()
    with pytest.raises(HTTPException) as exc:
        getattr(r, endpoint)(a.id, current_user=_user(), db=db)
    assert exc.value.status_code == 400


def test_cannot_split_in_closed_period(db, employee):
    from routers.activities import split_activity
    from database.schemas import ActivitySplit
    a = _activity(db, employee, "normal", closed=True)
    with pytest.raises(HTTPException) as exc:
        split_activity(a.id, ActivitySplit(split_at=datetime(2026, 1, 5, 9, 0)),
                       current_user=_user(), db=db)
    assert exc.value.status_code == 400
    db.refresh(a)
    assert a.status == ActivityStatus.pending


@pytest.mark.parametrize("activity_type", ["normal", "ferie"])
def test_cannot_create_on_date_in_closed_period(db, employee, activity_type):
    from routers.activities import create_manual_activity
    from database.schemas import ActivityCreate
    period = get_or_create_period_for_date(datetime(2026, 1, 5).date(), db)
    period.status = PayPeriodStatus.closed
    db.commit()
    with pytest.raises(HTTPException) as exc:
        create_manual_activity(ActivityCreate(
            employee_id=employee.id, activity_type=activity_type, vehicle_number="1",
            start_time=datetime(2026, 1, 5, 6, 0), end_time=datetime(2026, 1, 5, 13, 24),
        ), current_user=_user(), db=db)
    assert exc.value.status_code == 400
    assert db.query(Activity).count() == 0


def test_locked_dates_lists_only_closed_period_dates(db, employee):
    from routers.activities import locked_dates
    from datetime import date
    period = get_or_create_period_for_date(date(2026, 1, 5), db)
    period.status = PayPeriodStatus.closed
    get_or_create_period_for_date(period.end_date + timedelta(days=1), db)
    db.commit()
    result = locked_dates(period.end_date - timedelta(days=1), period.end_date + timedelta(days=2),
                          current_user=_user(), db=db)
    assert result == [period.end_date - timedelta(days=1), period.end_date]


def test_cannot_create_vagtplan_comment_in_closed_period(db, employee, monkeypatch):
    import routers.vagtplan_comments as vc
    from database.models import VagtplanComment
    from database.schemas import VagtplanCommentCreate
    from datetime import date
    monkeypatch.setattr(vc, "_has_edit_access", lambda *a: True)
    period = get_or_create_period_for_date(date(2026, 1, 5), db)
    period.status = PayPeriodStatus.closed
    db.commit()
    with pytest.raises(HTTPException) as exc:
        vc.create_comment(VagtplanCommentCreate(employee_id=employee.id, date=date(2026, 1, 5), text="x"),
                          current_user=_user(), db=db)
    assert exc.value.status_code == 400
    assert db.query(VagtplanComment).count() == 0


def test_response_exposes_period_closed(db, employee):
    from routers.activities import _to_response
    a = _activity(db, employee, "ferie", closed=True)
    assert _to_response(a).period_closed is True
