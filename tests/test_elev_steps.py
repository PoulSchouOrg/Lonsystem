"""Elevløn-trin (2026-10-06): rene regler, popups, godkend/behold og lønkørslens type pr. periode."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from datetime import date, datetime

import pytest
from fastapi import HTTPException

from calculators.elev_steps import (
    STEP_AGREEMENT_TYPES, STEP_LAST, STEP_SECOND_LAST, STEP_THIRD_LAST,
    step_changes, step_for_period, step_on,
)
from database.models import (
    AppUser, ElevStepDecision, MasterAgreementType, PayPeriod, PayPeriodStatus, Role, SystemSettings,
)

THIRD = STEP_AGREEMENT_TYPES[STEP_THIRD_LAST]
SECOND = STEP_AGREEMENT_TYPES[STEP_SECOND_LAST]
LAST = STEP_AGREEMENT_TYPES[STEP_LAST]

# Kontrakt 21/11-2024 – 20/11-2027: sidste år starter lørdag 21/11-2026,
# som ligger i lønperioden 16/11–29/11-2026 (anker mandag 1/6-2026).
START, END = date(2024, 11, 21), date(2027, 11, 20)
EVENT, EFFECTIVE = date(2026, 11, 21), date(2026, 11, 16)


# ── Rene regler ──────────────────────────────────────────────────────────────

def test_step_counts_backwards_from_end_date():
    assert step_on(START, END, date(2026, 11, 20)) == STEP_SECOND_LAST
    assert step_on(START, END, date(2026, 11, 21)) == STEP_LAST
    assert step_on(START, END, date(2025, 11, 21)) == STEP_SECOND_LAST
    assert step_on(START, END, date(2025, 11, 20)) == STEP_THIRD_LAST
    assert step_on(START, END, END) == STEP_LAST
    assert step_on(START, END, date(2027, 11, 21)) is None
    assert step_on(START, END, date(2024, 11, 20)) is None


def test_longer_than_three_years_uses_third_last_rate():
    assert step_on(date(2023, 8, 1), date(2027, 7, 31), date(2024, 1, 15)) == STEP_THIRD_LAST


def test_leap_day_end_date():
    end = date(2028, 2, 29)
    assert step_on(None, end, date(2027, 2, 28)) == STEP_SECOND_LAST
    assert step_on(None, end, date(2027, 3, 1)) == STEP_LAST


def test_change_inside_period_counts_for_whole_period():
    assert step_for_period(START, END, date(2026, 11, 16), date(2026, 11, 29)) == STEP_LAST
    assert step_for_period(START, END, date(2026, 11, 2), date(2026, 11, 15)) == STEP_SECOND_LAST


def test_change_on_contract_start_is_not_a_change():
    changes = step_changes(date(2025, 12, 1), END)
    assert [(c[0], c[2]) for c in changes] == [(EVENT, STEP_LAST)]


# ── Database / router ────────────────────────────────────────────────────────

def _user(db, name, perms, system=False):
    db.add(Role(name=name, display_name=name, is_system=system, permissions=perms))
    u = AppUser(name=name, initials=name[:3].upper(), role=name, password_hash="x", active=True)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture
def elev(db, employee):
    for name, rate in ((THIRD, 93.71), (SECOND, 105.75), (LAST, 119.17), ("Chauffør", 174.15),
                       ("EGU-elever", 70.74)):
        db.add(MasterAgreementType(name=name, hourly_rate=rate))
    db.add(SystemSettings(id=1, auto_approval_enabled=True, elev_alerts_enabled=True,
                          elev_notice_days=30, elev_remind_days=7))
    employee.elev, employee.elev_start_date, employee.elev_end_date = True, START, END
    employee.agreement_type = SECOND
    db.commit()
    return employee


@pytest.fixture
def lon(db):
    return _user(db, "lon", ["elev_wage_approve", "stamdata"])


def _alerts(db, user, today):
    from routers.elev_router import alerts
    return alerts(current_user=user, db=db, today=today)


def test_upcoming_alert_starts_notice_days_before_period(db, elev, lon):
    assert _alerts(db, lon, date(2026, 10, 16))["upcoming"] == []
    up = _alerts(db, lon, date(2026, 10, 17))["upcoming"]
    assert [(u["event_date"], u["effective_from"], u["to_type"]) for u in up] == [(EVENT, EFFECTIVE, LAST)]
    assert "går fra næstsidste ind i sidste år af sin lærekontrakt den 21.11.2026" in up[0]["reason"]


def test_no_popups_when_disabled_or_only_system_role(db, elev, lon):
    admin = _user(db, "admin", [], system=True)
    assert _alerts(db, admin, date(2026, 11, 1))["upcoming"] == []
    db.get(SystemSettings, 1).elev_alerts_enabled = False
    db.commit()
    assert _alerts(db, lon, date(2026, 11, 1))["upcoming"] == []


def test_remind_later_and_never(db, elev, lon):
    from routers.elev_router import SnoozeBody, snooze
    snooze(SnoozeBody(employee_id=elev.id, event_date=EVENT, mode="later"), current_user=lon, db=db)
    assert _alerts(db, lon, date(2026, 11, 1))["upcoming"] == []
    assert len(_alerts(db, lon, date(2026, 11, 9))["upcoming"]) == 1       # 7 dage før 16/11
    snooze(SnoozeBody(employee_id=elev.id, event_date=EVENT, mode="never"), current_user=lon, db=db)
    assert _alerts(db, lon, date(2026, 11, 12))["upcoming"] == []


def test_remind_again_never_setting(db, elev, lon):
    from routers.elev_router import SnoozeBody, snooze
    db.get(SystemSettings, 1).elev_remind_days = None
    db.commit()
    snooze(SnoozeBody(employee_id=elev.id, event_date=EVENT, mode="later"), current_user=lon, db=db)
    assert _alerts(db, lon, date(2026, 11, 12))["upcoming"] == []


def test_approve_schedules_change_for_whole_period(db, elev, lon):
    from calculators.elev_agreement import agreement_type_for_period
    from routers.elev_router import DecisionBody, create_decision
    create_decision(DecisionBody(employee_id=elev.id, event_date=EVENT, decision="approve", to_type=LAST),
                    current_user=lon, db=db, today=date(2026, 11, 1))
    assert elev.agreement_type == SECOND                                   # ikke skiftet endnu
    assert agreement_type_for_period(db, elev, date(2026, 11, 2)) == SECOND
    assert agreement_type_for_period(db, elev, EFFECTIVE) == LAST
    assert _alerts(db, lon, date(2026, 11, 1))["upcoming"] == []           # behandlet

    res = _alerts(db, lon, EFFECTIVE)                                       # træder i kraft
    db.refresh(elev)
    assert elev.agreement_type == LAST
    assert agreement_type_for_period(db, elev, date(2026, 11, 2)) == SECOND  # ældre periode uændret
    assert [(a["from_type"], a["to_type"], a["took_effect"]) for a in res["applied"]] == [(SECOND, LAST, True)]
    assert res["mismatches"] == []

    from routers.elev_router import ack_applied
    ack_applied(res["applied"][0]["decision_id"], current_user=lon, db=db)
    assert _alerts(db, lon, EFFECTIVE)["applied"] == []


def test_manual_type_change_is_not_overwritten(db, elev, lon):
    from routers.elev_router import DecisionBody, create_decision
    create_decision(DecisionBody(employee_id=elev.id, event_date=EVENT, decision="approve", to_type=LAST),
                    current_user=lon, db=db, today=date(2026, 11, 1))
    elev.agreement_type = "Chauffør"
    db.commit()
    res = _alerts(db, lon, EFFECTIVE)
    db.refresh(elev)
    assert elev.agreement_type == "Chauffør"
    assert res["applied"][0]["took_effect"] is False


def test_mismatch_until_fixed_or_kept_with_note(db, elev, lon):
    from routers.elev_router import DecisionBody, create_decision
    today = date(2026, 11, 20)
    mm = _alerts(db, lon, today)["mismatches"]
    assert [(m["period_start"], m["current_type"], m["expected_type"]) for m in mm] == [(EFFECTIVE, SECOND, LAST)]
    assert mm[0]["reason"] == (
        "Test Chauffør går ind i sidste år af sin lærekontrakt den 21.11.2026 (lærekontrakten slutter 20.11.2027). "
        f"Den nye sats gælder fra lønperioden 16.11.–29.11.2026, men er overenskomsttypen stadig '{SECOND}'.")
    later = _alerts(db, lon, date(2026, 12, 1))["mismatches"]       # næste periode, stadig ikke rettet
    assert "men i lønperioden 30.11.–13.12.2026 er overenskomsttypen stadig" in later[-1]["reason"]
    with pytest.raises(HTTPException):
        create_decision(DecisionBody(employee_id=elev.id, event_date=EVENT, decision="keep", to_type=LAST),
                        current_user=lon, db=db, today=today)
    create_decision(DecisionBody(employee_id=elev.id, event_date=EVENT, decision="keep", to_type=LAST,
                                 note="Aftalt med 3F"), current_user=lon, db=db, today=today)
    assert _alerts(db, lon, today)["mismatches"] == []


def test_mismatch_fixed_by_approving_current_period(db, elev, lon):
    from routers.elev_router import DecisionBody, create_decision
    today = date(2026, 11, 20)
    create_decision(DecisionBody(employee_id=elev.id, event_date=EVENT, decision="approve", to_type=LAST,
                                 effective_from=today), current_user=lon, db=db, today=today)
    db.refresh(elev)
    assert elev.agreement_type == LAST
    assert _alerts(db, lon, today)["mismatches"] == []


def test_cannot_approve_into_locked_period(db, elev, lon):
    from routers.elev_router import DecisionBody, create_decision
    db.add(PayPeriod(start_date=EFFECTIVE, end_date=date(2026, 11, 29), status=PayPeriodStatus.closed))
    db.commit()
    with pytest.raises(HTTPException):
        create_decision(DecisionBody(employee_id=elev.id, event_date=EVENT, decision="approve", to_type=LAST),
                        current_user=lon, db=db, today=date(2026, 11, 1))


def test_cancel_scheduled_change(db, elev, lon):
    from routers.elev_router import DecisionBody, cancel_decision, create_decision
    res = create_decision(DecisionBody(employee_id=elev.id, event_date=EVENT, decision="approve", to_type=LAST),
                          current_user=lon, db=db, today=date(2026, 11, 1))
    cancel_decision(res["id"], current_user=lon, db=db)
    assert db.query(ElevStepDecision).count() == 0
    assert len(_alerts(db, lon, date(2026, 11, 1))["upcoming"]) == 1


def test_voksenelev_and_egu_have_no_steps(db, elev, lon):
    from routers.elev_router import overview
    elev.voksenelev = True
    elev.agreement_type = "Chauffør"
    db.commit()
    assert _alerts(db, lon, date(2026, 11, 20)) == {"upcoming": [], "applied": [], "mismatches": []}
    elev.voksenelev = False
    elev.agreement_type = "EGU-elever"
    db.commit()
    assert _alerts(db, lon, date(2026, 11, 20))["mismatches"] == []
    rows = overview(current_user=lon, db=db, today=date(2026, 11, 20))["rows"]
    assert rows[0]["status"] == "ingen_trin"


def test_overview_marks_mismatch(db, elev, lon):
    from routers.elev_router import overview
    res = overview(current_user=lon, db=db, today=date(2026, 11, 20))
    assert res["rows"][0]["status"] == "afviger"
    assert res["missing_step_types"] == []
    res = overview(current_user=lon, db=db, today=date(2026, 11, 1))
    assert res["rows"][0]["status"] == "ok"
    assert res["rows"][0]["next_change"]["effective_from"] == EFFECTIVE


def test_settings_validation(db, elev, lon):
    from routers.elev_router import SettingsBody, put_settings
    with pytest.raises(HTTPException):
        put_settings(SettingsBody(notice_days=7, remind_days=7), current_user=lon, db=db)
    out = put_settings(SettingsBody(notice_days=21, remind_days=None), current_user=lon, db=db)
    assert out["notice_days"] == 21 and out["remind_days"] is None


def test_payroll_uses_type_for_the_period(db, elev, lon):
    from routers.elev_router import DecisionBody, create_decision
    from routers.payroll_router import _calculate_employee
    create_decision(DecisionBody(employee_id=elev.id, event_date=EVENT, decision="approve", to_type=LAST),
                    current_user=lon, db=db, today=date(2026, 11, 1))
    before = _calculate_employee(elev, date(2026, 11, 2), date(2026, 11, 15), db)
    after = _calculate_employee(elev, EFFECTIVE, date(2026, 11, 29), db)
    assert (before["agreement_type"], before["base_hourly_rate"]) == (SECOND, 105.75)
    assert (after["agreement_type"], after["base_hourly_rate"]) == (LAST, 119.17)
