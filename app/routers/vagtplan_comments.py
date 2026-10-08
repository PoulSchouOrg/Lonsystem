from datetime import date as date_type
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from auth import get_current_user, log_action, require_permission, user_has_permission
from calculators.pay_period import get_or_create_period_for_date
from routers.activities import in_activity_overview
from database.models import AppUser, Employee, PayPeriodStatus, VagtplanComment
from database.schemas import VagtplanCommentCreate, VagtplanCommentResponse
from database.session import get_db

router = APIRouter(prefix="/api/vagtplan-comments", tags=["vagtplan-comments"])


def _has_edit_access(db: Session, current_user: AppUser, emp: Employee) -> bool:
    if user_has_permission(db, current_user, "vagtplan_edit_all"):
        return True
    if user_has_permission(db, current_user, "vagtplan_edit_own"):
        return bool(emp.initials) and emp.initials.strip().lower() == current_user.initials.strip().lower()
    return False


@router.get("", response_model=list[VagtplanCommentResponse])
def list_comments(
    date_from: str,
    date_to: str,
    employee_id: Optional[int] = None,
    current_user: AppUser = Depends(require_permission("vagtplan_view")),
    db: Session = Depends(get_db),
):
    q = db.query(VagtplanComment).filter(
        VagtplanComment.date >= date_type.fromisoformat(date_from),
        VagtplanComment.date <= date_type.fromisoformat(date_to),
    )
    if employee_id:
        q = q.filter(VagtplanComment.employee_id == employee_id)
    return q.all()


@router.post("", response_model=VagtplanCommentResponse, status_code=201)
def create_comment(body: VagtplanCommentCreate,
                   current_user: AppUser = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    emp = db.query(Employee).filter(Employee.id == body.employee_id).first()
    if not emp:
        raise HTTPException(404, "Medarbejder ikke fundet")
    if not _has_edit_access(db, current_user, emp):
        raise HTTPException(403, "Ingen redigeringsret til Vagtplan for denne medarbejder")
    # Ingen kommentarer (oprettelse eller rettelse) på datoer i en låst lønperiode –
    # bekræftet af bruger 2026-09-30.
    # Gælder kun medarbejdere i Aktivitetsoversigten (2026-10-08).
    if in_activity_overview(emp) and get_or_create_period_for_date(body.date, db).status == PayPeriodStatus.closed:
        raise HTTPException(
            400, f"Kan ikke gemme kommentar d. {body.date.strftime('%d-%m-%Y')} – lønperioden er låst"
        )

    existing =db.query(VagtplanComment).filter(
        VagtplanComment.employee_id == body.employee_id,
        VagtplanComment.date == body.date,
    ).first()
    if existing:
        existing.text = body.text
        existing.created_by = current_user.initials
        log_action(db, current_user, "update_vagtplan_comment", "vagtplan_comment", existing.id)
        db.commit()
        db.refresh(existing)
        return existing

    comment = VagtplanComment(
        employee_id=body.employee_id, date=body.date, text=body.text,
        created_by=current_user.initials,
    )
    db.add(comment)
    db.flush()
    log_action(db, current_user, "create_vagtplan_comment", "vagtplan_comment", comment.id)
    db.commit()
    db.refresh(comment)
    return comment


@router.delete("/{comment_id}", status_code=204)
def delete_comment(comment_id: int,
                   current_user: AppUser = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    comment = db.query(VagtplanComment).filter(VagtplanComment.id == comment_id).first()
    if not comment:
        raise HTTPException(404, "Kommentar ikke fundet")
    emp = db.query(Employee).filter(Employee.id == comment.employee_id).first()
    if not emp or not _has_edit_access(db, current_user, emp):
        raise HTTPException(403, "Ingen redigeringsret til Vagtplan for denne medarbejder")
    if in_activity_overview(emp) and get_or_create_period_for_date(comment.date, db).status == PayPeriodStatus.closed:
        raise HTTPException(
            400, f"Kan ikke slette kommentar d. {comment.date.strftime('%d-%m-%Y')} – lønperioden er låst"
        )
    log_action(db, current_user, "delete_vagtplan_comment", "vagtplan_comment", comment.id)
    db.delete(comment)
    db.commit()
