"""Fejl i produktion 2026-10-07: gamle lønperioder der aldrig er låst (fx 2.–15. juni 2025) gav falske
'Mulig fejl i løn', fordi systemet kun kender medarbejderens type i dag. Kun den aktuelle periode og
perioden der lige er slut må tjekkes."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from datetime import date
from decimal import Decimal

from database.models import AppUser, MasterAgreementType, PayPeriod, PayPeriodStatus, Role, SystemSettings

THIRD, SECOND = "Lærling (EUD) Tredjesidste år af lærerkontrakt", "Lærling (EUD) Næstsidsteår af lærerkontrakt"
LAST = "Lærling (EUD) Sidste år af lærerkontrakt"
TODAY = date(2026, 10, 7)


def _setup(db, employee, perms):
    for n, r in ((THIRD, 93.71), (SECOND, 105.75), (LAST, 119.17), ("Chauffør", 174.15),
                 ("Chauffør. 9 mdr anciennitet", 182.30)):
        db.add(MasterAgreementType(name=n, hourly_rate=Decimal(str(r))))
    db.add(SystemSettings(id=1, auto_approval_enabled=True))
    db.add(PayPeriod(start_date=date(2025, 6, 2), end_date=date(2025, 6, 15), status=PayPeriodStatus.open))
    db.add(Role(name="lon", display_name="lon", is_system=False, permissions=perms))
    user = AppUser(name="lon", initials="LON", role="lon", password_hash="x", active=True)
    db.add(user)
    db.commit()
    return user


def test_apprentice_in_correct_step_today_gives_no_warning_from_old_open_period(db, employee):
    from routers.elev_router import alerts
    user = _setup(db, employee, ["elev_wage_approve"])
    # Startede 11/6-2025, slutter 10/6-2028 → næstsidste år fra 11/6-2026 (rigtig type i dag)
    employee.elev, employee.elev_start_date, employee.elev_end_date = True, date(2025, 6, 11), date(2028, 6, 10)
    employee.agreement_type = SECOND
    db.commit()
    assert alerts(current_user=user, db=db, today=TODAY)["mismatches"] == []


def test_anciennitet_not_flagged_for_old_open_period(db, employee):
    from routers.elev_router import alerts
    user = _setup(db, employee, ["anciennitet_alert"])
    employee.agreement_type, employee.hire_date = "Chauffør. 9 mdr anciennitet", date(2024, 1, 1)
    db.commit()
    assert alerts(current_user=user, db=db, today=TODAY)["mismatches"] == []


def test_wrong_type_today_is_still_flagged(db, employee):
    from routers.elev_router import alerts
    user = _setup(db, employee, ["elev_wage_approve"])
    employee.elev, employee.elev_start_date, employee.elev_end_date = True, date(2025, 6, 11), date(2028, 6, 10)
    employee.agreement_type = THIRD                      # skulle være næstsidste siden 11/6-2026
    db.commit()
    [m] = alerts(current_user=user, db=db, today=TODAY)["mismatches"]
    assert m["expected_type"] == SECOND and m["period_start"] >= date(2026, 9, 21)
