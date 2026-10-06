"""Anciennitet som lønstigning (2026-10-06): varsel før, godkend fra en lønperiode (hele perioden),
'Mulig fejl' hvis glemt, tæller fra anciennitetsdato hvis udfyldt – samme forløb som elevløn."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from datetime import date
from decimal import Decimal

import pytest
from fastapi import HTTPException

from database.models import AppUser, ElevStepDecision, MasterAgreementType, Role, SystemSettings

BASE, NINE = "Chauffør", "Chauffør. 9 mdr anciennitet"
# Ansat 20/2-2026 → 9 måneder fredag 20/11-2026, i lønperioden 16/11–29/11-2026
EVENT, EFFECTIVE = date(2026, 11, 20), date(2026, 11, 16)


def _user(db, name, perms):
    db.add(Role(name=name, display_name=name, is_system=False, permissions=perms))
    u = AppUser(name=name, initials=name[:3].upper(), role=name, password_hash="x", active=True)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture
def emp(db, employee):
    db.add(MasterAgreementType(name=BASE, hourly_rate=Decimal("174.15")))
    db.add(MasterAgreementType(name=NINE, hourly_rate=Decimal("182.30")))
    db.add(SystemSettings(id=1, auto_approval_enabled=True))
    employee.agreement_type, employee.hire_date = BASE, date(2026, 2, 20)
    db.commit()
    return employee


@pytest.fixture
def lon(db):
    return _user(db, "lon", ["anciennitet_alert"])


def _alerts(db, user, today):
    from routers.elev_router import alerts
    return alerts(current_user=user, db=db, today=today)


def test_upcoming_with_wage_rise_text(db, emp, lon):
    assert _alerts(db, lon, date(2026, 10, 16))["upcoming"] == []             # > 30 dage før
    [u] = _alerts(db, lon, date(2026, 10, 17))["upcoming"]
    assert (u["kind"], u["event_date"], u["effective_from"], u["to_type"]) == ("anciennitet", EVENT, EFFECTIVE, NINE)
    assert u["reason"] == ("Fra lønperioden 16. november til 29. november 2026 stiger Test Chaufførs timesats fra "
                           "174,15 kr til 182,30 kr, fordi Test når 9 måneders anciennitet den 20. november 2026 "
                           "(ansat 20. februar 2026).")


def test_counts_from_seniority_date_when_set(db, emp, lon):
    emp.seniority_date = date(2026, 1, 5)                  # 9 mdr den 5/10-2026
    db.commit()
    [m] = _alerts(db, lon, date(2026, 10, 6))["mismatches"]
    assert m["event_date"] == date(2026, 10, 5) and "(anciennitetsdato 5. januar 2026)" in m["reason"]


def test_approve_from_period_then_applied(db, emp, lon):
    from calculators.elev_agreement import agreement_type_for_period
    from routers.elev_router import DecisionBody, create_decision
    create_decision(DecisionBody(kind="anciennitet", employee_id=emp.id, event_date=EVENT, decision="approve",
                                 to_type=NINE), current_user=lon, db=db, today=date(2026, 11, 1))
    assert agreement_type_for_period(db, emp, date(2026, 11, 2)) == BASE
    assert agreement_type_for_period(db, emp, EFFECTIVE) == NINE          # hele perioden
    res = _alerts(db, lon, EFFECTIVE)
    db.refresh(emp)
    assert emp.agreement_type == NINE
    assert [(a["kind"], a["to_type"]) for a in res["applied"]] == [("anciennitet", NINE)]
    assert res["upcoming"] == [] and res["mismatches"] == []


def test_missed_becomes_mismatch_until_fixed_or_kept(db, emp, lon):
    from routers.elev_router import DecisionBody, create_decision
    [m] = _alerts(db, lon, date(2026, 11, 20))["mismatches"]
    assert (m["kind"], m["current_type"], m["expected_type"], m["suggested_from"]) == ("anciennitet", BASE, NINE, EFFECTIVE)
    assert "Timesatsen er 174,15 kr – den skulle være 182,30 kr." in m["reason"]
    create_decision(DecisionBody(kind="anciennitet", employee_id=emp.id, event_date=EVENT, decision="keep",
                                 to_type=NINE, note="Aftalt"), current_user=lon, db=db, today=date(2026, 11, 20))
    assert _alerts(db, lon, date(2026, 11, 20))["mismatches"] == []


def test_old_dismissal_counts_as_handled(db, emp, lon):
    from datetime import datetime
    emp.anciennitet_dismissed_at = datetime(2026, 1, 1)
    db.commit()
    assert _alerts(db, lon, date(2026, 11, 20)) == {"upcoming": [], "applied": [], "mismatches": []}


def test_permissions_per_kind(db, emp):
    from routers.elev_router import DecisionBody, create_decision
    elev_only = _user(db, "elev", ["elev_wage_approve"])
    assert _alerts(db, elev_only, date(2026, 10, 20))["upcoming"] == []
    with pytest.raises(HTTPException) as e:
        create_decision(DecisionBody(kind="anciennitet", employee_id=emp.id, event_date=EVENT, decision="approve",
                                     to_type=NINE), current_user=elev_only, db=db, today=date(2026, 11, 1))
    assert e.value.status_code == 403
    assert db.query(ElevStepDecision).count() == 0


def test_changed_hire_date_cancels_and_rejects_old_event(db, emp, lon):
    from database.schemas import EmployeeUpdate
    from routers.elev_router import DecisionBody, create_decision
    from routers.employees import update_employee
    create_decision(DecisionBody(kind="anciennitet", employee_id=emp.id, event_date=EVENT, decision="approve",
                                 to_type=NINE), current_user=lon, db=db, today=date(2026, 11, 1))
    hr = _user(db, "hr", ["manage_employees"])
    update_employee(emp.id, EmployeeUpdate(hire_date=date(2026, 3, 20)), current_user=hr, db=db)
    assert db.query(ElevStepDecision).count() == 0
    with pytest.raises(HTTPException) as e:
        create_decision(DecisionBody(kind="anciennitet", employee_id=emp.id, event_date=EVENT, decision="approve",
                                     to_type=NINE), current_user=lon, db=db, today=date(2026, 11, 1))
    assert e.value.status_code == 409


def test_future_date_in_current_period_says_naar(db, emp, lon):
    # 9 mdr den 20/11, men i dag er 17/11 (samme lønperiode) → hele perioden har allerede den nye sats
    [m] = _alerts(db, lon, date(2026, 11, 17))["mismatches"]
    assert m["reason"].startswith("Test Chauffør når 9 måneders anciennitet den 20. november 2026")
