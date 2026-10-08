from datetime import date as date_type
from typing import Optional

from sqlalchemy.orm import Session

from database.models import DailyPlanAssignment, Employee, Vehicle

# Typer der ikke er fravær, selvom de ikke er "normal" (2026-10-08): en
# overnatning er ikke et fravær i Dagsplanen (ingen rød farve/advarsel).
NON_ABSENCE_TYPES = ("normal", "overnatning", "dob_overnatning")


def dagsplan_vehicles_query(db: Session):
    """Vognene i Dagsplanens vognkolonne: Vognpark-markerede, ikke slettede."""
    return db.query(Vehicle).filter(Vehicle.vognpark == True, Vehicle.deleted_at.is_(None))


def fast_bil_defaults(db: Session) -> dict[int, Employee]:
    """vehicle_id -> den AKTIVE medarbejder der foreslås som Fast bil-chauffør.
    Deler flere medarbejdere samme faste vogn, vinder laveste id (deterministisk)."""
    result: dict[int, Employee] = {}
    for e in (
        db.query(Employee)
        .filter(Employee.active == True, Employee.fast_bil == True, Employee.fast_bil_vehicle_id.isnot(None))
        .order_by(Employee.id)
    ):
        result.setdefault(e.fast_bil_vehicle_id, e)
    return result


def effective_vehicle_for_employee(db: Session, employee_id: int, d: date_type) -> Optional[Vehicle]:
    """Vognen chaufføren reelt står på i Dagsplanen den givne dag - præcis
    samme regel som Dagsplan-tabellen (_build_vehicle_rows):

    - Kun vogne der vises i Dagsplanen (Vognpark-markeret, ikke slettet).
    - En gemt tildeling for dagen vinder altid.
    - Ellers medarbejderens "Fast bil", men kun hvis medarbejderen er aktiv,
      og vognen IKKE har en gemt tildeling den dag (givet til en anden eller
      bevidst ryddet).
    """
    assignment = (
        db.query(DailyPlanAssignment)
        .join(Vehicle, Vehicle.id == DailyPlanAssignment.vehicle_id)
        .filter(
            DailyPlanAssignment.date == d,
            DailyPlanAssignment.employee_id == employee_id,
            Vehicle.vognpark == True,
            Vehicle.deleted_at.is_(None),
        )
        .order_by(Vehicle.vehicle_number)
        .first()
    )
    if assignment:
        return assignment.vehicle
    emp = db.query(Employee).filter(Employee.id == employee_id).first()
    if not emp or not emp.fast_bil_vehicle_id:
        return None
    vehicle = dagsplan_vehicles_query(db).filter(Vehicle.id == emp.fast_bil_vehicle_id).first()
    if not vehicle or fast_bil_defaults(db).get(vehicle.id) is not emp:
        return None
    saved = db.query(DailyPlanAssignment).filter(
        DailyPlanAssignment.date == d, DailyPlanAssignment.vehicle_id == vehicle.id,
    ).first()
    if saved is not None:
        return None
    return vehicle
