import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from datetime import date

import pytest
from fastapi import HTTPException

from database.models import AppUser, Role
from database.schemas import MilestoneAlertDismiss

TODAY = date(2026, 11, 1)


def _user(db, name, perms):
    db.add(Role(name=name, display_name=name, is_system=False, permissions=perms))
    u = AppUser(name=name, initials=name[:3].upper(), role=name, password_hash="x", active=True)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


ALL = ["birthday_alert", "jubilee_alert", "elev_alert"]


def test_birthday_from_cpr(db, employee):
    from routers.employees import milestone_alerts
    employee.cpr_number = "151186-1234"   # fylder 40 den 15/11-2026
    db.commit()
    alerts = milestone_alerts(current_user=_user(db, "a", ALL), db=db, today=TODAY)
    assert [(a.kind, a.alert_key, a.event_date) for a in alerts] == [("birthday", "birthday_40", date(2026, 11, 15))]
    assert "40" in alerts[0].label


def test_jubilee_uses_seniority_date_before_hire_date(db, employee):
    from routers.employees import milestone_alerts
    employee.hire_date = date(2010, 1, 1)
    employee.seniority_date = date(2001, 11, 20)  # 25 år den 20/11-2026
    db.commit()
    alerts = milestone_alerts(current_user=_user(db, "a", ALL), db=db, today=TODAY)
    assert [a.alert_key for a in alerts] == ["jubilee_25"]


def test_jubilee_falls_back_to_hire_date(db, employee):
    from routers.employees import milestone_alerts
    employee.hire_date = date(1986, 11, 10)  # 40 år
    db.commit()
    assert [a.alert_key for a in milestone_alerts(current_user=_user(db, "a", ALL), db=db, today=TODAY)] == ["jubilee_40"]


def test_elev_alert_only_for_driver_with_elev(db, employee):
    from routers.employees import milestone_alerts
    employee.elev = True
    employee.elev_start_date = date(2023, 8, 1)
    employee.elev_end_date = date(2026, 11, 30)
    db.commit()
    user = _user(db, "a", ALL)
    assert [a.alert_key for a in milestone_alerts(current_user=user, db=db, today=TODAY)] == ["elev_2026-11-30"]
    employee.agreement_kind = "funktionaer"
    db.commit()
    assert milestone_alerts(current_user=user, db=db, today=TODAY) == []


def test_each_kind_requires_its_own_permission(db, employee):
    from routers.employees import milestone_alerts
    employee.cpr_number = "151186-1234"
    employee.hire_date = date(1986, 11, 10)
    db.commit()
    keys = [a.alert_key for a in milestone_alerts(current_user=_user(db, "a", ["jubilee_alert"]), db=db, today=TODAY)]
    assert keys == ["jubilee_40"]


def test_inactive_employees_and_passed_dates_ignored(db, employee):
    from routers.employees import milestone_alerts
    employee.cpr_number = "151186-1234"
    db.commit()
    user = _user(db, "a", ALL)
    assert milestone_alerts(current_user=user, db=db, today=date(2026, 11, 16)) == []
    employee.active = False
    db.commit()
    assert milestone_alerts(current_user=user, db=db, today=TODAY) == []


def test_dismiss_is_per_user_and_per_event(db, employee):
    from routers.employees import dismiss_milestone_alert, milestone_alerts
    employee.cpr_number = "151186-1234"
    db.commit()
    a, b = _user(db, "a", ALL), _user(db, "b", ALL)
    dismiss_milestone_alert(employee.id, MilestoneAlertDismiss(alert_key="birthday_40"), current_user=a, db=db)
    dismiss_milestone_alert(employee.id, MilestoneAlertDismiss(alert_key="birthday_40"), current_user=a, db=db)  # idempotent
    assert milestone_alerts(current_user=a, db=db, today=TODAY) == []
    assert len(milestone_alerts(current_user=b, db=db, today=TODAY)) == 1


def test_dismiss_rejects_unknown_key_or_missing_permission(db, employee):
    from routers.employees import dismiss_milestone_alert
    with pytest.raises(HTTPException) as exc:
        dismiss_milestone_alert(employee.id, MilestoneAlertDismiss(alert_key="upcoming"),
                                current_user=_user(db, "a", ALL), db=db)
    assert exc.value.status_code == 400
    with pytest.raises(HTTPException) as exc:
        dismiss_milestone_alert(employee.id, MilestoneAlertDismiss(alert_key="birthday_40"),
                                current_user=_user(db, "b", ["elev_alert"]), db=db)
    assert exc.value.status_code == 403
