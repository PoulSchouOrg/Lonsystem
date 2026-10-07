"""Gentagelse i Vagtplan (spec 2026-10-07-vagtplan-gentagelse). Serier oprettes,
forlænges/forkortes (kun i enden) og slettes samlet server-side. Hver forekomst er en
almindelig Activity (source=vagtplan) og/eller VagtplanComment med series_id."""
from datetime import date, datetime, time, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from auth import get_current_user, log_action, require_any_permission
from calculators.pay_period import get_or_create_period_for_date
from calculators.recurrence import describe, occurrence_dates, one_year_after
from database.models import (
    Activity, ActivitySource, ActivityStatus, AppUser, Employee, Holiday, PayPeriodStatus,
    VagtplanComment, VagtplanSeries,
)
from database.schemas import (
    ActivityCreate, VagtplanSeriesCreate, VagtplanSeriesCreateResult, VagtplanSeriesDeleteResult,
    VagtplanSeriesEndUpdate, VagtplanSeriesPreview, VagtplanSeriesResponse, VagtplanSeriesUpdateResult,
)
from database.session import get_db
from routers.activities import (
    _BACKEND_ONLY_TYPES, _COUNT_BASED_RANGE_TYPES, _HIDDEN_FROM_TYPE_PICKER,
    _create_manual_activity_row, _has_vagtplan_edit_access, _range_day_defaults,
)

router = APIRouter(prefix="/api/vagtplan-series", tags=["vagtplan-series"])

_view_access = require_any_permission("view_calendar", "vagtplan_view")


def _fmt(d: date) -> str:
    return d.strftime("%d-%m-%Y")


def _holidays(db: Session) -> set[date]:
    return {h.date for h in db.query(Holiday).all()}


def _is_locked(db: Session, d: date) -> bool:
    # Opretter også perioden hvis den mangler (get_or_create committer) – derfor
    # kaldes dette for ALLE datoer FØR noget oprettes, så senere opslag ikke committer
    # en halvt oprettet serie.
    return get_or_create_period_for_date(d, db).status == PayPeriodStatus.closed


def _employee_with_access(db: Session, user: AppUser, employee_id: int) -> Employee:
    emp = db.query(Employee).filter(Employee.id == employee_id).first()
    if not emp:
        raise HTTPException(404, "Medarbejder ikke fundet")
    if not _has_vagtplan_edit_access(db, user, emp):
        raise HTTPException(403, "Ingen redigeringsret til Vagtplan for denne medarbejder")
    return emp


def _load_series_with_access(db: Session, user: AppUser, series_id: int) -> tuple[VagtplanSeries, Employee]:
    series = db.query(VagtplanSeries).filter(VagtplanSeries.id == series_id).first()
    if not series:
        raise HTTPException(404, "Gentagelse ikke fundet")
    return series, _employee_with_access(db, user, series.employee_id)


def _interval(body: VagtplanSeriesCreate) -> int:
    return body.week_interval if body.freq == "weekly" else 1


def _validate_type(activity_type):
    if activity_type is None:
        return
    if activity_type == "normal":
        raise HTTPException(400, "Normal tid kan ikke gentages fra Vagtplan")
    if activity_type in _BACKEND_ONLY_TYPES or activity_type in _HIDDEN_FROM_TYPE_PICKER:
        raise HTTPException(400, "Denne aktivitetstype kan ikke angives manuelt")


def _occurrence_dates_of(db: Session, series: VagtplanSeries) -> list[date]:
    """Datoer der i dag har en forekomst (aktivitet og/eller kommentar) i serien."""
    act_dates = {a.start_time.date() for a in db.query(Activity).filter(Activity.series_id == series.id)}
    com_dates = {c.date for c in db.query(VagtplanComment).filter(VagtplanComment.series_id == series.id)}
    return sorted(act_dates | com_dates)


def _series_response(db: Session, series: VagtplanSeries) -> VagtplanSeriesResponse:
    dates = _occurrence_dates_of(db, series)
    return VagtplanSeriesResponse(
        id=series.id, employee_id=series.employee_id, activity_type=series.activity_type,
        comment_text=series.comment_text, freq=series.freq, weekdays=series.weekday_list,
        week_interval=series.week_interval or 1, start_date=series.start_date, end_mode=series.end_mode, end_count=series.end_count,
        end_date=series.end_date,
        description=describe(series.freq, series.weekday_list, series.start_date, series.week_interval or 1),
        occurrence_count=len(dates), first_date=dates[0] if dates else None,
        last_date=dates[-1] if dates else None,
    )


def _day_hours(activity_type: str, d: date, emp: Employee):
    """(start, slut) for fraværsforekomsten eller None hvis dagen springes over (ingen
    garanterede timer). Samme regler som oprettelse af en fraværsperiode."""
    if activity_type in _COUNT_BASED_RANGE_TYPES:
        start = datetime.combine(d, time(0, 0))
        return start, start
    hours = _range_day_defaults(activity_type, d, emp)
    if hours is None:
        return None
    start = datetime.combine(d, time(6, 0))
    return start, start + timedelta(minutes=round(hours * 60))


def _materialize(db: Session, user: AppUser, emp: Employee, series: VagtplanSeries,
                 dates: list[date]) -> tuple[int, list[date], list[date]]:
    """Opretter forekomster på datoerne. Returnerer (antal dage med noget oprettet,
    kommentar-konflikter, dage uden garanterede timer). Hverken log eller commit."""
    created, skipped_comments, skipped_no_hours = 0, [], []
    for d in dates:
        made = False
        if series.activity_type:
            times = _day_hours(series.activity_type, d, emp)
            if times is None:
                skipped_no_hours.append(d)
                continue
            body = ActivityCreate(
                employee_id=emp.id, activity_type=series.activity_type,
                start_time=times[0], end_time=times[1], terminsdato=series.terminsdato,
                vehicle_number=series.vehicle_number, source="vagtplan",
            )
            _create_manual_activity_row(db, user, emp, body, ActivitySource.vagtplan, series_id=series.id)
            made = True
        if series.comment_text:
            exists = db.query(VagtplanComment).filter(
                VagtplanComment.employee_id == emp.id, VagtplanComment.date == d).first()
            if exists:
                skipped_comments.append(d)
            else:
                db.add(VagtplanComment(employee_id=emp.id, date=d, text=series.comment_text,
                                       created_by=user.initials, series_id=series.id))
                made = True
        created += int(made)
    return created, skipped_comments, skipped_no_hours


def _plan(db: Session, body: VagtplanSeriesCreate, emp: Employee) -> VagtplanSeriesPreview:
    _validate_type(body.activity_type)
    if body.end_mode == "date" and body.end_date > one_year_after(body.start_date):
        raise HTTPException(400, f"Slutdato må højst være {_fmt(one_year_after(body.start_date))} (1 år frem)")
    dates = occurrence_dates(body.freq, body.weekdays, body.start_date, body.end_mode,
                             body.end_count, body.end_date, _holidays(db),
                             skip_holidays=bool(body.activity_type), interval=_interval(body))
    if not dates:
        raise HTTPException(400, "Ingen forekomster i den valgte periode")
    locked = [d for d in dates if _is_locked(db, d)]
    comment_conflicts = []
    if body.comment_text:
        existing = {c.date for c in db.query(VagtplanComment).filter(
            VagtplanComment.employee_id == emp.id,
            VagtplanComment.date >= dates[0], VagtplanComment.date <= dates[-1])}
        comment_conflicts = [d for d in dates if d in existing]
    driving, no_hours = [], []
    if body.activity_type:
        normal_dates = {a.start_time.date() for a in db.query(Activity).filter(
            Activity.employee_id == emp.id, Activity.activity_type == "normal",
            Activity.status != ActivityStatus.deactivated,
            Activity.start_time >= datetime.combine(dates[0], time(0, 0)),
            Activity.start_time < datetime.combine(dates[-1] + timedelta(days=1), time(0, 0)))}
        driving = [d for d in dates if d in normal_dates]
        no_hours = [d for d in dates if _day_hours(body.activity_type, d, emp) is None]
    return VagtplanSeriesPreview(
        dates=dates, locked_dates=locked, comment_conflicts=comment_conflicts,
        driving_conflicts=driving, skipped_no_hours=no_hours,
        description=describe(body.freq, body.weekdays, body.start_date, _interval(body)),
    )


@router.post("/preview", response_model=VagtplanSeriesPreview)
def preview_series(body: VagtplanSeriesCreate,
                   current_user: AppUser = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    emp = _employee_with_access(db, current_user, body.employee_id)
    return _plan(db, body, emp)


@router.post("", response_model=VagtplanSeriesCreateResult, status_code=201)
def create_series(body: VagtplanSeriesCreate,
                  current_user: AppUser = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    emp = _employee_with_access(db, current_user, body.employee_id)
    plan = _plan(db, body, emp)
    if plan.locked_dates:
        raise HTTPException(400, "Kan ikke oprette – lønperioden er låst for: "
                            + ", ".join(_fmt(d) for d in plan.locked_dates))
    if body.activity_type == "barsel" and body.terminsdato is None:
        raise HTTPException(400, "Terminsdato er påkrævet for barsel")
    series = VagtplanSeries(
        employee_id=emp.id, activity_type=body.activity_type, comment_text=body.comment_text,
        vehicle_number=body.vehicle_number, terminsdato=body.terminsdato, freq=body.freq,
        weekdays=",".join(str(w) for w in sorted(set(body.weekdays))) if body.freq == "weekly" else None,
        week_interval=_interval(body), start_date=body.start_date, end_mode=body.end_mode,
        end_count=body.end_count if body.end_mode == "count" else None,
        end_date=body.end_date if body.end_mode == "date" else None,
        created_by=current_user.initials,
    )
    db.add(series)
    db.flush()
    created, skipped_comments, skipped_no_hours = _materialize(db, current_user, emp, series, plan.dates)
    if created == 0:
        db.rollback()
        raise HTTPException(400, "Ingen forekomster blev oprettet")
    log_action(db, current_user, "create_vagtplan_series", "vagtplan_series", series.id,
               f"{emp.name}: {plan.description}, {created} forekomster fra {_fmt(plan.dates[0])}")
    db.commit()
    db.refresh(series)
    return VagtplanSeriesCreateResult(series=_series_response(db, series), created=created,
                                      skipped_comments=skipped_comments, skipped_no_hours=skipped_no_hours)


@router.get("/{series_id}", response_model=VagtplanSeriesResponse)
def get_series(series_id: int,
               current_user: AppUser = Depends(_view_access),
               db: Session = Depends(get_db)):
    series = db.query(VagtplanSeries).filter(VagtplanSeries.id == series_id).first()
    if not series:
        raise HTTPException(404, "Gentagelse ikke fundet")
    return _series_response(db, series)


def _delete_occurrence_rows(db: Session, series: VagtplanSeries, d: date) -> None:
    start = datetime.combine(d, time(0, 0))
    for a in db.query(Activity).filter(Activity.series_id == series.id,
                                       Activity.start_time >= start,
                                       Activity.start_time < start + timedelta(days=1)):
        db.delete(a)
    for c in db.query(VagtplanComment).filter(VagtplanComment.series_id == series.id,
                                              VagtplanComment.date == d):
        db.delete(c)


def _assert_removable(db: Session, series: VagtplanSeries, d: date) -> None:
    if _is_locked(db, d):
        raise HTTPException(400, f"Kan ikke fjerne {_fmt(d)} – lønperioden er låst")
    start = datetime.combine(d, time(0, 0))
    for a in db.query(Activity).filter(Activity.series_id == series.id,
                                       Activity.start_time >= start,
                                       Activity.start_time < start + timedelta(days=1)):
        if a.split_children:
            raise HTTPException(400, f"Kan ikke fjerne {_fmt(d)} – aktiviteten er splittet, fortryd splittet først")


@router.patch("/{series_id}", response_model=VagtplanSeriesUpdateResult)
def update_series_end(series_id: int, body: VagtplanSeriesEndUpdate,
                      current_user: AppUser = Depends(get_current_user),
                      db: Session = Depends(get_db)):
    """Ændrer seriens slutning – kun i enden: tilføjer efter sidste forekomst eller
    fjerner fra enden. Alt-eller-intet ved låste dage."""
    series, emp = _load_series_with_access(db, current_user, series_id)
    existing = _occurrence_dates_of(db, series)
    if not existing:
        raise HTTPException(400, "Serien har ingen forekomster")
    last = existing[-1]
    limit = one_year_after(series.start_date)

    if body.end_mode == "count":
        to_remove = existing[body.end_count:] if body.end_count < len(existing) else []
    else:
        if body.end_date > limit:
            raise HTTPException(400, f"Slutdato må højst være {_fmt(limit)} (1 år fra seriens start)")
        to_remove = [d for d in existing if d > body.end_date]
    if len(to_remove) == len(existing):
        raise HTTPException(400, "Serien skal have mindst én forekomst – brug 'Slet hele serien'")

    to_add: list[date] = []
    if not to_remove:
        to_add = occurrence_dates(series.freq, series.weekday_list, series.start_date, body.end_mode,
                                  body.end_count, body.end_date, _holidays(db),
                                  skip_holidays=bool(series.activity_type),
                                  after=last, existing_count=len(existing),
                                  interval=series.week_interval or 1)

    # Validér ALT før noget ændres
    for d in to_remove:
        _assert_removable(db, series, d)
    locked_add = [d for d in to_add if _is_locked(db, d)]
    if locked_add:
        raise HTTPException(400, "Kan ikke forlænge – lønperioden er låst for: "
                            + ", ".join(_fmt(d) for d in locked_add))

    for d in to_remove:
        _delete_occurrence_rows(db, series, d)
    added, skipped_comments, skipped_no_hours = _materialize(db, current_user, emp, series, to_add)

    series.end_mode = body.end_mode
    series.end_count = body.end_count if body.end_mode == "count" else None
    series.end_date = body.end_date if body.end_mode == "date" else None
    log_action(db, current_user, "update_vagtplan_series", "vagtplan_series", series.id,
               f"{emp.name}: slutning ændret ({added} tilføjet, {len(to_remove)} fjernet)")
    db.commit()
    db.refresh(series)
    return VagtplanSeriesUpdateResult(series=_series_response(db, series), added=added,
                                      removed=len(to_remove), skipped_comments=skipped_comments,
                                      skipped_no_hours=skipped_no_hours)


@router.delete("/{series_id}", response_model=VagtplanSeriesDeleteResult)
def delete_series(series_id: int,
                  current_user: AppUser = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    """Sletter alle forekomster permanent, undtagen dem i låste lønperioder (og
    splittede aktiviteter). Serierækken slettes når intet er tilbage."""
    series, emp = _load_series_with_access(db, current_user, series_id)
    dates = _occurrence_dates_of(db, series)
    locked = {d for d in dates if _is_locked(db, d)}
    deleted, kept_split = 0, 0
    for d in dates:
        if d in locked:
            continue
        start = datetime.combine(d, time(0, 0))
        acts = db.query(Activity).filter(Activity.series_id == series.id,
                                         Activity.start_time >= start,
                                         Activity.start_time < start + timedelta(days=1)).all()
        if any(a.split_children for a in acts):
            kept_split += 1
            continue
        _delete_occurrence_rows(db, series, d)
        deleted += 1
    db.flush()
    if not _occurrence_dates_of(db, series):
        db.delete(series)
    log_action(db, current_user, "delete_vagtplan_series", "vagtplan_series", series_id,
               f"{emp.name}: {deleted} forekomster slettet, {len(locked)} bevaret (låst), {kept_split} bevaret (splittet)")
    db.commit()
    return VagtplanSeriesDeleteResult(deleted=deleted, kept_locked=len(locked), kept_split=kept_split)


@router.delete("/{series_id}/occurrences/{occurrence_date}", status_code=204)
def delete_occurrence(series_id: int, occurrence_date: date,
                      current_user: AppUser = Depends(get_current_user),
                      db: Session = Depends(get_db)):
    """'Slet denne forekomst': fjerner dagens aktivitet og kommentar i serien. Dagen
    genopstår ikke ved forlængelse (forlængelse sker kun efter sidste forekomst)."""
    series, emp = _load_series_with_access(db, current_user, series_id)
    if occurrence_date not in _occurrence_dates_of(db, series):
        raise HTTPException(404, "Forekomsten findes ikke i serien")
    _assert_removable(db, series, occurrence_date)
    _delete_occurrence_rows(db, series, occurrence_date)
    db.flush()
    if not _occurrence_dates_of(db, series):
        db.delete(series)
    log_action(db, current_user, "delete_vagtplan_series_occurrence", "vagtplan_series", series_id,
               f"{emp.name}: forekomst {_fmt(occurrence_date)} slettet")
    db.commit()
