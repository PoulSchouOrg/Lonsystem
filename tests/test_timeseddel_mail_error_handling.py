import logging
from datetime import date

import pytest
from fastapi import HTTPException


def _visible_group(emp):
    from database.models import DispatcherGroup
    # Timesedler sendes kun til medarbejdere i synlige disponentgrupper.
    emp.dispatcher_group = DispatcherGroup(name="Testgruppe", visible_in_activity_overview=True)


def _approved_day(db, emp, day):
    from datetime import datetime
    from conftest import make_activity
    from database.models import ActivityStatus
    start = datetime.combine(day, datetime.min.time()).replace(hour=8)
    make_activity(db, emp, start, start.replace(hour=16), status=ActivityStatus.approved)


def test_send_timeseddel_logs_full_error_and_returns_generic_message(db, employee, monkeypatch, caplog):
    from routers.timeseddel_router import send_timeseddel
    from calculators.pay_period import get_or_create_period_for_date
    import utils.email_sender as email_sender

    _visible_group(employee)
    employee.email = "chauffoer@example.com"
    db.commit()

    period = get_or_create_period_for_date(date(2026, 1, 5), db)
    _approved_day(db, employee, period.start_date)

    def _boom(**kwargs):
        raise RuntimeError("535 5.7.3 Authentication unsuccessful")

    monkeypatch.setattr(email_sender, "send_timeseddel", _boom)

    with caplog.at_level(logging.ERROR):
        with pytest.raises(HTTPException) as exc_info:
            send_timeseddel(
                employee_id=employee.id,
                period_start=period.start_date.isoformat(),
                db=db,
                current_user=None,
            )

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Mailen kunne ikke sendes – kontakt administrator"
    assert "Authentication unsuccessful" not in exc_info.value.detail
    assert "Authentication unsuccessful" in caplog.text
    assert employee.name in caplog.text


def test_send_all_timesedler_logs_full_error_and_returns_generic_failed_entry(db, employee, monkeypatch, caplog):
    from routers.timeseddel_router import send_all_timesedler, SendAllRequest
    from calculators.pay_period import get_or_create_period_for_date
    from conftest import make_activity
    from database.models import ActivityStatus
    from datetime import datetime
    import utils.email_sender as email_sender

    _visible_group(employee)
    employee.email = "chauffoer@example.com"
    db.commit()

    period = get_or_create_period_for_date(date(2026, 1, 5), db)
    make_activity(
        db, employee,
        datetime.combine(period.start_date, datetime.min.time()).replace(hour=8),
        datetime.combine(period.start_date, datetime.min.time()).replace(hour=16),
        status=ActivityStatus.approved,
    )

    def _boom(**kwargs):
        raise RuntimeError("535 5.7.3 Authentication unsuccessful")

    monkeypatch.setattr(email_sender, "send_timeseddel", _boom)

    with caplog.at_level(logging.ERROR):
        result = send_all_timesedler(
            SendAllRequest(from_date=period.start_date, to_date=period.end_date, employee_id=employee.id),
            db=db,
            current_user=None,
        )

    assert result["failed"] == [{"name": employee.name, "error": "Kunne ikke sendes"}]
    assert "Authentication unsuccessful" in caplog.text
    assert employee.name in caplog.text


def _ok_sender(monkeypatch):
    import utils.email_sender as email_sender
    sent = []
    monkeypatch.setattr(email_sender, "send_timeseddel", lambda **kw: sent.append(kw["to_email"]))
    return sent


def test_send_all_skips_funktionaer_hidden_group_and_unapproved(db, employee, monkeypatch):
    """Send-alle: kun ikke-funktionærer i synlige disponentgrupper med godkendte
    aktiviteter – bekræftet af bruger 2026-10-06."""
    from routers.timeseddel_router import send_all_timesedler, SendAllRequest
    from calculators.pay_period import get_or_create_period_for_date
    from conftest import make_activity
    from database.models import ActivityStatus, DispatcherGroup, Employee
    from datetime import datetime

    visible = DispatcherGroup(name="Synlig", visible_in_activity_overview=True)
    hidden = DispatcherGroup(name="Skjult", visible_in_activity_overview=False)
    employee.dispatcher_group = visible
    employee.email = "chauffoer@example.com"

    def _emp(nr, email, group, kind="hourly_fixed"):
        e = Employee(employee_number=nr, first_name="X", last_name=nr, agreement_kind=kind,
                     agreement_type=employee.agreement_type, hire_date=employee.hire_date,
                     work_schedule=employee.work_schedule, email=email, dispatcher_group=group)
        db.add(e)
        return e

    office = _emp("9001", "kontor@example.com", visible, kind="funktionaer")
    hidden_emp = _emp("9002", "skjult@example.com", hidden)
    pending_emp = _emp("9003", "afventer@example.com", visible)
    db.commit()

    period = get_or_create_period_for_date(date(2026, 1, 5), db)
    for e in (employee, office, hidden_emp):
        _approved_day(db, e, period.start_date)
    start = datetime.combine(period.start_date, datetime.min.time()).replace(hour=8)
    make_activity(db, pending_emp, start, start.replace(hour=16), status=ActivityStatus.pending)

    sent = _ok_sender(monkeypatch)
    result = send_all_timesedler(
        SendAllRequest(from_date=period.start_date, to_date=period.end_date),
        db=db, current_user=None,
    )

    assert sent == ["chauffoer@example.com"]
    assert result["skipped_funktionaer"] == [office.name]
    assert pending_emp.name in result["skipped_no_activities"]


def test_send_single_rejects_funktionaer(db, employee, monkeypatch):
    from routers.timeseddel_router import send_timeseddel
    from calculators.pay_period import get_or_create_period_for_date

    _visible_group(employee)
    employee.agreement_kind = "funktionaer"
    employee.email = "kontor@example.com"
    db.commit()
    period = get_or_create_period_for_date(date(2026, 1, 5), db)
    _approved_day(db, employee, period.start_date)
    sent = _ok_sender(monkeypatch)

    with pytest.raises(HTTPException) as exc_info:
        send_timeseddel(employee_id=employee.id, period_start=period.start_date.isoformat(),
                        db=db, current_user=None)
    assert exc_info.value.status_code == 400
    assert sent == []


def test_send_single_rejects_without_approved_activities(db, employee, monkeypatch):
    from routers.timeseddel_router import send_timeseddel
    from calculators.pay_period import get_or_create_period_for_date

    _visible_group(employee)
    employee.email = "chauffoer@example.com"
    db.commit()
    period = get_or_create_period_for_date(date(2026, 1, 5), db)
    sent = _ok_sender(monkeypatch)

    with pytest.raises(HTTPException) as exc_info:
        send_timeseddel(employee_id=employee.id, period_start=period.start_date.isoformat(),
                        db=db, current_user=None)
    assert exc_info.value.status_code == 400
    assert sent == []
