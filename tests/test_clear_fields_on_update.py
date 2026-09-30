"""Tømmer man et felt i medarbejder-/aktivitetsmodalen, skal feltet stå tomt
bagefter – ikke bevare den gamle værdi."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from datetime import datetime

from database.models import Activity, ActivitySource, ActivityStatus, AppUser
from database.schemas import ActivityUpdate, EmployeeUpdate
from calculators.pay_period import get_or_create_period_for_date


def _user():
    return AppUser(name="Test", initials="TST", role="admin", password_hash="x")


def _seed_agreement(db):
    from database.models import MasterAgreementType, MasterAgreementKind
    from decimal import Decimal
    db.add(MasterAgreementType(name="Standardoverenskomst", hourly_rate=Decimal("150.00")))
    db.add(MasterAgreementKind(
        key="hourly_fixed", label="Timelønnet, fast arbejdstid",
        is_active=True, is_user_created=False,
        requires_agreement_type=True, sort_order=1,
    ))
    db.commit()


def test_update_employee_clears_emptied_text_fields(db, employee):
    from routers.employees import update_employee
    _seed_agreement(db)
    update_employee(employee.id, EmployeeUpdate(
        email="a@b.dk", phone="12345678", mobile="87654321", address="Vej 1",
        postal_code="8000", initials="ABC", tachograph_card_number="DK000000000001",
    ), current_user=_user(), db=db)

    resp = update_employee(employee.id, EmployeeUpdate(
        email=None, phone=None, mobile=None, address=None,
        postal_code=None, initials=None, tachograph_card_number=None,
    ), current_user=_user(), db=db)

    assert resp.email is None
    assert resp.phone is None
    assert resp.mobile is None
    assert resp.address is None
    assert resp.postal_code is None
    assert resp.tachograph_card_number is None
    db.refresh(employee)
    assert employee.initials is None


def test_update_employee_leaves_fields_not_sent_unchanged(db, employee):
    from routers.employees import update_employee
    _seed_agreement(db)
    update_employee(employee.id, EmployeeUpdate(email="a@b.dk"), current_user=_user(), db=db)
    resp = update_employee(employee.id, EmployeeUpdate(phone="1234"), current_user=_user(), db=db)
    assert resp.email == "a@b.dk"


def _activity(db, employee, **kw):
    start, end = datetime(2026, 1, 5, 6, 0), datetime(2026, 1, 5, 14, 0)
    period = get_or_create_period_for_date(start.date(), db)
    a = Activity(
        employee_id=employee.id, pay_period_id=period.id, source=ActivitySource.manual,
        activity_type="normal", start_time=start, end_time=end,
        status=ActivityStatus.pending, pause_intervals=[], segments=[], **kw,
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


def test_update_activity_clears_vehicle_and_km(db, employee):
    from routers.activities import update_activity
    a = _activity(db, employee, vehicle_number="12", km_start=100, km_end=200)
    update_activity(a.id, ActivityUpdate(vehicle_number=None, km_start=None, km_end=None),
                    current_user=_user(), db=db)
    db.refresh(a)
    assert a.vehicle_number is None
    assert a.km_start is None
    assert a.km_end is None


def test_update_activity_pause_only_leaves_vehicle_and_km(db, employee):
    from routers.activities import update_activity
    a = _activity(db, employee, vehicle_number="12", km_start=100, km_end=200)
    update_activity(a.id, ActivityUpdate(pause_intervals=[]), current_user=_user(), db=db)
    db.refresh(a)
    assert a.vehicle_number == "12"
    assert a.km_start == 100


def test_update_activity_keeps_vehicle_on_multi_vehicle_shift(db, employee):
    """Detaljevisningen sender tomt vognnummer på en vagt med bil-liste – betyder 'uændret'."""
    from routers.activities import update_activity
    uses = [["2026-01-05T06:00:00", "2026-01-05T14:00:00", "AB12345"]]
    a = _activity(db, employee, vehicle_number="12", vehicle_uses=uses)
    update_activity(a.id, ActivityUpdate(vehicle_number=None, km_start=None, km_end=None),
                    current_user=_user(), db=db)
    db.refresh(a)
    assert a.vehicle_number == "12"
