from datetime import date as date_type, datetime, time, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from auth import log_action, require_permission
from calculators.dagsplan_helpers import NON_ABSENCE_TYPES, dagsplan_vehicles_query, fast_bil_defaults
from calculators.vehicle_uses import clipped_vehicle_uses, has_multiple_vehicles
from database.models import (
    Activity, ActivityStatus, AppUser, DailyPlanAssignment, DailyPlanExtraAssignment, Employee,
    MasterAbsenceType, VagtplanComment, Vehicle, VehicleAbsence,
)
from database.schemas import (
    DagsplanEmployeeRow, DagsplanExtraRow, DagsplanResponse, DagsplanVehicleRow,
    DailyPlanAssignmentUpsert, DailyPlanExtraAssignmentUpsert, VehicleAbsenceCreate, VehicleAbsenceResponse,
)
from database.session import get_db

router = APIRouter(prefix="/api/dagsplan", tags=["dagsplan"])
vehicle_absence_router = APIRouter(prefix="/api/vehicle-absences", tags=["vehicle-absences"])


def _absent_vehicle_ids(db: Session, d: date_type) -> set[int]:
    rows = db.query(VehicleAbsence.vehicle_id).filter(
        VehicleAbsence.date_from <= d,
        or_(VehicleAbsence.date_to.is_(None), VehicleAbsence.date_to >= d),
    ).all()
    return {r[0] for r in rows}


def _mismatch_vehicle_number(db: Session, employee_id: int, d: date_type, vehicle: Vehicle) -> Optional[str]:
    """Kommasepareret liste over ANDRE biler end den tildelte, som chaufføren
    har kørt i dagens normal tid-vagter (2026-10-08). Vagter med flere biler
    tjekkes bil for bil (vehicle_uses), så en bil der kun er kørt lidt også
    giver advarsel. Deaktiverede aktiviteter tæller ikke med."""
    day_start = datetime.combine(d, time.min)
    day_end = day_start + timedelta(days=1)
    acts = db.query(Activity).filter(
        Activity.employee_id == employee_id,
        Activity.activity_type == "normal",
        Activity.status != ActivityStatus.deactivated,
        Activity.start_time >= day_start,
        Activity.start_time < day_end,
    ).order_by(Activity.start_time).all()
    others: list[str] = []
    for a in acts:
        uses = clipped_vehicle_uses(a)
        if has_multiple_vehicles(uses):
            for _, _, reg in uses:
                if reg != vehicle.registration_number:
                    # Slettede vogne medtages bevidst - nummeret er død tekst.
                    other = db.query(Vehicle).filter(Vehicle.registration_number == reg).first()
                    others.append(other.vehicle_number if other else reg)
        elif a.vehicle_number and a.vehicle_number != vehicle.vehicle_number:
            others.append(a.vehicle_number)
    unique = list(dict.fromkeys(others))
    return ", ".join(unique) if unique else None


def _build_vehicle_rows(db: Session, d: date_type) -> list[DagsplanVehicleRow]:
    """Effektiv chauffør-tildeling pr. vogn: gemt tildeling vinder, ellers
    'Fast bil'-fallback - samme regel som effective_vehicle_for_employee(),
    blot indekseret pr. vogn i stedet for pr. medarbejder (én forespørgsel
    i stedet for én pr. medarbejder). Slettede vogne med en historisk
    tildeling denne dag medtages som skrivebeskyttede rækker (død tekst)."""
    absent_ids = _absent_vehicle_ids(db, d)
    assignments = {
        a.vehicle_id: a for a in
        db.query(DailyPlanAssignment).filter(DailyPlanAssignment.date == d).all()
    }
    fast_bil_by_vehicle = fast_bil_defaults(db)
    deleted_with_assignment = [
        a.vehicle for a in assignments.values()
        if a.vehicle and a.vehicle.deleted_at and a.employee_id
    ]
    vehicles = sorted(
        dagsplan_vehicles_query(db).all() + deleted_with_assignment,
        key=lambda v: v.vehicle_number,
    )
    rows = []
    for v in vehicles:
        a = assignments.get(v.id)
        default_emp = fast_bil_by_vehicle.get(v.id) if a is None else None
        employee = a.employee if (a and a.employee) else default_emp
        mismatch = (
            _mismatch_vehicle_number(db, employee.id, d, v)
            if employee and not v.deleted_at else None
        )
        rows.append(DagsplanVehicleRow(
            vehicle_id=v.id,
            vehicle_number=v.vehicle_number,
            description=v.description,
            dispatcher_group_id=v.dispatcher_group_id,
            employee_id=employee.id if employee else None,
            employee_name=employee.name if employee else None,
            task=a.task if a else None,
            informed=a.informed if a else False,
            absent=v.id in absent_ids,
            mismatch_vehicle_number=mismatch,
            deleted=bool(v.deleted_at),
        ))
    return rows


def _build_extra_rows(db: Session, d: date_type) -> list[DagsplanExtraRow]:
    """De 10 faste EKSTRA-pladser (1-10) - i modsætning til vogne findes der
    intet 'Fast bil'-fallback for dem, kun en evt. gemt tildeling. En linje kan
    have en valgfri vogn for dagen (vogne uden Vognpark-flueben), som kun bruges
    til visning og ⚠️-advarsel."""
    assignments = {
        a.slot: a for a in
        db.query(DailyPlanExtraAssignment).filter(DailyPlanExtraAssignment.date == d).all()
    }
    rows = []
    for slot in range(1, 11):
        a = assignments.get(slot)
        employee = a.employee if (a and a.employee) else None
        vehicle = a.vehicle if a else None
        mismatch = (
            _mismatch_vehicle_number(db, employee.id, d, vehicle)
            if employee and vehicle and not vehicle.deleted_at else None
        )
        rows.append(DagsplanExtraRow(
            slot=slot,
            vehicle_id=vehicle.id if vehicle else None,
            vehicle_number=vehicle.vehicle_number if vehicle else None,
            description=vehicle.description if vehicle else None,
            dispatcher_group_id=vehicle.dispatcher_group_id if vehicle else None,
            vehicle_deleted=bool(vehicle and vehicle.deleted_at),
            mismatch_vehicle_number=mismatch,
            employee_id=employee.id if employee else None,
            employee_name=employee.name if employee else None,
            task=a.task if a else None,
            informed=a.informed if a else False,
        ))
    return rows


def _conflicting_assignment_label(
    db: Session, d: date_type, employee_id: int,
    exclude_vehicle_id: Optional[int] = None, exclude_slot: Optional[int] = None,
) -> Optional[str]:
    """Menneskelæsbar betegnelse ('vogn X' / 'EKSTRA Y'), hvis medarbejderen
    allerede har en anden effektiv tildeling (vogn ELLER EKSTRA-plads) samme
    dag - bruges til at advare, uanset hvor den anden tildeling stammer fra."""
    for r in _build_vehicle_rows(db, d):
        if r.employee_id == employee_id and r.vehicle_id != exclude_vehicle_id:
            return f"vogn {r.vehicle_number}"
    for r in _build_extra_rows(db, d):
        if r.employee_id == employee_id and r.slot != exclude_slot:
            return f"EKSTRA-plads {r.slot}" + (f" (vogn {r.vehicle_number})" if r.vehicle_number else "")
    return None


def dagsplan_employees(db: Session) -> list[Employee]:
    """Chaufførerne i Dagsplanen (2026-10-08) - bruges både til sidelisten og
    til chauffør-vælgeren i vogntabellen: aktive, ikke funktionærer, i en
    disponentgruppe med "Medtag i Dagsplan". Uden disponentgruppe udelades."""
    return [
        e for e in
        db.query(Employee).filter(Employee.active == True, Employee.agreement_kind != "funktionaer")
        .order_by(Employee.first_name, Employee.last_name).all()
        if e.dispatcher_group and e.dispatcher_group.visible_in_dagsplan
    ]


def _absence_warning_message(db: Session, employee: Employee, d: date_type) -> Optional[str]:
    day_start = datetime.combine(d, time.min)
    day_end = day_start + timedelta(days=1)
    absence = db.query(Activity).filter(
        Activity.employee_id == employee.id,
        Activity.activity_type.notin_(NON_ABSENCE_TYPES),
        Activity.status != ActivityStatus.deactivated,
        Activity.start_time < day_end,
        Activity.end_time > day_start,
    ).first()
    if not absence:
        return None
    label_row = db.query(MasterAbsenceType).filter(
        MasterAbsenceType.normalized_key == absence.activity_type
    ).first()
    label = label_row.label if label_row else absence.activity_type
    return f"{employee.name} har registreret {label}. Vil du tilføje til bilen?"


@router.get("", response_model=DagsplanResponse)
def get_dagsplan(
    date: date_type,
    dispatcher_group_id: Optional[int] = None,
    employee_id: Optional[int] = None,
    current_user: AppUser = Depends(require_permission("dagsplan_view")),
    db: Session = Depends(get_db),
):
    all_rows = _build_vehicle_rows(db, date)
    extra_rows = _build_extra_rows(db, date)
    assigned_employee_ids = {r.employee_id for r in all_rows if r.employee_id} | \
        {r.employee_id for r in extra_rows if r.employee_id}

    visible_rows = all_rows
    if dispatcher_group_id:
        visible_rows = [r for r in visible_rows if r.dispatcher_group_id == dispatcher_group_id]
    if employee_id:
        visible_rows = [r for r in visible_rows if r.employee_id == employee_id]

    day_start = datetime.combine(date, time.min)
    day_end = day_start + timedelta(days=1)
    absence_acts = db.query(Activity).filter(
        Activity.activity_type.notin_(NON_ABSENCE_TYPES),
        Activity.status != ActivityStatus.deactivated,
        Activity.start_time < day_end,
        Activity.end_time > day_start,
    ).all()
    absence_by_employee = {}
    for a in absence_acts:
        absence_by_employee.setdefault(a.employee_id, a)
    comment_by_employee = {
        c.employee_id: c for c in db.query(VagtplanComment).filter(VagtplanComment.date == date).all()
    }

    visible_employees = dagsplan_employees(db)

    employee_rows = []
    for emp in visible_employees:
        comment = comment_by_employee.get(emp.id)
        absence = absence_by_employee.get(emp.id)
        assigned = emp.id in assigned_employee_ids
        if comment:
            status, absence_text = "comment_only", comment.text
        elif absence:
            status, absence_text = "absent", absence.activity_type
        elif assigned:
            status, absence_text = "assigned", None
        else:
            status, absence_text = "none", None
        employee_rows.append(DagsplanEmployeeRow(
            employee_id=emp.id, employee_name=emp.name, status=status, absence_text=absence_text,
        ))

    return DagsplanResponse(date=date, vehicles=visible_rows, employees=employee_rows, extra_rows=extra_rows)


@router.patch("/assignment", response_model=DagsplanVehicleRow)
def upsert_assignment(
    body: DailyPlanAssignmentUpsert,
    current_user: AppUser = Depends(require_permission("dagsplan_edit")),
    db: Session = Depends(get_db),
):
    vehicle = db.query(Vehicle).filter(Vehicle.id == body.vehicle_id).first()
    if not vehicle:
        raise HTTPException(404, "Vogn ikke fundet")
    if vehicle.deleted_at:
        raise HTTPException(400, "Vognen er slettet og kan ikke længere tildeles")
    employee = db.query(Employee).filter(Employee.id == body.employee_id).first() if body.employee_id is not None else None
    if body.employee_id is not None and not employee:
        raise HTTPException(404, "Medarbejder ikke fundet")

    assignment = db.query(DailyPlanAssignment).filter(
        DailyPlanAssignment.date == body.date,
        DailyPlanAssignment.vehicle_id == body.vehicle_id,
    ).first()
    previous_employee_id = assignment.employee_id if assignment else None
    employee_is_changing = body.employee_id is not None and body.employee_id != previous_employee_id

    if employee_is_changing and not body.force:
        # Tjekker mod den EFFEKTIVE tildeling (gemt tildeling ELLER "Fast
        # bil"-standard, eller en EKSTRA-plads) alle andre steder end den der
        # lige nu redigeres, så brugeren advares uanset hvordan medarbejderen
        # endte der. Kun ved en FAKTISK ændring af chauffør - ikke ved fx
        # blot at redigere "Opgave" for en allerede tildelt (og evt. allerede
        # bekræftet) medarbejder.
        conflict_label = _conflicting_assignment_label(db, body.date, body.employee_id, exclude_vehicle_id=body.vehicle_id)
        if conflict_label:
            raise HTTPException(
                409, f"Medarbejderen er allerede tildelt {conflict_label} denne dag. "
                     f"Vil du stadig tildele til denne vogn?"
            )

        warning = _absence_warning_message(db, employee, body.date)
        if warning:
            raise HTTPException(409, warning)
    if assignment is None:
        assignment = DailyPlanAssignment(date=body.date, vehicle_id=body.vehicle_id)
        db.add(assignment)
    assignment.employee_id = body.employee_id
    assignment.task = body.task
    assignment.informed = body.informed
    db.flush()
    log_action(db, current_user, "upsert_dagsplan_assignment", "daily_plan_assignment", assignment.id)
    db.commit()

    rows = _build_vehicle_rows(db, body.date)
    return next(r for r in rows if r.vehicle_id == body.vehicle_id)


@router.patch("/extra-assignment", response_model=DagsplanExtraRow)
def upsert_extra_assignment(
    body: DailyPlanExtraAssignmentUpsert,
    current_user: AppUser = Depends(require_permission("dagsplan_edit")),
    db: Session = Depends(get_db),
):
    assignment = db.query(DailyPlanExtraAssignment).filter(
        DailyPlanExtraAssignment.date == body.date,
        DailyPlanExtraAssignment.slot == body.slot,
    ).first()
    previous_vehicle_id = assignment.vehicle_id if assignment else None
    vehicle_id = body.vehicle_id if "vehicle_id" in body.model_fields_set else previous_vehicle_id
    vehicle_is_changing = vehicle_id is not None and vehicle_id != previous_vehicle_id
    employee_id = body.employee_id
    if vehicle_id is None and previous_vehicle_id is not None:
        # Vognen fjernes fra linjen -> chaufføren fjernes også, så linjen står
        # som en tom (grå) EKSTRA-linje igen (brugerens ønske 2026-10-08).
        employee_id = None

    if vehicle_is_changing:
        vehicle = db.query(Vehicle).filter(Vehicle.id == vehicle_id).first()
        if not vehicle:
            raise HTTPException(404, "Vogn ikke fundet")
        if vehicle.deleted_at:
            raise HTTPException(400, "Vognen er slettet og kan ikke længere tildeles")
        if vehicle.vognpark:
            raise HTTPException(400, f"Vogn {vehicle.vehicle_number} har allerede sin egen linje i Dagsplanen")
        # Vognens faste chauffør skrives på linjen (brugerens ønske 2026-10-08).
        fast = fast_bil_defaults(db).get(vehicle.id)
        if fast:
            employee_id = fast.id
        if not body.force:
            other = db.query(DailyPlanExtraAssignment).filter(
                DailyPlanExtraAssignment.date == body.date,
                DailyPlanExtraAssignment.vehicle_id == vehicle.id,
                DailyPlanExtraAssignment.slot != body.slot,
            ).first()
            if other:
                raise HTTPException(
                    409, f"Vogn {vehicle.vehicle_number} står allerede på EKSTRA-plads {other.slot} "
                         f"denne dag. Vil du stadig tilføje den her?"
                )

    employee = db.query(Employee).filter(Employee.id == employee_id).first() if employee_id is not None else None
    if employee_id is not None and not employee:
        raise HTTPException(404, "Medarbejder ikke fundet")

    previous_employee_id = assignment.employee_id if assignment else None
    employee_is_changing = employee_id is not None and employee_id != previous_employee_id

    if employee_is_changing and not body.force:
        conflict_label = _conflicting_assignment_label(db, body.date, employee_id, exclude_slot=body.slot)
        if conflict_label:
            raise HTTPException(
                409, f"{employee.name} er allerede tildelt {conflict_label} denne dag. "
                     f"Vil du stadig tildele hertil?"
            )

        warning = _absence_warning_message(db, employee, body.date)
        if warning:
            raise HTTPException(409, warning)

    if assignment is None:
        assignment = DailyPlanExtraAssignment(date=body.date, slot=body.slot)
        db.add(assignment)
    assignment.vehicle_id = vehicle_id
    assignment.employee_id = employee_id
    assignment.task = body.task
    assignment.informed = body.informed
    db.flush()
    log_action(db, current_user, "upsert_dagsplan_extra_assignment", "daily_plan_extra_assignment", assignment.id)
    db.commit()

    rows = _build_extra_rows(db, body.date)
    return next(r for r in rows if r.slot == body.slot)


@vehicle_absence_router.get("", response_model=list[VehicleAbsenceResponse])
def list_vehicle_absences(
    date: date_type,
    current_user: AppUser = Depends(require_permission("dagsplan_view")),
    db: Session = Depends(get_db),
):
    return db.query(VehicleAbsence).filter(
        VehicleAbsence.date_from <= date,
        or_(VehicleAbsence.date_to.is_(None), VehicleAbsence.date_to >= date),
    ).order_by(VehicleAbsence.date_from).all()


@vehicle_absence_router.post("", response_model=VehicleAbsenceResponse, status_code=201)
def create_vehicle_absence(
    body: VehicleAbsenceCreate,
    current_user: AppUser = Depends(require_permission("dagsplan_edit")),
    db: Session = Depends(get_db),
):
    vehicle = db.query(Vehicle).filter(Vehicle.id == body.vehicle_id).first()
    if not vehicle:
        raise HTTPException(404, "Vogn ikke fundet")
    if vehicle.deleted_at:
        raise HTTPException(400, "Vognen er slettet")
    if body.date_to is not None and body.date_to < body.date_from:
        raise HTTPException(400, "Til dato kan ikke ligge før fra dato")
    absence = VehicleAbsence(
        vehicle_id=body.vehicle_id, date_from=body.date_from, date_to=body.date_to,
        comment=body.comment, created_by=current_user.initials,
    )
    db.add(absence)
    db.flush()
    log_action(db, current_user, "create_vehicle_absence", "vehicle_absence", absence.id)
    db.commit()
    db.refresh(absence)
    return absence


@vehicle_absence_router.delete("/{absence_id}", status_code=204)
def delete_vehicle_absence(
    absence_id: int,
    current_user: AppUser = Depends(require_permission("dagsplan_edit")),
    db: Session = Depends(get_db),
):
    absence = db.query(VehicleAbsence).filter(VehicleAbsence.id == absence_id).first()
    if not absence:
        raise HTTPException(404, "Fravær ikke fundet")
    if absence.vehicle_deleted:
        raise HTTPException(400, "Vognen er slettet – fraværet bevares som historik")
    log_action(db, current_user, "delete_vehicle_absence", "vehicle_absence", absence.id)
    db.delete(absence)
    db.commit()
