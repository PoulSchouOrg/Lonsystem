import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from datetime import date, datetime

import pytest
from fastapi import HTTPException

from conftest import make_activity
from database.models import (
    AgreementKind, AppUser, DailyPlanAssignment, DailyPlanExtraAssignment,
    DispatcherGroup, Employee, MasterAbsenceType, Vehicle, VehicleAbsence,
)
from database.schemas import DailyPlanAssignmentUpsert, DailyPlanExtraAssignmentUpsert, VehicleAbsenceCreate


def _user():
    return AppUser(name="Test", initials="TST", role="lonbogholder", password_hash="x")


def _vehicle(db, number="52", reg="BN47449", vognpark=True):
    v = Vehicle(registration_number=reg, vehicle_number=number, vognpark=vognpark)
    db.add(v)
    db.commit()
    db.refresh(v)
    return v


def _visible_group(db, name="Testgruppe", visible=True):
    """En disponentgruppe med "Medtag i Dagsplan" (som default) - medarbejdere
    skal have en af disse for at optræde i Dagsplanens chaufførlister (2026-10-08)."""
    g = DispatcherGroup(name=name, visible_in_dagsplan=visible)
    db.add(g)
    db.commit()
    db.refresh(g)
    return g


# NOTE: these tests call the route functions directly (matching this repo's
# existing convention, e.g. tests/test_activity_auto_approve_on_create.py) so
# they exercise only the endpoints' own logic - permission enforcement of
# dagsplan_view/dagsplan_edit is tested over HTTP in
# tests/test_dagsplan_permission_enforcement.py.


def test_get_dagsplan_lists_vehicles_and_employees(db, employee):
    from routers.dagsplan_router import get_dagsplan
    employee.dispatcher_group = _visible_group(db)
    db.commit()
    v = _vehicle(db)
    resp = get_dagsplan(date=date(2026, 9, 9), dispatcher_group_id=None, employee_id=None,
                        current_user=_user(), db=db)
    assert len(resp.vehicles) == 1
    assert resp.vehicles[0].vehicle_number == "52"
    assert resp.vehicles[0].employee_id is None
    names = [e.employee_name for e in resp.employees]
    assert employee.name in names


def test_employee_list_excludes_employees_without_visible_dispatcher_group(db, employee):
    """Kun medarbejdere i disponentgrupper med "Medtag i Dagsplan" må optræde
    i Dagsplanens chaufførlister; uden disponentgruppe udelades også."""
    from routers.dagsplan_router import get_dagsplan

    no_group = Employee(
        employee_number="9001", first_name="Uden", last_name="Gruppe",
        agreement_kind=AgreementKind.hourly_fixed, agreement_type="Standardoverenskomst",
        hire_date=date(2020, 1, 1),
        work_schedule={"even": [8, 8, 8, 8, 8, 0, 0], "odd": [8, 8, 8, 8, 8, 0, 0]},
    )
    hidden_group_emp = Employee(
        employee_number="9002", first_name="Skjult", last_name="Gruppe",
        agreement_kind=AgreementKind.hourly_fixed, agreement_type="Standardoverenskomst",
        hire_date=date(2020, 1, 1),
        work_schedule={"even": [8, 8, 8, 8, 8, 0, 0], "odd": [8, 8, 8, 8, 8, 0, 0]},
    )
    db.add_all([no_group, hidden_group_emp])
    db.commit()
    hidden_group_emp.dispatcher_group = _visible_group(db, "Skjult", visible=False)
    employee.dispatcher_group = _visible_group(db, "Synlig")
    db.commit()

    resp = get_dagsplan(date=date(2026, 9, 9), dispatcher_group_id=None, employee_id=None,
                        current_user=_user(), db=db)
    names = [e.employee_name for e in resp.employees]
    assert employee.name in names
    assert no_group.name not in names
    assert hidden_group_emp.name not in names


def test_upsert_assignment_creates_and_updates(db, employee):
    from routers.dagsplan_router import get_dagsplan, upsert_assignment
    employee.dispatcher_group = _visible_group(db)
    db.commit()
    v = _vehicle(db)
    upsert_assignment(DailyPlanAssignmentUpsert(date=date(2026, 9, 9), vehicle_id=v.id,
                                                employee_id=employee.id, task="Asfalt", informed=True),
                      current_user=_user(), db=db)
    row = upsert_assignment(DailyPlanAssignmentUpsert(date=date(2026, 9, 9), vehicle_id=v.id,
                                                       employee_id=employee.id, task="Grus", informed=False),
                            current_user=_user(), db=db)
    assert row.task == "Grus"
    assert row.informed is False
    assert db.query(DailyPlanAssignment).count() == 1  # upsert, ikke ny række

    resp = get_dagsplan(date=date(2026, 9, 9), dispatcher_group_id=None, employee_id=None,
                        current_user=_user(), db=db)
    emp_row = next(e for e in resp.employees if e.employee_id == employee.id)
    assert emp_row.status == "assigned"


def test_upsert_assignment_conflict_when_employee_already_assigned_elsewhere(db, employee):
    from routers.dagsplan_router import upsert_assignment
    v1 = _vehicle(db, "52", "BN47449")
    v2 = _vehicle(db, "60", "AB12345")
    upsert_assignment(DailyPlanAssignmentUpsert(date=date(2026, 9, 9), vehicle_id=v1.id,
                                                employee_id=employee.id),
                      current_user=_user(), db=db)

    with pytest.raises(HTTPException) as exc:
        upsert_assignment(DailyPlanAssignmentUpsert(date=date(2026, 9, 9), vehicle_id=v2.id,
                                                     employee_id=employee.id),
                          current_user=_user(), db=db)
    assert exc.value.status_code == 409
    assert "52" in exc.value.detail

    # force=True omgår advarslen og gennemfører alligevel (tilladt dobbelt-tildeling)
    row = upsert_assignment(DailyPlanAssignmentUpsert(date=date(2026, 9, 9), vehicle_id=v2.id,
                                                       employee_id=employee.id, force=True),
                            current_user=_user(), db=db)
    assert row.employee_id == employee.id


def test_upsert_assignment_conflict_with_fast_bil_default(db, employee):
    """Konflikt skal også opdages mod en 'Fast bil'-standard, ikke kun gemte tildelinger."""
    from routers.dagsplan_router import upsert_assignment
    v1 = _vehicle(db, "52", "BN47449")
    v2 = _vehicle(db, "60", "AB12345")
    employee.fast_bil = True
    employee.fast_bil_vehicle_id = v1.id
    db.commit()

    with pytest.raises(HTTPException) as exc:
        upsert_assignment(DailyPlanAssignmentUpsert(date=date(2026, 9, 9), vehicle_id=v2.id,
                                                     employee_id=employee.id),
                          current_user=_user(), db=db)
    assert exc.value.status_code == 409
    assert "52" in exc.value.detail


def test_upsert_assignment_no_conflict_when_reassigning_same_vehicle(db, employee):
    """At gemme samme vogn igen (uændret eller opdateret opgave) er ikke en konflikt."""
    from routers.dagsplan_router import upsert_assignment
    v = _vehicle(db)
    upsert_assignment(DailyPlanAssignmentUpsert(date=date(2026, 9, 9), vehicle_id=v.id,
                                                employee_id=employee.id),
                      current_user=_user(), db=db)
    row = upsert_assignment(DailyPlanAssignmentUpsert(date=date(2026, 9, 9), vehicle_id=v.id,
                                                       employee_id=employee.id, task="Grus"),
                            current_user=_user(), db=db)
    assert row.task == "Grus"


def test_upsert_assignment_conflict_when_employee_is_absent(db, employee):
    from routers.dagsplan_router import upsert_assignment
    from database.models import MasterAbsenceType
    v = _vehicle(db)
    db.add(MasterAbsenceType(label="Ferie", normalized_key="ferie"))
    db.commit()
    make_activity(db, employee, datetime(2026, 9, 9, 6, 0), datetime(2026, 9, 9, 14, 0), activity_type="ferie")

    with pytest.raises(HTTPException) as exc:
        upsert_assignment(DailyPlanAssignmentUpsert(date=date(2026, 9, 9), vehicle_id=v.id,
                                                     employee_id=employee.id),
                          current_user=_user(), db=db)
    assert exc.value.status_code == 409
    assert employee.name in exc.value.detail
    assert "Ferie" in exc.value.detail

    # force=True omgår advarslen og gennemfører alligevel
    row = upsert_assignment(DailyPlanAssignmentUpsert(date=date(2026, 9, 9), vehicle_id=v.id,
                                                       employee_id=employee.id, force=True),
                            current_user=_user(), db=db)
    assert row.employee_id == employee.id


def test_upsert_assignment_absence_conflict_falls_back_to_raw_key_without_master_absence_type(db, employee):
    """Findes fraværstypen ikke i Stamdata (fx en fjernet/ældre type), bruges den rå nøgle som label."""
    from routers.dagsplan_router import upsert_assignment
    v = _vehicle(db)
    make_activity(db, employee, datetime(2026, 9, 9, 6, 0), datetime(2026, 9, 9, 14, 0), activity_type="ukendt_type")

    with pytest.raises(HTTPException) as exc:
        upsert_assignment(DailyPlanAssignmentUpsert(date=date(2026, 9, 9), vehicle_id=v.id,
                                                     employee_id=employee.id),
                          current_user=_user(), db=db)
    assert exc.value.status_code == 409
    assert "ukendt_type" in exc.value.detail


def test_upsert_assignment_no_re_check_when_employee_unchanged(db, employee):
    """Redigering af Opgave/Informeret for en allerede tildelt (fraværende) medarbejder
    må ikke blive ved med at afbryde med advarslen - kun en FAKTISK chaufførskift skal tjekkes."""
    from routers.dagsplan_router import upsert_assignment
    from database.models import MasterAbsenceType
    v = _vehicle(db)
    db.add(MasterAbsenceType(label="Ferie", normalized_key="ferie"))
    db.commit()
    make_activity(db, employee, datetime(2026, 9, 9, 6, 0), datetime(2026, 9, 9, 14, 0), activity_type="ferie")

    upsert_assignment(DailyPlanAssignmentUpsert(date=date(2026, 9, 9), vehicle_id=v.id,
                                                employee_id=employee.id, force=True),
                      current_user=_user(), db=db)
    # Samme medarbejder, kun opgaveteksten ændres - skal IKKE fejle med 409
    row = upsert_assignment(DailyPlanAssignmentUpsert(date=date(2026, 9, 9), vehicle_id=v.id,
                                                       employee_id=employee.id, task="Grus"),
                            current_user=_user(), db=db)
    assert row.task == "Grus"


def test_employee_filter_only_affects_vehicles_list(db, employee):
    """Medarbejderlisten (kol. 6-7) må ALDRIG filtreres - kun hovedtabellen."""
    from routers.dagsplan_router import get_dagsplan, upsert_assignment
    group = _visible_group(db)
    employee.dispatcher_group = group
    other = Employee(
        employee_number="9999", first_name="Anden", last_name="Medarbejder",
        agreement_kind=AgreementKind.hourly_fixed, agreement_type="Standardoverenskomst",
        hire_date=date(2020, 1, 1),
        work_schedule={"even": [8, 8, 8, 8, 8, 0, 0], "odd": [8, 8, 8, 8, 8, 0, 0]},
        dispatcher_group=group,
    )
    db.add(other)
    db.commit()
    v1 = _vehicle(db, "52", "BN47449")
    _vehicle(db, "60", "AB12345")
    upsert_assignment(DailyPlanAssignmentUpsert(date=date(2026, 9, 9), vehicle_id=v1.id,
                                                employee_id=employee.id),
                      current_user=_user(), db=db)
    resp = get_dagsplan(date=date(2026, 9, 9), dispatcher_group_id=None, employee_id=employee.id,
                        current_user=_user(), db=db)
    assert len(resp.vehicles) == 1  # kun v1, som er tildelt den filtrerede medarbejder
    names = [e.employee_name for e in resp.employees]
    assert other.name in names  # den anden medarbejder er IKKE filtreret væk
    assert len(resp.employees) == 2


def test_fast_bil_default_shown_without_saved_assignment(db, employee):
    from routers.dagsplan_router import get_dagsplan
    employee.dispatcher_group = _visible_group(db)
    v = _vehicle(db)
    employee.fast_bil = True
    employee.fast_bil_vehicle_id = v.id
    db.commit()
    resp = get_dagsplan(date=date(2026, 9, 9), dispatcher_group_id=None, employee_id=None,
                        current_user=_user(), db=db)
    assert resp.vehicles[0].employee_id == employee.id
    emp_row = next(e for e in resp.employees if e.employee_id == employee.id)
    assert emp_row.status == "assigned"
    assert db.query(DailyPlanAssignment).count() == 0  # ikke persisteret


def test_mismatch_flagged_when_normal_activity_uses_different_vehicle(db, employee):
    from routers.dagsplan_router import get_dagsplan, upsert_assignment
    v = _vehicle(db, "52")
    upsert_assignment(DailyPlanAssignmentUpsert(date=date(2026, 9, 9), vehicle_id=v.id,
                                                employee_id=employee.id),
                      current_user=_user(), db=db)
    act = make_activity(db, employee, datetime(2026, 9, 9, 6, 0), datetime(2026, 9, 9, 14, 0))
    act.vehicle_number = "99"
    db.commit()

    resp = get_dagsplan(date=date(2026, 9, 9), dispatcher_group_id=None, employee_id=None,
                        current_user=_user(), db=db)
    assert resp.vehicles[0].mismatch_vehicle_number == "99"


def test_vehicle_absence_marks_vehicle_absent_and_crud(db):
    from routers.dagsplan_router import create_vehicle_absence, delete_vehicle_absence, get_dagsplan, list_vehicle_absences
    v = _vehicle(db)
    created = create_vehicle_absence(
        VehicleAbsenceCreate(vehicle_id=v.id, date_from=date(2026, 9, 9), comment="Til syn"),
        current_user=_user(), db=db,
    )
    assert created.vehicle_number == "52"

    resp = get_dagsplan(date=date(2026, 9, 9), dispatcher_group_id=None, employee_id=None,
                        current_user=_user(), db=db)
    assert resp.vehicles[0].absent is True

    listed = list_vehicle_absences(date=date(2026, 9, 9), current_user=_user(), db=db)
    assert len(listed) == 1

    delete_vehicle_absence(created.id, current_user=_user(), db=db)
    listed_after = list_vehicle_absences(date=date(2026, 9, 9), current_user=_user(), db=db)
    assert len(listed_after) == 0


def test_vehicle_absence_date_to_before_date_from_rejected(db):
    from routers.dagsplan_router import create_vehicle_absence
    v = _vehicle(db)
    with pytest.raises(HTTPException) as exc:
        create_vehicle_absence(
            VehicleAbsenceCreate(vehicle_id=v.id, date_from=date(2026, 9, 9),
                                 date_to=date(2026, 9, 8), comment="x"),
            current_user=_user(), db=db,
        )
    assert exc.value.status_code == 400


def test_get_dagsplan_always_returns_ten_extra_rows(db):
    from routers.dagsplan_router import get_dagsplan
    resp = get_dagsplan(date=date(2026, 9, 9), dispatcher_group_id=None, employee_id=None,
                        current_user=_user(), db=db)
    assert len(resp.extra_rows) == 10
    assert [r.slot for r in resp.extra_rows] == list(range(1, 11))
    assert all(r.employee_id is None for r in resp.extra_rows)


def test_upsert_extra_assignment_creates_and_updates(db, employee):
    from routers.dagsplan_router import get_dagsplan, upsert_extra_assignment
    employee.dispatcher_group = _visible_group(db)
    db.commit()

    row = upsert_extra_assignment(
        DailyPlanExtraAssignmentUpsert(date=date(2026, 9, 9), slot=3, employee_id=employee.id, task="Rydde op"),
        current_user=_user(), db=db,
    )
    assert row.slot == 3
    assert row.employee_name == employee.name
    assert row.task == "Rydde op"
    assert db.query(DailyPlanExtraAssignment).count() == 1

    updated = upsert_extra_assignment(
        DailyPlanExtraAssignmentUpsert(date=date(2026, 9, 9), slot=3, employee_id=employee.id, task="Andet"),
        current_user=_user(), db=db,
    )
    assert updated.task == "Andet"
    assert db.query(DailyPlanExtraAssignment).count() == 1  # upsert, ikke ny række

    resp = get_dagsplan(date=date(2026, 9, 9), dispatcher_group_id=None, employee_id=None,
                        current_user=_user(), db=db)
    slot3 = next(r for r in resp.extra_rows if r.slot == 3)
    assert slot3.employee_id == employee.id
    emp_row = next(e for e in resp.employees if e.employee_id == employee.id)
    assert emp_row.status == "assigned"  # medarbejderen skal også farves i tabel 2


def test_upsert_extra_assignment_unknown_slot_rejected(db, employee):
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        DailyPlanExtraAssignmentUpsert(date=date(2026, 9, 9), slot=11, employee_id=employee.id)
    with pytest.raises(ValidationError):
        DailyPlanExtraAssignmentUpsert(date=date(2026, 9, 9), slot=0, employee_id=employee.id)


def test_upsert_extra_assignment_conflict_with_vehicle_assignment(db, employee):
    """En medarbejder der allerede kører en rigtig vogn den dag, skal give samme advarsel
    ved forsøg på at tildele en EKSTRA-plads."""
    from routers.dagsplan_router import upsert_assignment, upsert_extra_assignment
    v = _vehicle(db)
    upsert_assignment(DailyPlanAssignmentUpsert(date=date(2026, 9, 9), vehicle_id=v.id, employee_id=employee.id),
                      current_user=_user(), db=db)

    with pytest.raises(HTTPException) as exc:
        upsert_extra_assignment(
            DailyPlanExtraAssignmentUpsert(date=date(2026, 9, 9), slot=1, employee_id=employee.id),
            current_user=_user(), db=db,
        )
    assert exc.value.status_code == 409
    assert v.vehicle_number in exc.value.detail

    row = upsert_extra_assignment(
        DailyPlanExtraAssignmentUpsert(date=date(2026, 9, 9), slot=1, employee_id=employee.id, force=True),
        current_user=_user(), db=db,
    )
    assert row.employee_id == employee.id


def test_upsert_extra_assignment_conflict_with_other_extra_slot(db, employee):
    from routers.dagsplan_router import upsert_extra_assignment
    upsert_extra_assignment(
        DailyPlanExtraAssignmentUpsert(date=date(2026, 9, 9), slot=1, employee_id=employee.id),
        current_user=_user(), db=db,
    )
    with pytest.raises(HTTPException) as exc:
        upsert_extra_assignment(
            DailyPlanExtraAssignmentUpsert(date=date(2026, 9, 9), slot=2, employee_id=employee.id),
            current_user=_user(), db=db,
        )
    assert exc.value.status_code == 409
    assert "EKSTRA-plads 1" in exc.value.detail


def test_upsert_extra_assignment_conflict_when_employee_is_absent(db, employee):
    from routers.dagsplan_router import upsert_extra_assignment
    db.add(MasterAbsenceType(label="Ferie", normalized_key="ferie"))
    db.commit()
    make_activity(db, employee, datetime(2026, 9, 9, 6, 0), datetime(2026, 9, 9, 14, 0), activity_type="ferie")

    with pytest.raises(HTTPException) as exc:
        upsert_extra_assignment(
            DailyPlanExtraAssignmentUpsert(date=date(2026, 9, 9), slot=1, employee_id=employee.id),
            current_user=_user(), db=db,
        )
    assert exc.value.status_code == 409
    assert "Ferie" in exc.value.detail


def test_vehicle_without_vognpark_flag_excluded_from_dagsplan(db):
    from routers.dagsplan_router import get_dagsplan
    _vehicle(db, vognpark=False)
    resp = get_dagsplan(date=date(2026, 9, 9), dispatcher_group_id=None, employee_id=None,
                        current_user=_user(), db=db)
    assert resp.vehicles == []


def test_fast_bil_on_non_vognpark_vehicle_hidden_and_no_conflict(db, employee):
    """En vogn der ikke er markeret 'Vognpark' må hverken vises i Dagsplanen via
    Fast bil-fallback, eller tælle som en eksisterende tildeling ved konflikttjek
    når medarbejderen tildeles en anden (vognpark-markeret) vogn."""
    from routers.dagsplan_router import get_dagsplan, upsert_assignment
    v_not_in_fleet = _vehicle(db, "52", "BN47449", vognpark=False)
    v_in_fleet = _vehicle(db, "60", "AB12345", vognpark=True)
    employee.fast_bil = True
    employee.fast_bil_vehicle_id = v_not_in_fleet.id
    db.commit()

    resp = get_dagsplan(date=date(2026, 9, 9), dispatcher_group_id=None, employee_id=None,
                        current_user=_user(), db=db)
    assert len(resp.vehicles) == 1
    assert resp.vehicles[0].vehicle_number == "60"
    assert resp.vehicles[0].employee_id is None  # Fast bil-fallback rammer ikke en vogn uden for Dagsplanen

    # Ingen 409-konflikt, selvom medarbejderen "burde" være optaget via Fast bil på v_not_in_fleet
    row = upsert_assignment(DailyPlanAssignmentUpsert(date=date(2026, 9, 9), vehicle_id=v_in_fleet.id,
                                                       employee_id=employee.id),
                            current_user=_user(), db=db)
    assert row.employee_id == employee.id


def test_vehicle_assignment_conflict_detects_existing_extra_slot(db, employee):
    """Omvendt retning: en EKSTRA-tildeling skal også opdages, når man
    bagefter forsøger at sætte samme medarbejder på en rigtig vogn."""
    from routers.dagsplan_router import upsert_assignment, upsert_extra_assignment
    v = _vehicle(db)
    upsert_extra_assignment(
        DailyPlanExtraAssignmentUpsert(date=date(2026, 9, 9), slot=1, employee_id=employee.id),
        current_user=_user(), db=db,
    )
    with pytest.raises(HTTPException) as exc:
        upsert_assignment(DailyPlanAssignmentUpsert(date=date(2026, 9, 9), vehicle_id=v.id, employee_id=employee.id),
                          current_user=_user(), db=db)
    assert exc.value.status_code == 409
    assert "EKSTRA-plads 1" in exc.value.detail
