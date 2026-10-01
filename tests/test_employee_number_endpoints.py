import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from datetime import date

from database.models import AppUser, Employee, MasterPosition


def _admin():
    return AppUser(name="Admin", initials="ADM", role="admin", password_hash="x")


def _emp(db, number, first="A", last="B"):
    db.add(Employee(employee_number=number, first_name=first, last_name=last,
                    agreement_type="X", hire_date=date(2026, 1, 1), active=False))
    db.commit()


def test_next_number_uses_highest_including_inactive(db):
    from routers.employees import next_number
    _emp(db, "34637")
    _emp(db, "34640")
    _emp(db, "TEST999")
    assert next_number(current_user=_admin(), db=db) == {"suggestion": "34641"}


def test_check_number_taken_and_exclude_self(db):
    from routers.employees import check_number
    _emp(db, "34625", "Alexander B.", "Knudsen")
    emp_id = db.query(Employee).first().id
    assert check_number(number="34625", exclude_id=None, current_user=_admin(), db=db) == \
        {"taken": True, "employee_name": "Alexander B. Knudsen"}
    assert check_number(number="34625", exclude_id=emp_id, current_user=_admin(), db=db) == \
        {"taken": False, "employee_name": None}
    assert check_number(number=" 34626 ", exclude_id=None, current_user=_admin(), db=db)["taken"] is False


def test_list_positions_alphabetical(db):
    from routers.employees import list_positions
    db.add(MasterPosition(name="Disponent"))
    db.add(MasterPosition(name="Bogholder"))
    db.commit()
    names = [p["name"] for p in list_positions(current_user=_admin(), db=db)]
    assert names == ["Bogholder", "Disponent", "Testchauffør"]
