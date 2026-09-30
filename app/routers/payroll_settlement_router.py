"""
Lønafregning:
- /api/payroll-settlement/preview           – JSON til Lønafregning-siden (periodetotaler
                                              + pr. medarbejder headline + 14-dages tabel)
- /api/payroll-settlement/export-csv        – CSV med Dato/Lønnummer/timer/kr/vognnummer pr.
                                              dag pr. medarbejder; kræver låst periode (admin altid)
"""
import csv
import io
import logging
from datetime import date
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth import log_action, require_permission
from database.models import AppUser, PayPeriod, PayPeriodStatus
from database.session import get_db

from calculators.overtime import OT_13_KEY, OT_BEFORE_KEY, OT_EXTRA_KEY
from calculators.pay_period import get_or_create_period_for_date
from calculators.rates_loader import get_active_supplement_for_period, load_agreement_types_from_db

from routers.payroll_router import _active_employees, _calculate_employee

router = APIRouter(prefix="/api/payroll-settlement", tags=["payroll-settlement"])

_view_access = require_permission("payroll_settlement_view")
_export_access = require_permission("payroll_settlement_export")


def _display_day(day: dict) -> dict:
    """Klargør én dag til visning/CSV i Lønafregning: folder søgnehelligdags-
    tillæg ind i OT13/OT-extra (samme konvention som Lønkørsel-visningen), og
    viser fraværsdages (sygdom/§56 syg/sygdom u. 8 uger/barn 1.sygedag/
    graviditetsbetinget sygdom/barsel/skole-kursus/ferie/afspadsering) egne
    timer+beløb i 'Total tid'/'Total i kr.' for netop DEN dag."""
    result = {**day, "ot_13": day["ot_13"] + day.get("sh_kode8", 0),
              "ot_extra": day["ot_extra"] + day.get("sh_kode9", 0)}
    if day.get("absence_hours") is not None:
        result["total_hours"] = day["absence_hours"]
        result["total_kr"] = day["absence_kr"]
    return result


def _expand_day(day: dict) -> list:
    """Udfolder én aktivitets dags-indgang i ét stykke pr. kalenderdag den
    reelt strækker sig over. En vagt der krydser midnat får sine timer fordelt
    via 'by_date' (sat af _calculate_employee) i stedet for at ligge samlet på
    vagtens startdato – bekræftet af bruger 2026-09-09 ('timerne skal ligge på
    de dage, hvor de afholdes'). Fraværs-/nul-rækker har intet 'by_date' og
    udfoldes derfor uændret.

    Er vagten kørt i flere biler, udfoldes den i stedet via 'by_vehicle' –
    ét stykke pr. (kalenderdag, bil) med bilens egne tidsrum (bekræftet af
    bruger 2026-09-30)."""
    parts = [(piece["date"], piece) for piece in day.get("by_vehicle") or []]
    if not parts:
        parts = list((day.get("by_date") or {}).items())
    if not parts:
        return [day]
    pieces = []
    for i, (date_str, part) in enumerate(parts):
        piece = {**day, "date": date_str, **part}
        if i > 0:
            # Overnatnings-markøren hører til vagtens FØRSTE dag – ikke de
            # øvrige stykker den splittes i her.
            piece["overnight"] = 0
            piece["dob_overnight"] = 0
        pieces.append(piece)
    return pieces


_AGGREGATE_NUMERIC_KEYS = ("normal", "ot_before", "ot_13", "ot_extra", "total_hours", "total_kr")


def _aggregate_days(days: list) -> list:
    """Slår Lønafregningens dags-indgange sammen til én række pr. kalenderdag
    OG vognnummer. En dag kan bestå af flere godkendte aktiviteter (fx en vagt
    splittet manuelt af brugeren, eller en nattevagt der krydser midnat og nu
    er fordelt via _expand_day) – de samles i én række, MEDMINDRE de reelt
    dækker forskellige vogne, for så skal dagen vise én række pr. vognnummer
    (bekræftet af bruger 2026-09-09: "den eneste årsag til at en dag skal
    splittes op i flere linjer, er hvis medarbejderen kører flere vagter med
    forskelligt vognnummer")."""
    buckets: dict = {}
    order: list = []
    for day in days:
        for piece in _expand_day(_display_day(day)):
            date_str = piece["date"]
            vehicle_number = piece.get("vehicle_number") or None
            key = (date_str, vehicle_number)
            if key not in buckets:
                buckets[key] = {
                    "date": date_str,
                    "vehicle_number": vehicle_number,
                    **{k: 0.0 for k in _AGGREGATE_NUMERIC_KEYS},
                    "overnight": 0, "dob_overnight": 0,
                    "absence_kr": None, "absence_hours": None,
                    "_absence_types": [],
                    "vehicle_times": [],
                }
                order.append(key)
            bucket = buckets[key]
            for numeric_key in _AGGREGATE_NUMERIC_KEYS:
                bucket[numeric_key] = round(bucket[numeric_key] + (piece.get(numeric_key) or 0), 2)
            bucket["overnight"] = 1 if (bucket["overnight"] or piece.get("overnight")) else 0
            bucket["dob_overnight"] = 1 if (bucket["dob_overnight"] or piece.get("dob_overnight")) else 0
            if piece.get("absence_kr") is not None:
                bucket["absence_kr"] = round((bucket["absence_kr"] or 0) + piece["absence_kr"], 2)
                bucket["absence_hours"] = round(
                    (bucket["absence_hours"] or 0) + (piece.get("absence_hours") or 0), 2)
            for vehicle_time in piece.get("vehicle_times") or []:
                if vehicle_time not in bucket["vehicle_times"]:
                    bucket["vehicle_times"].append(vehicle_time)
            absence_type = piece.get("absence_type")
            if absence_type and absence_type not in bucket["_absence_types"]:
                bucket["_absence_types"].append(absence_type)

    # _calculate_employee tilføjer en tom "ingen aktivitet"-placeholder-række
    # for enhver dato ingen aktivitet STARTER på – men en vagt der krydser
    # midnat kan nu (via _expand_day) lægge REELLE timer på netop den dato
    # (døgnet efter vagten startede). I så fald er placeholderen overflødig
    # og skal ikke vises som sin egen tomme række ved siden af de rigtige tal.
    dates_with_real_data = {
        key[0] for key, bucket in buckets.items()
        if bucket["vehicle_number"] is not None or bucket["total_hours"] or bucket["total_kr"]
        or bucket["_absence_types"] or bucket["overnight"] or bucket["dob_overnight"]
    }

    result = []
    for key in order:
        date_str, vehicle_number = key
        bucket = buckets[key]
        is_empty_placeholder = (
            vehicle_number is None and not bucket["total_hours"] and not bucket["total_kr"]
            and not bucket["_absence_types"] and not bucket["overnight"] and not bucket["dob_overnight"]
        )
        if is_empty_placeholder and date_str in dates_with_real_data:
            continue
        bucket["absence_type"] = ", ".join(bucket.pop("_absence_types")) or None
        # "Normal timer" skal kun være timer der IKKE udløser tillæg – "normal"
        # er her stadig ALLE arbejdede timer (tillæggene er additive, jf.
        # calculators/overtime.py), så tillægstimerne trækkes fra til visning,
        # ligesom Prøvekørsel-excel'en allerede gør (payroll_router.py). Total
        # tid/Total kr. er upåvirket. Bekræftet af bruger 2026-09-09.
        # max(0, …): tillægstimerne er hver især afrundet til 2 decimaler, så en
        # kort bil-linje med fx 1 min OT 1-3 (0,0167 -> 0,02) ellers kunne give
        # -0,01 normaltimer (set 2026-09-30, Knudsen 24-08, 2. bil).
        bucket["normal"] = max(0.0, round(
            bucket["normal"] - bucket["ot_before"] - bucket["ot_13"] - bucket["ot_extra"], 2,
        ) + 0.0)
        result.append(bucket)
    return result


def settlement_total_kr(calc: dict, days: Optional[list] = None) -> Decimal:
    """Medarbejderens samlede løn for perioden, som vist i Lønafregning – og (siden
    2026-09-30) også som 'I alt' i Lønkørsel-fanen, så de to altid stemmer.

    = total_kr fra _calculate_employee (normaltid, overtid, SH-tillæg, salt,
    SH-betaling kode 4/63) + springertillæg + overnatning + DOB-overnatning + alle
    fraværstyper med et beregnet beløb (sygdom, §56 syg, sygdom u. 8 uger, barn
    1.sygedag, graviditetsbetinget sygdom, barsel, skole/kursus, feriefri, ferie,
    afspadsering – bekræftet af bruger 2026-08-25: "fravær skal ... tælle med i
    totalen"). Overnatning/DOB tilføjet 2026-09-21."""
    if days is None:
        days = _aggregate_days(calc["days"])
    springer_kr = (
        Decimal(str(calc["normal_hours"])) * Decimal(str(calc["springer_rate"]))
        if calc["springer_enabled"] else Decimal("0")
    )
    absence_kr_total = sum(
        (Decimal(str(d["absence_kr"])) for d in days if d.get("absence_kr") is not None),
        Decimal("0"),
    )
    return (
        Decimal(str(calc["total_kr"])) + springer_kr + absence_kr_total
        + Decimal(str(calc["overnight_kr"])) + Decimal(str(calc["dob_overnight_kr"]))
    )


def _employee_settlement_data(emp, start: date, end: date, db: Session) -> dict:
    """Headline-info (satser vist separat) + periodetotal for én medarbejder,
    oven på den fælles _calculate_employee()-beregning (samme datakilde som Lønkørsel)."""
    calc = _calculate_employee(emp, start, end, db)

    agreement_rate = load_agreement_types_from_db(db).get(emp.agreement_type, Decimal("0"))
    supplement = get_active_supplement_for_period(db, emp.id, start, end)
    personal_supplement_rate = supplement.value if supplement else Decimal("0")

    springer_kr = (
        Decimal(str(calc["normal_hours"])) * Decimal(str(calc["springer_rate"]))
        if calc["springer_enabled"] else Decimal("0")
    )
    overnight_kr = Decimal(str(calc["overnight_kr"]))
    dob_overnight_kr = Decimal(str(calc["dob_overnight_kr"]))

    days = _aggregate_days(calc["days"])
    total_kr_with_extras = settlement_total_kr(calc, days)

    return {
        "employee_id": calc["employee_id"],
        "employee_number": calc["employee_number"],
        "employee_name": calc["employee_name"],
        "agreement_type": calc["agreement_type"],
        "agreement_rate": float(agreement_rate),
        "personal_supplement_rate": float(personal_supplement_rate),
        "springer_enabled": calc["springer_enabled"],
        "springer_rate": calc["springer_rate"],
        "springer_kr": float(springer_kr),
        "overnight_count": calc["overnight_count"],
        "overnight_rate": calc["overnight_rate"],
        "overnight_kr": float(overnight_kr),
        "dob_overnight_count": calc["dob_overnight_count"],
        "dob_overnight_rate": calc["dob_overnight_rate"],
        "dob_overnight_kr": float(dob_overnight_kr),
        "normal_hours": calc["normal_hours"],
        "hourly_rate": calc["hourly_rate"],
        "ot_before_hours": calc["ot_before_hours"],
        "ot_13_hours": calc["ot_13_hours"] + calc["sh_kode8_hours"],
        "ot_extra_hours": calc["ot_extra_hours"] + calc["sh_kode9_hours"],
        "ot_rates": calc["ot_rates"],
        "salt_kr": calc["salt_kr"],
        "total_kr": float(total_kr_with_extras),
        "activity_count": calc["activity_count"],
        "days": days,
    }


# Fraværstyper der får deres egen navngivne linje i "Total sum for perioden" –
# én linje pr. fraværstype der reelt har et beregnet beløb (bekræftet af bruger
# 2026-08-25). Selvbetalt fridag, Barn 2-3.sygedag, Barsel u. løn og "Fri" har
# ingen etableret betalingsregel i systemet og får derfor ingen linje.
_PAGE_TOTAL_ABSENCE_LABELS = {
    "sygdom_kr": "Sygdom",
    "sygdom_u_8_uger_kr": "Sygdom u. 8 uger",
    "barn_1sygedag_kr": "Barn 1.sygedag",
    "barn_1sygedag_u_8_uger_kr": "Barn 1.sygedag u. 8 uger",
    "graviditetsbetinget_sygdom_kr": "Graviditetsbetinget sygdom",
    "paragraf_56_syg_kr": "§56 syg",
    "barsel_kr": "Barsel",
    "feriefri_kr": "Feriefri",
    "ferie_kr": "Ferie",
    "skole_kursus_kr": "Skole/kursus",
    "afspadsering_kr": "Afspadsering",
}


def _sum_absence_kr(employees_data: list, label: str) -> float:
    # "in ... .split(', ')" i stedet for et rent "==" fordi en aggregeret
    # dags-række (se _aggregate_days) kan vise flere komma-separerede
    # fraværstyper, hvis dagen reelt bestod af mere end én type.
    return sum(
        d["absence_kr"]
        for e in employees_data
        for d in e["days"]
        if d.get("absence_kr") is not None
        and label in (d.get("absence_type") or "").split(", ")
    )


def _page_totals(employees_data: list) -> dict:
    """Periodetotaler for hele siden – aggregeret på tværs af alle medarbejdere.
    Grundtimeløn/OT/salt-rækkerne er informative highlights af arbejdstid;
    Sygdom/Ferie/Skole-kursus/Afspadsering-rækkerne er de fraværstyper brugeren
    bad om at få vist for sig. total_kr er den fulde sum af alle medarbejderes
    total_kr (som nu inkluderer al fraværsbetaling, jf. _employee_settlement_data)."""
    grundtimeloen_kr = sum(e["normal_hours"] * e["hourly_rate"] + e["springer_kr"] for e in employees_data)
    ot_before_kr = sum(e["ot_before_hours"] * e["ot_rates"].get(OT_BEFORE_KEY, 0) for e in employees_data)
    ot_13_kr = sum(e["ot_13_hours"] * e["ot_rates"].get(OT_13_KEY, 0) for e in employees_data)
    ot_extra_kr = sum(e["ot_extra_hours"] * e["ot_rates"].get(OT_EXTRA_KEY, 0) for e in employees_data)
    salt_kr = sum(e["salt_kr"] for e in employees_data)
    overnight_count = sum(e["overnight_count"] for e in employees_data)
    overnight_kr = sum(e["overnight_kr"] for e in employees_data)
    dob_overnight_count = sum(e["dob_overnight_count"] for e in employees_data)
    dob_overnight_kr = sum(e["dob_overnight_kr"] for e in employees_data)
    total_kr = sum(e["total_kr"] for e in employees_data)
    # Delsum "Total uden fravær": grundtimeløn t.o.m. øvrig overtid – IKKE salt
    # eller overnatning (bruger var eksplicit: "fra grundtimeløn til og med
    # øvrig overtid") – overnatning vises i stedet som egen linje, samme
    # princip som Salttillæg, men tæller stadig med i total_kr (rettet 2026-09-21,
    # se _employee_settlement_data).
    total_excl_absence_kr = grundtimeloen_kr + ot_before_kr + ot_13_kr + ot_extra_kr
    result = {
        "grundtimeloen_incl_tillaeg_kr": round(grundtimeloen_kr, 2),
        "ot_before_kr": round(ot_before_kr, 2),
        "ot_13_kr": round(ot_13_kr, 2),
        "ot_extra_kr": round(ot_extra_kr, 2),
        "total_excl_absence_kr": round(total_excl_absence_kr, 2),
        "salt_kr": round(salt_kr, 2),
        "overnight_count": overnight_count,
        "overnight_kr": round(overnight_kr, 2),
        "dob_overnight_count": dob_overnight_count,
        "dob_overnight_kr": round(dob_overnight_kr, 2),
        "total_kr": round(total_kr, 2),
    }
    for key, label in _PAGE_TOTAL_ABSENCE_LABELS.items():
        result[key] = round(_sum_absence_kr(employees_data, label), 2)
    return result


def _resolve_period(period_start: Optional[str], db: Session):
    """Slår perioden op ud fra en valgt periode-startdato, ligesom Lønkørsel
    (payroll_router._resolve_period) – falder tilbage til dagens periode, hvis
    ingen er valgt (fx via aktivitetsoversigtens frem/tilbage-navigation)."""
    d = date.fromisoformat(period_start) if period_start else date.today()
    return get_or_create_period_for_date(d, db)


def _resolve_range(date_from: Optional[str], date_to: Optional[str],
                   period_start: Optional[str], db: Session):
    """Bestemmer datointervallet siden skal vise/eksportere for. Et frit
    Fra/Til-interval (date_from/date_to, som i Fraværsoversigt) har forrang og
    bruges råt uden at oprette/slå en lønperiode op – falder ellers tilbage til
    den faste periode via period_start (bagudkompatibel), og uden nogen af
    delene dagens periode. Bekræftet af bruger 2026-09-04."""
    if date_from and date_to:
        return date.fromisoformat(date_from), date.fromisoformat(date_to)
    if bool(date_from) != bool(date_to):
        raise HTTPException(400, "Angiv både fra- og til-dato, eller ingen af dem")
    period = _resolve_period(period_start, db)
    return period.start_date, period.end_date


def _period_for_range(start: date, end: date, db: Session) -> Optional[PayPeriod]:
    """Den lønperiode der PRÆCIST matcher intervallet, hvis nogen – bruges til
    at afgøre låsestatus og til revisionslog ved CSV-eksport."""
    return db.query(PayPeriod).filter(
        PayPeriod.start_date == start, PayPeriod.end_date == end,
    ).first()


def _period_status_for_range(start: date, end: date, db: Session) -> Optional[PayPeriodStatus]:
    """Låsestatus for CSV-eksport gælder KUN når det valgte interval matcher en
    hel lønperiode præcist – et frit interval uden eksakt match er altid
    eksporterbart, uanset om det overlapper en åben periode (bekræftet af
    bruger 2026-09-04: 'kun låst ved eksakt periodematch')."""
    period = _period_for_range(start, end, db)
    return period.status if period else None


@router.get("/preview")
def payroll_settlement_preview(date_from: Optional[str] = None, date_to: Optional[str] = None,
                               period_start: Optional[str] = None,
                               employee_id: Optional[int] = None,
                               dispatcher_group_id: Optional[int] = None,
                               current_user: AppUser = Depends(_view_access),
                               db: Session = Depends(get_db)):
    start, end = _resolve_range(date_from, date_to, period_start, db)
    employees = _active_employees(db, employee_id=employee_id, dispatcher_group_id=dispatcher_group_id)
    employees_data = [_employee_settlement_data(e, start, end, db) for e in employees]
    # Kun medarbejdere med data (mindst én godkendt aktivitet) for perioden
    # skal vises – bekræftet af bruger 2026-09-03.
    employees_data = [e for e in employees_data if e["activity_count"] > 0]
    employees_data.sort(key=lambda e: e["employee_name"] or "")
    exact_status = _period_status_for_range(start, end, db)
    return {
        "period_start": start.isoformat(),
        "period_end": end.isoformat(),
        "period_status": exact_status.value if exact_status else None,
        "page_totals": _page_totals(employees_data),
        "employees": employees_data,
    }


def _fmt_hm(decimal_hours: float) -> str:
    """Konverterer decimaltimer til 'Tt:mm'-format, fx 7.5 -> '7:30'."""
    total_minutes = round((decimal_hours or 0) * 60)
    hh, mm = divmod(total_minutes, 60)
    return f"{hh}:{mm:02d}"


def _fmt_decimal_comma(v: float) -> str:
    """Decimaltal med dansk komma, fx 7.5 -> '7,50'."""
    return f"{(v or 0):.2f}".replace(".", ",")


def _fmt_kr_da(v: float) -> str:
    """Dansk kr-format med tusindtalspunktum og kommadecimal, fx 1234.5 -> '1.234,50'."""
    return f"{(v or 0):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


class ExportSettlementCsvRequest(BaseModel):
    period_start: Optional[str] = None
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    employee_id: Optional[int] = None
    dispatcher_group_id: Optional[int] = None


def _csv_zeroed_absence_types(emp) -> set:
    """Fraværstyper der vises som 0 kr/0 timer i CSV-eksporten (men IKKE på
    siden selv) – Vognnummer-kolonnen viser stadig typens navn. Feriefri
    zeroes kun for timelønnede medarbejdere. Bekræftet af bruger 2026-08-26."""
    types = {"Ferie", "Afspadsering"}
    if not emp.fuldloennet:
        types.add("Feriefri")
    return types


def _csv_days(emp, employee_data: dict) -> list:
    """Bygger CSV-specifikke dagsrækker hvor de zero'ede fraværstypers timer/
    beløb er nulstillet (Vognnummer beholder stadig typens navn)."""
    zero_types = _csv_zeroed_absence_types(emp)
    return [
        {**day, "total_hours": 0, "total_kr": 0} if day.get("absence_type") in zero_types else day
        for day in employee_data["days"]
    ]


@router.post("/export-csv")
def export_settlement_csv(body: ExportSettlementCsvRequest,
                          current_user: AppUser = Depends(_export_access),
                          db: Session = Depends(get_db)):
    """
    Eksporterer Lønafregning som CSV: én række pr. dag pr. medarbejder (alle
    dage i det valgte interval), med lønnummer tilføjet – ingen 'Total løn
    for'-rækker og ingen topsummering. Kræver at det valgte interval matcher
    en låst lønperiode PRÆCIST – administratorer kan altid eksportere, og et
    frit interval uden eksakt periodematch er altid eksporterbart (bekræftet
    af bruger 2026-09-04).
    """
    start, end = _resolve_range(body.date_from, body.date_to, body.period_start, db)
    is_admin = current_user.role == "admin"
    exact_period = _period_for_range(start, end, db)
    if exact_period is not None and exact_period.status != PayPeriodStatus.closed and not is_admin:
        raise HTTPException(
            400,
            "Lønperioden skal være låst, før den kan eksporteres. Kør løn under Lønkørsel-fanen først.",
        )

    employees = _active_employees(db, employee_id=body.employee_id, dispatcher_group_id=body.dispatcher_group_id)
    # Kun medarbejdere med data (mindst én godkendt aktivitet) for perioden
    # skal med i eksporten – bekræftet af bruger 2026-09-03.
    employee_pairs = sorted(
        (
            (e, data)
            for e in employees
            for data in [_employee_settlement_data(e, start, end, db)]
            if data["activity_count"] > 0
        ),
        key=lambda pair: pair[1]["employee_name"] or "",
    )

    output = io.StringIO()
    writer = csv.writer(output, delimiter=";", lineterminator="\r\n")
    writer.writerow(["Dato", "Lønnummer", "Normal timer", "Overtid 1 time før",
                      "Overtid 1-3 timer efter", "Øvrig overtid", "Total tid",
                      "Total i kr.", "Vognnummer", "Beløb"])
    for emp, e in employee_pairs:
        for day in _csv_days(emp, e):
            d = date.fromisoformat(day["date"])
            vognnummer = day["absence_type"] or day["vehicle_number"] or ""
            writer.writerow([
                d.strftime("%d-%m-%Y"), e["employee_number"],
                _fmt_hm(day["normal"]), _fmt_hm(day["ot_before"]),
                _fmt_hm(day["ot_13"]), _fmt_hm(day["ot_extra"]),
                _fmt_decimal_comma(day["total_hours"]), _fmt_kr_da(day["total_kr"]),
                vognnummer, _fmt_kr_da(day["total_kr"]),
            ])

    filename = f"lonafregning_{start.isoformat()}_{end.isoformat()}.csv"
    csv_bytes = output.getvalue().encode("utf-8-sig")

    log_action(db, current_user, "payroll_settlement_export", "pay_period",
               exact_period.id if exact_period else None,
               f"Lønafregning eksporteret for periode {start} – {end}")
    db.commit()

    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
