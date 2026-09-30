"""
Flere biler på én vagt (bekræftet af bruger 2026-09-30): en .ddd-vagt kan være
kørt i flere biler efter hinanden. Alle biler gemmes på vagten, aktivitets-
modalen viser listen (uden manuel ændring af vognnummer), og Lønafregning
viser én linje pr. bil pr. dag. Vagtplan/timeseddel/Danløn-CSV er uændrede.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))
sys.path.insert(0, os.path.dirname(__file__))

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi import HTTPException

from database.models import ActivityStatus, AppUser, Vehicle
from calculators.pay_period import get_or_create_period_for_date
from calculators.vehicle_uses import vehicle_assignment_intervals
from calculators.overtime import calculate_overtime
from conftest import make_activity


def _dt(day, hh, mm=0):
    return datetime(2026, 1, day, hh, mm)


def _uses_json(*uses):
    return [[s.isoformat(), e.isoformat(), reg] for s, e, reg in uses]


def _setup_rates(db, employee, hourly=Decimal("150.00")):
    from database.models import MasterAgreementType, MasterOvertimeRate
    from calculators.overtime import OT_BEFORE_KEY, OT_13_KEY, OT_EXTRA_KEY
    db.add(MasterAgreementType(name=employee.agreement_type, hourly_rate=hourly))
    db.add(MasterOvertimeRate(label=OT_BEFORE_KEY, rate=Decimal("50")))
    db.add(MasterOvertimeRate(label=OT_13_KEY, rate=Decimal("75")))
    db.add(MasterOvertimeRate(label=OT_EXTRA_KEY, rate=Decimal("100")))
    db.commit()


# ---------------------------------------------------------------------------
# Nærmeste-bil-reglen
# ---------------------------------------------------------------------------

def test_assignment_gives_time_without_vehicle_to_nearest_vehicle():
    uses = [
        (_dt(5, 6, 10), _dt(5, 9), "AA11111"),
        (_dt(5, 9, 30), _dt(5, 12), "BB22222"),
        (_dt(5, 13), _dt(5, 15), "AA11111"),
    ]
    intervals = vehicle_assignment_intervals(_dt(5, 6), _dt(5, 16), uses)
    assert intervals == [
        (_dt(5, 6), _dt(5, 9, 30), "AA11111"),       # før første bil -> første bil
        (_dt(5, 9, 30), _dt(5, 13), "BB22222"),      # hul -> forrige bil
        (_dt(5, 13), _dt(5, 16), "AA11111"),         # efter sidste bil -> sidste bil
    ]


def test_assignment_is_none_for_single_vehicle():
    uses = [(_dt(5, 6), _dt(5, 9), "AA11111"), (_dt(5, 10), _dt(5, 14), "AA11111")]
    assert vehicle_assignment_intervals(_dt(5, 6), _dt(5, 14), uses) is None


def test_overtime_by_vehicle_follows_chronological_cap():
    intervals = [(_dt(5, 6), _dt(5, 10), "AA11111"), (_dt(5, 10), _dt(5, 17), "BB22222")]
    with_vehicles = calculate_overtime(_dt(5, 6), _dt(5, 17), Decimal("8"), [], {},
                                       vehicle_intervals=intervals)
    without = calculate_overtime(_dt(5, 6), _dt(5, 17), Decimal("8"), [], {})

    a = with_vehicles.by_date_vehicle[(date(2026, 1, 5), "AA11111")]
    b = with_vehicles.by_date_vehicle[(date(2026, 1, 5), "BB22222")]
    assert a["total_hours"] == 4 and a["ot_13"] == 0
    assert b["total_hours"] == 7 and b["ot_13"] == 3
    # Fordelingen ændrer ikke selve beregningen.
    assert with_vehicles.total_hours == without.total_hours
    assert with_vehicles.ot_13_hours == without.ot_13_hours
    assert with_vehicles.by_date == without.by_date
    assert without.by_date_vehicle == {}


# ---------------------------------------------------------------------------
# Lønafregning
# ---------------------------------------------------------------------------

def test_settlement_splits_multi_vehicle_shift_into_one_row_per_vehicle(db, employee):
    from routers.payroll_settlement_router import _employee_settlement_data
    _setup_rates(db, employee)
    db.add(Vehicle(registration_number="AA11111", vehicle_number="11"))
    db.commit()
    period = get_or_create_period_for_date(date(2026, 1, 5), db)
    act = make_activity(db, employee, _dt(5, 6), _dt(5, 17), status=ActivityStatus.approved)
    act.vehicle_registration = "BB22222"
    act.vehicle_uses = _uses_json(
        (_dt(5, 6, 5), _dt(5, 10), "AA11111"),
        (_dt(5, 10, 5), _dt(5, 17), "BB22222"),   # ikke oprettet i Vognpark
    )
    db.commit()

    data = _employee_settlement_data(employee, period.start_date, period.end_date, db)

    rows = [d for d in data["days"] if d["date"] == "2026-01-05"]
    assert len(rows) == 2
    row_a = next(r for r in rows if r["vehicle_number"] == "11")
    row_b = next(r for r in rows if r["vehicle_number"] != "11")
    assert row_b["vehicle_number"] in (None, "")   # tomt vognnummer – bilen skal oprettes
    assert row_a["vehicle_times"] == ["06:05–10:00"]
    assert row_b["vehicle_times"] == ["10:05–17:00"]
    assert row_a["total_hours"] == pytest.approx(4 + 5 / 60, abs=0.01)
    assert row_a["ot_13"] == 0
    assert row_b["ot_13"] == pytest.approx(3.0)
    assert row_a["total_kr"] + row_b["total_kr"] == pytest.approx(11 * 150 + 3 * 75, abs=0.02)
    # Periodetotalen er den samme som uden opdeling.
    assert data["total_kr"] == pytest.approx(11 * 150 + 3 * 75)


def test_settlement_same_vehicle_twice_is_one_row_with_all_time_ranges(db, employee):
    from routers.payroll_settlement_router import _employee_settlement_data
    _setup_rates(db, employee)
    db.add(Vehicle(registration_number="AA11111", vehicle_number="11"))
    db.add(Vehicle(registration_number="BB22222", vehicle_number="22"))
    db.commit()
    period = get_or_create_period_for_date(date(2026, 1, 5), db)
    act = make_activity(db, employee, _dt(5, 6), _dt(5, 14), status=ActivityStatus.approved)
    act.vehicle_uses = _uses_json(
        (_dt(5, 6), _dt(5, 9), "AA11111"),
        (_dt(5, 9), _dt(5, 11), "BB22222"),
        (_dt(5, 11), _dt(5, 14), "AA11111"),
    )
    db.commit()

    data = _employee_settlement_data(employee, period.start_date, period.end_date, db)

    rows = {r["vehicle_number"]: r for r in data["days"] if r["date"] == "2026-01-05"}
    assert set(rows) == {"11", "22"}
    assert rows["11"]["vehicle_times"] == ["06:00–09:00", "11:00–14:00"]
    assert rows["11"]["total_hours"] == pytest.approx(6.0)
    assert rows["22"]["total_hours"] == pytest.approx(2.0)


def test_settlement_multi_vehicle_on_sunday_splits_kode9(db, employee):
    from routers.payroll_settlement_router import _employee_settlement_data
    _setup_rates(db, employee)
    db.add(Vehicle(registration_number="AA11111", vehicle_number="11"))
    db.add(Vehicle(registration_number="BB22222", vehicle_number="22"))
    db.commit()
    period = get_or_create_period_for_date(date(2026, 1, 4), db)
    act = make_activity(db, employee, _dt(4, 8), _dt(4, 14), status=ActivityStatus.approved)
    act.vehicle_uses = _uses_json((_dt(4, 8), _dt(4, 11), "AA11111"), (_dt(4, 11), _dt(4, 14), "BB22222"))
    db.commit()

    data = _employee_settlement_data(employee, period.start_date, period.end_date, db)

    rows = {r["vehicle_number"]: r for r in data["days"] if r["date"] == "2026-01-04"}
    assert set(rows) == {"11", "22"}
    for row in rows.values():
        assert row["total_hours"] == pytest.approx(3.0)
        assert row["ot_extra"] == pytest.approx(3.0)       # søndag: kode 9 på alle timer
        assert row["total_kr"] == pytest.approx(3 * 150 + 3 * 100)


def test_settlement_single_vehicle_shift_unchanged(db, employee):
    from routers.payroll_settlement_router import _employee_settlement_data
    _setup_rates(db, employee)
    period = get_or_create_period_for_date(date(2026, 1, 5), db)
    act = make_activity(db, employee, _dt(5, 6), _dt(5, 14), status=ActivityStatus.approved)
    act.vehicle_number = "11"
    act.vehicle_uses = _uses_json((_dt(5, 6), _dt(5, 14), "AA11111"))
    db.commit()

    data = _employee_settlement_data(employee, period.start_date, period.end_date, db)

    rows = [r for r in data["days"] if r["date"] == "2026-01-05"]
    assert len(rows) == 1
    assert rows[0]["vehicle_number"] == "11"
    assert rows[0]["vehicle_times"] == []


# ---------------------------------------------------------------------------
# Aktivitet: visning og ingen manuel ændring af vognnummer
# ---------------------------------------------------------------------------

def _user():
    return AppUser(name="Test", initials="LB1", role="lonbogholder", password_hash="x")


def test_activity_response_lists_all_vehicles_only_when_multiple(db, employee):
    from routers.activities import _to_response
    db.add(Vehicle(registration_number="AA11111", vehicle_number="11"))
    db.commit()
    act = make_activity(db, employee, _dt(5, 6), _dt(5, 14))
    act.vehicle_uses = _uses_json((_dt(5, 6), _dt(5, 9), "AA11111"), (_dt(5, 9), _dt(5, 14), "BB22222"))
    db.commit()

    uses = _to_response(act).vehicle_uses
    assert [(u["registration"], u["vehicle_number"]) for u in uses] == [("AA11111", "11"), ("BB22222", None)]

    act.vehicle_uses = _uses_json((_dt(5, 6), _dt(5, 14), "AA11111"))
    db.commit()
    assert _to_response(act).vehicle_uses == []


def test_update_activity_rejects_manual_vehicle_change_on_multi_vehicle_shift(db, employee):
    from routers.activities import update_activity
    from database.schemas import ActivityUpdate
    act = make_activity(db, employee, _dt(5, 6), _dt(5, 14))
    act.vehicle_number = "11"
    act.vehicle_uses = _uses_json((_dt(5, 6), _dt(5, 9), "AA11111"), (_dt(5, 9), _dt(5, 14), "BB22222"))
    db.commit()

    with pytest.raises(HTTPException) as exc:
        update_activity(act.id, ActivityUpdate(vehicle_number="99"), current_user=_user(), db=db)
    assert exc.value.status_code == 400

    # Øvrige felter kan stadig gemmes (frontend sender ikke vognnummer).
    resp = update_activity(act.id, ActivityUpdate(km_start=100), current_user=_user(), db=db)
    assert resp.km_start == 100
    assert resp.vehicle_number == "11"


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------

def _parsed(start, end, vehicle_uses):
    from parsers.ddd_parser import ParsedActivity
    return ParsedActivity(
        tachograph_card_number="X", start_time=start, end_time=end,
        availability_time_pct=Decimal("0"), rest_pause_pct=Decimal("0"),
        other_work_pct=Decimal("0"), driving_pct=Decimal("0"), source_file="test.ddd",
        pause_intervals=[], segments=[(start, end, "driving")],
        vehicle_registration="AA11111", vehicle_uses=vehicle_uses,
    )


def test_import_stores_vehicle_uses_and_reimport_updates_them(db, employee):
    from database.models import Activity
    from routers.import_ddd import _import_activity
    uses = [(_dt(5, 6), _dt(5, 9), "AA11111"), (_dt(5, 9), _dt(5, 14), "BB22222")]
    _import_activity(_parsed(_dt(5, 6), _dt(5, 14), uses[:1]), db, employee)
    db.commit()
    act = db.query(Activity).one()
    assert act.vehicle_uses == _uses_json(*uses[:1])

    _import_activity(_parsed(_dt(5, 6), _dt(5, 14), uses), db, employee)
    db.commit()
    db.refresh(act)
    assert db.query(Activity).count() == 1
    assert act.vehicle_uses == _uses_json(*uses)


# ---------------------------------------------------------------------------
# Parser – reelle .ddd-filer (springes over hvis filen ikke ligger lokalt)
# ---------------------------------------------------------------------------

_DDD_DIR = Path(__file__).resolve().parent.parent / "app" / "ddd_input"


def _parse_real(name):
    from parsers.ddd_parser import parse_ddd_file
    matches = list(_DDD_DIR.glob(f"*/{name}"))
    if not matches:
        pytest.skip(f"{name} findes ikke lokalt")
    return parse_ddd_file(matches[0])


def _shift(acts, day_month):
    return next(a for a in acts if a.start_time.strftime("%d-%m-%Y") == day_month)


def test_parser_finds_both_vehicles_on_shift():
    acts = _parse_real("C_20260911_0720_Knudsen_Alexander_Brugge_DK00000130193001.ddd")
    shift = _shift(acts, "31-03-2026")
    assert [reg for _, _, reg in shift.vehicle_uses] == ["DX22215", "EP18202"]
    assert shift.vehicle_uses[0][0] == shift.start_time
    assert shift.vehicle_uses[-1][1] == shift.end_time


def test_parser_ignores_misaligned_record_with_invalid_codepage():
    acts = _parse_real("C_20260824_0829_Eriksen_Finn_Thor_DK00000012666013.ddd")
    shift = _shift(acts, "13-04-2026")
    assert {reg for _, _, reg in shift.vehicle_uses} == {"DM23112"}   # ikke falsk "M23112"


def test_parser_prefers_gen1_records_over_merged_gen2_record():
    acts = _parse_real("C_20260914_1306_Nicolaisen_Claus_Ulrik_DK00000064356003.ddd")
    shift = _shift(acts, "03-07-2026")
    assert [(s.strftime("%H:%M"), e.strftime("%H:%M"), reg) for s, e, reg in shift.vehicle_uses] == [
        ("06:55", "11:11", "DL52884"),
        ("11:17", "13:24", "CH78037"),
        ("13:30", "14:19", "DL52884"),
    ]


def test_vehicle_split_never_changes_employee_total(db, employee):
    """Bilskift midt i en time (fx 17:40) må ikke give en øre-forskel i
    totalen (set 2026-09-30 ved første udgave: 2.405,59 mod 2.405,60 kr)."""
    from routers.payroll_settlement_router import _employee_settlement_data
    _setup_rates(db, employee)
    db.add(Vehicle(registration_number="AA11111", vehicle_number="11"))
    db.add(Vehicle(registration_number="BB22222", vehicle_number="22"))
    period = get_or_create_period_for_date(date(2026, 1, 5), db)
    act = make_activity(db, employee, _dt(5, 6, 15), _dt(5, 18, 12), status=ActivityStatus.approved)
    db.commit()
    without = _employee_settlement_data(employee, period.start_date, period.end_date, db)

    act.vehicle_uses = _uses_json((_dt(5, 6, 15), _dt(5, 17, 11), "AA11111"),
                                  (_dt(5, 17, 40), _dt(5, 18, 12), "BB22222"))
    db.commit()
    with_split = _employee_settlement_data(employee, period.start_date, period.end_date, db)

    assert with_split["total_kr"] == without["total_kr"]
    rows = [r for r in with_split["days"] if r["date"] == "2026-01-05"]
    assert len(rows) == 2
    assert sum(r["total_kr"] for r in rows) == pytest.approx(without["total_kr"], abs=0.01)
    assert all(r["normal"] >= 0 for r in rows)
