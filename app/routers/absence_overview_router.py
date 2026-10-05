from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import List, Optional
import io

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from openpyxl import load_workbook
from sqlalchemy.orm import Session

from auth import get_current_user, require_permission
from calculators.pay_period import get_or_create_period_for_date
from calculators.rates_loader import get_supplements_for_period, load_agreement_types_from_db, supplement_sum_on
from database.models import Activity, ActivityStatus, AppUser, DispatcherGroup, Employee
from database.session import get_db
from utils.natural_sort import natural_key

router = APIRouter(prefix="/api/absence-overview", tags=["absence-overview"])

_access = require_permission("absence_overview")

_XLSX = Path(__file__).parent.parent / "Fraværstyper.xlsx"

_FALLBACK_LABELS = {
    "normal":       "Normal tid",
    "ferie":        "Ferie",
    "fri":          "Fri",
    "afspadsering": "Afspadsering",
    "skole_kursus": "Kursus/Skole",
}


def _normalize_type(label: str) -> str:
    _OVERRIDES = {"Kursus/Skole": "skole_kursus"}
    if label in _OVERRIDES:
        return _OVERRIDES[label]
    s = label.lower()
    s = s.replace("§", "paragraf_")
    s = s.replace("æ", "ae").replace("ø", "oe").replace("å", "aa")
    s = s.replace(" ", "_").replace("/", "_").replace(".", "").replace("-", "_")
    while "__" in s:
        s = s.replace("__", "_")
    return s.strip("_")


def _load_type_labels(db: Session) -> dict:
    """Returns {value: label} from MasterAbsenceType DB + fallbacks."""
    from database.models import MasterAbsenceType
    labels = dict(_FALLBACK_LABELS)
    try:
        rows = db.query(MasterAbsenceType).all()
        if rows:
            for r in rows:
                labels[r.normalized_key] = r.label
            return labels
    except Exception:
        pass
    # fallback til Excel hvis DB er tom
    try:
        wb = load_workbook(_XLSX, read_only=True, data_only=True)
        ws = wb.active
        first = True
        for row in ws.iter_rows(values_only=True):
            if first:
                first = False
                continue
            cell = row[0]
            if cell:
                label = str(cell).strip()
                labels[_normalize_type(label)] = label
        wb.close()
    except Exception:
        pass
    return labels


def _resolve_dates(date_from: Optional[str], date_to: Optional[str], db: Session):
    if date_from and date_to:
        return date.fromisoformat(date_from), date.fromisoformat(date_to)
    period = get_or_create_period_for_date(date.today(), db)
    return period.start_date, period.end_date


_PAID_ABSENCE_TYPES = {"sygdom", "barn_1sygedag", "barn_2_3sygedag", "barsel", "graviditetsbetinget_sygdom", "skole_kursus"}  # timesats = medarbejderens overenskomstsats
_FIXED_RATE_ABSENCE = {"paragraf_56_syg": 137.43}                    # fast sats uanset overenskomsttype


def _compute_data(d_from: date, d_to: date, db: Session) -> dict:
    type_labels = _load_type_labels(db)
    agreement_rates = load_agreement_types_from_db(db)

    activities = (
        db.query(Activity)
        .join(Activity.employee)
        .filter(
            Activity.status == ActivityStatus.approved,
            Activity.activity_type != "normal",
            Activity.start_time >= d_from.isoformat(),
            Activity.start_time < (d_to + timedelta(days=1)).isoformat(),
            Employee.active == True,
        )
        .order_by(Employee.first_name, Employee.last_name, Activity.start_time)
        .all()
    )

    all_types: set = set()
    emp_map: dict = {}

    for act in activities:
        emp = act.employee
        if emp.id not in emp_map:
            emp_map[emp.id] = {
                "employee_id":     emp.id,
                "employee_name":   emp.name,
                "employee_number": emp.employee_number,
                "base_rate":       Decimal(str(agreement_rates.get(emp.agreement_type, 0))),
                "supplements":     get_supplements_for_period(db, emp.id, date.min, date.max),
                "absences":        defaultdict(lambda: {"minutes": 0, "day_set": set(), "rate_kr": Decimal("0")}),
            }
        atype = act.activity_type
        all_types.add(atype)
        duration_min = int((act.end_time - act.start_time).total_seconds() // 60)
        emp_map[emp.id]["absences"][atype]["minutes"] += duration_min
        # Timesatsen regnes dag for dag (grundsats + summen af dagens tillæg), med
        # timerne fordelt ligeligt på aktivitetens dage – samme fordeling som eksporten.
        _day_count = (act.end_time.date() - act.start_time.date()).days + 1
        _d = act.start_time.date()
        while _d <= act.end_time.date():
            _rate = emp_map[emp.id]["base_rate"] + supplement_sum_on(emp_map[emp.id]["supplements"], _d)
            emp_map[emp.id]["absences"][atype]["rate_kr"] += Decimal(duration_min) / 60 / _day_count * _rate
            _d += timedelta(days=1)

        cur_day = act.start_time.date()
        end_day = act.end_time.date()
        while cur_day <= end_day:
            emp_map[emp.id]["absences"][atype]["day_set"].add(cur_day)
            cur_day += timedelta(days=1)

    employees = []
    for emp_info in emp_map.values():
        absences = {}
        for atype, data in emp_info["absences"].items():
            label = type_labels.get(atype, atype.replace("_", " ").capitalize())
            if atype in _FIXED_RATE_ABSENCE:
                rate = _FIXED_RATE_ABSENCE[atype]
            elif atype in _PAID_ABSENCE_TYPES:
                # Vægtet gennemsnit når satsen skifter i perioden (flere/nye tillæg).
                rate = (float(data["rate_kr"] / (Decimal(data["minutes"]) / 60)) if data["minutes"]
                        else float(emp_info["base_rate"]))
            else:
                rate = 0.0
            absences[atype] = {
                "label": label,
                "hours": round(data["minutes"] / 60, 2),
                "days":  len(data["day_set"]),
                "rate":  rate,
            }
        employees.append({
            "employee_id":     emp_info["employee_id"],
            "employee_name":   emp_info["employee_name"],
            "employee_number": emp_info["employee_number"],
            "absences":        absences,
        })

    sorted_types = sorted(all_types, key=lambda t: type_labels.get(t, t))

    return {
        "date_from":     d_from.isoformat(),
        "date_to":       d_to.isoformat(),
        "absence_types": [{"value": t, "label": type_labels.get(t, t)} for t in sorted_types],
        "employees":     employees,
    }


@router.get("/data")
def absence_data(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    current_user: AppUser = Depends(_access),
    db: Session = Depends(get_db),
):
    d_from, d_to = _resolve_dates(date_from, date_to, db)
    return _compute_data(d_from, d_to, db)


@router.get("/employee-options")
def employee_options(
    current_user: AppUser = Depends(_access),
    db: Session = Depends(get_db),
):
    emps = (
        db.query(Employee)
        .filter(Employee.active == True)
        .order_by(Employee.first_name, Employee.last_name)
        .all()
    )
    used_group_ids = {e.dispatcher_group_id for e in emps if e.dispatcher_group_id}
    groups = sorted(
        db.query(DispatcherGroup).filter(DispatcherGroup.id.in_(used_group_ids)).all(),
        key=lambda g: natural_key(g.name),
    )
    return {
        "employees": [
            {"id": e.id, "name": e.name, "dispatcher_group_id": e.dispatcher_group_id}
            for e in emps
        ],
        "dispatcher_groups": [{"id": g.id, "name": g.name} for g in groups],
    }


@router.get("/export-per-employee")
def export_per_employee(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    employee_id: Optional[int] = None,
    dispatcher_group_id: Optional[int] = None,
    current_user: AppUser = Depends(_access),
    db: Session = Depends(get_db),
):
    import openpyxl
    from openpyxl.styles import Font, PatternFill

    d_from, d_to = _resolve_dates(date_from, date_to, db)
    type_labels = _load_type_labels(db)
    agreement_rates = load_agreement_types_from_db(db)

    activities_q = (
        db.query(Activity)
        .join(Activity.employee)
        .filter(
            Activity.status == ActivityStatus.approved,
            Activity.activity_type != "normal",
            Activity.start_time >= d_from.isoformat(),
            Activity.start_time < (d_to + timedelta(days=1)).isoformat(),
            Employee.active == True,
        )
    )
    if employee_id:
        activities_q = activities_q.filter(Activity.employee_id == employee_id)
    elif dispatcher_group_id:
        activities_q = activities_q.filter(Employee.dispatcher_group_id == dispatcher_group_id)
    activities = activities_q.order_by(Employee.first_name, Employee.last_name, Activity.start_time).all()

    group_name = None
    employee_name = None
    if employee_id:
        emp = db.query(Employee).filter(Employee.id == employee_id).first()
        employee_name = emp.name if emp else None
    elif dispatcher_group_id:
        group = db.query(DispatcherGroup).filter(DispatcherGroup.id == dispatcher_group_id).first()
        group_name = group.name if group else None

    supplements_cache: dict = {}

    def _hourly_rate(emp, d: date) -> float:
        """Grundsats + summen af medarbejdertillæg gyldige på dagen d."""
        if emp.id not in supplements_cache:
            supplements_cache[emp.id] = get_supplements_for_period(db, emp.id, date.min, date.max)
        rate = Decimal(str(agreement_rates.get(emp.agreement_type, 0)))
        return float(rate + supplement_sum_on(supplements_cache[emp.id], d))

    # Byg én række per kalenderdag med fravær (splitter aktiviteter der spænder over flere dage)
    rows = []
    for act in activities:
        emp = act.employee
        atype = act.activity_type
        label = type_labels.get(atype, atype.replace("_", " ").capitalize())
        total_minutes = int((act.end_time - act.start_time).total_seconds() // 60)
        start_day = act.start_time.date()
        end_day = act.end_time.date()
        day_count = (end_day - start_day).days + 1
        minutes_per_day = total_minutes / day_count if day_count else total_minutes

        cur_day = start_day
        while cur_day <= end_day:
            if atype in _FIXED_RATE_ABSENCE:
                rate = _FIXED_RATE_ABSENCE[atype]
            elif atype in _PAID_ABSENCE_TYPES:
                rate = _hourly_rate(emp, cur_day)
            else:
                rate = 0.0
            rows.append({
                "employee_name":   emp.name,
                "employee_number": emp.employee_number,
                "date":            cur_day,
                "label":           label,
                "hours":           round(minutes_per_day / 60, 2),
                "rate":            rate,
            })
            cur_day += timedelta(days=1)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Fravær per medarbejder"

    header_fill = PatternFill(start_color="317423", end_color="317423", fill_type="solid")
    row_fill    = PatternFill(start_color="D4EDCC", end_color="D4EDCC", fill_type="solid")

    ws.append(["Medarbejder", "Lønnr", "Dato", "Fraværstype", "Timer", "Sats"])
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = header_fill
    ws.freeze_panes = "A2"

    ws.column_dimensions["A"].width = 28
    ws.column_dimensions["B"].width = 12
    ws.column_dimensions["C"].width = 12
    ws.column_dimensions["D"].width = 28
    ws.column_dimensions["E"].width = 10
    ws.column_dimensions["F"].width = 12

    rows.sort(key=lambda r: (r["employee_name"], r["date"]))

    emp_seen_order: list = []
    for r in rows:
        if not emp_seen_order or emp_seen_order[-1] != r["employee_name"]:
            emp_seen_order.append(r["employee_name"])
    emp_fill_idx = {name: i for i, name in enumerate(emp_seen_order)}

    last_emp = None
    for r in rows:
        rate_val = r.get("rate", 0)
        show_emp = r["employee_name"] != last_emp
        ws.append([
            r["employee_name"] if show_emp else "",
            r["employee_number"] if show_emp else "",
            r["date"].strftime("%d-%m-%Y"),
            r["label"],
            r["hours"],
            rate_val if rate_val else "",
        ])
        if emp_fill_idx[r["employee_name"]] % 2 == 0:
            for cell in ws[ws.max_row]:
                cell.fill = row_fill
        last_emp = r["employee_name"]

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    def _safe(s):
        return s.replace(" ", "_").replace("/", "_")

    if employee_id and employee_name:
        suffix = f"_{_safe(employee_name)}"
    elif group_name:
        suffix = f"_{_safe(group_name)}"
    else:
        suffix = ""
    filename = f"fravaer_per_medarbejder{suffix}_{d_from}_{d_to}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/export-per-type")
def export_per_type(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    absence_type: Optional[List[str]] = Query(None),
    current_user: AppUser = Depends(_access),
    db: Session = Depends(get_db),
):
    import openpyxl
    from openpyxl.styles import Font, PatternFill

    d_from, d_to = _resolve_dates(date_from, date_to, db)
    data = _compute_data(d_from, d_to, db)

    # Aggregate totals per type across all employees (optionally filtered)
    type_totals: dict = {}
    type_labels: dict = {}
    for emp in data["employees"]:
        for atype, ainfo in emp["absences"].items():
            if absence_type and atype not in absence_type:
                continue
            if atype not in type_totals:
                type_totals[atype] = {"days": 0, "hours": 0.0}
                type_labels[atype] = ainfo["label"]
            type_totals[atype]["days"]  += ainfo["days"]
            type_totals[atype]["hours"]  = round(type_totals[atype]["hours"] + ainfo["hours"], 2)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Fravær per type"

    header_fill = PatternFill(start_color="317423", end_color="317423", fill_type="solid")
    row_fill    = PatternFill(start_color="D4EDCC", end_color="D4EDCC", fill_type="solid")

    ws.append(["Fraværstype", "Dage i alt", "Timer i alt"])
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = header_fill
    ws.freeze_panes = "A2"

    ws.column_dimensions["A"].width = 28
    ws.column_dimensions["B"].width = 14
    ws.column_dimensions["C"].width = 14

    sorted_types = sorted(type_totals.items(), key=lambda x: type_labels.get(x[0], x[0]))
    for i, (atype, totals) in enumerate(sorted_types):
        ws.append([type_labels.get(atype, atype), totals["days"], totals["hours"]])
        if i % 2 == 0:
            for cell in ws[ws.max_row]:
                cell.fill = row_fill

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    if not absence_type:
        type_suffix = ""
    elif len(absence_type) == 1:
        lbl = type_labels.get(absence_type[0], absence_type[0])
        type_suffix = "_" + lbl.replace(" ", "_").replace("/", "_")
    else:
        type_suffix = "_udvalgte"
    filename = f"fravaer_per_type{type_suffix}_{d_from}_{d_to}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
