"""'Vis tidligere' i Advarsler-oversigten (2026-10-06): behandlede lønstigninger (fælles) og egne
'OK' på øvrige advarsler, sidste 90 dage, kun læsning."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from datetime import date, datetime, timedelta

import pytest

from database.models import AppUser, AuditLog, Role, UserAlertDismissal


def _user(db, name, perms):
    db.add(Role(name=name, display_name=name, is_system=False, permissions=perms))
    u = AppUser(name=name, initials=name[:3].upper(), role=name, password_hash="x", active=True)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


NOW = datetime(2026, 10, 6, 12, 0)


def _hist(db, user):
    from routers.alerts_router import history
    return history(current_user=user, db=db, now=NOW)


def _log(db, action, details, when, initials="LON"):
    db.add(AuditLog(user_initials=initials, action=action, entity_type="employee", entity_id=1,
                    details=details, timestamp=when))
    db.commit()


def test_raise_decisions_shared_for_users_with_permission(db, employee):
    lon = _user(db, "lon", ["elev_wage_approve"])
    other = _user(db, "per", ["anciennitet_alert"])
    nobody = _user(db, "bob", ["view_calendar"])
    _log(db, "elev_step_approve", "Test Chauffør: 'A' → 'B' fra lønperioden …", NOW - timedelta(days=1))
    _log(db, "elev_step_cancel", "Test Chauffør: … annulleret automatisk, fordi elev_end_date er ændret",
         NOW - timedelta(days=2))
    _log(db, "elev_step_applied", "Elevløn-trin trådt i kraft …", NOW - timedelta(days=3))
    labels = [(e["label"], e["who"]) for e in _hist(db, lon)]
    assert labels == [("Godkendt", "LON"), ("Annulleret automatisk", "LON"), ("Trådt i kraft", "")]
    assert len(_hist(db, other)) == 3                      # også anciennitets-rettigheden
    assert _hist(db, nobody) == []


def test_only_last_90_days(db, employee):
    lon = _user(db, "lon", ["elev_wage_approve"])
    _log(db, "elev_step_keep", "gammel", NOW - timedelta(days=91))
    _log(db, "elev_step_keep", "ny", NOW - timedelta(days=89))
    assert [e["text"] for e in _hist(db, lon)] == ["ny"]


def test_own_ok_on_other_warnings_only(db, employee):
    lon = _user(db, "lon", ["birthday_alert"])
    per = _user(db, "per", ["birthday_alert"])
    db.add(UserAlertDismissal(user_id=lon.id, key=f"ok:ms:{employee.id}:birthday_40@7", dismissed_at=NOW))
    db.add(UserAlertDismissal(user_id=per.id, key=f"ok:ms:{employee.id}:birthday_40@30", dismissed_at=NOW))
    db.add(UserAlertDismissal(user_id=lon.id, key="seen:up:elev:1:2026-11-21", dismissed_at=NOW))   # ikke historik
    [e] = _hist(db, lon)
    assert (e["label"], e["who"], e["employee_name"], e["text"]) == \
        ("OK", "dig", "Test Chauffør", "fylder 40 år (anden besked)")


def test_times_are_marked_utc(db, employee):
    lon = _user(db, "lon", ["elev_wage_approve"])
    _log(db, "elev_step_approve", "x", datetime(2026, 10, 6, 8, 42))
    assert _hist(db, lon)[0]["at"] == "2026-10-06T08:42:00Z"   # browseren viser 10.42 dansk sommertid
