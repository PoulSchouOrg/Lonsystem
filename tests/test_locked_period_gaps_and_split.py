"""Huller i spærringen af låste lønperioder (lukket 2026-09-30), split efter
'Ret til andet arbejde' og Lønkørsel-'I alt' = Lønafregningens total."""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from datetime import date, datetime
from decimal import Decimal

import pytest
from fastapi import HTTPException

from database.models import (
    Activity, ActivitySource, ActivityStatus, AppUser, PayPeriodStatus, VagtplanComment,
)
from database.schemas import ActivityDeactivate, ActivitySplit
from calculators.pay_period import get_or_create_period_for_date



@pytest.fixture(autouse=True)
def _employee_in_activity_overview(db, employee):
    """Låse-tests: medarbejderen skal være med i Aktivitetsoversigten, ellers gælder
    låst lønperiode ikke for fravær/kommentarer (2026-10-08)."""
    from conftest import put_in_activity_overview
    put_in_activity_overview(db, employee)

def _user():
    return AppUser(name="Test", initials="LB1", role="admin", password_hash="x")


def _activity(db, employee, closed, source=ActivitySource.manual, activity_type="normal",
              start=datetime(2026, 1, 5, 6, 0), end=datetime(2026, 1, 5, 14, 0), **kw):
    period = get_or_create_period_for_date(start.date(), db)
    period.status = PayPeriodStatus.closed if closed else PayPeriodStatus.open
    a = Activity(
        employee_id=employee.id, pay_period_id=period.id, source=source,
        activity_type=activity_type, start_time=start, end_time=end,
        status=kw.pop("status", ActivityStatus.pending),
        pause_intervals=[], segments=kw.pop("segments", []), **kw,
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


# ── Låst periode ─────────────────────────────────────────────────────────────

def test_cannot_deactivate_normal_activity_in_closed_period(db, employee):
    from routers.activities import deactivate_activity
    a = _activity(db, employee, closed=True, source=ActivitySource.tachograph)
    with pytest.raises(HTTPException) as exc:
        deactivate_activity(a.id, ActivityDeactivate(comment=None), current_user=_user(), db=db)
    assert exc.value.status_code == 400
    db.refresh(a)
    assert a.status == ActivityStatus.pending


def test_cannot_delete_manual_normal_activity_in_closed_period(db, employee):
    from routers.activities import delete_activity
    a = _activity(db, employee, closed=True)
    with pytest.raises(HTTPException) as exc:
        delete_activity(a.id, current_user=_user(), db=db)
    assert exc.value.status_code == 400
    assert db.query(Activity).filter(Activity.id == a.id).first() is not None


def test_can_still_deactivate_normal_activity_in_open_period(db, employee):
    from routers.activities import deactivate_activity
    a = _activity(db, employee, closed=False)
    deactivate_activity(a.id, ActivityDeactivate(comment=None), current_user=_user(), db=db)
    db.refresh(a)
    assert a.status == ActivityStatus.deactivated


def test_undo_edit_cannot_move_activity_into_closed_period(db, employee):
    """Aktiviteten ligger nu i en åben periode, men dens oprindelige dato er i en låst."""
    from routers.activities import undo_edit
    locked = get_or_create_period_for_date(date(2026, 1, 5), db)
    locked.status = PayPeriodStatus.closed
    db.commit()
    a = _activity(db, employee, closed=False,
                  start=datetime(2026, 2, 2, 6, 0), end=datetime(2026, 2, 2, 14, 0))
    a.original_start_time = datetime(2026, 1, 5, 6, 0)
    a.original_end_time = datetime(2026, 1, 5, 14, 0)
    db.commit()
    with pytest.raises(HTTPException) as exc:
        undo_edit(a.id, current_user=_user(), db=db)
    assert exc.value.status_code == 400
    db.refresh(a)
    assert a.start_time == datetime(2026, 2, 2, 6, 0)


def test_cannot_delete_vagtplan_comment_in_closed_period(db, employee, monkeypatch):
    import routers.vagtplan_comments as vc
    monkeypatch.setattr(vc, "_has_edit_access", lambda *a: True)
    period = get_or_create_period_for_date(date(2026, 1, 5), db)
    c = VagtplanComment(employee_id=employee.id, date=date(2026, 1, 5), text="x", created_by="LB1")
    db.add(c)
    period.status = PayPeriodStatus.closed
    db.commit()
    with pytest.raises(HTTPException) as exc:
        vc.delete_comment(c.id, current_user=_user(), db=db)
    assert exc.value.status_code == 400
    assert db.query(VagtplanComment).count() == 1


def test_bulk_auto_approve_skips_closed_period(db, employee):
    from routers.activities import bulk_auto_approve
    from database.models import SystemSettings
    db.add(SystemSettings(id=1, auto_approval_enabled=True))
    db.commit()
    a = _activity(db, employee, closed=True, source=ActivitySource.tachograph)
    result = bulk_auto_approve(period_start="2026-01-05", current_user=_user(), db=db)
    assert result == {"approved": 0, "flagged": 0}
    db.refresh(a)
    assert a.status == ActivityStatus.pending
    assert not a.auto_approval_flags


# ── Split efter 'Ret til andet arbejde' ─────────────────────────────────────

def test_split_after_segment_correction_keeps_original_type(db, employee):
    from routers.activities import split_activity
    segs = [
        ["2026-01-05T06:00:00", "2026-01-05T10:00:00", "driving"],
        ["2026-01-05T10:00:00", "2026-01-05T11:00:00", "work", "rest"],  # rettet pause
        ["2026-01-05T11:00:00", "2026-01-05T14:00:00", "driving"],
    ]
    a = _activity(db, employee, closed=False, source=ActivitySource.tachograph, segments=segs)
    split_activity(a.id, ActivitySplit(split_at=datetime(2026, 1, 5, 10, 30)),
                   current_user=_user(), db=db)
    parts = db.query(Activity).filter(Activity.parent_activity_id == a.id).order_by(Activity.split_part).all()
    assert len(parts) == 2
    assert parts[0].segments[-1] == ["2026-01-05T10:00:00", "2026-01-05T10:30:00", "work", "rest"]
    assert parts[1].segments[0] == ["2026-01-05T10:30:00", "2026-01-05T11:00:00", "work", "rest"]


# ── Lønkørsel 'I alt' = Lønafregning ────────────────────────────────────────

def test_payroll_preview_grand_total_matches_settlement_incl_ferie_and_afspadsering(db, employee):
    from database.models import DispatcherGroup, MasterAgreementType, MasterOvertimeRate
    from calculators.overtime import OT_BEFORE_KEY, OT_13_KEY, OT_EXTRA_KEY
    from routers.payroll_router import payroll_preview
    from routers.payroll_settlement_router import _employee_settlement_data
    db.add(MasterAgreementType(name=employee.agreement_type, hourly_rate=Decimal("150.00")))
    for label, rate in ((OT_BEFORE_KEY, 50), (OT_13_KEY, 75), (OT_EXTRA_KEY, 100)):
        db.add(MasterOvertimeRate(label=label, rate=Decimal(rate)))
    employee.dispatcher_group = DispatcherGroup(name="G", visible_in_activity_overview=True)
    db.commit()
    approved = ActivityStatus.approved
    _activity(db, employee, closed=False, status=approved)
    _activity(db, employee, closed=False, status=approved, activity_type="ferie",
              start=datetime(2026, 1, 6, 6, 0), end=datetime(2026, 1, 6, 14, 0))
    _activity(db, employee, closed=False, status=approved, activity_type="afspadsering",
              start=datetime(2026, 1, 7, 6, 0), end=datetime(2026, 1, 7, 14, 0))

    period = get_or_create_period_for_date(date(2026, 1, 5), db)
    preview = payroll_preview(period_start="2026-01-05", current_user=_user(), db=db)
    emp = next(e for e in preview["employees"] if e["employee_id"] == employee.id)
    settlement = _employee_settlement_data(employee, period.start_date, period.end_date, db)

    assert emp["grand_total_kr"] == pytest.approx(settlement["total_kr"])
    assert emp["ferie_hours"] == pytest.approx(8.0)
    # Ferie og afspadsering er med i totalen (ud over den ene arbejdsdag)
    assert emp["grand_total_kr"] >= emp["total_kr"] + 8 * 150 + emp["afspadsering_hours"] * 150 - 0.01
