from datetime import date
from decimal import Decimal

import pytest

from database.models import MasterAgreementType, MasterOvertimeRate, MasterSupplementRate
from calculators.rates_loader import (
    load_overtime_rates_by_id_from_db,
    load_supplement_rates_by_id_from_db,
)


def test_load_overtime_rates_by_id_returns_all_rows(db):
    r1 = MasterOvertimeRate(label="Overtid 1 time før", rate=Decimal("44.54"))
    r2 = MasterOvertimeRate(label="Øvrigt overtid", rate=Decimal("109.40"))
    db.add(r1)
    db.add(r2)
    db.commit()
    db.refresh(r1)
    db.refresh(r2)

    result = load_overtime_rates_by_id_from_db(db)

    assert result == {r1.id: Decimal("44.54"), r2.id: Decimal("109.40")}


def test_load_supplement_rates_by_id_returns_all_rows(db):
    r1 = MasterSupplementRate(label="Salttillæg", rate=Decimal("12.50"))
    r2 = MasterSupplementRate(label="DOB_overnatning", rate=Decimal("597.00"), is_user_created=True)
    db.add(r1)
    db.add(r2)
    db.commit()
    db.refresh(r1)
    db.refresh(r2)

    result = load_supplement_rates_by_id_from_db(db)

    assert result == {r1.id: Decimal("12.50"), r2.id: Decimal("597.00")}


def test_load_functions_return_empty_dict_when_no_rows(db):
    assert load_overtime_rates_by_id_from_db(db) == {}
    assert load_supplement_rates_by_id_from_db(db) == {}


from routers.payroll_router import _resolve_rate
from calculators.overtime import OT_BEFORE_KEY


def test_resolve_rate_overtime_prefix_looks_up_by_id():
    calc = {"ot_rates_by_id": {7: Decimal("44.54")}, "hourly_rate": Decimal("150.00")}
    assert _resolve_rate("overtime:7", calc) == 44.54


def test_resolve_rate_supplement_prefix_looks_up_by_id():
    calc = {"supplement_rates_by_id": {5: Decimal("597.00")}, "hourly_rate": Decimal("150.00")}
    assert _resolve_rate("supplement:5", calc) == 597.00


def test_resolve_rate_unknown_id_in_prefix_returns_zero():
    calc = {"ot_rates_by_id": {}, "supplement_rates_by_id": {}, "hourly_rate": Decimal("150.00")}
    assert _resolve_rate("overtime:999", calc) == 0
    assert _resolve_rate("supplement:999", calc) == 0


def test_resolve_rate_legacy_fixed_values_still_work():
    calc = {
        "ot_rates": {OT_BEFORE_KEY: Decimal("44.54")},
        "salt_rate": Decimal("12.50"),
        "hourly_rate": Decimal("150.00"),
    }
    assert _resolve_rate("ot_before", calc) == 44.54
    assert _resolve_rate("salt", calc) == 12.50


def test_resolve_rate_hourly_and_unknown_fall_back_to_hourly_rate():
    calc = {"hourly_rate": Decimal("150.00")}
    assert _resolve_rate("hourly", calc) == 150.00
    assert _resolve_rate("noget_ukendt", calc) == 150.00


from routers.payroll_router import _calculate_employee


def test_calculate_employee_exposes_rate_dicts_by_id(db, employee):
    ot = MasterOvertimeRate(label="Overtid 1 time før", rate=Decimal("44.54"))
    supp = MasterSupplementRate(label="DOB_overnatning", rate=Decimal("597.00"), is_user_created=True)
    db.add(MasterAgreementType(name=employee.agreement_type, hourly_rate=Decimal("150.00")))
    db.add(ot)
    db.add(supp)
    db.commit()
    db.refresh(ot)
    db.refresh(supp)

    calc = _calculate_employee(employee, date(2026, 1, 1), date(2026, 1, 31), db)

    assert calc["ot_rates_by_id"][ot.id] == pytest.approx(44.54)
    assert calc["supplement_rates_by_id"][supp.id] == pytest.approx(597.00)


from fastapi import HTTPException

from routers.stamdata import delete_overtime_rate, delete_supplement
from database.models import AppUser, MasterPayType


def _dummy_user():
    """Ugemt AppUser til at kalde route-funktioner direkte i tests uden en
    rigtig session — samme mønster som i tests/test_springertillaeg.py."""
    return AppUser(name="Test", initials="TST", role="admin", password_hash="x")


def test_delete_overtime_rate_blocked_when_referenced_by_pay_type(db):
    ot = MasterOvertimeRate(label="Ekstra overtid", rate=Decimal("50.00"), is_user_created=True)
    db.add(ot)
    db.commit()
    db.refresh(ot)
    db.add(MasterPayType(
        code_key="TEST_TYPE", label="Testtype", csv_rate_source=f"overtime:{ot.id}",
        is_user_created=True,
    ))
    db.commit()

    with pytest.raises(HTTPException) as exc_info:
        delete_overtime_rate(ot.id, current_user=_dummy_user(), db=db)
    assert exc_info.value.status_code == 400
    assert "Testtype" in exc_info.value.detail


def test_delete_overtime_rate_allowed_when_not_referenced(db):
    ot = MasterOvertimeRate(label="Ubrugt overtid", rate=Decimal("50.00"), is_user_created=True)
    db.add(ot)
    db.commit()
    db.refresh(ot)

    delete_overtime_rate(ot.id, current_user=_dummy_user(), db=db)

    assert db.query(MasterOvertimeRate).filter(MasterOvertimeRate.id == ot.id).first() is None


def test_delete_supplement_blocked_when_referenced_by_pay_type(db):
    supp = MasterSupplementRate(label="Ekstra tillæg", rate=Decimal("30.00"), is_user_created=True)
    db.add(supp)
    db.commit()
    db.refresh(supp)
    db.add(MasterPayType(
        code_key="TEST_TYPE2", label="Testtype 2", csv_rate_source=f"supplement:{supp.id}",
        is_user_created=True,
    ))
    db.commit()

    with pytest.raises(HTTPException) as exc_info:
        delete_supplement(supp.id, current_user=_dummy_user(), db=db)
    assert exc_info.value.status_code == 400
    assert "Testtype 2" in exc_info.value.detail


def test_delete_supplement_allowed_when_not_referenced(db):
    supp = MasterSupplementRate(label="Ubrugt tillæg", rate=Decimal("30.00"), is_user_created=True)
    db.add(supp)
    db.commit()
    db.refresh(supp)

    delete_supplement(supp.id, current_user=_dummy_user(), db=db)

    assert db.query(MasterSupplementRate).filter(MasterSupplementRate.id == supp.id).first() is None


import routers.payroll_router as payroll_router


def test_calculate_employee_raises_when_rate_lookup_fails(db, employee, monkeypatch):
    """Hvis timeløns-opslaget fejler, skal det give en synlig 500-fejl —
    ikke stille beregne 0 kr. i løn for medarbejderen (se payroll_router.py)."""
    def _boom(*_args):
        raise RuntimeError("databasen er midlertidigt utilgængelig")

    # Satsen slås op pr. periode siden 2026-10-06 (daterede satser)
    monkeypatch.setattr(payroll_router, "agreement_rate_for_period", _boom)

    with pytest.raises(HTTPException) as exc_info:
        payroll_router._calculate_employee(employee, date(2026, 1, 1), date(2026, 1, 31), db)

    assert exc_info.value.status_code == 500
