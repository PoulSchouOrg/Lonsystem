"""Dagsplan-ændringer 2026-10-08: autoudfyld følger Dagsplanens regel, overnatning
er ikke fravær, ⚠️ ved flere biler, chaufførlister (funktionær/"Medtag i Dagsplan"),
inaktive Fast bil-chauffører, og blød sletning af vogne."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from datetime import date, datetime, timedelta

import pytest
from fastapi import HTTPException

from conftest import make_activity
from calculators.dagsplan_helpers import effective_vehicle_for_employee
from calculators.pay_period import get_or_create_period_for_date
from database.models import (
    ActivityStatus, AgreementKind, AppUser, DailyPlanAssignment, DispatcherGroup, Employee,
    PayPeriodStatus, Vehicle, VehicleAbsence,
)
from database.schemas import DailyPlanAssignmentUpsert, VehicleCreate

D = date(2026, 9, 9)


def _user():
    return AppUser(id=1, name="Test", initials="TST", role="admin", password_hash="x")


def _vehicle(db, number="52", reg="BN47449", vognpark=True):
    v = Vehicle(registration_number=reg, vehicle_number=number, vognpark=vognpark)
    db.add(v)
    db.commit()
    db.refresh(v)
    return v


def _group(db, name="Gruppe", dagsplan=True):
    g = DispatcherGroup(name=name, visible_in_dagsplan=dagsplan)
    db.add(g)
    db.commit()
    return g


def _employee(db, number, first="Anden", kind=AgreementKind.hourly_fixed, group=None):
    e = Employee(
        employee_number=number, first_name=first, last_name="Chauffør",
        agreement_kind=kind, agreement_type="Standardoverenskomst", hire_date=date(2020, 1, 1),
        work_schedule={"even": [8, 8, 8, 8, 8, 0, 0], "odd": [8, 8, 8, 8, 8, 0, 0]},
        dispatcher_group=group,
    )
    db.add(e)
    db.commit()
    db.refresh(e)
    return e


def _dagsplan(db, d=D):
    from routers.dagsplan_router import get_dagsplan
    return get_dagsplan(date=d, dispatcher_group_id=None, employee_id=None, current_user=_user(), db=db)


# ── 1 + 5: autoudfyld følger Dagsplanens regel ────────────────────────────────

def test_autofill_ignores_fast_bil_on_non_vognpark_vehicle(db, employee):
    v = _vehicle(db, vognpark=False)
    employee.fast_bil, employee.fast_bil_vehicle_id = True, v.id
    db.commit()
    assert effective_vehicle_for_employee(db, employee.id, D) is None


def test_autofill_ignores_saved_assignment_on_non_vognpark_vehicle(db, employee):
    v = _vehicle(db, vognpark=False)
    db.add(DailyPlanAssignment(date=D, vehicle_id=v.id, employee_id=employee.id))
    db.commit()
    assert effective_vehicle_for_employee(db, employee.id, D) is None


def test_autofill_ignores_fast_bil_given_to_another_that_day(db, employee):
    v = _vehicle(db)
    other = _employee(db, "2002")
    employee.fast_bil, employee.fast_bil_vehicle_id = True, v.id
    db.add(DailyPlanAssignment(date=D, vehicle_id=v.id, employee_id=other.id))
    db.commit()
    assert effective_vehicle_for_employee(db, employee.id, D) is None
    assert effective_vehicle_for_employee(db, other.id, D).id == v.id


def test_autofill_ignores_fast_bil_cleared_that_day(db, employee):
    v = _vehicle(db)
    employee.fast_bil, employee.fast_bil_vehicle_id = True, v.id
    db.add(DailyPlanAssignment(date=D, vehicle_id=v.id, employee_id=None))
    db.commit()
    assert effective_vehicle_for_employee(db, employee.id, D) is None
    assert effective_vehicle_for_employee(db, employee.id, D + timedelta(days=1)).id == v.id


def test_inactive_fast_bil_employee_neither_shown_nor_autofilled(db, employee):
    v = _vehicle(db)
    employee.fast_bil, employee.fast_bil_vehicle_id, employee.active = True, v.id, False
    db.commit()
    assert _dagsplan(db).vehicles[0].employee_id is None
    assert effective_vehicle_for_employee(db, employee.id, D) is None


def test_autofill_matches_dagsplan_row_for_fast_bil(db, employee):
    v = _vehicle(db)
    employee.fast_bil, employee.fast_bil_vehicle_id = True, v.id
    db.commit()
    assert _dagsplan(db).vehicles[0].employee_id == employee.id
    assert effective_vehicle_for_employee(db, employee.id, D).id == v.id


# ── 2: overnatning er ikke fravær ──────────────────────────────────────────────

@pytest.mark.parametrize("kind", ["overnatning", "dob_overnatning"])
def test_overnatning_is_not_absence_in_dagsplan(db, employee, kind):
    from routers.dagsplan_router import upsert_assignment
    employee.dispatcher_group = _group(db)
    db.commit()
    v = _vehicle(db)
    make_activity(db, employee, datetime(2026, 9, 9, 20, 0), datetime(2026, 9, 9, 20, 1), activity_type=kind)

    emp_row = next(e for e in _dagsplan(db).employees if e.employee_id == employee.id)
    assert emp_row.status == "none"
    row = upsert_assignment(DailyPlanAssignmentUpsert(date=D, vehicle_id=v.id, employee_id=employee.id),
                            current_user=_user(), db=db)  # ingen 409
    assert row.employee_id == employee.id


# ── 3: ⚠️ ved flere biler / deaktiverede ──────────────────────────────────────

def _multi_vehicle_act(db, employee, regs):
    act = make_activity(db, employee, datetime(2026, 9, 9, 6, 0), datetime(2026, 9, 9, 14, 0))
    act.vehicle_number = "52"
    act.vehicle_uses = [
        ["2026-09-09T06:00:00", "2026-09-09T10:00:00", regs[0]],
        ["2026-09-09T10:00:00", "2026-09-09T14:00:00", regs[1]],
    ]
    db.commit()
    return act


def test_mismatch_when_another_vehicle_driven_even_if_assigned_is_main(db, employee):
    v = _vehicle(db, "52", "BN47449")
    _vehicle(db, "60", "AB12345", vognpark=False)
    db.add(DailyPlanAssignment(date=D, vehicle_id=v.id, employee_id=employee.id))
    db.commit()
    _multi_vehicle_act(db, employee, ["BN47449", "AB12345"])
    assert _dagsplan(db).vehicles[0].mismatch_vehicle_number == "60"


def test_mismatch_unknown_registration_shown_as_registration(db, employee):
    v = _vehicle(db, "52", "BN47449")
    db.add(DailyPlanAssignment(date=D, vehicle_id=v.id, employee_id=employee.id))
    db.commit()
    _multi_vehicle_act(db, employee, ["BN47449", "XY99999"])
    assert _dagsplan(db).vehicles[0].mismatch_vehicle_number == "XY99999"


def test_no_mismatch_from_deactivated_activity(db, employee):
    v = _vehicle(db, "52")
    db.add(DailyPlanAssignment(date=D, vehicle_id=v.id, employee_id=employee.id))
    db.commit()
    act = make_activity(db, employee, datetime(2026, 9, 9, 6, 0), datetime(2026, 9, 9, 14, 0),
                        status=ActivityStatus.deactivated)
    act.vehicle_number = "99"
    db.commit()
    assert _dagsplan(db).vehicles[0].mismatch_vehicle_number is None


# ── 6: chaufførlister ──────────────────────────────────────────────────────────

def test_employee_list_excludes_funktionaer_and_groups_without_dagsplan_flag(db, employee):
    employee.dispatcher_group = _group(db, "Med")
    db.commit()
    funk = _employee(db, "3001", "Funk", kind="funktionaer", group=employee.dispatcher_group)
    outside = _employee(db, "3002", "Ude", group=_group(db, "Uden", dagsplan=False))
    names = [e.employee_name for e in _dagsplan(db).employees]
    assert employee.name in names
    assert funk.name not in names
    assert outside.name not in names


def test_dispatcher_group_dagsplan_flag_via_stamdata(db):
    from routers.stamdata import DispatcherGroupBody, create_dispatcher_group, update_dispatcher_group
    created = create_dispatcher_group(DispatcherGroupBody(name="Ny"), current_user=_user(), db=db)
    assert created["visible_in_dagsplan"] is False
    updated = update_dispatcher_group(created["id"], DispatcherGroupBody(visible_in_dagsplan=True),
                                      current_user=_user(), db=db)
    assert updated["visible_in_dagsplan"] is True


# ── 4: blød sletning af vogne ──────────────────────────────────────────────────

def _delete(db, vehicle_id, force=False):
    from routers.vehicles import delete_vehicle
    delete_vehicle(vehicle_id, force=force, current_user=_user(), db=db)


def test_delete_unused_vehicle_is_soft_and_hidden_from_list(db):
    from routers.vehicles import list_vehicles
    v = _vehicle(db)
    _delete(db, v.id)
    db.refresh(v)
    assert v.deleted_at is not None
    assert list_vehicles(current_user=_user(), db=db) == []


def test_delete_vehicle_used_in_open_period_warns_then_force(db, employee):
    v = _vehicle(db)
    act = make_activity(db, employee, datetime(2026, 9, 9, 6, 0), datetime(2026, 9, 9, 14, 0))
    act.vehicle_registration, act.vehicle_number = v.registration_number, v.vehicle_number
    db.commit()
    with pytest.raises(HTTPException) as exc:
        _delete(db, v.id)
    assert exc.value.status_code == 409
    assert "ikke er låst" in exc.value.detail

    _delete(db, v.id, force=True)
    db.refresh(act)
    assert act.vehicle_number == "52"  # død tekst på vagten
    db.refresh(v)
    assert v.deleted_at is not None


def test_delete_vehicle_used_only_in_closed_period_no_warning(db, employee):
    v = _vehicle(db)
    act = make_activity(db, employee, datetime(2026, 9, 9, 6, 0), datetime(2026, 9, 9, 14, 0))
    act.vehicle_registration, act.vehicle_number = v.registration_number, v.vehicle_number
    act.pay_period.status = PayPeriodStatus.closed
    db.commit()
    _delete(db, v.id)  # ingen 409
    db.refresh(act)
    assert act.vehicle_number == "52"


def test_delete_vehicle_used_as_second_vehicle_in_open_period_warns(db, employee):
    v = _vehicle(db, "60", "AB12345")
    _multi_vehicle_act(db, employee, ["BN47449", "AB12345"])
    with pytest.raises(HTTPException) as exc:
        _delete(db, v.id)
    assert exc.value.status_code == 409


def test_delete_vehicle_clears_links_and_keeps_history(db, employee):
    v = _vehicle(db)
    group = _group(db)
    group.vehicle_id = v.id
    employee.fast_bil, employee.fast_bil_vehicle_id, employee.absence_vehicle_id = True, v.id, v.id
    past, future = date.today() - timedelta(days=3), date.today() + timedelta(days=3)
    db.add_all([
        DailyPlanAssignment(date=past, vehicle_id=v.id, employee_id=employee.id, task="Grus"),
        DailyPlanAssignment(date=future, vehicle_id=v.id, employee_id=employee.id),
        VehicleAbsence(vehicle_id=v.id, date_from=past, comment="Syn"),
        VehicleAbsence(vehicle_id=v.id, date_from=future, comment="Senere"),
    ])
    db.commit()
    with pytest.raises(HTTPException) as exc:
        _delete(db, v.id)
    assert "Fast bil for" in exc.value.detail
    _delete(db, v.id, force=True)

    db.refresh(employee)
    db.refresh(group)
    assert employee.fast_bil is False and employee.fast_bil_vehicle_id is None
    assert employee.absence_vehicle_id is None
    assert group.vehicle_id is None
    assert [a.date for a in db.query(DailyPlanAssignment).all()] == [past]
    assert [a.comment for a in db.query(VehicleAbsence).all()] == ["Syn"]

    rows = _dagsplan(db, past).vehicles
    assert len(rows) == 1 and rows[0].deleted and rows[0].task == "Grus"
    assert _dagsplan(db, date.today()).vehicles == []


def test_deleted_vehicle_cannot_be_assigned(db, employee):
    from routers.dagsplan_router import upsert_assignment
    v = _vehicle(db)
    _delete(db, v.id)
    with pytest.raises(HTTPException) as exc:
        upsert_assignment(DailyPlanAssignmentUpsert(date=D, vehicle_id=v.id, employee_id=employee.id),
                          current_user=_user(), db=db)
    assert exc.value.status_code == 400


def test_recreating_plate_of_deleted_vehicle_renames_the_deleted_one(db):
    from routers.vehicles import create_vehicle
    old = _vehicle(db, "52", "BN47449")
    _delete(db, old.id)
    new = create_vehicle(VehicleCreate(registration_number="BN47449", vehicle_number="70"),
                         current_user=_user(), db=db)
    db.refresh(old)
    assert new.registration_number == "BN47449"
    assert old.registration_number == f"BN47449 (slettet {old.id})"
    assert old.vehicle_number == "52"


# ── EKSTRA-linjer med vognnummer ───────────────────────────────────────────────

def _extra(db, slot=1, **kw):
    from routers.dagsplan_router import upsert_extra_assignment
    from database.schemas import DailyPlanExtraAssignmentUpsert
    return upsert_extra_assignment(DailyPlanExtraAssignmentUpsert(date=D, slot=slot, **kw),
                                   current_user=_user(), db=db)


def test_extra_row_vehicle_shows_description_and_fast_chauffeur(db, employee):
    v = _vehicle(db, "77", "KR11111", vognpark=False)
    v.description = "Kranbil"
    employee.fast_bil, employee.fast_bil_vehicle_id = True, v.id
    db.commit()
    row = _extra(db, vehicle_id=v.id)
    assert (row.vehicle_number, row.description, row.employee_id) == ("77", "Kranbil", employee.id)
    # Kun den valgte dag
    assert next(r for r in _dagsplan(db, D + timedelta(days=1)).extra_rows if r.slot == 1).vehicle_id is None


def test_extra_row_without_fast_chauffeur_keeps_chosen_employee(db, employee):
    v = _vehicle(db, "77", "KR11111", vognpark=False)
    row = _extra(db, vehicle_id=v.id, employee_id=employee.id)
    assert row.employee_id == employee.id


def test_extra_row_rejects_vognpark_and_deleted_vehicles(db):
    in_fleet = _vehicle(db, "52", "BN47449", vognpark=True)
    with pytest.raises(HTTPException) as exc:
        _extra(db, vehicle_id=in_fleet.id)
    assert exc.value.status_code == 400
    gone = _vehicle(db, "77", "KR11111", vognpark=False)
    _delete(db, gone.id)
    with pytest.raises(HTTPException) as exc:
        _extra(db, vehicle_id=gone.id)
    assert exc.value.status_code == 400


def test_extra_row_task_save_without_vehicle_field_keeps_vehicle(db):
    v = _vehicle(db, "77", "KR11111", vognpark=False)
    _extra(db, vehicle_id=v.id)
    row = _extra(db, task="Grus")
    assert row.vehicle_id == v.id and row.task == "Grus"
    row = _extra(db, vehicle_id=None, task="Grus")
    assert row.vehicle_id is None


def test_removing_vehicle_from_extra_row_also_removes_chauffeur(db, employee):
    employee.dispatcher_group = _group(db)
    db.commit()
    v = _vehicle(db, "77", "KR11111", vognpark=False)
    _extra(db, vehicle_id=v.id, employee_id=employee.id)
    row = _extra(db, vehicle_id=None, employee_id=employee.id)  # frontend sender nuværende chauffør med
    assert row.vehicle_id is None and row.employee_id is None
    emp_row = next(e for e in _dagsplan(db).employees if e.employee_id == employee.id)
    assert emp_row.status == "none"  # grå igen


def test_extra_row_without_vehicle_can_still_have_chauffeur(db, employee):
    row = _extra(db, employee_id=employee.id)
    assert row.vehicle_id is None and row.employee_id == employee.id


def test_extra_row_same_vehicle_on_two_slots_warns(db):
    v = _vehicle(db, "77", "KR11111", vognpark=False)
    _extra(db, slot=1, vehicle_id=v.id)
    with pytest.raises(HTTPException) as exc:
        _extra(db, slot=2, vehicle_id=v.id)
    assert exc.value.status_code == 409 and "EKSTRA-plads 1" in exc.value.detail
    assert _extra(db, slot=2, vehicle_id=v.id, force=True).vehicle_id == v.id


def test_extra_row_mismatch_warning(db, employee):
    v = _vehicle(db, "77", "KR11111", vognpark=False)
    _extra(db, vehicle_id=v.id, employee_id=employee.id)
    act = make_activity(db, employee, datetime(2026, 9, 9, 6, 0), datetime(2026, 9, 9, 14, 0))
    act.vehicle_number = "99"
    db.commit()
    assert _dagsplan(db).extra_rows[0].mismatch_vehicle_number == "99"


def test_extra_row_vehicle_not_used_for_autofill(db, employee):
    v = _vehicle(db, "77", "KR11111", vognpark=False)
    _extra(db, vehicle_id=v.id, employee_id=employee.id)
    assert effective_vehicle_for_employee(db, employee.id, D) is None


def test_plate_of_active_vehicle_still_rejected(db):
    from routers.vehicles import create_vehicle
    _vehicle(db, "52", "BN47449")
    with pytest.raises(HTTPException) as exc:
        create_vehicle(VehicleCreate(registration_number="BN47449", vehicle_number="70"),
                       current_user=_user(), db=db)
    assert exc.value.status_code == 400
