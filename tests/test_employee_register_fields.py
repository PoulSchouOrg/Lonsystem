import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))
sys.path.insert(0, os.path.dirname(__file__))

import sqlite3
from datetime import date

from database.models import Employee, MasterPosition


def test_new_employee_defaults(db):
    emp = Employee(employee_number="34001", first_name="A", last_name="B",
                   agreement_type="X", hire_date=date(2026, 1, 1))
    db.add(emp)
    db.commit()
    db.refresh(emp)
    assert emp.personaleforening is True
    assert emp.elev is False
    assert emp.natarbejde_tillaeg is False
    assert emp.position_id is None and emp.cpr_number is None and emp.seniority_date is None


def test_db_fixture_seeds_test_position(db):
    pos = db.query(MasterPosition).get(1)
    assert pos.name == "Testchauffør"


def test_to_response_includes_new_fields(db, employee):
    from routers.employees import _to_response
    employee.position_id = 1
    employee.seniority_date = date(2001, 5, 1)
    employee.cpr_number = "120385-1234"
    employee.elev = True
    employee.elev_start_date = date(2026, 8, 1)
    employee.elev_end_date = date(2029, 7, 31)
    employee.natarbejde_tillaeg = True
    db.commit()
    resp = _to_response(employee, db)
    assert resp.position_id == 1 and resp.position_name == "Testchauffør"
    assert resp.seniority_date == date(2001, 5, 1)
    assert resp.cpr_number == "120385-1234"
    assert resp.elev is True and resp.elev_end_date == date(2029, 7, 31)
    assert resp.personaleforening is True and resp.natarbejde_tillaeg is True


def test_migrate_adds_columns_and_existing_rows_are_not_members(tmp_path, monkeypatch):
    """Eksisterende medarbejdere sættes IKKE som medlem af personaleforeningen."""
    from sqlalchemy import create_engine
    from database.models import Base
    import database.session as session_mod

    db_file = tmp_path / "old.db"
    engine = create_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(engine)
    engine.dispose()
    new_cols = ["position_id", "seniority_date", "cpr_number", "elev", "elev_start_date",
                "elev_end_date", "personaleforening", "natarbejde_tillaeg"]
    with sqlite3.connect(db_file) as conn:
        # Genskab en "gammel" employees-tabel uden de nye kolonner. DROP COLUMN kan
        # ikke bruges, fordi position_id indgår i en FOREIGN KEY.
        old_cols = [r[1] for r in conn.execute("PRAGMA table_info(employees)") if r[1] not in new_cols]
        conn.execute(f"CREATE TABLE employees_old AS SELECT {', '.join(old_cols)} FROM employees")
        conn.execute("DROP TABLE employees")
        conn.execute("ALTER TABLE employees_old RENAME TO employees")
        conn.execute(
            "INSERT INTO employees (employee_number, first_name, last_name, agreement_kind, agreement_type, "
            "fuldloennet, active, hire_date, termination_date, work_schedule, paragraf_56, afloeser, "
            "ot_extra_alle_timer, fast_bil) VALUES ('34001','A','B','hourly_fixed','X',1,1,'2026-01-01',"
            "'9999-12-31','{}',0,0,0,0)"
        )
        conn.commit()

    monkeypatch.setattr(session_mod, "DB_PATH", db_file)
    session_mod._migrate()

    with sqlite3.connect(db_file) as conn:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(employees)")}
        assert set(new_cols) <= cols
        assert conn.execute("SELECT personaleforening, elev, natarbejde_tillaeg FROM employees").fetchone() == (0, 0, 0)


import pytest
from decimal import Decimal
from fastapi import HTTPException

from conftest import required_employee_fields
from database.models import AppUser, MasterAgreementKind, MasterAgreementType, Role
from database.schemas import EmployeeCreate, EmployeeUpdate, WorkSchedule


def _seed(db):
    db.add(MasterAgreementType(name="Standardoverenskomst", hourly_rate=Decimal("150.00")))
    db.add(MasterAgreementKind(key="hourly_fixed", label="Timelønnet", is_active=True,
                               is_user_created=False, requires_agreement_type=True, sort_order=1))
    db.add(MasterAgreementKind(key="funktionaer", label="Funktionær", is_active=True,
                               is_user_created=False, requires_agreement_type=False, sort_order=2))
    db.commit()


def _user(db, name, perms):
    db.add(Role(name=name, display_name=name, is_system=False, permissions=perms))
    u = AppUser(name=name, initials=name[:3].upper(), role=name, password_hash="x", active=True)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _driver_body(**overrides):
    data = dict(employee_number="34500", first_name="Ny", last_name="Chauffør",
                agreement_kind="hourly_fixed", agreement_type="Standardoverenskomst",
                hire_date=date(2026, 1, 1), work_schedule=WorkSchedule())
    data.update(overrides)
    data = {**required_employee_fields(data["employee_number"]), **data}
    return EmployeeCreate(**data)


def _office_body(**overrides):
    data = dict(employee_number="34600", first_name="Ny", last_name="Funktionær",
                agreement_kind="funktionaer", agreement_type="", initials="NYF",
                position_id=1, email="ny@poulschou.dk",
                hire_date=date(2026, 1, 1), work_schedule=WorkSchedule())
    data.update(overrides)
    return EmployeeCreate(**data)


@pytest.mark.parametrize("field,label", [
    ("position_id", "Stilling"), ("email", "Email"), ("tachograph_card_number", "Førerkortnummer"),
])
def test_create_driver_requires_fields(db, field, label):
    from routers.employees import create_employee
    _seed(db)
    with pytest.raises(HTTPException) as exc:
        create_employee(_driver_body(**{field: None}), current_user=_user(db, "a", ["manage_employees"]), db=db)
    assert exc.value.status_code == 400 and label in exc.value.detail


def test_create_office_requires_initials_but_not_card(db):
    from routers.employees import create_employee
    _seed(db)
    user = _user(db, "a", ["manage_employees"])
    resp = create_employee(_office_body(), current_user=user, db=db)
    assert resp.tachograph_card_number is None
    with pytest.raises(HTTPException) as exc:
        create_employee(_office_body(employee_number="34601", initials=None), current_user=user, db=db)
    assert "Initialer" in exc.value.detail


def test_create_rejects_unknown_position(db):
    from routers.employees import create_employee
    _seed(db)
    with pytest.raises(HTTPException) as exc:
        create_employee(_driver_body(position_id=999), current_user=_user(db, "a", ["manage_employees"]), db=db)
    assert exc.value.status_code == 400


def test_elev_requires_dates_for_driver(db):
    from routers.employees import create_employee
    _seed(db)
    user = _user(db, "a", ["manage_employees"])
    with pytest.raises(HTTPException):
        create_employee(_driver_body(elev=True), current_user=user, db=db)
    with pytest.raises(HTTPException):
        create_employee(_driver_body(elev=True, elev_start_date=date(2026, 8, 1),
                                     elev_end_date=date(2026, 7, 1)), current_user=user, db=db)
    resp = create_employee(_driver_body(elev=True, elev_start_date=date(2026, 8, 1),
                                        elev_end_date=date(2029, 7, 31)), current_user=user, db=db)
    assert resp.elev is True


def test_elev_dates_not_required_for_office(db):
    """Skjulte påkrævede felter er ikke påkrævede – og værdien bevares."""
    from routers.employees import create_employee
    _seed(db)
    resp = create_employee(_office_body(elev=True), current_user=_user(db, "a", ["manage_employees"]), db=db)
    assert resp.elev is True


def test_create_rejects_invalid_cpr(db):
    from routers.employees import create_employee
    _seed(db)
    with pytest.raises(HTTPException) as exc:
        create_employee(_driver_body(cpr_number="1203851234"), current_user=_user(db, "a", ["manage_employees"]), db=db)
    assert "CPR" in exc.value.detail


def test_cpr_masked_without_view_cpr_and_full_with(db):
    from routers.employees import create_employee, get_employee
    _seed(db)
    creator = _user(db, "a", ["manage_employees"])
    resp = create_employee(_driver_body(cpr_number="120385-1234"), current_user=creator, db=db)
    assert resp.cpr_number == "120385-****"
    viewer = _user(db, "b", ["view_employees", "view_cpr"])
    assert get_employee(resp.id, current_user=viewer, db=db).cpr_number == "120385-1234"
    assert get_employee(resp.id, current_user=_user(db, "c", ["view_employees"]), db=db).cpr_number == "120385-****"
    assert get_employee(resp.id, current_user=_user(db, "d", ["view_calendar"]), db=db).cpr_number is None


def test_update_with_masked_cpr_keeps_stored_value(db):
    from routers.employees import create_employee, update_employee
    _seed(db)
    user = _user(db, "a", ["manage_employees"])
    resp = create_employee(_driver_body(cpr_number="120385-1234"), current_user=user, db=db)
    update_employee(resp.id, EmployeeUpdate(cpr_number="120385-****"), current_user=user, db=db)
    assert db.query(Employee).get(resp.id).cpr_number == "120385-1234"
    update_employee(resp.id, EmployeeUpdate(cpr_number="010190-4321"), current_user=user, db=db)
    assert db.query(Employee).get(resp.id).cpr_number == "010190-4321"
    update_employee(resp.id, EmployeeUpdate(cpr_number=None), current_user=user, db=db)
    assert db.query(Employee).get(resp.id).cpr_number is None


def test_update_old_employee_without_new_fields_still_allowed_for_partial_patch(db, employee):
    """Gamle medarbejdere uden stilling/email kan stadig PATCH'es på andre felter."""
    from routers.employees import update_employee
    _seed(db)
    resp = update_employee(employee.id, EmployeeUpdate(afloeser=True),
                           current_user=_user(db, "a", ["manage_employees"]), db=db)
    assert resp.afloeser is True


def test_update_cannot_blank_required_field(db, employee):
    from routers.employees import update_employee
    _seed(db)
    with pytest.raises(HTTPException) as exc:
        update_employee(employee.id, EmployeeUpdate(email=None),
                        current_user=_user(db, "a", ["manage_employees"]), db=db)
    assert "Email" in exc.value.detail


def test_update_rejects_duplicate_employee_number(db, employee):
    from routers.employees import create_employee, update_employee
    _seed(db)
    user = _user(db, "a", ["manage_employees"])
    other = create_employee(_driver_body(), current_user=user, db=db)
    with pytest.raises(HTTPException) as exc:
        update_employee(other.id, EmployeeUpdate(employee_number=employee.employee_number), current_user=user, db=db)
    assert exc.value.status_code == 400


def test_switch_to_office_keeps_hidden_values(db):
    from routers.employees import create_employee, update_employee
    _seed(db)
    user = _user(db, "a", ["manage_employees"])
    resp = create_employee(_driver_body(afloeser=True, natarbejde_tillaeg=True), current_user=user, db=db)
    out = update_employee(resp.id, EmployeeUpdate(agreement_kind="funktionaer", initials="ABC",
                                                  tachograph_card_number=resp.tachograph_card_number),
                          current_user=user, db=db)
    assert out.afloeser is True and out.natarbejde_tillaeg is True
    assert out.tachograph_card_number == resp.tachograph_card_number


def test_paragraf56_change_does_not_wipe_milestone_dismissals(db, employee):
    from routers.employees import update_employee
    from database.models import Paragraf56AlertDismissal
    _seed(db)
    user = _user(db, "a", ["manage_employees"])
    db.add(Paragraf56AlertDismissal(employee_id=employee.id, user_id=user.id, alert_type="birthday_40"))
    db.add(Paragraf56AlertDismissal(employee_id=employee.id, user_id=user.id, alert_type="upcoming"))
    db.commit()
    update_employee(employee.id, EmployeeUpdate(paragraf_56=True, paragraf_56_start_date=date(2026, 1, 1),
                                                paragraf_56_end_date=date(2026, 12, 1)),
                    current_user=user, db=db)
    types = {d.alert_type for d in db.query(Paragraf56AlertDismissal).all()}
    assert types == {"birthday_40"}
