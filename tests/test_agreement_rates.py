"""Daterede overenskomstsatser (2026-10-06): sats pr. lønperiode, ikrafttræden, Stamdata-boks,
fælles advarsel og engangs-indlægning af Lærlingeoverenskomstens satser."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from datetime import date
from decimal import Decimal

import pytest
from fastapi import HTTPException

from calculators.agreement_rates import agreement_rate_for_period, apply_due_rates
from database.models import (
    AppUser, AuditLog, MasterAgreementType, MasterAgreementTypeRate, PayPeriod, PayPeriodStatus, Role,
    SystemSettings,
)

LAST = "Lærling (EUD) Sidste år af lærerkontrakt"
# 1/3-2027 er en mandag midt i lønperioden 22/2–7/3-2027
P_BEFORE = (date(2027, 2, 8), date(2027, 2, 21))
P_CHANGE = (date(2027, 2, 22), date(2027, 3, 7))
P_AFTER = (date(2027, 3, 8), date(2027, 3, 21))


def _user(db, name, perms, system=False):
    db.add(Role(name=name, display_name=name, is_system=system, permissions=perms))
    u = AppUser(name=name, initials=name[:3].upper(), role=name, password_hash="x", active=True)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture
def last_type(db):
    t = MasterAgreementType(name=LAST, hourly_rate=Decimal("119.17"))
    db.add(t)
    db.add(MasterAgreementType(name="Chauffør", hourly_rate=Decimal("174.15")))
    db.add(SystemSettings(id=1, auto_approval_enabled=True))
    db.commit()
    return t


@pytest.fixture
def future_2027(db, last_type):
    r = MasterAgreementTypeRate(agreement_type_id=last_type.id, valid_from=date(2027, 3, 1),
                                hourly_rate=Decimal("123.34"))
    db.add(r)
    db.commit()
    return r


def _rate(db, name, period):
    return agreement_rate_for_period(db, name, *period)


def test_without_dated_rates_nothing_changes(db, last_type):
    for p in (P_BEFORE, P_CHANGE, P_AFTER):
        assert _rate(db, LAST, p) == Decimal("119.17")
        assert _rate(db, "Chauffør", p) == Decimal("174.15")


def test_new_rate_applies_to_whole_period_containing_the_date(db, future_2027):
    assert _rate(db, LAST, P_BEFORE) == Decimal("119.17")
    assert _rate(db, LAST, P_CHANGE) == Decimal("123.34")
    assert _rate(db, LAST, P_AFTER) == Decimal("123.34")


def test_taking_effect_keeps_old_rate_for_older_periods(db, last_type, future_2027):
    assert apply_due_rates(db, date(2027, 2, 28)) == []
    applied = apply_due_rates(db, date(2027, 3, 1))
    assert len(applied) == 1
    db.refresh(last_type)
    assert last_type.hourly_rate == Decimal("123.34")
    assert future_2027.old_rate == Decimal("119.17")
    assert _rate(db, LAST, P_BEFORE) == Decimal("119.17")
    assert _rate(db, LAST, P_CHANGE) == Decimal("123.34")
    assert db.query(AuditLog).filter(AuditLog.action == "agreement_rate_applied").count() == 1


def test_payroll_uses_rate_for_the_period(db, employee, future_2027):
    from routers.payroll_router import _calculate_employee
    employee.agreement_type = LAST
    db.commit()
    assert _calculate_employee(employee, *P_BEFORE, db)["base_hourly_rate"] == 119.17
    assert _calculate_employee(employee, *P_CHANGE, db)["base_hourly_rate"] == 123.34


# ── Stamdata-boksen ──────────────────────────────────────────────────────────

def test_create_edit_delete_future_rate_is_logged(db, last_type):
    from routers.agreement_rates_router import RateBody, create_rate, delete_rate, list_rates, update_rate
    u = _user(db, "lon", ["stamdata"])
    r = create_rate(RateBody(agreement_type_id=last_type.id, valid_from=date(2027, 3, 1), hourly_rate=123.0),
                    current_user=u, db=db)
    update_rate(r["id"], RateBody(agreement_type_id=last_type.id, valid_from=date(2027, 3, 1), hourly_rate=123.34),
                current_user=u, db=db)
    assert [x["hourly_rate"] for x in list_rates(current_user=u, db=db)] == [123.34]
    delete_rate(r["id"], current_user=u, db=db)
    logs = [a.details for a in db.query(AuditLog).order_by(AuditLog.id).all()]
    assert "123.00 kr fra 01.03.2027" in logs[0]
    assert "→" in logs[1] and "123.34" in logs[1]
    assert "slettet" in logs[2] and "123.34 kr fra 01.03.2027" in logs[2]   # nok til at genskabe rækken


def test_applied_rates_cannot_be_changed_or_deleted(db, last_type, future_2027):
    from routers.agreement_rates_router import delete_rate
    future_2027.applied_at = future_2027.created_at or __import__("datetime").datetime.now()
    db.commit()
    with pytest.raises(HTTPException):
        delete_rate(future_2027.id, current_user=_user(db, "lon", ["stamdata"]), db=db)


def test_duplicate_and_locked_period_rejected(db, last_type, future_2027):
    from routers.agreement_rates_router import RateBody, create_rate
    u = _user(db, "lon", ["stamdata"])
    with pytest.raises(HTTPException):
        create_rate(RateBody(agreement_type_id=last_type.id, valid_from=date(2027, 3, 1), hourly_rate=1),
                    current_user=u, db=db)
    db.add(PayPeriod(start_date=date(2026, 9, 21), end_date=date(2026, 10, 4), status=PayPeriodStatus.closed))
    db.commit()
    with pytest.raises(HTTPException):
        create_rate(RateBody(agreement_type_id=last_type.id, valid_from=date(2026, 9, 25), hourly_rate=1),
                    current_user=u, db=db)


def test_agreement_type_with_future_rates_cannot_be_deleted(db, last_type, future_2027):
    from routers.stamdata import delete_agreement_type
    with pytest.raises(HTTPException):
        delete_agreement_type(last_type.id, current_user=_user(db, "lon", ["stamdata"]), db=db)


# ── Fælles advarsel ──────────────────────────────────────────────────────────

def test_rate_alert_for_explicit_payroll_role_until_dismissed(db, future_2027):
    from routers.agreement_rates_router import DismissBody, dismiss_rate_alert, rate_alerts
    lon = _user(db, "lon", ["payroll"])
    admin = _user(db, "admin", [], system=True)
    assert rate_alerts(current_user=lon, db=db, today=date(2027, 1, 22)) == []       # > 30 dage før 22/2
    alerts = rate_alerts(current_user=lon, db=db, today=date(2027, 1, 23))
    assert [(a["valid_from"], a["period_start"], a["rates"][0]["new_rate"]) for a in alerts] == \
        [(date(2027, 3, 1), date(2027, 2, 22), 123.34)]
    assert rate_alerts(current_user=admin, db=db, today=date(2027, 1, 23)) == []
    dismiss_rate_alert(DismissBody(valid_from=date(2027, 3, 1)), current_user=lon, db=db)
    assert rate_alerts(current_user=lon, db=db, today=date(2027, 2, 1)) == []


# ── Engangs-indlægning ───────────────────────────────────────────────────────

def test_seed_keeps_current_rate_and_adds_history_and_future(db, monkeypatch):
    import database.session as session
    db.add(MasterAgreementType(name=LAST, hourly_rate=Decimal("119.17")))
    db.add(MasterAgreementType(name="EGU-elever", hourly_rate=Decimal("70.74")))
    db.commit()
    monkeypatch.setattr(session, "SessionLocal", lambda: db)
    monkeypatch.setattr(db, "close", lambda: None)
    session._seed_agreement_rates_2025_2028()
    session._seed_agreement_rates_2025_2028()     # kun én gang

    last = db.query(MasterAgreementType).filter_by(name=LAST).one()
    assert last.hourly_rate == (Decimal("123.34") if date.today() >= date(2027, 3, 1) else Decimal("119.17"))
    assert _rate(db, LAST, (date(2025, 6, 2), date(2025, 6, 15))) == Decimal("115.14")
    assert _rate(db, LAST, (date(2026, 3, 2), date(2026, 3, 15))) == Decimal("119.17")
    assert _rate(db, LAST, P_AFTER) == Decimal("123.34")
    assert db.query(MasterAgreementTypeRate).filter_by(agreement_type_id=last.id).count() == 3

    egu = db.query(MasterAgreementType).filter_by(name="EGU-elever").one()
    assert egu.hourly_rate >= Decimal("82.36")                                   # 70,74 → 79,57 → 82,36
    assert _rate(db, "EGU-elever", (date(2025, 1, 6), date(2025, 1, 19))) == Decimal("70.74")
    disp = db.query(MasterAgreementType).filter_by(name="Lærling (EUD) Disponentspecialet, sidste uddannelsestrin").one()
    assert _rate(db, disp.name, P_AFTER) == Decimal("130.86")


def test_rate_alert_shows_reason_and_affected_employees(db, employee, future_2027):
    from routers.agreement_rates_router import rate_alerts
    future_2027.note = "Lærlingeoverenskomsten 2025-2028"
    employee.agreement_type = LAST
    db.commit()
    lon = _user(db, "lon", ["payroll"])
    r = rate_alerts(current_user=lon, db=db, today=date(2027, 2, 1))[0]["rates"][0]
    assert (r["note"], r["employees"]) == ("Lærlingeoverenskomsten 2025-2028", ["Test Chauffør"])


def test_reason_is_saved_and_logged(db, last_type):
    from routers.agreement_rates_router import RateBody, create_rate
    r = create_rate(RateBody(agreement_type_id=last_type.id, valid_from=date(2027, 3, 1), hourly_rate=123.34,
                             note="  Lokal lønaftale  "), current_user=_user(db, "lon", ["stamdata"]), db=db)
    assert r["note"] == "Lokal lønaftale"
    assert "begrundelse: Lokal lønaftale" in db.query(AuditLog).one().details
