import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

from datetime import date

import pytest
from fastapi import HTTPException

from database.models import AppUser, Employee, MasterPosition


def _admin(db):
    u = AppUser(name="Admin", initials="ADM", role="admin", password_hash="x")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def test_create_update_list_delete_position(db):
    from routers.stamdata import (PositionBody, create_position, delete_position,
                                  list_positions_stamdata, update_position)
    user = _admin(db)
    row = create_position(PositionBody(name="  Disponent "), current_user=user, db=db)
    assert row["name"] == "Disponent"
    update_position(row["id"], PositionBody(name="Disponent (dag)"), current_user=user, db=db)
    names = [r["name"] for r in list_positions_stamdata(current_user=user, db=db)]
    assert names == ["Disponent (dag)", "Testchauffør"]
    assert any(r["employee_count"] == 0 for r in list_positions_stamdata(current_user=user, db=db))
    delete_position(row["id"], current_user=user, db=db)
    assert db.query(MasterPosition).filter(MasterPosition.id == row["id"]).first() is None


def test_duplicate_and_blank_name_rejected(db):
    from routers.stamdata import PositionBody, create_position
    user = _admin(db)
    with pytest.raises(HTTPException):
        create_position(PositionBody(name="testchauffør"), current_user=user, db=db)
    with pytest.raises(HTTPException):
        create_position(PositionBody(name="   "), current_user=user, db=db)


def test_delete_rejected_when_in_use(db):
    from routers.stamdata import delete_position
    user = _admin(db)
    db.add(Employee(employee_number="34001", first_name="A", last_name="B", agreement_type="X",
                    hire_date=date(2026, 1, 1), position_id=1))
    db.commit()
    with pytest.raises(HTTPException) as exc:
        delete_position(1, current_user=user, db=db)
    assert exc.value.status_code == 400 and "1 medarbejder" in exc.value.detail
