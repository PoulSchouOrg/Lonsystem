import bcrypt

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from database.models import AppUser
from database.session import get_db

ALL_PERMISSIONS = {
    "payroll":             "Lønkørsel",
    "absence_overview":    "Fraværsoversigt",
    "import_ddd":          "Importer .ddd",
    "user_management":     "Brugerstyring",
    "reopen_period":       "Åbn låst lønperiode",
    "stamdata":            "Stamdata",
    "view_employees":      "Se medarbejdere",
    "manage_employees":    "Tilføj medarbejdere",
    "view_vehicles":       "Se vognpark",
    "manage_vehicles":     "Tilføj vogn",
    "manage_employee_supplements": "Administrér medarbejdertillæg",
    "manage_holidays":     "Administrér helligdage",
    "anciennitet_alert":   "Anciennitetsvarsel",
    "paragraf_56_alert":   "§56-advarsel",
    "approve_activities":  "Godkend aktiviteter",
    "edit_activities":     "Redigér aktiviteter",
    "auto_approve_manual_activities": "Auto-godkend ved oprettelse",
    "manage_auto_approval": "Slå auto-godkendelse til/fra",
    "view_calendar":       "Se aktivitetskalender",
    "toggle_springer":     "Sæt springertillæg",
    "vagtplan_view":       "Se vagtplan",
    "vagtplan_edit_own":   "Redigér egen linje i vagtplan",
    "vagtplan_edit_all":   "Redigér alle linjer i vagtplan",
    "payroll_settlement_view":   "Lønafregning (se)",
    "payroll_settlement_export": "Lønafregning (eksport)",
    "dagsplan_view":       "Se dagsplan",
    "dagsplan_edit":       "Redigere dagsplan",
    "view_cpr":            "Se CPR-nummer",
    "jubilee_alert":       "Jubilæumsadvarsel",
    "elev_alert":          "Elevadvarsel",
    "birthday_alert":      "Fødselsdagsadvarsel",
    "employee_table_view": "Tabelvisning af medarbejdere",
    "employee_export":     "Eksportér medarbejderregister",
}


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def get_current_user(request: Request, db: Session = Depends(get_db)) -> AppUser:
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Ikke logget ind")
    user = db.query(AppUser).filter(AppUser.id == user_id, AppUser.active == True).first()
    if not user:
        raise HTTPException(status_code=401, detail="Ugyldig session")
    return user


def _role_has_permission(db: Session, role_name: str, perm: str) -> bool:
    from database.models import Role
    role = db.query(Role).filter(Role.name == role_name).first()
    if not role:
        return False
    if role.is_system:
        return True
    return perm in (role.permissions or [])


def user_has_permission(db: Session, user: AppUser, perm: str) -> bool:
    return _role_has_permission(db, user.role, perm)


def require_permission(perm: str):
    def checker(request: Request, db: Session = Depends(get_db)) -> AppUser:
        user_id = request.session.get("user_id")
        if not user_id:
            raise HTTPException(status_code=401, detail="Ikke logget ind")
        user = db.query(AppUser).filter(AppUser.id == user_id, AppUser.active == True).first()
        if not user:
            raise HTTPException(status_code=401, detail="Ugyldig session")
        if not _role_has_permission(db, user.role, perm):
            raise HTTPException(status_code=403, detail="Ingen adgang")
        return user
    return checker


def user_has_any_permission(db: Session, user: AppUser, *perms: str) -> bool:
    return any(_role_has_permission(db, user.role, p) for p in perms)


def require_any_permission(*perms: str):
    """Som require_permission, men nøjes med ÉN af de angivne rettigheder – til
    opslag (fx medarbejder-/vognlisten) som flere skærmbilleder har brug for."""
    def checker(request: Request, db: Session = Depends(get_db)) -> AppUser:
        user_id = request.session.get("user_id")
        if not user_id:
            raise HTTPException(status_code=401, detail="Ikke logget ind")
        user = db.query(AppUser).filter(AppUser.id == user_id, AppUser.active == True).first()
        if not user:
            raise HTTPException(status_code=401, detail="Ugyldig session")
        if not any(_role_has_permission(db, user.role, p) for p in perms):
            raise HTTPException(status_code=403, detail="Ingen adgang")
        return user
    return checker


def get_user_permissions(db: Session, role_name: str) -> list:
    from database.models import Role
    role = db.query(Role).filter(Role.name == role_name).first()
    if not role:
        return []
    if role.is_system:
        return list(ALL_PERMISSIONS.keys())
    return role.permissions or []


def log_action(db: Session, user: AppUser, action: str,
               entity_type: str = None, entity_id: int = None, details: str = None):
    from database.models import AuditLog
    entry = AuditLog(
        user_id=user.id,
        user_initials=user.initials,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=details,
    )
    db.add(entry)
