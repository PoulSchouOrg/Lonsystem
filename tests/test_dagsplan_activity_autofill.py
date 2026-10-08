import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from datetime import date, datetime

from database.models import AppUser, DailyPlanAssignment, Vehicle
from database.schemas import ActivityCreate


def _user():
    return AppUser(name="Test", initials="TST", role="disponent", password_hash="x")


def _vehicle(db, number="52", reg="BN47449", vognpark=True):
    # Autoudfyldning bruger kun vogne der vises i Dagsplanen (Vognpark-flueben, 2026-10-08)
    v = Vehicle(registration_number=reg, vehicle_number=number, vognpark=vognpark)
    db.add(v)
    db.commit()
    db.refresh(v)
    return v


def test_normal_activity_autofills_vehicle_number_from_dagsplan(db, employee):
    from routers.activities import create_manual_activity
    v = _vehicle(db)
    db.add(DailyPlanAssignment(date=date(2026, 9, 9), vehicle_id=v.id, employee_id=employee.id))
    db.commit()

    body = ActivityCreate(employee_id=employee.id, activity_type="normal",
                          start_time=datetime(2026, 9, 9, 6, 0), end_time=datetime(2026, 9, 9, 14, 0))
    resp = create_manual_activity(body, current_user=_user(), db=db)
    assert resp.vehicle_number == "52"


def test_normal_activity_autofills_from_fast_bil_when_no_assignment_saved(db, employee):
    from routers.activities import create_manual_activity
    v = _vehicle(db)
    employee.fast_bil = True
    employee.fast_bil_vehicle_id = v.id
    db.commit()

    body = ActivityCreate(employee_id=employee.id, activity_type="normal",
                          start_time=datetime(2026, 9, 9, 6, 0), end_time=datetime(2026, 9, 9, 14, 0))
    resp = create_manual_activity(body, current_user=_user(), db=db)
    assert resp.vehicle_number == "52"


def test_normal_activity_does_not_overwrite_explicit_vehicle_number(db, employee):
    from routers.activities import create_manual_activity
    v = _vehicle(db)
    db.add(DailyPlanAssignment(date=date(2026, 9, 9), vehicle_id=v.id, employee_id=employee.id))
    db.commit()

    body = ActivityCreate(employee_id=employee.id, activity_type="normal",
                          start_time=datetime(2026, 9, 9, 6, 0), end_time=datetime(2026, 9, 9, 14, 0),
                          vehicle_number="99")
    resp = create_manual_activity(body, current_user=_user(), db=db)
    assert resp.vehicle_number == "99"


def test_absence_type_activity_not_affected_by_dagsplan_assignment(db, employee):
    """Fraværstyper bruger fortsat kun den eksisterende disponentgruppe-baserede
    autoudfyldning (frontend) - Dagsplan-opslaget må ikke røre ved dem."""
    from routers.activities import create_manual_activity
    v = _vehicle(db)
    db.add(DailyPlanAssignment(date=date(2026, 9, 9), vehicle_id=v.id, employee_id=employee.id))
    db.commit()

    body = ActivityCreate(employee_id=employee.id, activity_type="ferie",
                          start_time=datetime(2026, 9, 9, 6, 0), end_time=datetime(2026, 9, 9, 14, 0))
    resp = create_manual_activity(body, current_user=_user(), db=db)
    assert resp.vehicle_number is None
