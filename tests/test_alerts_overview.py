"""Advarsler-oversigten (2026-10-06): ét kald med alle advarsler brugeren har rettighed til,
'Øvrige' med påmindelser 30/7/0 dage, personlige indstillinger, og vinduet åbner kun ved NYE advarsler."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from datetime import date
from decimal import Decimal

import pytest
from fastapi import HTTPException

from database.models import AppUser, MasterAgreementType, Role, SystemSettings


def _user(db, name, perms, system=False):
    db.add(Role(name=name, display_name=name, is_system=system, permissions=perms))
    u = AppUser(name=name, initials=name[:3].upper(), role=name, password_hash="x", active=True)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture
def data(db, employee):
    for name, rate in (("Chauffør", 174.15), ("Chauffør. 9 mdr anciennitet", 182.30)):
        db.add(MasterAgreementType(name=name, hourly_rate=Decimal(str(rate))))
    db.add(SystemSettings(id=1, auto_approval_enabled=True))
    employee.agreement_type = "Chauffør"
    employee.hire_date = date(2026, 2, 20)                 # 9 måneder den 20/11-2026
    employee.cpr_number = "151186-1234"                    # fylder 40 den 15/11-2026
    db.commit()
    return employee


def _get(db, user, today):
    from routers.alerts_router import get_alerts
    return get_alerts(current_user=user, db=db, today=today)


def test_only_groups_the_user_has_permission_for(db, data):
    res = _get(db, _user(db, "anc", ["anciennitet_alert"]), date(2026, 11, 1))
    assert [r["kind"] for r in res["groups"]["raises"]] == ["anciennitet"]
    assert res["groups"]["other"] == []
    res = _get(db, _user(db, "bday", ["birthday_alert"]), date(2026, 11, 1))
    assert [o["type"] for o in res["groups"]["other"]] == ["milestone"] and res["groups"]["raises"] == []


def test_new_until_seen_then_only_in_the_bell(db, data):
    from routers.alerts_router import KeysBody, mark_seen
    user = _user(db, "all", ["anciennitet_alert", "birthday_alert"])
    res = _get(db, user, date(2026, 11, 1))
    assert res["total"] == 2 and len(res["new_keys"]) == 2          # vinduet åbner af sig selv
    mark_seen(KeysBody(keys=res["new_keys"]), current_user=user, db=db)
    res = _get(db, user, date(2026, 11, 1))
    assert res["total"] == 2 and res["new_keys"] == []              # stadig i klokken, men åbner ikke


def test_other_reminders_month_week_and_day(db, data):
    from routers.alerts_router import KeysBody, mark_ok
    user = _user(db, "bday", ["birthday_alert"])
    first = _get(db, user, date(2026, 10, 20))["groups"]["other"]   # 26 dage før
    assert [o["stage"] for o in first] == ["30"]
    mark_ok(KeysBody(keys=[first[0]["key"]]), current_user=user, db=db)
    assert _get(db, user, date(2026, 11, 1))["groups"]["other"] == []           # OK til næste påmindelse
    week = _get(db, user, date(2026, 11, 8))                                    # 7 dage før
    assert [o["stage"] for o in week["groups"]["other"]] == ["7"] and len(week["new_keys"]) == 1
    mark_ok(KeysBody(keys=[week["groups"]["other"][0]["key"]]), current_user=user, db=db)
    assert _get(db, user, date(2026, 11, 14))["groups"]["other"] == []
    assert [o["stage"] for o in _get(db, user, date(2026, 11, 15))["groups"]["other"]] == ["0"]   # på dagen


def test_personal_settings(db, data):
    from routers.alerts_router import SettingsBody, get_settings, put_settings
    user = _user(db, "lon", ["birthday_alert", "anciennitet_alert"])
    s = get_settings(current_user=user, db=db)
    assert (s["other_first_days"], s["other_second_days"], s["sections"]) == (30, 7, {"raises": True, "other": True})
    put_settings(SettingsBody(raise_notice_days=7, raise_remind_days=None, other_first_days=7,
                              other_second_days=None, other_on_day=True), current_user=user, db=db)
    assert _get(db, user, date(2026, 11, 1))["groups"]["other"] == []          # 14 dage før: nu for tidligt
    assert [o["stage"] for o in _get(db, user, date(2026, 11, 8))["groups"]["other"]] == ["7"]
    with pytest.raises(HTTPException):
        put_settings(SettingsBody(raise_notice_days=7, raise_remind_days=7, other_first_days=7,
                                  other_second_days=None), current_user=user, db=db)
    other = _user(db, "per", ["birthday_alert"])
    assert get_settings(current_user=other, db=db)["other_first_days"] == 30   # kun for den bruger


def test_seen_keys_fit_the_column():
    from routers.alerts_router import _short, SEEN
    assert len(_short(SEEN, "x" * 80)) == 50
