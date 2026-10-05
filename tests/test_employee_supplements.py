from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi import HTTPException

from database.models import AppUser, EmployeeSupplement, MasterAgreementType, MasterOvertimeRate
from database.schemas import EmployeeSupplementCreate
from calculators.rates_loader import get_supplements_for_period, supplement_sum_on
from routers.employee_supplements import _create_supplement
from calculators.overtime import OT_BEFORE_KEY, OT_13_KEY, OT_EXTRA_KEY
from routers.payroll_router import _calculate_employee


def _dummy_user():
    """Ubevaret AppUser til at kalde route-funktioner direkte i tests uden en
    rigtig session — log_action() læser kun .id/.initials, som begge er None/
    ubrugt på et ugemt objekt, hvilket er fint da AuditLog.user_id er nullable.
    Samme mønster som _test_user() i tests/test_import_ddd.py."""
    return AppUser(name="Test", initials="TST", role="admin", password_hash="x")


def test_supplement_defaults_to_open_ended_with_hardcoded_name_and_type(db, employee):
    row = EmployeeSupplement(employee_id=employee.id, value=Decimal("10.00"), start_date=date(2026, 1, 1))
    db.add(row)
    db.commit()
    db.refresh(row)
    assert row.end_date == date(9999, 12, 31)
    assert row.name == "Ikke overenskomstmæssigt tillæg"
    assert row.type == "Timebaseret"


def test_schema_rejects_non_positive_value():
    with pytest.raises(Exception):
        EmployeeSupplementCreate(employee_id=1, start_date=date(2026, 1, 1), value=0)


def test_schema_accepts_positive_value():
    body = EmployeeSupplementCreate(employee_id=1, start_date=date(2026, 1, 1), value=12.5)
    assert body.value == 12.5


def _setup_rates(db, employee, base="150.00"):
    db.add(MasterAgreementType(name=employee.agreement_type, hourly_rate=Decimal(base)))
    db.add(MasterOvertimeRate(label=OT_BEFORE_KEY, rate=Decimal("0")))
    db.add(MasterOvertimeRate(label=OT_13_KEY, rate=Decimal("0")))
    db.add(MasterOvertimeRate(label=OT_EXTRA_KEY, rate=Decimal("0")))
    db.commit()


def test_no_overlap_returns_empty(db, employee):
    assert get_supplements_for_period(db, employee.id, date(2026, 1, 1), date(2026, 1, 31)) == []


def test_single_overlap_found(db, employee):
    _create_supplement(db, employee.id, date(2026, 1, 1), Decimal("15.00"))
    rows = get_supplements_for_period(db, employee.id, date(2026, 1, 1), date(2026, 1, 31))
    assert [r.value for r in rows] == [Decimal("15.00")]


def test_multiple_active_supplements_are_summed_per_day(db, employee):
    rows_in = [
        _create_supplement(db, employee.id, date(2026, 1, 1), Decimal("10.00")),
        _create_supplement(db, employee.id, date(2026, 1, 15), Decimal("20.00")),
    ]
    rows = get_supplements_for_period(db, employee.id, date(2026, 1, 1), date(2026, 1, 31))
    assert len(rows) == 2
    assert supplement_sum_on(rows, date(2026, 1, 14)) == Decimal("10.00")
    assert supplement_sum_on(rows, date(2026, 1, 15)) == Decimal("30.00")
    assert supplement_sum_on(rows, date(2025, 12, 31)) == Decimal("0")
    assert all(r.end_date == date(9999, 12, 31) for r in rows_in)


def test_create_does_not_close_existing_open_row(db, employee):
    first = _create_supplement(db, employee.id, date(2026, 1, 1), Decimal("10.00"))
    _create_supplement(db, employee.id, date(2026, 2, 1), Decimal("20.00"))
    db.refresh(first)
    assert first.end_date == date(9999, 12, 31)


def test_create_allows_start_date_before_existing_open_row(db, employee):
    _create_supplement(db, employee.id, date(2026, 1, 15), Decimal("10.00"))
    row = _create_supplement(db, employee.id, date(2026, 1, 10), Decimal("20.00"))
    assert row.start_date == date(2026, 1, 10)


def test_create_rejects_non_positive_value(db, employee):
    with pytest.raises(HTTPException):
        _create_supplement(db, employee.id, date(2026, 1, 1), Decimal("0"))


def test_create_rejects_unknown_employee(db):
    with pytest.raises(HTTPException):
        _create_supplement(db, 999999, date(2026, 1, 1), Decimal("10.00"))


def test_calculate_employee_includes_supplement_in_hourly_rate(db, employee):
    _setup_rates(db, employee)
    _create_supplement(db, employee.id, date(2026, 1, 1), Decimal("12.50"))

    calc = _calculate_employee(employee, date(2026, 1, 1), date(2026, 1, 31), db)

    assert calc["hourly_rate"] == pytest.approx(162.50)
    assert calc["supplement_rate"] == pytest.approx(12.50)


def test_calculate_employee_unaffected_when_no_supplement(db, employee):
    _setup_rates(db, employee)

    calc = _calculate_employee(employee, date(2026, 1, 1), date(2026, 1, 31), db)

    assert calc["hourly_rate"] == pytest.approx(150.00)


def test_calculate_employee_sums_supplements_day_by_day(db, employee):
    """10 kr/t hele perioden + 20 kr/t fra 15/1: 8 t den 13/1 à 160 og 8 t den 20/1
    à 180 → gennemsnitssats 170, og kr er præcist dag for dag."""
    from database.models import ActivityStatus
    from conftest import make_activity
    _setup_rates(db, employee)
    _create_supplement(db, employee.id, date(2026, 1, 1), Decimal("10.00"))
    _create_supplement(db, employee.id, date(2026, 1, 15), Decimal("20.00"))
    for d in (13, 20):
        make_activity(db, employee, datetime(2026, 1, d, 8, 0), datetime(2026, 1, d, 16, 0),
                      status=ActivityStatus.approved)
        make_activity(db, employee, datetime(2026, 1, d + 1, 8, 0), datetime(2026, 1, d + 1, 16, 0),
                      activity_type="sygdom", status=ActivityStatus.approved)

    calc = _calculate_employee(employee, date(2026, 1, 1), date(2026, 1, 31), db)

    assert calc["normal_hours"] == pytest.approx(16)
    assert calc["hourly_rate"] == pytest.approx(170.00)
    assert calc["hourly_rates"]["normal"] == pytest.approx(170.00)
    assert calc["hourly_rates"]["sygdom"] == pytest.approx(170.00)
    day_kr = {d["date"]: d["total_kr"] for d in calc["days"] if d["total_hours"]}
    assert day_kr["2026-01-13"] == pytest.approx(8 * 160)
    assert day_kr["2026-01-20"] == pytest.approx(8 * 180)


# ── Punkt A: "Afslut tillæg" ────────────────────────────────────────────────


def test_end_supplement_sets_end_date_to_today(db, employee):
    from routers.employee_supplements import end_supplement
    row = _create_supplement(db, employee.id, date.today() - timedelta(days=5), Decimal("10.00"))
    result = end_supplement(row.id, current_user=_dummy_user(), db=db)
    assert result.end_date == date.today()
    assert result.is_active is True  # i dag er sidste gyldige dag
    assert result.deactivated is True


def test_ended_supplement_keeps_history_but_stops_after_today(db, employee):
    from routers.employee_supplements import end_supplement
    row = _create_supplement(db, employee.id, date.today() - timedelta(days=30), Decimal("10.00"))
    end_supplement(row.id, current_user=_dummy_user(), db=db)
    rows = get_supplements_for_period(db, employee.id, date.today() - timedelta(days=30), date.today() + timedelta(days=30))
    assert supplement_sum_on(rows, date.today() - timedelta(days=20)) == Decimal("10.00")
    assert supplement_sum_on(rows, date.today()) == Decimal("10.00")
    assert supplement_sum_on(rows, date.today() + timedelta(days=1)) == Decimal("0")


def test_end_supplement_rejects_already_ended(db, employee):
    from routers.employee_supplements import end_supplement
    row = _create_supplement(db, employee.id, date.today() - timedelta(days=5), Decimal("10.00"))
    end_supplement(row.id, current_user=_dummy_user(), db=db)
    with pytest.raises(HTTPException):
        end_supplement(row.id, current_user=_dummy_user(), db=db)


def test_end_supplement_rejects_future_row(db, employee):
    from routers.employee_supplements import end_supplement
    row = _create_supplement(db, employee.id, date.today() + timedelta(days=5), Decimal("10.00"))
    with pytest.raises(HTTPException):
        end_supplement(row.id, current_user=_dummy_user(), db=db)


def test_end_supplement_rejects_unknown_id(db):
    from routers.employee_supplements import end_supplement
    with pytest.raises(HTTPException):
        end_supplement(999999, current_user=_dummy_user(), db=db)


def test_get_active_returns_all_active_supplements(db, employee):
    from routers.employee_supplements import get_active_supplement
    _create_supplement(db, employee.id, date.today() - timedelta(days=10), Decimal("10.00"))
    _create_supplement(db, employee.id, date.today() - timedelta(days=5), Decimal("5.00"))
    _create_supplement(db, employee.id, date.today() + timedelta(days=5), Decimal("99.00"))
    active = get_active_supplement(employee.id, current_user=_dummy_user(), db=db)
    assert sorted(a.value for a in active) == [5.0, 10.0]


def test_two_open_rows_allowed_for_same_employee(db, employee):
    db.add(EmployeeSupplement(employee_id=employee.id, value=Decimal("10"), start_date=date(2026, 1, 1)))
    db.add(EmployeeSupplement(employee_id=employee.id, value=Decimal("20"), start_date=date(2026, 6, 1)))
    db.commit()  # det unikke indeks for én åbentstående række er fjernet (2026-10-05)


# ── Punkt F: værdi-præcision ─────────────────────────────────────────────────


def test_create_supplement_rounds_down_to_zero_is_rejected(db, employee):
    with pytest.raises(HTTPException):
        _create_supplement(db, employee.id, date(2026, 1, 1), Decimal("0.001"))


# ── Punkt G: 404 for ukendt employee_id ──────────────────────────────────────


def test_list_supplements_unknown_employee_id_raises_404(db):
    from routers.employee_supplements import list_supplements
    with pytest.raises(HTTPException):
        list_supplements(employee_id=999999, date_from=None, date_to=None, current_user=_dummy_user(), db=db)


def test_get_active_supplement_unknown_employee_id_raises_404(db):
    from routers.employee_supplements import get_active_supplement
    with pytest.raises(HTTPException):
        get_active_supplement(999999, current_user=_dummy_user(), db=db)


# ── Punkt J: is_active-beregning ─────────────────────────────────────────────


def test_is_active_computed_correctly_for_past_present_future(db, employee):
    from routers.employee_supplements import _to_response
    past = EmployeeSupplement(employee_id=employee.id, value=Decimal("10"),
                               start_date=date(2000, 1, 1), end_date=date(2000, 12, 31))
    current = EmployeeSupplement(employee_id=employee.id, value=Decimal("10"),
                                  start_date=date(2000, 1, 1))
    future = EmployeeSupplement(employee_id=employee.id, value=Decimal("10"),
                                 start_date=date(9999, 1, 1), end_date=date(9999, 12, 30))
    for row in (past, current, future):
        db.add(row)
    db.commit()
    assert _to_response(past).is_active is False
    assert _to_response(current).is_active is True
    assert _to_response(future).is_active is False


# ── Punkt B: fraværsoversigten matcher lønkørslens sats ─────────────────────


def test_absence_overview_rate_matches_payroll_calculation(db, employee):
    from database.models import ActivityStatus
    from conftest import make_activity
    from routers.absence_overview_router import _compute_data

    db.add(MasterAgreementType(name=employee.agreement_type, hourly_rate=Decimal("150.00")))
    db.add(MasterOvertimeRate(label=OT_BEFORE_KEY, rate=Decimal("0")))
    db.add(MasterOvertimeRate(label=OT_13_KEY, rate=Decimal("0")))
    db.add(MasterOvertimeRate(label=OT_EXTRA_KEY, rate=Decimal("0")))
    db.commit()
    _create_supplement(db, employee.id, date(2026, 1, 1), Decimal("12.50"))

    make_activity(
        db, employee,
        datetime(2026, 1, 10, 8, 0), datetime(2026, 1, 10, 16, 0),
        activity_type="sygdom", status=ActivityStatus.approved,
    )

    calc = _calculate_employee(employee, date(2026, 1, 1), date(2026, 1, 31), db)
    overview = _compute_data(date(2026, 1, 1), date(2026, 1, 31), db)

    emp_overview = next(e for e in overview["employees"] if e["employee_id"] == employee.id)
    overview_rate = emp_overview["absences"]["sygdom"]["rate"]

    assert overview_rate == pytest.approx(calc["hourly_rate"])
    assert overview_rate == pytest.approx(162.50)
