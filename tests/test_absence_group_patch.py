import sys, os
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from datetime import datetime, date

import pytest
from fastapi import HTTPException

from database.models import Activity, AppUser, ActivityStatus, ActivitySource, PayPeriodStatus, Role
from database.schemas import AbsenceGroupDatesUpdate


def _user(role="lonbogholder", initials="LB1"):
    return AppUser(name="Test", initials=initials, role=role, password_hash="x")


def _grant(db, role_name, permissions, is_system=False):
    db.add(Role(name=role_name, display_name=role_name, is_system=is_system, permissions=permissions))
    db.commit()


def _make_group(db, employee, dates, activity_type="ferie", status=ActivityStatus.approved,
                group_id="grp-1", source=ActivitySource.manual):
    from conftest import make_activity
    acts = []
    for d in dates:
        a = make_activity(db, employee,
                          datetime.combine(d, datetime.min.time().replace(hour=6)),
                          datetime.combine(d, datetime.min.time().replace(hour=14)),
                          activity_type=activity_type, source=source, status=status)
        a.absence_group_id = group_id
        acts.append(a)
    db.commit()
    return acts


def test_shrinking_range_deletes_pending_days_outside_new_range(db, employee):
    from routers.activities import update_absence_group_dates
    dates = [date(2026, 1, 5), date(2026, 1, 6), date(2026, 1, 7), date(2026, 1, 8), date(2026, 1, 9)]
    _make_group(db, employee, dates, status=ActivityStatus.pending)

    body = AbsenceGroupDatesUpdate(new_start_date=date(2026, 1, 5), new_end_date=date(2026, 1, 7))
    result = update_absence_group_dates("grp-1", body, current_user=_user(), db=db)

    remaining_dates = sorted(a.start_time.date() for a in result.activities)
    assert remaining_dates == [date(2026, 1, 5), date(2026, 1, 6), date(2026, 1, 7)]
    assert db.query(Activity).filter(Activity.absence_group_id == "grp-1").count() == 3


def test_growing_range_creates_new_days_with_scheduled_hours(db, employee):
    from routers.activities import update_absence_group_dates
    dates = [date(2026, 1, 5), date(2026, 1, 6), date(2026, 1, 7), date(2026, 1, 8), date(2026, 1, 9)]
    _make_group(db, employee, dates)

    body = AbsenceGroupDatesUpdate(new_start_date=date(2026, 1, 5), new_end_date=date(2026, 1, 13))
    result = update_absence_group_dates("grp-1", body, current_user=_user(), db=db)

    remaining_dates = sorted(a.start_time.date() for a in result.activities)
    assert remaining_dates == [date(2026, 1, 5), date(2026, 1, 6), date(2026, 1, 7),
                               date(2026, 1, 8), date(2026, 1, 9),
                               date(2026, 1, 12), date(2026, 1, 13)]
    new_day = next(a for a in result.activities if a.start_time.date() == date(2026, 1, 12))
    assert new_day.start_time.strftime("%H:%M") == "06:00"
    assert new_day.end_time.strftime("%H:%M") == "14:00"  # 8 timer skemalagt (mandag)
    assert new_day.status == ActivityStatus.approved
    assert result.skipped == []


def test_unchanged_days_are_not_touched(db, employee):
    from routers.activities import update_absence_group_dates
    dates = [date(2026, 1, 5), date(2026, 1, 6)]
    acts = _make_group(db, employee, dates)
    original_id = acts[0].id
    original_approved_at = acts[0].approved_at

    body = AbsenceGroupDatesUpdate(new_start_date=date(2026, 1, 5), new_end_date=date(2026, 1, 7))
    update_absence_group_dates("grp-1", body, current_user=_user(), db=db)

    kept = db.query(Activity).filter(Activity.id == original_id).first()
    assert kept is not None
    assert kept.approved_at == original_approved_at


def test_removing_day_in_closed_period_blocks_entire_call(db, employee):
    from routers.activities import update_absence_group_dates
    from conftest import put_in_activity_overview
    put_in_activity_overview(db, employee)  # låsen gælder kun medarbejdere i oversigten
    dates = [date(2026, 1, 5), date(2026, 1, 6), date(2026, 1, 7)]
    acts = _make_group(db, employee, dates, status=ActivityStatus.pending)
    # Luk lønperioden for den dag der skulle fjernes
    acts[2].pay_period.status = PayPeriodStatus.closed
    db.commit()

    body = AbsenceGroupDatesUpdate(new_start_date=date(2026, 1, 5), new_end_date=date(2026, 1, 6))
    with pytest.raises(HTTPException) as exc_info:
        update_absence_group_dates("grp-1", body, current_user=_user(), db=db)
    assert exc_info.value.status_code == 400

    # Intet må være ændret – alle tre dage skal stadig findes
    assert db.query(Activity).filter(Activity.absence_group_id == "grp-1").count() == 3


def test_removing_split_activity_blocks_entire_call(db, employee):
    from routers.activities import update_absence_group_dates
    dates = [date(2026, 1, 5), date(2026, 1, 6)]
    acts = _make_group(db, employee, dates, status=ActivityStatus.pending)
    # Simulér et split-barn på den dag der skulle fjernes
    child = Activity(
        employee_id=employee.id, pay_period_id=acts[1].pay_period_id, source=ActivitySource.manual,
        activity_type="ferie", start_time=acts[1].start_time, end_time=acts[1].end_time,
        status=ActivityStatus.pending, pause_intervals=[], segments=[],
        parent_activity_id=acts[1].id, split_part=1,
    )
    db.add(child)
    db.commit()

    body = AbsenceGroupDatesUpdate(new_start_date=date(2026, 1, 5), new_end_date=date(2026, 1, 5))
    with pytest.raises(HTTPException) as exc_info:
        update_absence_group_dates("grp-1", body, current_user=_user(), db=db)
    assert exc_info.value.status_code == 400
    assert db.query(Activity).filter(Activity.absence_group_id == "grp-1").count() == 2


def test_afspadsering_skips_day_with_no_scheduled_hours(db):
    from routers.activities import update_absence_group_dates
    from database.models import Employee, AgreementKind
    emp = Employee(
        employee_number="9998", first_name="Test", last_name="Afspadserer",
        agreement_kind=AgreementKind.hourly_fixed, agreement_type="Standardoverenskomst",
        hire_date=date(2020, 1, 1),
        work_schedule={"even": [8, 8, 0, 8, 8, 0, 0], "odd": [8, 8, 0, 8, 8, 0, 0]},  # onsdag = 0
    )
    db.add(emp)
    db.commit()
    db.refresh(emp)

    dates = [date(2026, 1, 5), date(2026, 1, 6)]  # man+tir
    _make_group(db, emp, dates, activity_type="afspadsering")

    body = AbsenceGroupDatesUpdate(new_start_date=date(2026, 1, 5), new_end_date=date(2026, 1, 7))  # +onsdag
    result = update_absence_group_dates("grp-1", body, current_user=_user(), db=db)

    assert result.skipped == [date(2026, 1, 7).isoformat()]
    remaining_dates = sorted(a.start_time.date() for a in result.activities)
    assert date(2026, 1, 7) not in remaining_dates


def test_vagtplan_source_without_permission_is_forbidden(db, employee):
    from routers.activities import update_absence_group_dates
    _grant(db, "disponent", [])
    _make_group(db, employee, [date(2026, 1, 5), date(2026, 1, 6)], source=ActivitySource.vagtplan)

    body = AbsenceGroupDatesUpdate(new_start_date=date(2026, 1, 5), new_end_date=date(2026, 1, 6))
    with pytest.raises(HTTPException) as exc_info:
        update_absence_group_dates("grp-1", body, current_user=_user(role="disponent", initials="DSP"), db=db)
    assert exc_info.value.status_code == 403


def test_vagtplan_source_with_permission_succeeds(db, employee):
    from routers.activities import update_absence_group_dates
    _grant(db, "disponent", ["vagtplan_edit_all"])
    _make_group(db, employee, [date(2026, 1, 5), date(2026, 1, 6)], source=ActivitySource.vagtplan)

    body = AbsenceGroupDatesUpdate(new_start_date=date(2026, 1, 5), new_end_date=date(2026, 1, 6))
    result = update_absence_group_dates("grp-1", body, current_user=_user(role="disponent", initials="DSP"), db=db)
    assert len(result.activities) == 2


def test_growing_overnatning_range_includes_weekend_with_midnight_times(db, employee):
    from routers.activities import update_absence_group_dates
    dates = [date(2026, 1, 5), date(2026, 1, 6)]  # man+tir
    _make_group(db, employee, dates, activity_type="overnatning")

    body = AbsenceGroupDatesUpdate(new_start_date=date(2026, 1, 5), new_end_date=date(2026, 1, 11))  # +weekend
    result = update_absence_group_dates("grp-1", body, current_user=_user(), db=db)

    remaining_dates = sorted(a.start_time.date() for a in result.activities)
    assert remaining_dates == [date(2026, 1, 5), date(2026, 1, 6), date(2026, 1, 7),
                               date(2026, 1, 8), date(2026, 1, 9), date(2026, 1, 10),
                               date(2026, 1, 11)]
    saturday = next(a for a in result.activities if a.start_time.date() == date(2026, 1, 10))
    assert saturday.start_time.strftime("%H:%M") == "00:00"
    assert saturday.end_time == saturday.start_time
    assert saturday.activity_type == "overnatning"
    assert saturday.status == ActivityStatus.approved
    assert result.skipped == []


def test_growing_dob_overnatning_range_includes_weekend(db, employee):
    from routers.activities import update_absence_group_dates
    dates = [date(2026, 1, 5)]
    _make_group(db, employee, dates, activity_type="dob_overnatning")

    body = AbsenceGroupDatesUpdate(new_start_date=date(2026, 1, 5), new_end_date=date(2026, 1, 6))
    result = update_absence_group_dates("grp-1", body, current_user=_user(), db=db)

    remaining_dates = sorted(a.start_time.date() for a in result.activities)
    assert remaining_dates == [date(2026, 1, 5), date(2026, 1, 6)]
    for a in result.activities:
        assert a.activity_type == "dob_overnatning"
    new_day = next(a for a in result.activities if a.start_time.date() == date(2026, 1, 6))
    assert new_day.start_time == new_day.end_time
    assert new_day.start_time.strftime("%H:%M") == "00:00"


def test_shrinking_overnatning_range_deletes_pending_days_outside_new_range(db, employee):
    from routers.activities import update_absence_group_dates
    dates = [date(2026, 1, 5), date(2026, 1, 6), date(2026, 1, 7)]
    _make_group(db, employee, dates, activity_type="overnatning", status=ActivityStatus.pending)

    body = AbsenceGroupDatesUpdate(new_start_date=date(2026, 1, 5), new_end_date=date(2026, 1, 6))
    result = update_absence_group_dates("grp-1", body, current_user=_user(), db=db)

    remaining_dates = sorted(a.start_time.date() for a in result.activities)
    assert remaining_dates == [date(2026, 1, 5), date(2026, 1, 6)]
    assert db.query(Activity).filter(Activity.absence_group_id == "grp-1").count() == 2


def test_ferie_range_still_uses_weekday_dates_not_all_dates(db, employee):
    """Regression: almindelige fraværstyper må IKKE pludselig få weekend-dage med."""
    from routers.activities import update_absence_group_dates
    dates = [date(2026, 1, 5)]
    _make_group(db, employee, dates, activity_type="ferie")

    body = AbsenceGroupDatesUpdate(new_start_date=date(2026, 1, 5), new_end_date=date(2026, 1, 11))  # +weekend
    result = update_absence_group_dates("grp-1", body, current_user=_user(), db=db)

    remaining_dates = sorted(a.start_time.date() for a in result.activities)
    assert date(2026, 1, 10) not in remaining_dates  # lørdag
    assert date(2026, 1, 11) not in remaining_dates  # søndag
