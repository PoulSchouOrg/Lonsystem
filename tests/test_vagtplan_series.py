import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from datetime import date, datetime

import pytest
from fastapi import HTTPException

from conftest import make_activity
from database.models import (
    Activity, ActivitySource, ActivityStatus, AppUser, Holiday, PayPeriodStatus, Role,
    VagtplanComment, VagtplanSeries,
)
from calculators.pay_period import get_or_create_period_for_date



@pytest.fixture(autouse=True)
def _employee_in_activity_overview(db, employee):
    """Låse-tests: medarbejderen skal være med i Aktivitetsoversigten, ellers gælder
    låst lønperiode ikke for fravær/kommentarer (2026-10-08)."""
    from conftest import put_in_activity_overview
    put_in_activity_overview(db, employee)

def _admin(db, initials="TST"):
    if not db.query(Role).filter(Role.name == "admin").first():
        db.add(Role(name="admin", display_name="Administrator", is_system=True, permissions=[]))
        db.commit()
    return AppUser(name="Test", initials=initials, role="admin", password_hash="x")


def _lock(db, d: date):
    p = get_or_create_period_for_date(d, db)
    p.status = PayPeriodStatus.closed
    db.commit()


def test_series_model_and_series_id_on_activity_and_comment(db, employee):
    s = VagtplanSeries(employee_id=employee.id, activity_type="ferie", freq="weekly",
                       weekdays="1,3", start_date=date(2026, 10, 13), end_mode="count", end_count=2,
                       created_by="TST")
    db.add(s)
    db.commit()
    assert s.weekday_list == [1, 3]
    a = make_activity(db, employee, datetime(2026, 10, 13, 6), datetime(2026, 10, 13, 14),
                      activity_type="ferie", source=ActivitySource.vagtplan)
    a.series_id = s.id
    c = VagtplanComment(employee_id=employee.id, date=date(2026, 10, 13), text="x", series_id=s.id)
    db.add(c)
    db.commit()
    from routers.activities import _to_response
    from database.schemas import VagtplanCommentResponse
    assert _to_response(a).series_id == s.id
    assert VagtplanCommentResponse.model_validate(c).series_id == s.id


def test_create_manual_activity_row_reclassifies_and_sets_series(db, employee):
    from routers.activities import _create_manual_activity_row
    from database.schemas import ActivityCreate
    employee.hire_date = date(2026, 10, 1)  # ansat < 8 uger
    db.commit()
    body = ActivityCreate(employee_id=employee.id, activity_type="sygdom",
                          start_time=datetime(2026, 10, 13, 6), end_time=datetime(2026, 10, 13, 14),
                          source="vagtplan")
    a = _create_manual_activity_row(db, _admin(db), employee, body, ActivitySource.vagtplan, series_id=None)
    db.commit()
    assert a.activity_type == "sygdom_u_8uger"
    assert a.status == ActivityStatus.approved
    assert a.source == ActivitySource.vagtplan


from database.schemas import VagtplanSeriesCreate


def _ferie_weekly(employee, **kw):
    data = dict(employee_id=employee.id, activity_type="ferie", comment_text=None,
                vehicle_number="1234", freq="weekly", weekdays=[1],
                start_date=date(2026, 10, 13), end_mode="count", end_count=3)
    data.update(kw)
    return VagtplanSeriesCreate(**data)


def test_create_weekly_ferie_series_creates_activities(db, employee):
    from routers.vagtplan_series import create_series
    res = create_series(_ferie_weekly(employee), current_user=_admin(db), db=db)
    acts = db.query(Activity).filter(Activity.series_id == res.series.id).order_by(Activity.start_time).all()
    assert [a.start_time for a in acts] == [datetime(2026, 10, 13, 6), datetime(2026, 10, 20, 6), datetime(2026, 10, 27, 6)]
    assert all(a.end_time.hour == 14 for a in acts)  # 8 t fra arbejdsplanen
    assert all(a.source == ActivitySource.vagtplan for a in acts)
    assert res.created == 3
    assert res.series.description == "Hver tirsdag"
    assert res.series.occurrence_count == 3


def test_create_skips_holiday_for_absence(db, employee):
    from routers.vagtplan_series import create_series
    db.add(Holiday(date=date(2026, 10, 20), name="Testhelligdag"))
    db.commit()
    res = create_series(_ferie_weekly(employee), current_user=_admin(db), db=db)
    dates = [a.start_time.date() for a in db.query(Activity).filter(Activity.series_id == res.series.id)]
    assert sorted(dates) == [date(2026, 10, 13), date(2026, 10, 27), date(2026, 11, 3)]


def test_comment_only_series_ignores_holidays_and_skips_existing_comment(db, employee):
    from routers.vagtplan_series import create_series
    db.add(Holiday(date=date(2026, 10, 20), name="Testhelligdag"))
    db.add(VagtplanComment(employee_id=employee.id, date=date(2026, 10, 27), text="findes"))
    db.commit()
    body = _ferie_weekly(employee, activity_type=None, comment_text="Ringer kl. 10", vehicle_number=None)
    res = create_series(body, current_user=_admin(db), db=db)
    rows = db.query(VagtplanComment).filter(VagtplanComment.series_id == res.series.id).all()
    assert sorted(c.date for c in rows) == [date(2026, 10, 13), date(2026, 10, 20)]
    assert res.skipped_comments == [date(2026, 10, 27)]
    existing = db.query(VagtplanComment).filter(VagtplanComment.date == date(2026, 10, 27)).one()
    assert existing.text == "findes"


def test_absence_plus_comment_creates_both(db, employee):
    from routers.vagtplan_series import create_series
    res = create_series(_ferie_weekly(employee, comment_text="Ferie", end_count=2),
                        current_user=_admin(db), db=db)
    assert db.query(Activity).filter(Activity.series_id == res.series.id).count() == 2
    assert db.query(VagtplanComment).filter(VagtplanComment.series_id == res.series.id).count() == 2


def test_create_rejected_when_any_date_locked(db, employee):
    from routers.vagtplan_series import create_series
    _lock(db, date(2026, 10, 27))
    with pytest.raises(HTTPException) as e:
        create_series(_ferie_weekly(employee), current_user=_admin(db), db=db)
    assert e.value.status_code == 400
    assert "27-10-2026" in e.value.detail
    assert db.query(Activity).count() == 0
    assert db.query(VagtplanSeries).count() == 0


def test_preview_reports_conflicts(db, employee):
    from routers.vagtplan_series import preview_series
    make_activity(db, employee, datetime(2026, 10, 20, 6), datetime(2026, 10, 20, 15))  # kørsel
    db.add(VagtplanComment(employee_id=employee.id, date=date(2026, 10, 27), text="findes"))
    db.commit()
    _lock(db, date(2026, 10, 13))
    p = preview_series(_ferie_weekly(employee, comment_text="x"), current_user=_admin(db), db=db)
    assert p.dates == [date(2026, 10, 13), date(2026, 10, 20), date(2026, 10, 27)]
    assert p.locked_dates == [date(2026, 10, 13)]
    assert p.driving_conflicts == [date(2026, 10, 20)]
    assert p.comment_conflicts == [date(2026, 10, 27)]
    assert p.description == "Hver tirsdag"


def test_preview_reports_no_hours_for_afspadsering(db, employee):
    from routers.vagtplan_series import preview_series
    p = preview_series(_ferie_weekly(employee, activity_type="afspadsering", weekdays=[5], start_date=date(2026, 10, 17), end_count=2),
                       current_user=_admin(db), db=db)
    assert p.skipped_no_hours == [date(2026, 10, 17), date(2026, 10, 24)]


def test_series_schema_validation():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        VagtplanSeriesCreate(employee_id=1, activity_type=None, comment_text=None, freq="weekly",
                             weekdays=[1], start_date=date(2026, 10, 13), end_mode="count", end_count=2)
    with pytest.raises(ValidationError):
        VagtplanSeriesCreate(employee_id=1, activity_type="ferie", freq="weekly", weekdays=[],
                             start_date=date(2026, 10, 13), end_mode="count", end_count=2)
    with pytest.raises(ValidationError):
        VagtplanSeriesCreate(employee_id=1, activity_type="ferie", freq="weekly", weekdays=[1],
                             start_date=date(2026, 10, 13), end_mode="count", end_count=101)
    with pytest.raises(ValidationError):
        VagtplanSeriesCreate(employee_id=1, activity_type="ferie", freq="weekly", weekdays=[1],
                             start_date=date(2026, 10, 13), end_mode="date", end_date=date(2026, 10, 1))


def test_create_rejects_normal_type(db, employee):
    from routers.vagtplan_series import create_series
    with pytest.raises(HTTPException) as e:
        create_series(_ferie_weekly(employee, activity_type="normal"), current_user=_admin(db), db=db)
    assert e.value.status_code == 400


def test_create_requires_vagtplan_edit_access(db, employee):
    from routers.vagtplan_series import create_series
    db.add(Role(name="kontor", display_name="Kontor", is_system=False, permissions=["vagtplan_view", "vagtplan_edit_own"]))
    db.commit()
    other = AppUser(name="Anden", initials="XYZ", role="kontor", password_hash="x")
    with pytest.raises(HTTPException) as e:
        create_series(_ferie_weekly(employee), current_user=other, db=db)
    assert e.value.status_code == 403
    employee.initials = "XYZ"
    db.commit()
    res = create_series(_ferie_weekly(employee), current_user=other, db=db)
    assert res.created == 3


from database.schemas import VagtplanSeriesEndUpdate


def _make_series(db, employee, **kw):
    from routers.vagtplan_series import create_series
    return create_series(_ferie_weekly(employee, **kw), current_user=_admin(db), db=db).series


def _series_dates(db, sid):
    return sorted(a.start_time.date() for a in db.query(Activity).filter(Activity.series_id == sid))


def test_get_series(db, employee):
    from routers.vagtplan_series import get_series
    s = _make_series(db, employee)
    r = get_series(s.id, current_user=_admin(db), db=db)
    assert r.occurrence_count == 3 and r.last_date == date(2026, 10, 27)


def test_extend_by_count_adds_after_last(db, employee):
    from routers.vagtplan_series import update_series_end
    s = _make_series(db, employee)
    r = update_series_end(s.id, VagtplanSeriesEndUpdate(end_mode="count", end_count=5),
                          current_user=_admin(db), db=db)
    assert r.added == 2 and r.removed == 0
    assert _series_dates(db, s.id)[-2:] == [date(2026, 11, 3), date(2026, 11, 10)]
    assert r.series.end_count == 5


def test_deleted_occurrence_is_not_recreated_on_extend(db, employee):
    from routers.vagtplan_series import update_series_end
    s = _make_series(db, employee)
    mid = db.query(Activity).filter(Activity.series_id == s.id,
                                    Activity.start_time == datetime(2026, 10, 20, 6)).one()
    db.delete(mid)
    db.commit()
    update_series_end(s.id, VagtplanSeriesEndUpdate(end_mode="count", end_count=4),
                      current_user=_admin(db), db=db)
    assert _series_dates(db, s.id) == [date(2026, 10, 13), date(2026, 10, 27), date(2026, 11, 3), date(2026, 11, 10)]


def test_shorten_by_date_deletes_approved_tail(db, employee):
    from routers.vagtplan_series import update_series_end
    s = _make_series(db, employee)
    r = update_series_end(s.id, VagtplanSeriesEndUpdate(end_mode="date", end_date=date(2026, 10, 20)),
                          current_user=_admin(db), db=db)
    assert r.removed == 1
    assert _series_dates(db, s.id) == [date(2026, 10, 13), date(2026, 10, 20)]
    assert r.series.end_mode == "date" and r.series.end_count is None


def test_shorten_by_count(db, employee):
    from routers.vagtplan_series import update_series_end
    s = _make_series(db, employee)
    update_series_end(s.id, VagtplanSeriesEndUpdate(end_mode="count", end_count=1),
                      current_user=_admin(db), db=db)
    assert _series_dates(db, s.id) == [date(2026, 10, 13)]


def test_change_rejected_when_removed_day_locked(db, employee):
    from routers.vagtplan_series import update_series_end
    s = _make_series(db, employee)
    _lock(db, date(2026, 10, 27))
    with pytest.raises(HTTPException) as e:
        update_series_end(s.id, VagtplanSeriesEndUpdate(end_mode="count", end_count=1),
                          current_user=_admin(db), db=db)
    # 20/10 og 27/10 ligger i samme lønperiode (19/10–1/11) → første blokerende dato nævnes
    assert "lønperioden er låst" in e.value.detail
    assert len(_series_dates(db, s.id)) == 3


def test_change_rejected_when_added_day_locked(db, employee):
    from routers.vagtplan_series import update_series_end
    s = _make_series(db, employee)
    _lock(db, date(2026, 11, 3))
    with pytest.raises(HTTPException):
        update_series_end(s.id, VagtplanSeriesEndUpdate(end_mode="count", end_count=4),
                          current_user=_admin(db), db=db)
    assert len(_series_dates(db, s.id)) == 3


def test_cannot_remove_all_occurrences(db, employee):
    from routers.vagtplan_series import update_series_end
    s = _make_series(db, employee)
    update_series_end(s.id, VagtplanSeriesEndUpdate(end_mode="date", end_date=date(2026, 10, 13)),
                      current_user=_admin(db), db=db)
    assert _series_dates(db, s.id) == [date(2026, 10, 13)]
    with pytest.raises(HTTPException) as e:
        update_series_end(s.id, VagtplanSeriesEndUpdate(end_mode="date", end_date=date(2026, 10, 12)),
                          current_user=_admin(db), db=db)
    assert "mindst én forekomst" in e.value.detail


def test_delete_series_keeps_locked(db, employee):
    from routers.vagtplan_series import delete_series
    s = _make_series(db, employee, comment_text="Ferie")
    _lock(db, date(2026, 10, 13))
    r = delete_series(s.id, current_user=_admin(db), db=db)
    assert r.deleted == 2 and r.kept_locked == 1 and r.kept_split == 0
    assert _series_dates(db, s.id) == [date(2026, 10, 13)]
    assert db.query(VagtplanComment).filter(VagtplanComment.series_id == s.id).count() == 1
    assert db.query(VagtplanSeries).filter(VagtplanSeries.id == s.id).count() == 1


def test_delete_series_removes_series_row_when_empty(db, employee):
    from routers.vagtplan_series import delete_series
    s = _make_series(db, employee)
    r = delete_series(s.id, current_user=_admin(db), db=db)
    assert r.deleted == 3
    assert db.query(VagtplanSeries).count() == 0
    assert db.query(Activity).count() == 0


def test_delete_occurrence_removes_activity_and_comment(db, employee):
    from routers.vagtplan_series import delete_occurrence
    s = _make_series(db, employee, comment_text="Ferie")
    delete_occurrence(s.id, date(2026, 10, 20), current_user=_admin(db), db=db)
    assert _series_dates(db, s.id) == [date(2026, 10, 13), date(2026, 10, 27)]
    assert sorted(c.date for c in db.query(VagtplanComment).filter(VagtplanComment.series_id == s.id)) == [
        date(2026, 10, 13), date(2026, 10, 27)]


def test_delete_occurrence_locked_rejected(db, employee):
    from routers.vagtplan_series import delete_occurrence
    s = _make_series(db, employee)
    _lock(db, date(2026, 10, 20))
    with pytest.raises(HTTPException) as e:
        delete_occurrence(s.id, date(2026, 10, 20), current_user=_admin(db), db=db)
    assert e.value.status_code == 400


def test_delete_series_requires_access(db, employee):
    from routers.vagtplan_series import delete_series
    s = _make_series(db, employee)
    db.add(Role(name="laeser", display_name="Læser", is_system=False, permissions=["vagtplan_view"]))
    db.commit()
    with pytest.raises(HTTPException) as e:
        delete_series(s.id, current_user=AppUser(name="L", initials="LLL", role="laeser", password_hash="x"), db=db)
    assert e.value.status_code == 403


def test_create_every_second_week_series(db, employee):
    from routers.vagtplan_series import create_series, update_series_end
    res = create_series(_ferie_weekly(employee, week_interval=2), current_user=_admin(db), db=db)
    assert _series_dates(db, res.series.id) == [date(2026, 10, 13), date(2026, 10, 27), date(2026, 11, 10)]
    assert res.series.week_interval == 2
    assert res.series.description == "Hver 2. uge: tirsdag"
    r = update_series_end(res.series.id, VagtplanSeriesEndUpdate(end_mode="count", end_count=4),
                          current_user=_admin(db), db=db)
    assert _series_dates(db, res.series.id)[-1] == date(2026, 11, 24)


def test_week_interval_validation():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        VagtplanSeriesCreate(employee_id=1, activity_type="ferie", freq="weekly", weekdays=[1], week_interval=5,
                             start_date=date(2026, 10, 13), end_mode="count", end_count=2)
