import logging
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from auth import get_current_user, require_any_permission, require_permission, user_has_any_permission
from calculators.rates_loader import (
    load_agreement_types_from_db,
    seniority_variant_exists_from_db,
)
from database.session import get_db
from utils.natural_sort import natural_key
from database.models import AppUser, DispatcherGroup, Employee, MasterAgreementKind, Paragraf56AlertDismissal, Vehicle
from database.schemas import (
    AnciennitetsAlert,
    DispatcherGroupResponse,
    EmployeeCreate,
    EmployeeResponse,
    EmployeeUpdate,
    Paragraf56Alert,
    Paragraf56AlertDismiss,
    Paragraf56AlertsResponse,
    WorkSchedule,
)

router = APIRouter(prefix="/api/employees", tags=["employees"])


def _months_employed(hire_date: date, today: date = None) -> int:
    if today is None:
        today = date.today()
    months = (today.year - hire_date.year) * 12 + (today.month - hire_date.month)
    if today.day < hire_date.day:
        months -= 1
    return max(0, months)


def _validate_paragraf_56(active: bool, start: Optional[date], end: Optional[date]) -> tuple:
    if not active:
        return None, None
    if not start or not end:
        raise HTTPException(400, "Start- og slutdato for §56 skal udfyldes")
    if end < start:
        raise HTTPException(400, "§56 slutdato skal være efter startdato")
    return start, end


def _sweep_expired_paragraf_56(db: Session) -> None:
    """Deaktiverer automatisk §56 for medarbejdere hvor slutdatoen er overskredet.
    Kører uafhængigt af paragraf_56_alert-tilladelsen (se list_employees()), så
    deaktiveringen sker uanset hvilke roller der har advarslen slået til. Datoerne
    bevares bevidst (ikke nulstillet), så de kan indgå i "udløbet"-informationen."""
    today = date.today()
    expired = db.query(Employee).filter(
        Employee.paragraf_56 == True,
        Employee.paragraf_56_end_date.isnot(None),
        Employee.paragraf_56_end_date < today,
    ).all()
    for emp in expired:
        emp.paragraf_56 = False
    if expired:
        db.commit()


def _paragraf56_alert(emp: Employee) -> Paragraf56Alert:
    return Paragraf56Alert(
        employee_id=emp.id,
        employee_name=emp.name,
        employee_number=emp.employee_number,
        paragraf_56_end_date=emp.paragraf_56_end_date,
    )


def _to_response(emp: Employee, db) -> EmployeeResponse:
    try:
        rate = float(load_agreement_types_from_db(db).get(emp.agreement_type, 0)) or None
    except Exception:
        rate = None
    return EmployeeResponse(
        id=emp.id,
        employee_number=emp.employee_number,
        tachograph_card_number=emp.tachograph_card_number,
        first_name=emp.first_name,
        last_name=emp.last_name,
        name=emp.name,
        address=emp.address,
        postal_code=emp.postal_code,
        email=emp.email,
        phone=emp.phone,
        mobile=emp.mobile,
        agreement_kind=emp.agreement_kind,
        agreement_type=emp.agreement_type,
        hourly_rate=rate,
        fuldloennet=emp.fuldloennet,
        active=emp.active,
        hire_date=emp.hire_date,
        termination_date=emp.termination_date,
        work_schedule=WorkSchedule(**emp.work_schedule),
        months_employed=_months_employed(emp.hire_date),
        dispatcher_group=DispatcherGroupResponse.model_validate(emp.dispatcher_group) if emp.dispatcher_group else None,
        cvr_number=emp.cvr_number,
        anciennitet_dismissed_at=emp.anciennitet_dismissed_at,
        terminsdato=emp.terminsdato,
        initials=emp.initials,
        paragraf_56=emp.paragraf_56,
        paragraf_56_start_date=emp.paragraf_56_start_date,
        paragraf_56_end_date=emp.paragraf_56_end_date,
        afloeser=emp.afloeser,
        ot_extra_alle_timer=emp.ot_extra_alle_timer,
        fast_bil=emp.fast_bil,
        fast_bil_vehicle_id=emp.fast_bil_vehicle_id,
        fast_bil_vehicle_number=emp.fast_bil_vehicle.vehicle_number if emp.fast_bil_vehicle else None,
        absence_vehicle_id=emp.absence_vehicle_id,
        absence_vehicle_number=emp.absence_vehicle.vehicle_number if emp.absence_vehicle else None,
    )


# Medarbejderlisten (navne, grupper, skema m.m.) bruges af alle skærmbilleder der viser
# medarbejdere – men kontakt-/løn-/kortoplysninger kun med 'Se medarbejdere'.
_employee_list_access = require_any_permission(
    "view_employees", "manage_employees", "view_calendar", "edit_activities", "approve_activities",
    "vagtplan_view", "dagsplan_view", "payroll", "payroll_settlement_view", "absence_overview",
    "manage_employee_supplements", "stamdata",
)
_PRIVATE_EMPLOYEE_FIELDS = (
    "tachograph_card_number", "address", "postal_code", "email", "phone", "mobile",
    "hourly_rate", "cvr_number",
)


def _visible_response(emp: Employee, db, current_user: AppUser) -> EmployeeResponse:
    """Fuld stamdata kun med 'Se medarbejdere'/'Tilføj medarbejdere' – ellers
    udelades kontakt-, løn- og førerkortoplysninger."""
    resp = _to_response(emp, db)
    if not user_has_any_permission(db, current_user, "view_employees", "manage_employees"):
        for field in _PRIVATE_EMPLOYEE_FIELDS:
            setattr(resp, field, None)
    return resp


@router.get("", response_model=list[EmployeeResponse])
def list_employees(active_only: bool = True,
                   current_user: AppUser = Depends(_employee_list_access),
                   db: Session = Depends(get_db)):
    _sweep_expired_paragraf_56(db)
    q = db.query(Employee)
    if active_only:
        q = q.filter(Employee.active == True)
    return [_visible_response(e, db, current_user)
            for e in q.order_by(Employee.last_name, Employee.first_name).all()]


@router.get("/agreement-types")
def agreement_types(current_user: AppUser = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    """Overenskomsttyper og timesatser fra stamdata-tabellen."""
    try:
        types = load_agreement_types_from_db(db)
    except Exception as e:
        logging.error(f"Overenskomsttyper kunne ikke indlæses: {e}")
        raise HTTPException(500, "Overenskomsttyper kunne ikke indlæses – kontakt administrator")
    return [{"name": k, "hourly_rate": float(v)} for k, v in types.items()]


@router.get("/agreement-kinds")
def agreement_kinds(current_user: AppUser = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    """Aktive Aftale-typer fra Stamdata – bruges til at udfylde medarbejder-modalens dropdown."""
    rows = db.query(MasterAgreementKind).filter(MasterAgreementKind.is_active == True).order_by(
        MasterAgreementKind.sort_order, MasterAgreementKind.label
    ).all()
    return [
        {"key": r.key, "label": r.label, "requires_agreement_type": r.requires_agreement_type}
        for r in rows
    ]


def _agreement_type_required(db: Session, agreement_kind: str) -> bool:
    row = db.query(MasterAgreementKind).filter(MasterAgreementKind.key == agreement_kind).first()
    return row.requires_agreement_type if row else True


@router.get("/dispatcher-groups", response_model=list[DispatcherGroupResponse])
def dispatcher_groups(current_user: AppUser = Depends(get_current_user),
                      db: Session = Depends(get_db)):
    """Liste over disponentgrupper – bruges til at udfylde medarbejder-modalens afkrydsningsliste."""
    return sorted(db.query(DispatcherGroup).all(), key=lambda g: natural_key(g.name))


def _resolve_dispatcher_group(db: Session, group_id: Optional[int]) -> Optional[DispatcherGroup]:
    if group_id is None:
        return None
    group = db.query(DispatcherGroup).filter(DispatcherGroup.id == group_id).first()
    if not group:
        raise HTTPException(400, f"Ukendt disponentgruppe-id: {group_id}")
    return group


def _resolve_vehicle_id(db: Session, vehicle_id: Optional[int]) -> Optional[int]:
    if vehicle_id is None:
        return None
    if not db.query(Vehicle).filter(Vehicle.id == vehicle_id).first():
        raise HTTPException(400, f"Ukendt vogn-id: {vehicle_id}")
    return vehicle_id


@router.post("", response_model=EmployeeResponse, status_code=201)
def create_employee(body: EmployeeCreate,
                    current_user: AppUser = Depends(require_permission("manage_employees")),
                    db: Session = Depends(get_db)):
    if db.query(Employee).filter(Employee.employee_number == body.employee_number).first():
        raise HTTPException(400, "Lønnummer eksisterer allerede")
    if body.tachograph_card_number:
        if db.query(Employee).filter(Employee.tachograph_card_number == body.tachograph_card_number).first():
            raise HTTPException(400, "Førerkortnummer eksisterer allerede")
    if not db.query(MasterAgreementKind).filter(MasterAgreementKind.key == body.agreement_kind).first():
        raise HTTPException(400, f"Ukendt aftaletype: {body.agreement_kind}")
    if _agreement_type_required(db, body.agreement_kind):
        if not body.agreement_type or body.agreement_type not in load_agreement_types_from_db(db):
            raise HTTPException(400, f"Ukendt overenskomsttype: {body.agreement_type}")
    else:
        body.agreement_type = ""
    body.paragraf_56_start_date, body.paragraf_56_end_date = _validate_paragraf_56(
        body.paragraf_56, body.paragraf_56_start_date, body.paragraf_56_end_date
    )

    data = body.model_dump(exclude={"dispatcher_group_id", "fast_bil_vehicle_id", "absence_vehicle_id"})
    data["work_schedule"] = body.work_schedule.model_dump()
    data["fast_bil_vehicle_id"] = _resolve_vehicle_id(db, body.fast_bil_vehicle_id)
    data["absence_vehicle_id"] = _resolve_vehicle_id(db, body.absence_vehicle_id)
    emp = Employee(**data)
    emp.dispatcher_group = _resolve_dispatcher_group(db, body.dispatcher_group_id)
    db.add(emp)
    db.commit()
    db.refresh(emp)
    return _to_response(emp, db)


@router.get("/anciennitet-alerts", response_model=list[AnciennitetsAlert])
def anciennitet_alerts(current_user: AppUser = Depends(require_permission("anciennitet_alert")),
                       db: Session = Depends(get_db)):
    """
    Medarbejdere der har opnået 9 måneders anciennitet, men hvor
    overenskomsttypen har en 9-mdr-variant, de endnu ikke er flyttet til.
    Springer medarbejdere over, hvor advarslen er afvist server-side.
    """
    alerts = []
    employees = db.query(Employee).filter(Employee.active == True).all()
    for emp in employees:
        months = _months_employed(emp.hire_date)
        if months < 9:
            continue
        if emp.anciennitet_dismissed_at is not None:
            continue
        variant = seniority_variant_exists_from_db(db, emp.agreement_type)
        if variant:
            alerts.append(AnciennitetsAlert(
                employee_id=emp.id,
                employee_name=emp.name,
                employee_number=emp.employee_number,
                hire_date=emp.hire_date,
                months_employed=months,
                suggested_agreement_type=variant,
            ))
    return alerts


@router.post("/{employee_id}/dismiss-anciennitet", status_code=204)
def dismiss_anciennitet(employee_id: int,
                        current_user: AppUser = Depends(require_permission("anciennitet_alert")),
                        db: Session = Depends(get_db)):
    """Marker anciennitetsadvarsel som afvist for denne medarbejder."""
    emp = db.query(Employee).filter(Employee.id == employee_id).first()
    if not emp:
        raise HTTPException(404, "Medarbejder ikke fundet")
    emp.anciennitet_dismissed_at = datetime.utcnow()
    db.commit()


@router.get("/paragraf56-alerts", response_model=Paragraf56AlertsResponse)
def paragraf56_alerts(current_user: AppUser = Depends(require_permission("paragraf_56_alert")),
                      db: Session = Depends(get_db)):
    """
    §56-advarsler for den aktuelle bruger: 'upcoming' (slutdato inden for 30 dage,
    §56 stadig aktiv) og 'expired' (§56 netop auto-deaktiveret pga. overskredet
    slutdato). Afvisning er pr. bruger (Paragraf56AlertDismissal), ikke global.
    """
    _sweep_expired_paragraf_56(db)
    today = date.today()
    window = today + timedelta(days=30)
    dismissed = {
        (d.employee_id, d.alert_type)
        for d in db.query(Paragraf56AlertDismissal).filter(
            Paragraf56AlertDismissal.user_id == current_user.id
        ).all()
    }
    upcoming = [
        _paragraf56_alert(e) for e in db.query(Employee).filter(
            Employee.paragraf_56 == True,
            Employee.paragraf_56_end_date.isnot(None),
            Employee.paragraf_56_end_date >= today,
            Employee.paragraf_56_end_date <= window,
        ).all()
        if (e.id, "upcoming") not in dismissed
    ]
    expired = [
        _paragraf56_alert(e) for e in db.query(Employee).filter(
            Employee.paragraf_56 == False,
            Employee.paragraf_56_end_date.isnot(None),
            Employee.paragraf_56_end_date < today,
        ).all()
        if (e.id, "expired") not in dismissed
    ]
    return Paragraf56AlertsResponse(upcoming=upcoming, expired=expired)


@router.post("/{employee_id}/dismiss-paragraf56-alert", status_code=204)
def dismiss_paragraf56_alert(employee_id: int, body: Paragraf56AlertDismiss,
                             current_user: AppUser = Depends(require_permission("paragraf_56_alert")),
                             db: Session = Depends(get_db)):
    """Marker en §56-advarsel som afvist for DEN AKTUELLE BRUGER (ikke globalt)."""
    if body.alert_type not in ("upcoming", "expired"):
        raise HTTPException(400, f"Ukendt alert_type: {body.alert_type}")
    existing = db.query(Paragraf56AlertDismissal).filter(
        Paragraf56AlertDismissal.employee_id == employee_id,
        Paragraf56AlertDismissal.user_id == current_user.id,
        Paragraf56AlertDismissal.alert_type == body.alert_type,
    ).first()
    if not existing:
        db.add(Paragraf56AlertDismissal(
            employee_id=employee_id, user_id=current_user.id, alert_type=body.alert_type
        ))
        db.commit()


@router.get("/{employee_id}", response_model=EmployeeResponse)
def get_employee(employee_id: int,
                 current_user: AppUser = Depends(_employee_list_access),
                 db: Session = Depends(get_db)):
    emp = db.query(Employee).filter(Employee.id == employee_id).first()
    if not emp:
        raise HTTPException(404, "Medarbejder ikke fundet")
    return _visible_response(emp, db, current_user)


_CLEARABLE_EMPLOYEE_FIELDS = (
    "tachograph_card_number", "initials", "address", "postal_code",
    "email", "phone", "mobile",
)


@router.patch("/{employee_id}", response_model=EmployeeResponse)
def update_employee(employee_id: int, body: EmployeeUpdate,
                    current_user: AppUser = Depends(require_permission("manage_employees")),
                    db: Session = Depends(get_db)):
    emp = db.query(Employee).filter(Employee.id == employee_id).first()
    if not emp:
        raise HTTPException(404, "Medarbejder ikke fundet")
    if body.agreement_kind and not db.query(MasterAgreementKind).filter(
        MasterAgreementKind.key == body.agreement_kind
    ).first():
        raise HTTPException(400, f"Ukendt aftaletype: {body.agreement_kind}")
    effective_kind = body.agreement_kind or emp.agreement_kind
    effective_agreement_type = (
        body.agreement_type if body.agreement_type is not None else emp.agreement_type
    )
    if _agreement_type_required(db, effective_kind):
        if not effective_agreement_type or effective_agreement_type not in load_agreement_types_from_db(db):
            raise HTTPException(400, f"Ukendt overenskomsttype: {effective_agreement_type}")
    elif body.agreement_type is None and body.agreement_kind and body.agreement_kind != emp.agreement_kind:
        # Skiftes til en type der ikke kræver Overenskomsttype, uden at et nyt
        # felt er angivet samtidig – nulstil det gemte felt til "ikke relevant".
        body.agreement_type = ""
    old_agreement_type = emp.agreement_type
    _paragraf56_excludes = {"dispatcher_group_id", "fast_bil_vehicle_id", "absence_vehicle_id",
                            "paragraf_56", "paragraf_56_start_date", "paragraf_56_end_date"}
    for field_name, value in body.model_dump(exclude_none=True, exclude=_paragraf56_excludes).items():
        if field_name == "work_schedule":
            value = body.work_schedule.model_dump()
        setattr(emp, field_name, value)
    # Valgfri tekstfelter der sendes som tomme (null) skal tømmes – ikke bevare den
    # gamle værdi, som exclude_none ovenfor ellers ville gøre.
    for field_name in _CLEARABLE_EMPLOYEE_FIELDS:
        if field_name in body.model_fields_set and getattr(body, field_name) is None:
            setattr(emp, field_name, None)
    if "dispatcher_group_id" in body.model_fields_set:
        emp.dispatcher_group = _resolve_dispatcher_group(db, body.dispatcher_group_id)
    if "fast_bil_vehicle_id" in body.model_fields_set:
        emp.fast_bil_vehicle_id = _resolve_vehicle_id(db, body.fast_bil_vehicle_id)
    if "absence_vehicle_id" in body.model_fields_set:
        emp.absence_vehicle_id = _resolve_vehicle_id(db, body.absence_vehicle_id)
    if "paragraf_56" in body.model_fields_set:
        start, end = _validate_paragraf_56(
            bool(body.paragraf_56), body.paragraf_56_start_date, body.paragraf_56_end_date
        )
        if end != emp.paragraf_56_end_date:
            db.query(Paragraf56AlertDismissal).filter(
                Paragraf56AlertDismissal.employee_id == emp.id
            ).delete()
        emp.paragraf_56 = bool(body.paragraf_56)
        emp.paragraf_56_start_date = start
        emp.paragraf_56_end_date = end
    # Nulstil afvist anciennitetsadvarsel hvis overenskomsttype er ændret
    if body.agreement_type and body.agreement_type != old_agreement_type:
        emp.anciennitet_dismissed_at = None
    db.commit()
    db.refresh(emp)
    return _to_response(emp, db)
