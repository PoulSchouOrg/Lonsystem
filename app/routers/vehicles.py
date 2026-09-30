from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from auth import require_any_permission, require_permission
from database.session import get_db
from database.models import Activity, AppUser, DispatcherGroup, Vehicle
from database.schemas import VehicleCreate, VehicleUpdate, VehicleResponse

router = APIRouter(prefix="/api/vehicles", tags=["vehicles"])


def _resolve_dispatcher_group_id(db: Session, group_id):
    if group_id is None:
        return None
    if not db.query(DispatcherGroup).filter(DispatcherGroup.id == group_id).first():
        raise HTTPException(400, f"Ukendt disponentgruppe-id: {group_id}")
    return group_id


# Vognlisten bruges af flere skærmbilleder (vognnr.-felter i aktiviteter, fast bil/
# fraværsvogn på medarbejderen, Dagsplan, Vagtplan) – ikke kun Vognpark-siden.
_vehicle_list_access = require_any_permission(
    "view_vehicles", "manage_vehicles", "view_calendar", "edit_activities", "vagtplan_view",
    "dagsplan_view", "view_employees", "manage_employees", "payroll_settlement_view", "stamdata",
)


@router.get("", response_model=list[VehicleResponse])
def list_vehicles(current_user: AppUser = Depends(_vehicle_list_access),
                  db: Session = Depends(get_db)):
    return db.query(Vehicle).order_by(Vehicle.registration_number).all()


@router.post("", response_model=VehicleResponse, status_code=201)
def create_vehicle(body: VehicleCreate,
                   current_user: AppUser = Depends(require_permission("manage_vehicles")),
                   db: Session = Depends(get_db)):
    reg = body.registration_number.strip()
    if db.query(Vehicle).filter(Vehicle.registration_number == reg).first():
        raise HTTPException(400, "Registreringsnummer eksisterer allerede")
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
    v = db.query(Vehicle).filter(Vehicle.id == vehicle_id).first()
    if not v:
        raise HTTPException(404, "Vogn ikke fundet")
    if body.registration_number is not None:
        reg = body.registration_number.strip()
        existing = db.query(Vehicle).filter(
            Vehicle.registration_number == reg,
            Vehicle.id != vehicle_id,
        ).first()
        if existing:
            raise HTTPException(400, "Registreringsnummer eksisterer allerede")
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


@router.delete("/{vehicle_id}", status_code=204)
def delete_vehicle(vehicle_id: int,
                   current_user: AppUser = Depends(require_permission("manage_vehicles")),
                   db: Session = Depends(get_db)):
    v = db.query(Vehicle).filter(Vehicle.id == vehicle_id).first()
    if not v:
        raise HTTPException(404, "Vogn ikke fundet")
    if db.query(Activity).filter(Activity.vehicle_registration == v.registration_number).count() > 0:
        raise HTTPException(400, "Vognen er tilknyttet aktiviteter og kan ikke slettes")
    db.delete(v)
    db.commit()
