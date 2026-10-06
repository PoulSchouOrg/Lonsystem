"""Funktionærer (agreement_kind='funktionaer') udelades af Danløn-CSV'en, men
vises stadig i Lønkørsel og Lønafregning – bekræftet af bruger 2026-10-06."""
from datetime import date, datetime, timedelta
from decimal import Decimal

from database.models import (
    ActivityStatus, DispatcherGroup, Employee, MasterAgreementType, MasterOvertimeRate,
)
from calculators.overtime import OT_BEFORE_KEY, OT_13_KEY, OT_EXTRA_KEY
from calculators.pay_period import get_or_create_period_for_date


def _setup(db, employee):
    group = DispatcherGroup(name="Testgruppe", visible_in_activity_overview=True)
    employee.dispatcher_group = group
    employee.cvr_number = "13246505"
    db.add(MasterAgreementType(name=employee.agreement_type, hourly_rate=Decimal("150.00")))
    for key in (OT_BEFORE_KEY, OT_13_KEY, OT_EXTRA_KEY):
        db.add(MasterOvertimeRate(label=key, rate=Decimal("0")))
    office = Employee(
        employee_number="9001", first_name="Fie", last_name="Kontor",
        agreement_kind="funktionaer", agreement_type=employee.agreement_type,
        cvr_number="13246505", initials="FK", dispatcher_group=group, active=True,
        hire_date=employee.hire_date, work_schedule=employee.work_schedule,
    )
    db.add(office)
    db.commit()
    return office


def _approved_day(db, emp, day):
    from conftest import make_activity
    start = datetime.combine(day, datetime.min.time()) + timedelta(hours=7)
    make_activity(db, emp, start, start + timedelta(hours=8), status=ActivityStatus.approved)


def test_danloen_csv_excludes_funktionaer_but_keeps_driver(db, employee):
    from routers.payroll_router import _build_danloen_csv, _active_employees
    office = _setup(db, employee)
    period = get_or_create_period_for_date(date(2026, 8, 20), db)
    _approved_day(db, employee, period.start_date)
    _approved_day(db, office, period.start_date)

    employees = _active_employees(db)
    assert office in employees  # stadig med i Lønkørsel-/Lønafregning-grundlaget

    lines = [l for l in _build_danloen_csv(employees, period, db).decode("utf-8").splitlines() if l]
    numbers = {l.split(";")[1] for l in lines}
    assert employee.employee_number in numbers
    assert office.employee_number not in numbers
