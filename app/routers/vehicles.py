from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import String, and_, cast, or_
from sqlalchemy.orm import Session

from auth import log_action, require_any_permission, require_permission
from database.session import get_db
from database.models import (
    Activity, ActivityStatus, AppUser, DailyPlanAssignment, DailyPlanExtraAssignment, DispatcherGroup, Employee,
    PayPeriod, PayPeriodStatus, Vehicle, VehicleAbsence,
)
from database.schemas import VehicleCreate, VehicleUpdate, VehicleResponse

router = APIRouter(prefix="/api/vehicles", tags=["vehicles"])


def _resolve_dispatcher_group_id(db: Session, group_id):
    if group_id is None:
        return None
    if not db.query(DispatcherGroup).filter(DispatcherGroup.id == group_id).first():
        raise HTTPException(400, f"Ukendt disponentgruppe-id: {group_id}")
    return group_id


def _free_registration(db: Session, reg: str, exclude_id: int | None = None) -> None:
    """Afviser en nummerplade der bruges af en anden IKKE-slettet vogn. Bruges
    den af en slettet vogn, omdøbes den slettedes plade, så den nye kan
    oprettes (brugerens valg 2026-10-08). Gamle vagters vognnummer-opslag via
    pladen finder derefter den nye vogn."""
    q = db.query(Vehicle).filter(Vehicle.registration_number == reg)
    if exclude_id is not None:
        q = q.filter(Vehicle.id != exclude_id)
    existing = q.first()
    if not existing:
        return
    if existing.deleted_at is None:
        raise HTTPException(400, "Registreringsnummer eksisterer allerede")
    existing.registration_number = f"{reg} (slettet {existing.id})"
    db.flush()


# Vognlisten bruges af flere skærmbilleder (vognnr.-felter i aktiviteter, fast bil/
# fraværsvogn på medarbejderen, Dagsplan, Vagtplan) – ikke kun Vognpark-siden.
_vehicle_list_access = require_any_permission(
    "view_vehicles", "manage_vehicles", "view_calendar", "edit_activities", "vagtplan_view",
    "dagsplan_view", "view_employees", "manage_employees", "payroll_settlement_view", "stamdata",
)


@router.get("", response_model=list[VehicleResponse])
def list_vehicles(current_user: AppUser = Depends(_vehicle_list_access),
                  db: Session = Depends(get_db)):
    return (
        db.query(Vehicle).filter(Vehicle.deleted_at.is_(None))
        .order_by(Vehicle.registration_number).all()
    )


@router.post("", response_model=VehicleResponse, status_code=201)
def create_vehicle(body: VehicleCreate,
                   current_user: AppUser = Depends(require_permission("manage_vehicles")),
                   db: Session = Depends(get_db)):
    reg = body.registration_number.strip()
    _free_registration(db, reg)
    v = Vehicle(
        registration_number=reg,
        vehicle_number=body.vehicle_number.strip(),
        description=body.description,
        dispatcher_group_id=_resolve_dispatcher_group_id(db, body.dispatcher_group_id),
        vognpark=body.vognpark,
    )
    db.add(v)
    db.commit()
    db.refresh(v)
    return v


@router.patch("/{vehicle_id}", response_model=VehicleResponse)
def update_vehicle(vehicle_id: int, body: VehicleUpdate,
                   current_user: AppUser = Depends(require_permission("manage_vehicles")),
                   db: Session = Depends(get_db)):
    v = db.query(Vehicle).filter(Vehicle.id == vehicle_id, Vehicle.deleted_at.is_(None)).first()
    if not v:
        raise HTTPException(404, "Vogn ikke fundet")
    if body.registration_number is not None:
        reg = body.registration_number.strip()
        _free_registration(db, reg, exclude_id=vehicle_id)
        v.registration_number = reg
    if body.vehicle_number is not None:
        v.vehicle_number = body.vehicle_number.strip()
    if body.description is not None:
        v.description = body.description
    if body.vognpark is not None:
        v.vognpark = body.vognpark
    if "dispatcher_group_id" in body.model_fields_set:
        v.dispatcher_group_id = _resolve_dispatcher_group_id(db, body.dispatcher_group_id)
    db.commit()
    db.refresh(v)
    return v


def _activities_using_vehicle(db: Session, v: Vehicle):
    """Ikke-deaktiverede aktiviteter hvor vognen er skrevet på: som hovedbil
    (registreringsnummer, eller vognnummer når intet reg.nr. er gemt, fx
    manuelle) eller som en af flere biler på vagten (vehicle_uses)."""
    return db.query(Activity).filter(
        Activity.status != ActivityStatus.deactivated,
        or_(
            Activity.vehicle_registration == v.registration_number,
            and_(Activity.vehicle_registration.is_(None), Activity.vehicle_number == v.vehicle_number),
            cast(Activity.vehicle_uses, String).like(f'%"{v.registration_number}"%'),
        ),
    )


def _deletion_warning(db: Session, v: Vehicle) -> str | None:
    """Advarsel før sletning: brug i ulåste lønperioder + koblinger der nulstilles."""
    lines = []
    open_periods = (
        db.query(PayPeriod)
        .join(Activity, Activity.pay_period_id == PayPeriod.id)
        .filter(
            PayPeriod.status != PayPeriodStatus.closed,
            Activity.id.in_(_activities_using_vehicle(db, v).with_entities(Activity.id)),
        )
        .distinct().order_by(PayPeriod.start_date).all()
    )
    if open_periods:
        periods = ", ".join(
            f"{p.start_date.strftime('%d-%m-%Y')} – {p.end_date.strftime('%d-%m-%Y')}" for p in open_periods
        )
        lines.append(
            f"Vognen er skrevet på vagter i lønperioder, der ikke er låst ({periods}). "
            f"Vognnummeret bliver stående på vagterne som tekst."
        )
    fast_bil = db.query(Employee).filter(Employee.fast_bil_vehicle_id == v.id).all()
    if fast_bil:
        lines.append("Fast bil for: " + ", ".join(e.name for e in fast_bil) + " (nulstilles).")
    absence_vehicle = db.query(Employee).filter(Employee.absence_vehicle_id == v.id).all()
    if absence_vehicle:
        lines.append("Vognnummer ved fravær for: " + ", ".join(e.name for e in absence_vehicle) + " (nulstilles).")
    groups = db.query(DispatcherGroup).filter(DispatcherGroup.vehicle_id == v.id).all()
    if groups:
        lines.append("Standardvogn for disponentgruppe: " + ", ".join(g.name for g in groups) + " (nulstilles).")
    if not lines:
        return None
    return "\n".join(lines) + "\n\nVil du slette vognen alligevel?"


@router.delete("/{vehicle_id}", status_code=204)
def delete_vehicle(vehicle_id: int, force: bool = False,
                   current_user: AppUser = Depends(require_permission("manage_vehicles")),
                   db: Session = Depends(get_db)):
    """Blød sletning (2026-10-08): vognen skjules fremadrettet, men rækken
    bevares, så vognnummeret står som død tekst på gamle vagter, i Lønafregning
    og i gamle Dagsplan-rækker/materielt fravær. Er vognen brugt i en ulåst
    lønperiode (eller koblet til medarbejdere/grupper), returneres 409 med en
    advarsel - force=true gennemfører sletningen."""
    v = db.query(Vehicle).filter(Vehicle.id == vehicle_id, Vehicle.deleted_at.is_(None)).first()
    if not v:
        raise HTTPException(404, "Vogn ikke fundet")
    if not force:
        warning = _deletion_warning(db, v)
        if warning:
            raise HTTPException(409, warning)

    today = date.today()
    for e in db.query(Employee).filter(Employee.fast_bil_vehicle_id == v.id):
        e.fast_bil_vehicle_id = None
        e.fast_bil = False
    for e in db.query(Employee).filter(Employee.absence_vehicle_id == v.id):
        e.absence_vehicle_id = None
    for g in db.query(DispatcherGroup).filter(DispatcherGroup.vehicle_id == v.id):
        g.vehicle_id = None
    # Historik (til og med i dag) bevares som død tekst; fremtidig planlægning fjernes.
    db.query(DailyPlanAssignment).filter(
        DailyPlanAssignment.vehicle_id == v.id, DailyPlanAssignment.date > today,
    ).delete(synchronize_session=False)
    for a in db.query(DailyPlanExtraAssignment).filter(
        DailyPlanExtraAssignment.vehicle_id == v.id, DailyPlanExtraAssignment.date > today,
    ):
        a.vehicle_id = None  # EKSTRA-linjen bliver stående, kun vognen fjernes
    for a in db.query(VehicleAbsence).filter(VehicleAbsence.vehicle_id == v.id):
        if a.date_from > today:
            db.delete(a)
        elif a.date_to is not None and a.date_to > today:
            a.date_to = today
    v.deleted_at = datetime.now()
    log_action(db, current_user, "delete_vehicle", "vehicle", v.id,
               f"Slettet vogn {v.vehicle_number} ({v.registration_number})")
    db.commit()
