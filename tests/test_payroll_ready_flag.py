import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from datetime import date

import pytest
from fastapi import HTTPException

from database.models import AppUser, EmployeePayrollReadyFlag, PayPeriodStatus, Role
from calculators.pay_period import get_or_create_period_for_date


def _user():
    return AppUser(name="Test", initials="ADM", role="admin", password_hash="x")


def _period(db, closed=False):
    period = get_or_create_period_for_date(date(2026, 1, 5), db)
    period.status = PayPeriodStatus.closed if closed else PayPeriodStatus.open
    db.commit()
    return period


def test_set_and_remove_payroll_ready_flag(db, employee):
    from routers.activities import (
        PayrollReadyFlagUpdate, get_payroll_ready_flags, set_payroll_ready_flag,
    )
    period = _period(db)
    set_payroll_ready_flag(PayrollReadyFlagUpdate(employee_id=employee.id, pay_period_id=period.id, enabled=True),
                           current_user=_user(), db=db)
    assert get_payroll_ready_flags(period.id, current_user=_user(), db=db) == {employee.id: True}

    set_payroll_ready_flag(PayrollReadyFlagUpdate(employee_id=employee.id, pay_period_id=period.id, enabled=False),
                           current_user=_user(), db=db)
    assert get_payroll_ready_flags(period.id, current_user=_user(), db=db) == {}
    # Upsert – kun én række pr. medarbejder pr. periode
    assert db.query(EmployeePayrollReadyFlag).count() == 1


def test_payroll_ready_flag_is_per_period(db, employee):
    from routers.activities import PayrollReadyFlagUpdate, get_payroll_ready_flags, set_payroll_ready_flag
    period = _period(db)
    next_period = get_or_create_period_for_date(period.end_date.fromordinal(period.end_date.toordinal() + 1), db)
    set_payroll_ready_flag(PayrollReadyFlagUpdate(employee_id=employee.id, pay_period_id=period.id, enabled=True),
                           current_user=_user(), db=db)
    assert get_payroll_ready_flags(next_period.id, current_user=_user(), db=db) == {}


def test_payroll_ready_flag_blocked_in_closed_period(db, employee):
    from routers.activities import PayrollReadyFlagUpdate, set_payroll_ready_flag
    period = _period(db, closed=True)
    with pytest.raises(HTTPException) as exc:
        set_payroll_ready_flag(PayrollReadyFlagUpdate(employee_id=employee.id, pay_period_id=period.id, enabled=True),
                               current_user=_user(), db=db)
    assert exc.value.status_code == 400
    assert db.query(EmployeePayrollReadyFlag).count() == 0


def test_toggle_payroll_ready_permission_only_admin(db):
    from auth import ALL_PERMISSIONS, _role_has_permission
    assert "toggle_payroll_ready" in ALL_PERMISSIONS
    db.add(Role(name="admin", display_name="Administrator", is_system=True, permissions=[]))
    db.add(Role(name="lonbogholder", display_name="Lønbogholder", is_system=False,
                permissions=["view_calendar", "toggle_springer"]))
    db.commit()
    assert _role_has_permission(db, "admin", "toggle_payroll_ready")
    assert not _role_has_permission(db, "lonbogholder", "toggle_payroll_ready")
