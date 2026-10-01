import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))

import io
from datetime import date

import openpyxl

from database.models import AppUser, AuditLog, DispatcherGroup, Employee
from database.schemas import EmployeeExportRequest


def _user(db):
    u = AppUser(name="Admin", initials="ADM", role="admin", password_hash="x")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


async def _read(resp):
    chunks = [c async for c in resp.body_iterator]
    return openpyxl.load_workbook(io.BytesIO(b"".join(chunks))).active


def _emp(db, number, **kw):
    e = Employee(employee_number=number, first_name="Fornavn" + number, last_name="Efternavn",
                 agreement_type="X", hire_date=date(2020, 5, 1), **kw)
    db.add(e)
    db.commit()
    return e


def test_export_columns_order_and_no_cpr(db):
    import asyncio
    from routers.employees import EXPORT_HEADERS, export_employees_xlsx
    group = DispatcherGroup(name="2 - Kran")
    db.add(group)
    db.commit()
    a = _emp(db, "34001", phone="11223344", mobile="55667788", email="a@x.dk", position_id=1,
             dispatcher_group_id=group.id, cpr_number="120385-1234", fuldloennet=True, natarbejde_tillaeg=True,
             elev=True, elev_start_date=date(2026, 8, 1), elev_end_date=date(2029, 7, 31))
    b = _emp(db, "34002", fuldloennet=False)
    resp = export_employees_xlsx(EmployeeExportRequest(employee_ids=[b.id, a.id]), current_user=_user(db), db=db)
    ws = asyncio.run(_read(resp))
    rows = list(ws.iter_rows(values_only=True))
    assert list(rows[0]) == EXPORT_HEADERS
    assert rows[1][0] == "34002"           # klientens rækkefølge bevares
    assert rows[2][:7] == ("34001", "Fornavn34001 Efternavn", "Ja", "Ja", "Testchauffør", "2 - Kran", "01-05-2020")
    assert rows[2][7:] == ("11223344", "55667788", "a@x.dk", "Ja", "01-08-2026", "31-07-2029")
    assert rows[1][3] == "Nej" and rows[1][10] == "Nej" and rows[1][11] is None
    flat = " ".join(str(v) for r in rows for v in r if v)
    assert "1234" not in flat and "120385" not in flat


def test_export_is_audit_logged(db):
    from routers.employees import export_employees_xlsx
    a = _emp(db, "34001")
    user = _user(db)
    export_employees_xlsx(EmployeeExportRequest(employee_ids=[a.id]), current_user=user, db=db)
    assert db.query(AuditLog).filter(AuditLog.action == "employee_export").count() == 1
