from datetime import date
from decimal import Decimal

import pytest


def test_ensure_payroll_settlement_permissions_adds_to_lonbogholder(db, monkeypatch):
    from database.models import Role
    from database.session import _ensure_payroll_settlement_permissions
    import database.session as session_module
    from sqlalchemy.orm import sessionmaker

    monkeypatch.setattr(session_module, "SessionLocal", sessionmaker(bind=db.get_bind()))

    db.add(Role(name="admin", display_name="Administrator", is_system=True, permissions=["payroll"]))
    db.add(Role(name="lonbogholder", display_name="Lønbogholder", is_system=False, permissions=["payroll"]))
    db.add(Role(name="disponent", display_name="Disponent", is_system=False, permissions=[]))
    db.commit()

    _ensure_payroll_settlement_permissions()

    lonbogholder = db.query(Role).filter(Role.name == "lonbogholder").first()
    db.refresh(lonbogholder)
    assert "payroll_settlement_view" in lonbogholder.permissions
    assert "payroll_settlement_export" in lonbogholder.permissions

    disponent = db.query(Role).filter(Role.name == "disponent").first()
    db.refresh(disponent)
    assert "payroll_settlement_view" not in disponent.permissions

    # Idempotent — running again doesn't duplicate or error
    _ensure_payroll_settlement_permissions()
    db.refresh(lonbogholder)
    assert lonbogholder.permissions.count("payroll_settlement_view") == 1


def _setup_rates(db, employee, hourly=Decimal("150.00")):
    from database.models import MasterAgreementType, MasterOvertimeRate
    from calculators.overtime import OT_BEFORE_KEY, OT_13_KEY, OT_EXTRA_KEY
    db.add(MasterAgreementType(name=employee.agreement_type, hourly_rate=hourly))
    db.add(MasterOvertimeRate(label=OT_BEFORE_KEY, rate=Decimal("50")))
    db.add(MasterOvertimeRate(label=OT_13_KEY, rate=Decimal("75")))
    db.add(MasterOvertimeRate(label=OT_EXTRA_KEY, rate=Decimal("100")))
    db.commit()


def test_employee_settlement_data_separates_agreement_and_personal_rate(db, employee):
    from calculators.pay_period import get_or_create_period_for_date
    from database.models import EmployeeSupplement
    from routers.payroll_settlement_router import _employee_settlement_data
    _setup_rates(db, employee, hourly=Decimal("150.00"))
    period = get_or_create_period_for_date(date(2026, 1, 1), db)
    db.add(EmployeeSupplement(employee_id=employee.id, name="Ikke overenskomstmæssigt tillæg",
                               type="Timebaseret", value=Decimal("10.00"),
                               start_date=date(2025, 1, 1)))
    db.commit()

    data = _employee_settlement_data(employee, period.start_date, period.end_date, db)

    assert data["agreement_rate"] == 150.00
    assert data["personal_supplement_rate"] == 10.00
    assert data["hourly_rate"] == 160.00  # kombineret sats bruges fortsat til selve beregningen
    assert data["springer_enabled"] is False
    assert data["springer_kr"] == 0
    assert len(data["days"]) == 14  # alle dage i perioden, også uden aktivitet


def test_employee_settlement_data_includes_springer_kr_in_total(db, employee):
    from calculators.pay_period import get_or_create_period_for_date
    from database.models import EmployeeSpringerFlag, MasterSupplementRate
    from routers.payroll_settlement_router import _employee_settlement_data
    from conftest import make_activity
    from datetime import datetime
    from database.models import ActivityStatus
    _setup_rates(db, employee, hourly=Decimal("150.00"))
    period = get_or_create_period_for_date(date(2026, 1, 1), db)
    db.add(MasterSupplementRate(label="Springertillæg", rate=Decimal("20.00")))
    db.add(EmployeeSpringerFlag(employee_id=employee.id, pay_period_id=period.id, enabled=True))
    db.commit()
    make_activity(db, employee, datetime(2026, 1, 5, 6, 0), datetime(2026, 1, 5, 14, 0),
                  status=ActivityStatus.approved)

    data = _employee_settlement_data(employee, period.start_date, period.end_date, db)

    assert data["springer_enabled"] is True
    assert data["springer_rate"] == 20.00
    assert data["springer_kr"] == pytest.approx(8.0 * 20.00)
    assert data["total_kr"] == pytest.approx(8.0 * 150.00 + 8.0 * 20.00)


def test_employee_settlement_data_includes_overnight_kr_in_total(db, employee):
    """Overnatningstillæg manglede i Lønafregningens total – bruger opdagede at
    'Total sum for denne periode' ikke viste den fulde løn (2026-09-21)."""
    from calculators.pay_period import get_or_create_period_for_date
    from database.models import ActivityStatus, MasterSupplementRate
    from routers.payroll_settlement_router import _employee_settlement_data
    from conftest import make_activity
    from datetime import datetime
    _setup_rates(db, employee, hourly=Decimal("150.00"))
    db.add(MasterSupplementRate(label="Overnatning", rate=Decimal("95.00")))
    db.commit()
    period = get_or_create_period_for_date(date(2026, 1, 1), db)
    midnight = datetime(2026, 1, 5, 0, 0, 0)
    make_activity(db, employee, midnight, midnight, activity_type="overnatning",
                  status=ActivityStatus.approved)

    data = _employee_settlement_data(employee, period.start_date, period.end_date, db)

    assert data["overnight_count"] == 1
    assert data["overnight_rate"] == pytest.approx(95.00)
    assert data["overnight_kr"] == pytest.approx(95.00)
    assert data["total_kr"] == pytest.approx(95.00)


def test_employee_settlement_data_includes_dob_overnight_kr_in_total(db, employee):
    from calculators.pay_period import get_or_create_period_for_date
    from database.models import ActivityStatus, MasterSupplementRate
    from routers.payroll_settlement_router import _employee_settlement_data
    from conftest import make_activity
    from datetime import datetime
    _setup_rates(db, employee, hourly=Decimal("150.00"))
    db.add(MasterSupplementRate(label="DOB_overnatning", rate=Decimal("597.00"), is_user_created=True))
    db.commit()
    period = get_or_create_period_for_date(date(2026, 1, 1), db)
    midnight = datetime(2026, 1, 5, 0, 0, 0)
    make_activity(db, employee, midnight, midnight, activity_type="dob_overnatning",
                  status=ActivityStatus.approved)

    data = _employee_settlement_data(employee, period.start_date, period.end_date, db)

    assert data["dob_overnight_count"] == 1
    assert data["dob_overnight_rate"] == pytest.approx(597.00)
    assert data["dob_overnight_kr"] == pytest.approx(597.00)
    assert data["total_kr"] == pytest.approx(597.00)


def _find_day(data, iso_date):
    return next(d for d in data["days"] if d["date"] == iso_date)


@pytest.mark.parametrize("activity_type, label, expected_rate", [
    ("sygdom", "Sygdom", Decimal("150.00")),
    ("barn_1sygedag", "Barn 1.sygedag", Decimal("150.00")),
    ("graviditetsbetinget_sygdom", "Graviditetsbetinget sygdom", Decimal("150.00")),
    ("barsel", "Barsel", Decimal("150.00")),
    ("skole_kursus", "Skole/kursus", Decimal("150.00")),
    ("ferie", "Ferie", Decimal("150.00")),
    ("afspadsering", "Afspadsering", Decimal("150.00")),
    ("feriefri", "Feriefri", Decimal("150.00")),
])
def test_employee_settlement_data_shows_hours_and_kr_for_fully_paid_absence_days(
    db, employee, activity_type, label, expected_rate,
):
    """Sygdom, Barn 1.sygedag, Graviditetsbetinget sygdom, Barsel, Skole/kursus,
    Ferie, Afspadsering og Feriefri betales alle med medarbejderens timesats –
    bekræftet af bruger 2026-08-25 (Feriefri: fuldlønnet/timelønnet afgør kun
    Danløn-koden, ikke selve beløbet, så begge bruger samme timesats her)."""
    from datetime import datetime
    from database.models import ActivityStatus
    from calculators.pay_period import get_or_create_period_for_date
    from routers.payroll_settlement_router import _employee_settlement_data
    from conftest import make_activity
    _setup_rates(db, employee, hourly=Decimal("150.00"))
    period = get_or_create_period_for_date(date(2026, 1, 1), db)
    make_activity(db, employee, datetime(2026, 1, 5, 6, 0), datetime(2026, 1, 5, 14, 0),
                  activity_type=activity_type, status=ActivityStatus.approved)

    data = _employee_settlement_data(employee, period.start_date, period.end_date, db)

    day = _find_day(data, "2026-01-05")
    assert day["absence_type"] == label
    assert day["total_hours"] == pytest.approx(8.0)
    assert day["total_kr"] == pytest.approx(8.0 * float(expected_rate))


def test_employee_settlement_data_shows_hours_and_kr_for_paragraf_56_at_dagpenge_sats(db, employee):
    from datetime import datetime
    from database.models import ActivityStatus, MasterSupplementRate
    from calculators.pay_period import get_or_create_period_for_date
    from routers.payroll_settlement_router import _employee_settlement_data
    from conftest import make_activity
    _setup_rates(db, employee, hourly=Decimal("150.00"))
    db.add(MasterSupplementRate(label="Dagpenge §56", rate=Decimal("137.43")))
    db.commit()
    period = get_or_create_period_for_date(date(2026, 1, 1), db)
    make_activity(db, employee, datetime(2026, 1, 5, 6, 0), datetime(2026, 1, 5, 14, 0),
                  activity_type="paragraf_56_syg", status=ActivityStatus.approved)

    data = _employee_settlement_data(employee, period.start_date, period.end_date, db)

    day = _find_day(data, "2026-01-05")
    assert day["absence_type"] == "§56 syg"
    assert day["total_hours"] == pytest.approx(8.0)
    assert day["total_kr"] == pytest.approx(8.0 * 137.43)


def test_employee_settlement_data_shows_hours_and_kr_for_barn_1sygedag_u_8uger_at_dagpenge_sats(db, employee):
    from datetime import datetime
    from database.models import ActivityStatus, MasterSupplementRate
    from calculators.pay_period import get_or_create_period_for_date
    from routers.payroll_settlement_router import _employee_settlement_data
    from conftest import make_activity
    _setup_rates(db, employee, hourly=Decimal("150.00"))
    db.add(MasterSupplementRate(label="Dagpenge §56", rate=Decimal("137.43")))
    db.commit()
    period = get_or_create_period_for_date(date(2026, 1, 1), db)
    make_activity(db, employee, datetime(2026, 1, 5, 6, 0), datetime(2026, 1, 5, 14, 0),
                  activity_type="barn_1sygedag_u_8uger", status=ActivityStatus.approved)

    data = _employee_settlement_data(employee, period.start_date, period.end_date, db)

    day = _find_day(data, "2026-01-05")
    assert day["absence_type"] == "Barn 1.sygedag u. 8 uger"
    assert day["total_hours"] == pytest.approx(8.0)
    assert day["total_kr"] == pytest.approx(8.0 * 137.43)


def test_employee_settlement_data_shows_hours_but_zero_kr_for_sygdom_u_8_uger(db, employee):
    from datetime import datetime
    from database.models import ActivityStatus
    from calculators.pay_period import get_or_create_period_for_date
    from routers.payroll_settlement_router import _employee_settlement_data
    from conftest import make_activity
    _setup_rates(db, employee, hourly=Decimal("150.00"))
    period = get_or_create_period_for_date(date(2026, 1, 1), db)
    make_activity(db, employee, datetime(2026, 1, 5, 6, 0), datetime(2026, 1, 5, 14, 0),
                  activity_type="sygdom_u_8uger", status=ActivityStatus.approved)

    data = _employee_settlement_data(employee, period.start_date, period.end_date, db)

    day = _find_day(data, "2026-01-05")
    assert day["absence_type"] == "Sygdom u. 8 uger"
    assert day["total_hours"] == pytest.approx(8.0)
    assert day["total_kr"] == 0


def test_employee_settlement_data_does_not_show_hours_for_unrelated_absence_types(db, employee):
    """Selvbetalt fridag er IKKE en af de typer brugeren bad om at få vist
    timer/beløb for – dagens række skal derfor forblive 0."""
    from datetime import datetime
    from database.models import ActivityStatus
    from calculators.pay_period import get_or_create_period_for_date
    from routers.payroll_settlement_router import _employee_settlement_data
    from conftest import make_activity
    _setup_rates(db, employee, hourly=Decimal("150.00"))
    period = get_or_create_period_for_date(date(2026, 1, 1), db)
    make_activity(db, employee, datetime(2026, 1, 5, 6, 0), datetime(2026, 1, 5, 14, 0),
                  activity_type="selvbetalt_fridag", status=ActivityStatus.approved)

    data = _employee_settlement_data(employee, period.start_date, period.end_date, db)

    day = _find_day(data, "2026-01-05")
    assert day["absence_type"] == "Selvbetalt fridag"
    assert day["total_hours"] == 0
    assert day["total_kr"] == 0


def test_employee_settlement_data_does_not_show_hours_for_loen_andet_sted_fra(db, employee):
    """'Løn andet sted fra' har ligesom Selvbetalt fridag ingen etableret
    betalingsregel – dagens række skal derfor forblive 0 kr."""
    from datetime import datetime
    from database.models import ActivityStatus
    from calculators.pay_period import get_or_create_period_for_date
    from routers.payroll_settlement_router import _employee_settlement_data
    from conftest import make_activity
    _setup_rates(db, employee, hourly=Decimal("150.00"))
    period = get_or_create_period_for_date(date(2026, 1, 1), db)
    make_activity(db, employee, datetime(2026, 1, 5, 6, 0), datetime(2026, 1, 5, 14, 0),
                  activity_type="loen_andet_sted_fra", status=ActivityStatus.approved)

    data = _employee_settlement_data(employee, period.start_date, period.end_date, db)

    day = _find_day(data, "2026-01-05")
    assert day["absence_type"] == "Løn andet sted fra"
    assert day["total_hours"] == 0
    assert day["total_kr"] == 0


def test_employee_settlement_data_does_not_show_hours_for_eksport(db, employee):
    """'Eksport' opfører sig præcis som 'Løn andet sted fra' – 0 kr."""
    from datetime import datetime
    from database.models import ActivityStatus
    from calculators.pay_period import get_or_create_period_for_date
    from routers.payroll_settlement_router import _employee_settlement_data
    from conftest import make_activity
    _setup_rates(db, employee, hourly=Decimal("150.00"))
    period = get_or_create_period_for_date(date(2026, 1, 1), db)
    make_activity(db, employee, datetime(2026, 1, 5, 6, 0), datetime(2026, 1, 5, 14, 0),
                  activity_type="eksport", status=ActivityStatus.approved)

    data = _employee_settlement_data(employee, period.start_date, period.end_date, db)

    day = _find_day(data, "2026-01-05")
    assert day["absence_type"] == "Eksport"
    assert day["total_hours"] == 0
    assert day["total_kr"] == 0

def test_employee_settlement_data_absence_kr_counts_toward_employee_total(db, employee):
    """Bekræftet beslutning 2026-08-25: fraværsbeløb (her sygdom) tæller nu MED
    i medarbejderens 'Total løn', oveni den almindelige arbejdstid."""
    from datetime import datetime
    from database.models import ActivityStatus
    from calculators.pay_period import get_or_create_period_for_date
    from routers.payroll_settlement_router import _employee_settlement_data
    from conftest import make_activity
    _setup_rates(db, employee, hourly=Decimal("150.00"))
    period = get_or_create_period_for_date(date(2026, 1, 1), db)
    make_activity(db, employee, datetime(2026, 1, 5, 6, 0), datetime(2026, 1, 5, 14, 0),
                  activity_type="sygdom", status=ActivityStatus.approved)
    make_activity(db, employee, datetime(2026, 1, 6, 6, 0), datetime(2026, 1, 6, 14, 0),
                  activity_type="normal", status=ActivityStatus.approved)

    data = _employee_settlement_data(employee, period.start_date, period.end_date, db)

    # Begge dage tæller nu med: 6/1 (normal, 8 arbejdstimer) + 5/1 (sygdom,
    # 8 * 150,00 kr) – bekræftet af bruger 2026-08-25 ("fravær skal ... tælle
    # med i totalen").
    assert data["total_kr"] == pytest.approx(8.0 * 150.00 + 8.0 * 150.00)


def test_employee_settlement_data_splits_shift_crossing_midnight_onto_both_days(db, employee):
    """En vagt der krydser midnat skal vise sine timer på de kalenderdage den
    reelt er arbejdet på – ikke lagt samlet på vagtens startdato. Bekræftet af
    bruger 2026-09-09 (Preben Thornfeldt-sagen: en manuelt oprettet vagt hen
    over midnat viste forkerte tal, fordi hele vagten lå på startdatoen)."""
    from datetime import datetime
    from database.models import ActivityStatus
    from calculators.pay_period import get_or_create_period_for_date
    from routers.payroll_settlement_router import _employee_settlement_data
    from conftest import make_activity
    _setup_rates(db, employee, hourly=Decimal("150.00"))
    period = get_or_create_period_for_date(date(2026, 1, 1), db)
    make_activity(db, employee, datetime(2026, 1, 5, 22, 0), datetime(2026, 1, 6, 8, 0),
                  status=ActivityStatus.approved)

    data = _employee_settlement_data(employee, period.start_date, period.end_date, db)

    day1 = _find_day(data, "2026-01-05")
    day2 = _find_day(data, "2026-01-06")
    assert day1["total_hours"] == pytest.approx(2.0)   # 22-24: øvrig overtid
    assert day1["ot_extra"] == pytest.approx(2.0)
    assert day1["normal"] == pytest.approx(0.0)   # ingen timer uden tillæg denne dag
    assert day1["total_kr"] == pytest.approx(2 * 150.0 + 2 * 100.0)
    assert day2["total_hours"] == pytest.approx(8.0)   # 00-05 øvrig, 05-06 før, 06-08 normal
    assert day2["ot_extra"] == pytest.approx(5.0)
    assert day2["ot_before"] == pytest.approx(1.0)
    assert day2["normal"] == pytest.approx(2.0)   # kun 06-08 er uden tillæg
    assert day2["total_kr"] == pytest.approx(8 * 150.0 + 1 * 50.0 + 5 * 100.0)
    # Periodetotalen er upåvirket af hvordan timerne fordeles på dagene.
    assert data["total_kr"] == pytest.approx(day1["total_kr"] + day2["total_kr"])


def test_employee_settlement_data_no_spurious_empty_row_on_split_arrival_day(db, employee):
    """Regressionsværn: dagen EFTER en vagt der krydser midnat får rigtige
    timer via by_date-opdelingen, men _calculate_employee tilføjer stadig sin
    egen tomme 'ingen aktivitet'-placeholder for den dato (ingen aktivitet
    STARTER der) – de to må ikke blive til to rækker (én rigtig + én tom) for
    samme dag. Fundet under verifikation 2026-09-09."""
    from datetime import datetime
    from database.models import ActivityStatus
    from calculators.pay_period import get_or_create_period_for_date
    from routers.payroll_settlement_router import _employee_settlement_data
    from conftest import make_activity
    _setup_rates(db, employee, hourly=Decimal("150.00"))
    period = get_or_create_period_for_date(date(2026, 1, 1), db)
    make_activity(db, employee, datetime(2026, 1, 5, 22, 0), datetime(2026, 1, 6, 8, 0),
                  status=ActivityStatus.approved)

    data = _employee_settlement_data(employee, period.start_date, period.end_date, db)

    matching = [d for d in data["days"] if d["date"] == "2026-01-06"]
    assert len(matching) == 1
    assert matching[0]["total_hours"] == pytest.approx(8.0)


def test_employee_settlement_data_collapses_multiple_activities_same_day_into_one_row(db, employee):
    """Flere godkendte aktiviteter samme dag (fx en vagt splittet manuelt af
    brugeren i flere sammenhængende aktiviteter) skal vises som ÉN samlet
    række pr. dag i Lønafregning, ikke én række pr. aktivitet – bekræftet af
    bruger 2026-09-09."""
    from datetime import datetime
    from database.models import ActivityStatus
    from calculators.pay_period import get_or_create_period_for_date
    from routers.payroll_settlement_router import _employee_settlement_data
    from conftest import make_activity
    _setup_rates(db, employee, hourly=Decimal("150.00"))
    period = get_or_create_period_for_date(date(2026, 1, 1), db)
    make_activity(db, employee, datetime(2026, 1, 5, 6, 0), datetime(2026, 1, 5, 10, 0),
                  status=ActivityStatus.approved)
    make_activity(db, employee, datetime(2026, 1, 5, 10, 0), datetime(2026, 1, 5, 14, 0),
                  status=ActivityStatus.approved)

    data = _employee_settlement_data(employee, period.start_date, period.end_date, db)

    matching = [d for d in data["days"] if d["date"] == "2026-01-05"]
    assert len(matching) == 1
    day = matching[0]
    assert day["total_hours"] == pytest.approx(8.0)
    assert day["total_kr"] == pytest.approx(8.0 * 150.0)


def test_employee_settlement_data_splits_same_day_into_rows_by_vehicle_number(db, employee):
    """Den ENESTE grund til at en dag skal vises som flere rækker er hvis
    medarbejderen har kørt flere vagne samme dag – bekræftet af bruger
    2026-09-09 ('den eneste årsag til, at en dag skal splittes op i flere
    linjer, er hvis medarbejderen kører flere vagter med forskelligt
    vognnummer'). Samme vognnummer to gange samme dag skal stadig give ÉN
    række (se test_..._collapses_multiple_activities_same_day_into_one_row)."""
    from datetime import datetime
    from database.models import ActivityStatus
    from calculators.pay_period import get_or_create_period_for_date
    from routers.payroll_settlement_router import _employee_settlement_data
    from conftest import make_activity
    _setup_rates(db, employee, hourly=Decimal("150.00"))
    period = get_or_create_period_for_date(date(2026, 1, 1), db)
    act1 = make_activity(db, employee, datetime(2026, 1, 5, 6, 0), datetime(2026, 1, 5, 10, 0),
                         status=ActivityStatus.approved)
    act1.vehicle_number = "1111"
    act2 = make_activity(db, employee, datetime(2026, 1, 5, 10, 0), datetime(2026, 1, 5, 14, 0),
                         status=ActivityStatus.approved)
    act2.vehicle_number = "2222"
    db.commit()

    data = _employee_settlement_data(employee, period.start_date, period.end_date, db)

    matching = sorted(
        (d for d in data["days"] if d["date"] == "2026-01-05"),
        key=lambda d: d["vehicle_number"],
    )
    assert len(matching) == 2
    assert matching[0]["vehicle_number"] == "1111"
    assert matching[0]["total_hours"] == pytest.approx(4.0)
    assert matching[0]["total_kr"] == pytest.approx(4.0 * 150.0)
    assert matching[1]["vehicle_number"] == "2222"
    assert matching[1]["total_hours"] == pytest.approx(4.0)
    assert matching[1]["total_kr"] == pytest.approx(4.0 * 150.0)
    # Periodetotalen er upåvirket af opdelingen i to rækker.
    assert data["total_kr"] == pytest.approx(8.0 * 150.0)


def test_page_totals_aggregates_across_employees():
    from routers.payroll_settlement_router import _page_totals
    from calculators.overtime import OT_BEFORE_KEY, OT_13_KEY, OT_EXTRA_KEY
    employees_data = [
        {"normal_hours": 74.0, "hourly_rate": 150.0, "springer_kr": 0.0,
         "ot_before_hours": 1.0, "ot_13_hours": 2.0, "ot_extra_hours": 0.0,
         "ot_rates": {OT_BEFORE_KEY: 50.0, OT_13_KEY: 75.0, OT_EXTRA_KEY: 100.0},
         "salt_kr": 0.0, "total_kr": 11250.0,
         "overnight_count": 2, "overnight_kr": 190.0,
         "dob_overnight_count": 0, "dob_overnight_kr": 0.0,
         "days": [{"absence_type": "Sygdom", "absence_kr": 1200.0}]},
        {"normal_hours": 70.0, "hourly_rate": 160.0, "springer_kr": 1600.0,
         "ot_before_hours": 0.0, "ot_13_hours": 0.0, "ot_extra_hours": 3.0,
         "ot_rates": {OT_BEFORE_KEY: 50.0, OT_13_KEY: 75.0, OT_EXTRA_KEY: 100.0},
         "salt_kr": 200.0, "total_kr": 11500.0,
         "overnight_count": 1, "overnight_kr": 95.0,
         "dob_overnight_count": 1, "dob_overnight_kr": 597.0,
         "days": [{"absence_type": "Ferie", "absence_kr": 800.0},
                   {"absence_type": "Skole/kursus", "absence_kr": 300.0},
                   {"absence_type": "Afspadsering", "absence_kr": 400.0},
                   {"absence_type": "Barsel", "absence_kr": 999.0},
                   {"absence_type": "§56 syg", "absence_kr": 111.0},
                   {"absence_type": "Barn 1.sygedag", "absence_kr": 222.0},
                   {"absence_type": "Barn 1.sygedag u. 8 uger", "absence_kr": 333.0},
                   {"absence_type": "Graviditetsbetinget sygdom", "absence_kr": 444.0},
                   {"absence_type": "Feriefri", "absence_kr": 555.0},
                   {"absence_type": "Sygdom u. 8 uger", "absence_kr": 0.0},
                   {"absence_type": None, "absence_kr": None}]},
    ]
    totals = _page_totals(employees_data)
    assert totals["grundtimeloen_incl_tillaeg_kr"] == pytest.approx(74.0 * 150.0 + 70.0 * 160.0 + 1600.0)
    assert totals["ot_before_kr"] == pytest.approx(1.0 * 50.0)
    assert totals["ot_13_kr"] == pytest.approx(2.0 * 75.0)
    assert totals["ot_extra_kr"] == pytest.approx(3.0 * 100.0)
    assert totals["salt_kr"] == pytest.approx(200.0)
    assert totals["total_kr"] == pytest.approx(11250.0 + 11500.0)
    # "Total uden fravær" = grundtimeløn t.o.m. øvrig overtid – IKKE salt eller fravær.
    expected_excl_absence = (74.0 * 150.0 + 70.0 * 160.0 + 1600.0) + 1.0 * 50.0 + 2.0 * 75.0 + 3.0 * 100.0
    assert totals["total_excl_absence_kr"] == pytest.approx(expected_excl_absence)
    assert totals["sygdom_kr"] == pytest.approx(1200.0)
    assert totals["ferie_kr"] == pytest.approx(800.0)
    assert totals["skole_kursus_kr"] == pytest.approx(300.0)
    assert totals["afspadsering_kr"] == pytest.approx(400.0)
    assert totals["barsel_kr"] == pytest.approx(999.0)
    assert totals["paragraf_56_syg_kr"] == pytest.approx(111.0)
    assert totals["barn_1sygedag_kr"] == pytest.approx(222.0)
    assert totals["barn_1sygedag_u_8_uger_kr"] == pytest.approx(333.0)
    assert totals["graviditetsbetinget_sygdom_kr"] == pytest.approx(444.0)
    assert totals["feriefri_kr"] == pytest.approx(555.0)
    assert totals["sygdom_u_8_uger_kr"] == pytest.approx(0.0)
    assert totals["overnight_count"] == 3
    assert totals["overnight_kr"] == pytest.approx(190.0 + 95.0)
    assert totals["dob_overnight_count"] == 1
    assert totals["dob_overnight_kr"] == pytest.approx(597.0)


def test_payroll_settlement_preview_defaults_to_current_period(db, employee):
    from datetime import datetime, timedelta
    from database.models import ActivityStatus
    from calculators.pay_period import get_or_create_period_for_date
    from routers.payroll_settlement_router import payroll_settlement_preview
    from conftest import make_activity
    _setup_rates(db, employee, hourly=Decimal("150.00"))
    _assign_visible_dispatcher_group(db, employee)
    period = get_or_create_period_for_date(date.today(), db)
    activity_start = datetime.combine(period.start_date, datetime.min.time()) + timedelta(hours=6)
    make_activity(db, employee, activity_start, activity_start + timedelta(hours=8),
                  status=ActivityStatus.approved)

    result = payroll_settlement_preview(current_user=_dummy_user(), db=db)

    assert "page_totals" in result
    assert len(result["employees"]) == 1
    assert result["employees"][0]["employee_number"] == employee.employee_number


def test_payroll_settlement_preview_excludes_employees_without_activity_in_period(db, employee):
    """Kun medarbejdere med data (mindst én godkendt aktivitet) for perioden
    skal vises – bekræftet af bruger 2026-09-03."""
    from routers.payroll_settlement_router import payroll_settlement_preview
    _setup_rates(db, employee, hourly=Decimal("150.00"))
    _assign_visible_dispatcher_group(db, employee)

    result = payroll_settlement_preview(current_user=_dummy_user(), db=db)

    assert result["employees"] == []


def test_payroll_settlement_preview_follows_explicit_period_start(db, employee):
    from datetime import datetime
    from database.models import ActivityStatus
    from calculators.pay_period import get_or_create_period_for_date
    from routers.payroll_settlement_router import payroll_settlement_preview
    from conftest import make_activity
    _setup_rates(db, employee, hourly=Decimal("150.00"))
    _assign_visible_dispatcher_group(db, employee)
    past_period = get_or_create_period_for_date(date(2026, 1, 1), db)
    make_activity(db, employee, datetime(2026, 1, 5, 6, 0), datetime(2026, 1, 5, 14, 0),
                  status=ActivityStatus.approved)

    result = payroll_settlement_preview(period_start=past_period.start_date.isoformat(),
                                         current_user=_dummy_user(), db=db)

    assert result["period_start"] == past_period.start_date.isoformat()
    assert result["employees"][0]["normal_hours"] == pytest.approx(8.0)


def test_payroll_settlement_preview_uses_free_date_range(db, employee):
    """Frit Fra/Til-interval (som i Fraværsoversigt) har forrang og bruges
    råt – bekræftet af bruger 2026-09-04."""
    from datetime import datetime
    from database.models import ActivityStatus
    from routers.payroll_settlement_router import payroll_settlement_preview
    from conftest import make_activity
    _setup_rates(db, employee, hourly=Decimal("150.00"))
    _assign_visible_dispatcher_group(db, employee)
    make_activity(db, employee, datetime(2026, 1, 5, 6, 0), datetime(2026, 1, 5, 14, 0),
                  status=ActivityStatus.approved)

    result = payroll_settlement_preview(date_from="2026-01-03", date_to="2026-01-10",
                                         current_user=_dummy_user(), db=db)

    assert result["period_start"] == "2026-01-03"
    assert result["period_end"] == "2026-01-10"
    assert len(result["employees"][0]["days"]) == 8  # 3.-10. januar inkl.


def test_payroll_settlement_preview_period_status_is_none_for_non_matching_range(db, employee):
    """Låse-status vises KUN når intervallet matcher en hel lønperiode
    præcist – ellers None, selvom intervallet overlapper en låst periode."""
    from calculators.pay_period import get_or_create_period_for_date
    from database.models import PayPeriodStatus
    from routers.payroll_settlement_router import payroll_settlement_preview
    _setup_rates(db, employee, hourly=Decimal("150.00"))
    _assign_visible_dispatcher_group(db, employee)
    period = get_or_create_period_for_date(date(2026, 1, 1), db)
    period.status = PayPeriodStatus.closed
    db.commit()

    result = payroll_settlement_preview(date_from="2026-01-02", date_to="2026-01-09",
                                         current_user=_dummy_user(), db=db)

    assert result["period_status"] is None


def test_payroll_settlement_preview_period_status_matches_exact_period(db, employee):
    from calculators.pay_period import get_or_create_period_for_date
    from database.models import PayPeriodStatus
    from routers.payroll_settlement_router import payroll_settlement_preview
    _setup_rates(db, employee, hourly=Decimal("150.00"))
    _assign_visible_dispatcher_group(db, employee)
    period = get_or_create_period_for_date(date(2026, 1, 1), db)
    period.status = PayPeriodStatus.closed
    db.commit()

    result = payroll_settlement_preview(date_from=period.start_date.isoformat(),
                                         date_to=period.end_date.isoformat(),
                                         current_user=_dummy_user(), db=db)

    assert result["period_status"] == "closed"


def test_payroll_settlement_preview_rejects_partial_date_range(db, employee):
    from fastapi import HTTPException
    from routers.payroll_settlement_router import payroll_settlement_preview
    _setup_rates(db, employee, hourly=Decimal("150.00"))
    _assign_visible_dispatcher_group(db, employee)

    with pytest.raises(HTTPException) as exc:
        payroll_settlement_preview(date_from="2026-01-03", current_user=_dummy_user(), db=db)
    assert exc.value.status_code == 400


def test_export_settlement_csv_allows_free_range_that_overlaps_open_period_for_non_admin(db, employee):
    """Et frit interval der IKKE matcher en hel lønperiode præcist er altid
    eksporterbart, også for ikke-admin, selvom det overlapper en åben periode
    – bekræftet af bruger 2026-09-04 ('kun låst ved eksakt periodematch')."""
    from datetime import datetime
    from database.models import ActivityStatus, AppUser
    from calculators.pay_period import get_or_create_period_for_date
    from routers.payroll_settlement_router import export_settlement_csv, ExportSettlementCsvRequest
    from conftest import make_activity
    _setup_rates(db, employee, hourly=Decimal("150.00"))
    _assign_visible_dispatcher_group(db, employee)
    get_or_create_period_for_date(date(2026, 1, 1), db)  # forbliver 'open'
    make_activity(db, employee, datetime(2026, 1, 5, 6, 0), datetime(2026, 1, 5, 14, 0),
                  status=ActivityStatus.approved)
    non_admin = AppUser(name="Test", initials="LB1", role="lonbogholder", password_hash="x")

    result = export_settlement_csv(
        ExportSettlementCsvRequest(date_from="2026-01-02", date_to="2026-01-09"),
        current_user=non_admin, db=db)

    assert result.headers["content-disposition"].startswith("attachment; filename=lonafregning_")


def test_export_settlement_csv_uses_date_range_in_filename(db, employee):
    from routers.payroll_settlement_router import export_settlement_csv, ExportSettlementCsvRequest
    _setup_rates(db, employee, hourly=Decimal("150.00"))
    _assign_visible_dispatcher_group(db, employee)

    result = export_settlement_csv(
        ExportSettlementCsvRequest(date_from="2026-01-02", date_to="2026-01-09"),
        current_user=_dummy_user(), db=db)

    assert result.headers["content-disposition"] == "attachment; filename=lonafregning_2026-01-02_2026-01-09.csv"


def _make_employee(db, employee_number, group=None, hourly=Decimal("150.00")):
    """Opretter en ANDEN medarbejder end 'employee'-fixturen, med egen
    overenskomstsats, til brug i filtreringstests der kræver flere medarbejdere."""
    from database.models import Employee, AgreementKind, MasterAgreementType
    agreement_type = f"Overenskomst{employee_number}"
    emp = Employee(
        employee_number=employee_number,
        first_name="Anden",
        last_name="Chauffør",
        agreement_kind=AgreementKind.hourly_fixed,
        agreement_type=agreement_type,
        hire_date=date(2020, 1, 1),
        work_schedule={"even": [8, 8, 8, 8, 8, 0, 0], "odd": [8, 8, 8, 8, 8, 0, 0]},
    )
    if group is not None:
        emp.dispatcher_group = group
    db.add(emp)
    db.add(MasterAgreementType(name=agreement_type, hourly_rate=hourly))
    db.commit()
    db.refresh(emp)
    return emp


def _make_two_groups(db):
    from database.models import DispatcherGroup
    group_a = DispatcherGroup(name="Gruppe A", visible_in_activity_overview=True)
    group_b = DispatcherGroup(name="Gruppe B", visible_in_activity_overview=True)
    db.add_all([group_a, group_b])
    db.commit()
    db.refresh(group_a)
    db.refresh(group_b)
    return group_a, group_b


def test_active_employees_filters_by_dispatcher_group_id(db, employee):
    """Filteret på lønafregningssidens toolbar (Alle medarbejdere / Disponentgruppe
    / Medarbejder) genbruger _active_employees() – bekræftet af bruger 2026-09-03."""
    from routers.payroll_router import _active_employees
    group_a, group_b = _make_two_groups(db)
    employee.dispatcher_group = group_a
    other = _make_employee(db, "2002", group=group_b)
    db.commit()

    result = _active_employees(db, dispatcher_group_id=group_a.id)

    assert [e.id for e in result] == [employee.id]


def test_payroll_settlement_preview_filters_by_dispatcher_group_id(db, employee):
    from datetime import datetime
    from database.models import ActivityStatus
    from calculators.pay_period import get_or_create_period_for_date
    from routers.payroll_settlement_router import payroll_settlement_preview
    from conftest import make_activity
    _setup_rates(db, employee, hourly=Decimal("150.00"))
    group_a, group_b = _make_two_groups(db)
    employee.dispatcher_group = group_a
    other = _make_employee(db, "2002", group=group_b)
    db.commit()
    period = get_or_create_period_for_date(date(2026, 1, 1), db)
    make_activity(db, employee, datetime(2026, 1, 5, 6, 0), datetime(2026, 1, 5, 14, 0),
                  status=ActivityStatus.approved)
    make_activity(db, other, datetime(2026, 1, 5, 6, 0), datetime(2026, 1, 5, 14, 0),
                  status=ActivityStatus.approved)

    result = payroll_settlement_preview(period_start=period.start_date.isoformat(),
                                         dispatcher_group_id=group_a.id,
                                         current_user=_dummy_user(), db=db)

    assert [e["employee_number"] for e in result["employees"]] == [employee.employee_number]


def test_payroll_settlement_preview_filters_by_employee_id(db, employee):
    from datetime import datetime
    from database.models import ActivityStatus
    from calculators.pay_period import get_or_create_period_for_date
    from routers.payroll_settlement_router import payroll_settlement_preview
    from conftest import make_activity
    _setup_rates(db, employee, hourly=Decimal("150.00"))
    group_a, group_b = _make_two_groups(db)
    employee.dispatcher_group = group_a
    other = _make_employee(db, "2002", group=group_b)
    db.commit()
    period = get_or_create_period_for_date(date(2026, 1, 1), db)
    make_activity(db, employee, datetime(2026, 1, 5, 6, 0), datetime(2026, 1, 5, 14, 0),
                  status=ActivityStatus.approved)
    make_activity(db, other, datetime(2026, 1, 5, 6, 0), datetime(2026, 1, 5, 14, 0),
                  status=ActivityStatus.approved)

    result = payroll_settlement_preview(period_start=period.start_date.isoformat(),
                                         employee_id=other.id,
                                         current_user=_dummy_user(), db=db)

    assert [e["employee_number"] for e in result["employees"]] == [other.employee_number]


def test_export_settlement_csv_filters_by_dispatcher_group_id(db, employee):
    from datetime import datetime
    from database.models import ActivityStatus
    from calculators.pay_period import get_or_create_period_for_date
    from routers.payroll_settlement_router import export_settlement_csv, ExportSettlementCsvRequest
    from conftest import make_activity
    _setup_rates(db, employee, hourly=Decimal("150.00"))
    group_a, group_b = _make_two_groups(db)
    employee.dispatcher_group = group_a
    other = _make_employee(db, "2002", group=group_b)
    db.commit()
    period = get_or_create_period_for_date(date(2026, 1, 1), db)
    make_activity(db, employee, datetime(2026, 1, 5, 6, 0), datetime(2026, 1, 5, 14, 0),
                  status=ActivityStatus.approved)
    make_activity(db, other, datetime(2026, 1, 5, 6, 0), datetime(2026, 1, 5, 14, 0),
                  status=ActivityStatus.approved)

    result = export_settlement_csv(
        ExportSettlementCsvRequest(period_start=period.start_date.isoformat(),
                                    dispatcher_group_id=group_a.id),
        current_user=_dummy_user(), db=db)

    content = result.body.decode("utf-8-sig")
    assert employee.employee_number in content
    assert other.employee_number not in content


def test_export_settlement_csv_filters_by_employee_id(db, employee):
    from datetime import datetime
    from database.models import ActivityStatus
    from calculators.pay_period import get_or_create_period_for_date
    from routers.payroll_settlement_router import export_settlement_csv, ExportSettlementCsvRequest
    from conftest import make_activity
    _setup_rates(db, employee, hourly=Decimal("150.00"))
    group_a, group_b = _make_two_groups(db)
    employee.dispatcher_group = group_a
    other = _make_employee(db, "2002", group=group_b)
    db.commit()
    period = get_or_create_period_for_date(date(2026, 1, 1), db)
    make_activity(db, employee, datetime(2026, 1, 5, 6, 0), datetime(2026, 1, 5, 14, 0),
                  status=ActivityStatus.approved)
    make_activity(db, other, datetime(2026, 1, 5, 6, 0), datetime(2026, 1, 5, 14, 0),
                  status=ActivityStatus.approved)

    result = export_settlement_csv(
        ExportSettlementCsvRequest(period_start=period.start_date.isoformat(),
                                    employee_id=other.id),
        current_user=_dummy_user(), db=db)

    content = result.body.decode("utf-8-sig")
    assert other.employee_number in content
    assert employee.employee_number not in content


def _dummy_user():
    from database.models import AppUser
    return AppUser(name="Test", initials="TST", role="admin", password_hash="x")


def _assign_visible_dispatcher_group(db, employee):
    """_active_employees() (payroll_router.py:669) udelukker medarbejdere uden
    mindst én disponentgruppe med visible_in_activity_overview=True — den delte
    'employee'-fixture i conftest.py har ingen grupper, så enhver test der
    rammer preview/export skal selv tildele én."""
    from database.models import DispatcherGroup
    group = DispatcherGroup(name="Testgruppe", visible_in_activity_overview=True)
    db.add(group)
    db.commit()
    db.refresh(group)
    employee.dispatcher_group = group
    db.commit()


def test_fmt_hm_converts_decimal_hours_to_hm():
    from routers.payroll_settlement_router import _fmt_hm
    assert _fmt_hm(7.5) == "7:30"
    assert _fmt_hm(0) == "0:00"
    assert _fmt_hm(1.0) == "1:00"


def test_fmt_decimal_comma_uses_danish_comma():
    from routers.payroll_settlement_router import _fmt_decimal_comma
    assert _fmt_decimal_comma(7.5) == "7,50"
    assert _fmt_decimal_comma(0) == "0,00"


def test_fmt_kr_da_uses_thousands_dot_and_comma_decimal():
    from routers.payroll_settlement_router import _fmt_kr_da
    assert _fmt_kr_da(1234.5) == "1.234,50"
    assert _fmt_kr_da(0) == "0,00"


def test_export_settlement_csv_rejects_open_period_for_non_admin(db, employee):
    from fastapi import HTTPException
    from database.models import AppUser
    from routers.payroll_settlement_router import export_settlement_csv, ExportSettlementCsvRequest
    _setup_rates(db, employee, hourly=Decimal("150.00"))
    non_admin = AppUser(name="Test", initials="LB1", role="lonbogholder", password_hash="x")

    with pytest.raises(HTTPException) as exc:
        export_settlement_csv(ExportSettlementCsvRequest(),
                               current_user=non_admin, db=db)
    assert exc.value.status_code == 400


def test_export_settlement_csv_allows_admin_on_open_period(db, employee):
    from routers.payroll_settlement_router import export_settlement_csv, ExportSettlementCsvRequest
    _setup_rates(db, employee, hourly=Decimal("150.00"))
    _assign_visible_dispatcher_group(db, employee)

    result = export_settlement_csv(ExportSettlementCsvRequest(),
                                    current_user=_dummy_user(), db=db)

    assert result.headers["content-disposition"].startswith("attachment; filename=lonafregning_")


def test_export_settlement_csv_allows_non_admin_on_closed_period(db, employee):
    from database.models import AppUser
    from calculators.pay_period import get_or_create_period_for_date
    from database.models import PayPeriodStatus
    from routers.payroll_settlement_router import export_settlement_csv, ExportSettlementCsvRequest
    _setup_rates(db, employee, hourly=Decimal("150.00"))
    period = get_or_create_period_for_date(date.today(), db)
    period.status = PayPeriodStatus.closed
    db.commit()
    _assign_visible_dispatcher_group(db, employee)
    non_admin = AppUser(name="Test", initials="LB1", role="lonbogholder", password_hash="x")

    result = export_settlement_csv(ExportSettlementCsvRequest(),
                                    current_user=non_admin, db=db)

    assert result.headers["content-disposition"].startswith("attachment; filename=lonafregning_")


def test_export_settlement_csv_can_target_a_past_closed_period_while_today_is_open(db, employee):
    """Reproducerer den virkelige situation en bruger stødte på 2026-08-25: en
    tidligere periode blev låst (Kør løn), men 'i dag' er allerede rykket videre
    til en nyere, åben periode. Eksport skal stadig kunne ramme den gamle,
    låste periode ved at angive period_start eksplicit."""
    from database.models import AppUser, PayPeriodStatus
    from calculators.pay_period import get_or_create_period_for_date
    from routers.payroll_settlement_router import export_settlement_csv, ExportSettlementCsvRequest
    _setup_rates(db, employee, hourly=Decimal("150.00"))
    _assign_visible_dispatcher_group(db, employee)
    past_period = get_or_create_period_for_date(date(2026, 1, 1), db)
    past_period.status = PayPeriodStatus.closed
    get_or_create_period_for_date(date.today(), db)  # dagens periode forbliver 'open'
    db.commit()
    non_admin = AppUser(name="Test", initials="LB1", role="lonbogholder", password_hash="x")

    result = export_settlement_csv(
        ExportSettlementCsvRequest(period_start=past_period.start_date.isoformat()),
        current_user=non_admin, db=db)

    assert past_period.start_date.isoformat() in result.headers["content-disposition"]
    assert result.headers["content-disposition"].startswith("attachment; filename=lonafregning_")


def test_export_settlement_csv_content_has_lonnummer_column_and_all_14_days(db, employee):
    from datetime import datetime
    from database.models import ActivityStatus
    from calculators.pay_period import get_or_create_period_for_date
    from routers.payroll_settlement_router import export_settlement_csv, ExportSettlementCsvRequest
    from conftest import make_activity
    _setup_rates(db, employee, hourly=Decimal("150.00"))
    _assign_visible_dispatcher_group(db, employee)
    period = get_or_create_period_for_date(date(2026, 1, 1), db)
    make_activity(db, employee, datetime(2026, 1, 5, 6, 0), datetime(2026, 1, 5, 14, 0),
                  status=ActivityStatus.approved)

    result = export_settlement_csv(
        ExportSettlementCsvRequest(period_start=period.start_date.isoformat()),
        current_user=_dummy_user(), db=db)

    content = result.body.decode("utf-8-sig")
    lines = [l for l in content.splitlines() if l]
    header = lines[0].split(";")
    assert header == ["Dato", "Lønnummer", "Normal timer", "Overtid 1 time før",
                       "Overtid 1-3 timer efter", "Øvrig overtid", "Total tid",
                       "Total i kr.", "Vognnummer", "Beløb"]
    # 14 dagsrækker for den ene medarbejder – ingen "Total løn for"-række
    assert len(lines) == 1 + 14
    assert employee.employee_number in lines[1]


def test_export_settlement_csv_excludes_employees_without_activity_in_period(db, employee):
    """Kun medarbejdere med data (mindst én godkendt aktivitet) for den
    eksporterede periode skal med i CSV'en – bekræftet af bruger 2026-09-03."""
    from routers.payroll_settlement_router import export_settlement_csv, ExportSettlementCsvRequest
    _setup_rates(db, employee, hourly=Decimal("150.00"))
    _assign_visible_dispatcher_group(db, employee)

    result = export_settlement_csv(ExportSettlementCsvRequest(),
                                    current_user=_dummy_user(), db=db)

    content = result.body.decode("utf-8-sig")
    lines = [l for l in content.splitlines() if l]
    assert len(lines) == 1  # kun header – ingen medarbejderrækker


def test_export_settlement_csv_content_shows_sygdom_hours_and_beloeb(db, employee):
    from datetime import datetime
    from database.models import ActivityStatus
    from calculators.pay_period import get_or_create_period_for_date
    from routers.payroll_settlement_router import export_settlement_csv, ExportSettlementCsvRequest
    from conftest import make_activity
    _setup_rates(db, employee, hourly=Decimal("150.00"))
    _assign_visible_dispatcher_group(db, employee)
    period = get_or_create_period_for_date(date(2026, 1, 1), db)
    make_activity(db, employee, datetime(2026, 1, 5, 6, 0), datetime(2026, 1, 5, 14, 0),
                  activity_type="sygdom", status=ActivityStatus.approved)

    result = export_settlement_csv(
        ExportSettlementCsvRequest(period_start=period.start_date.isoformat()),
        current_user=_dummy_user(), db=db)

    content = result.body.decode("utf-8-sig")
    sygdom_line = next(l for l in content.splitlines() if l.startswith("05-01-2026"))
    cols = sygdom_line.split(";")
    # Dato;Lønnummer;Normal timer;OT-før;OT-1-3;Øvrig OT;Total tid;Total i kr.;Vognnummer;Beløb
    assert cols[2:6] == ["0:00", "0:00", "0:00", "0:00"]  # ingen normal-/overtidstimer på en sygedag
    assert cols[6] == "8,00"          # Total tid
    assert cols[7] == "1.200,00"      # Total i kr. (8t * 150,00 kr)
    assert cols[8] == "Sygdom"        # Vognnummer overskrevet af fraværstypen
    assert cols[9] == "1.200,00"      # Beløb


def test_export_settlement_csv_content_shows_skole_kursus_hours_and_beloeb(db, employee):
    from datetime import datetime
    from database.models import ActivityStatus
    from calculators.pay_period import get_or_create_period_for_date
    from routers.payroll_settlement_router import export_settlement_csv, ExportSettlementCsvRequest
    from conftest import make_activity
    _setup_rates(db, employee, hourly=Decimal("150.00"))
    _assign_visible_dispatcher_group(db, employee)
    period = get_or_create_period_for_date(date(2026, 1, 1), db)
    make_activity(db, employee, datetime(2026, 1, 5, 6, 0), datetime(2026, 1, 5, 14, 0),
                  activity_type="skole_kursus", status=ActivityStatus.approved)

    result = export_settlement_csv(
        ExportSettlementCsvRequest(period_start=period.start_date.isoformat()),
        current_user=_dummy_user(), db=db)

    content = result.body.decode("utf-8-sig")
    line = next(l for l in content.splitlines() if l.startswith("05-01-2026"))
    cols = line.split(";")
    assert cols[2:6] == ["0:00", "0:00", "0:00", "0:00"]
    assert cols[6] == "8,00"          # Total tid
    assert cols[7] == "1.200,00"      # Total i kr. (8t * 150,00 kr)
    assert cols[8] == "Skole/kursus"  # Vognnummer overskrevet af fraværstypen
    assert cols[9] == "1.200,00"      # Beløb


@pytest.mark.parametrize("activity_type, label", [
    ("ferie", "Ferie"),
    ("afspadsering", "Afspadsering"),
])
def test_export_settlement_csv_zeroes_ferie_and_afspadsering_but_keeps_vognnummer(
    db, employee, activity_type, label,
):
    """Bekræftet af bruger 2026-08-26: Ferie og Afspadsering skal ALTID vise
    0 i CSV'en (uanset fuldlønnet/timelønnet), men Vognnummer viser stadig
    fraværstypens navn. Siden selv (test_employee_settlement_data_*) er upåvirket."""
    from datetime import datetime
    from database.models import ActivityStatus
    from calculators.pay_period import get_or_create_period_for_date
    from routers.payroll_settlement_router import export_settlement_csv, ExportSettlementCsvRequest
    from conftest import make_activity
    _setup_rates(db, employee, hourly=Decimal("150.00"))
    _assign_visible_dispatcher_group(db, employee)
    period = get_or_create_period_for_date(date(2026, 1, 1), db)
    make_activity(db, employee, datetime(2026, 1, 5, 6, 0), datetime(2026, 1, 5, 14, 0),
                  activity_type=activity_type, status=ActivityStatus.approved)

    result = export_settlement_csv(
        ExportSettlementCsvRequest(period_start=period.start_date.isoformat()),
        current_user=_dummy_user(), db=db)

    content = result.body.decode("utf-8-sig")
    lines = [l for l in content.splitlines() if l]
    line = next(l for l in lines if l.startswith("05-01-2026"))
    cols = line.split(";")
    assert cols[2:8] == ["0:00", "0:00", "0:00", "0:00", "0,00", "0,00"]
    assert cols[8] == label
    assert cols[9] == "0,00"


def test_export_settlement_csv_zeroes_feriefri_for_timeloennet_employee(db, employee):
    from datetime import datetime
    from database.models import ActivityStatus
    from calculators.pay_period import get_or_create_period_for_date
    from routers.payroll_settlement_router import export_settlement_csv, ExportSettlementCsvRequest
    from conftest import make_activity
    _setup_rates(db, employee, hourly=Decimal("150.00"))
    _assign_visible_dispatcher_group(db, employee)
    employee.fuldloennet = False
    db.commit()
    period = get_or_create_period_for_date(date(2026, 1, 1), db)
    make_activity(db, employee, datetime(2026, 1, 5, 6, 0), datetime(2026, 1, 5, 14, 0),
                  activity_type="feriefri", status=ActivityStatus.approved)

    result = export_settlement_csv(
        ExportSettlementCsvRequest(period_start=period.start_date.isoformat()),
        current_user=_dummy_user(), db=db)

    content = result.body.decode("utf-8-sig")
    lines = [l for l in content.splitlines() if l]
    line = next(l for l in lines if l.startswith("05-01-2026"))
    cols = line.split(";")
    assert cols[6:8] == ["0,00", "0,00"]
    assert cols[8] == "Feriefri"
    assert cols[9] == "0,00"


def test_export_settlement_csv_keeps_feriefri_value_for_fuldloennet_employee(db, employee):
    """employee-fixturen er fuldlønnet som standard (fuldloennet defaulter til True) –
    for fuldlønnede medarbejdere skal Feriefri IKKE zeroes i CSV'en."""
    from datetime import datetime
    from database.models import ActivityStatus
    from calculators.pay_period import get_or_create_period_for_date
    from routers.payroll_settlement_router import export_settlement_csv, ExportSettlementCsvRequest
    from conftest import make_activity
    _setup_rates(db, employee, hourly=Decimal("150.00"))
    _assign_visible_dispatcher_group(db, employee)
    assert employee.fuldloennet is True
    period = get_or_create_period_for_date(date(2026, 1, 1), db)
    make_activity(db, employee, datetime(2026, 1, 5, 6, 0), datetime(2026, 1, 5, 14, 0),
                  activity_type="feriefri", status=ActivityStatus.approved)

    result = export_settlement_csv(
        ExportSettlementCsvRequest(period_start=period.start_date.isoformat()),
        current_user=_dummy_user(), db=db)

    content = result.body.decode("utf-8-sig")
    lines = [l for l in content.splitlines() if l]
    line = next(l for l in lines if l.startswith("05-01-2026"))
    cols = line.split(";")
    assert cols[6:8] == ["8,00", "1.200,00"]
    assert cols[9] == "1.200,00"


def test_export_settlement_csv_ferie_zeroing_does_not_affect_page_preview(db, employee):
    """Regressionsværn: CSV-specifik zeroing (_csv_days) må aldrig lække ind i
    _employee_settlement_data(), som bruges af selve siden."""
    from datetime import datetime
    from database.models import ActivityStatus
    from calculators.pay_period import get_or_create_period_for_date
    from routers.payroll_settlement_router import _employee_settlement_data
    from conftest import make_activity
    _setup_rates(db, employee, hourly=Decimal("150.00"))
    period = get_or_create_period_for_date(date(2026, 1, 1), db)
    make_activity(db, employee, datetime(2026, 1, 5, 6, 0), datetime(2026, 1, 5, 14, 0),
                  activity_type="ferie", status=ActivityStatus.approved)

    data = _employee_settlement_data(employee, period.start_date, period.end_date, db)

    day = _find_day(data, "2026-01-05")
    assert day["total_hours"] == pytest.approx(8.0)
    assert day["total_kr"] == pytest.approx(8.0 * 150.00)
    assert data["total_kr"] == pytest.approx(8.0 * 150.00)


def test_export_settlement_csv_ferie_day_zeroed_normal_day_unaffected(db, employee):
    """En medarbejder med både en normal arbejdsdag og en feriedag: feriedagens
    række skal være 0, mens den normale arbejdsdags række er upåvirket."""
    from datetime import datetime
    from database.models import ActivityStatus
    from calculators.pay_period import get_or_create_period_for_date
    from routers.payroll_settlement_router import export_settlement_csv, ExportSettlementCsvRequest
    from conftest import make_activity
    _setup_rates(db, employee, hourly=Decimal("150.00"))
    _assign_visible_dispatcher_group(db, employee)
    period = get_or_create_period_for_date(date(2026, 1, 1), db)
    make_activity(db, employee, datetime(2026, 1, 5, 6, 0), datetime(2026, 1, 5, 14, 0),
                  activity_type="ferie", status=ActivityStatus.approved)
    make_activity(db, employee, datetime(2026, 1, 6, 6, 0), datetime(2026, 1, 6, 14, 0),
                  activity_type="normal", status=ActivityStatus.approved)

    result = export_settlement_csv(
        ExportSettlementCsvRequest(period_start=period.start_date.isoformat()),
        current_user=_dummy_user(), db=db)

    content = result.body.decode("utf-8-sig")
    lines = [l for l in content.splitlines() if l]
    ferie_cols = next(l for l in lines if l.startswith("05-01-2026")).split(";")
    normal_cols = next(l for l in lines if l.startswith("06-01-2026")).split(";")
    assert ferie_cols[6:10] == ["0,00", "0,00", "Ferie", "0,00"]
    assert normal_cols[2] == "8:00"       # normal timer, upåvirket
    assert normal_cols[7] == "1.200,00"   # 8t * 150,00 kr, upåvirket
    assert not any(l.startswith("Total løn for") for l in lines)


def test_export_settlement_csv_is_written_with_utf8_bom_for_excel(db, employee):
    """Excel fejltolker æ/ø/å som ANSI, hvis filen mangler en UTF-8 BOM –
    bekræftet af bruger 2026-08-26 ('Lønnummer' viste forkert i Excel)."""
    from routers.payroll_settlement_router import export_settlement_csv, ExportSettlementCsvRequest
    _setup_rates(db, employee, hourly=Decimal("150.00"))
    _assign_visible_dispatcher_group(db, employee)

    result = export_settlement_csv(ExportSettlementCsvRequest(),
                                    current_user=_dummy_user(), db=db)

    raw = result.body
    assert raw.startswith(b"\xef\xbb\xbf")
    header = raw.decode("utf-8-sig").splitlines()[0]
    assert header == "Dato;Lønnummer;Normal timer;Overtid 1 time før;Overtid 1-3 timer efter;Øvrig overtid;Total tid;Total i kr.;Vognnummer;Beløb"
