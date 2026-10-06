"""
Advarsler-oversigten (2026-10-06): alle advarsler brugeren har rettighed til i ét kald,
i stedet for at hver type åbner sin egen popup ved login.

Grupper:
- mismatches: "Mulig fejl i løn" (elevløn-trin og anciennitet der er glemt)
- raises:     "Kommende ændringer i overenskomst" (kommende elevløn-trin og 9 måneders anciennitet)
- applied:    lønstigninger der lige er trådt i kraft
- other:      "Øvrige" – nye satser, §56 og mærkedage. Vises 30 dage før, igen 7 dage før og
              på dagen (personlige indstillinger); "OK" skjuler kun til næste påmindelse.

Hver advarsel har en stabil `key`. Nøgler brugeren har fået vist, gemmes som "set", så
vinduet kun åbner af sig selv ved start, når der er noget NYT.
"""
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth import get_current_user, user_has_permission
from database.models import AppUser, AuditLog, Employee, Role, UserAlertDismissal, UserAlertSettings
from database.session import get_db

router = APIRouter(prefix="/api/alerts", tags=["alerts"])

SEEN, OK = "seen:", "ok:"
DEFAULTS = {"raise_notice_days": 30, "raise_remind_days": 7,
            "other_first_days": 30, "other_second_days": 7, "other_on_day": True, "auto_open": True}


def _short(prefix: str, key: str) -> str:
    return (prefix + key)[:50]


def _settings(db: Session, user: AppUser) -> dict:
    st = db.get(UserAlertSettings, user.id)
    return {k: getattr(st, k) for k in DEFAULTS} if st else dict(DEFAULTS)


def _sections(db: Session, user: AppUser) -> dict:
    """Hvilke indstillinger brugeren kan se – afhænger af rettighederne på rollen."""
    from routers.employees import _MILESTONE_PERMS
    role = db.query(Role).filter(Role.name == user.role).first()
    explicit = set(role.permissions or []) if role else set()
    return {
        "raises": "elev_wage_approve" in explicit or user_has_permission(db, user, "anciennitet_alert"),
        "other": "payroll" in explicit or user_has_permission(db, user, "paragraf_56_alert")
                 or any(user_has_permission(db, user, p) for p in _MILESTONE_PERMS.values()),
    }


def _stage(event: Optional[date], today: date, st: dict) -> Optional[str]:
    """Hvilken påmindelse vi er i: '30', '7', '0' (på dagen) – eller None hvis det er for tidligt."""
    if event is None:
        return "x"                                     # fx §56 udløbet: vises én gang
    days_left = (event - today).days
    stages = [st["other_first_days"]] + ([st["other_second_days"]] if st["other_second_days"] is not None else []) \
        + ([0] if st["other_on_day"] else [])
    stages = sorted(set(stages), reverse=True)
    if days_left > stages[0]:
        return None
    reached = [s for s in stages if s >= days_left]
    return str(min(reached)) if reached else str(stages[-1])


def collect(db: Session, user: AppUser, today: Optional[date] = None) -> dict:
    from routers.agreement_rates_router import _explicit, rate_groups
    from routers.elev_router import alerts as raise_alerts
    from routers.employees import _MILESTONE_PERMS, milestone_alerts, paragraf56_alerts

    today = today or date.today()
    st = _settings(db, user)
    out = {"mismatches": [], "raises": [], "applied": [], "other": []}

    if user_has_permission(db, user, "elev_wage_approve") or user_has_permission(db, user, "anciennitet_alert"):
        r = raise_alerts(current_user=user, db=db, today=today)
        out["mismatches"] = [dict(m, key=f"mm:{m['kind']}:{m['employee_id']}:{m['event_date']}") for m in r["mismatches"]]
        out["raises"] = [dict(u, key=f"up:{u['kind']}:{u['employee_id']}:{u['event_date']}") for u in r["upcoming"]]
        out["applied"] = [dict(a, key=f"fx:{a['decision_id']}") for a in r["applied"]]

    other = []   # (type, event date, data, base key)
    if _explicit(db, user, "payroll"):
        for g in rate_groups(db, today, st["other_first_days"]):
            other.append(("rates", g["valid_from"], g, f"rates:{g['valid_from']}"))
    if user_has_permission(db, user, "paragraf_56_alert"):
        p = paragraf56_alerts(current_user=user, db=db)
        for a in p.upcoming:
            other.append(("p56_upcoming", a.paragraf_56_end_date, a.model_dump(), f"p56u:{a.employee_id}:{a.paragraf_56_end_date}"))
        for a in p.expired:
            other.append(("p56_expired", None, a.model_dump(), f"p56x:{a.employee_id}:{a.paragraf_56_end_date}"))
    if any(user_has_permission(db, user, perm) for perm in _MILESTONE_PERMS.values()):
        for a in milestone_alerts(current_user=user, db=db, today=today):
            other.append(("milestone", a.event_date, a.model_dump(), f"ms:{a.employee_id}:{a.alert_key}"))

    acked = {d.key for d in db.query(UserAlertDismissal)
             .filter(UserAlertDismissal.user_id == user.id, UserAlertDismissal.key.like(OK + "%")).all()}
    for typ, event, data, base in other:
        stage = _stage(event, today, st)
        key = f"{base}@{stage}"
        if stage is None or _short(OK, key) in acked:
            continue
        out["other"].append(dict(data, type=typ, key=key, stage=stage))
    return out


@router.get("")
def get_alerts(current_user: AppUser = Depends(get_current_user), db: Session = Depends(get_db),
               today: Optional[date] = None):
    groups = collect(db, current_user, today)
    keys = [i["key"] for items in groups.values() for i in items]
    seen = {d.key for d in db.query(UserAlertDismissal)
            .filter(UserAlertDismissal.user_id == current_user.id, UserAlertDismissal.key.like(SEEN + "%")).all()}
    return {"groups": groups, "total": len(keys), "new_keys": [k for k in keys if _short(SEEN, k) not in seen],
            "sections": _sections(db, current_user), "auto_open": _settings(db, current_user)["auto_open"]}


class KeysBody(BaseModel):
    keys: list[str]


def _store(db: Session, user: AppUser, prefix: str, keys: list) -> None:
    have = {d.key for d in db.query(UserAlertDismissal).filter(UserAlertDismissal.user_id == user.id).all()}
    for k in keys[:500]:
        key = _short(prefix, k)
        if key not in have:
            db.add(UserAlertDismissal(user_id=user.id, key=key))
            have.add(key)
    db.commit()


@router.post("/seen", status_code=204)
def mark_seen(body: KeysBody, current_user: AppUser = Depends(get_current_user), db: Session = Depends(get_db)):
    """Kaldes når oversigten er vist: disse advarsler åbner ikke vinduet af sig selv igen."""
    _store(db, current_user, SEEN, body.keys)


@router.post("/ok", status_code=204)
def mark_ok(body: KeysBody, current_user: AppUser = Depends(get_current_user), db: Session = Depends(get_db)):
    """'OK' på en øvrig advarsel: skjules til næste påmindelse (nøglen indeholder påmindelsen)."""
    _store(db, current_user, OK, body.keys)


# ── Tidligere advarsler (sidste 90 dage) ─────────────────────────────────────

HISTORY_DAYS = 90
_RAISE_ACTIONS = {"elev_step_approve": "Godkendt", "elev_step_keep": "Beholdt",
                  "elev_step_cancel": "Annulleret", "elev_step_applied": "Trådt i kraft"}
_STAGE_TEXT = {"30": "første besked", "7": "anden besked", "0": "på dagen", "x": ""}


def _utc(ts: Optional[datetime]) -> Optional[str]:
    """Databasen gemmer tider i UTC (SQLite CURRENT_TIMESTAMP) – markeres så browseren viser dansk tid."""
    return ts.isoformat() + "Z" if ts else None


def _ok_text(db: Session, key: str) -> tuple:
    """(medarbejder, tekst) for en 'OK'-nøgle som 'ms:12:birthday_40@7'."""
    base, _, stage = key.partition("@")
    parts = base.split(":")
    stage_txt = f" ({_STAGE_TEXT.get(stage, stage)})" if _STAGE_TEXT.get(stage) else ""
    if parts[0] == "rates":
        return "", f"Nye satser fra {parts[1]}{stage_txt}"
    emp = db.get(Employee, int(parts[1])) if len(parts) > 1 and parts[1].isdigit() else None
    name = emp.name if emp else ""
    if parts[0] == "ms":
        kind, _, val = parts[2].partition("_")
        what = {"birthday": f"fylder {val} år", "jubilee": f"{val} års jubilæum",
                "elev": "afslutter elevtiden"}.get(kind, parts[2])
    elif parts[0] == "p56u":
        what = f"§56-aftalen udløber {parts[2]}"
    elif parts[0] == "p56x":
        what = "§56-aftalen er udløbet"
    else:
        what = base
    return name, what + stage_txt


@router.get("/history")
def history(current_user: AppUser = Depends(get_current_user), db: Session = Depends(get_db),
            now: Optional[datetime] = None):
    """Behandlede advarsler de sidste 90 dage: lønstigninger (fælles for alle med rettigheden)
    og brugerens egne 'OK' på øvrige advarsler. Kun læsning."""
    since = (now or datetime.utcnow()) - timedelta(days=HISTORY_DAYS)
    out = []
    if _sections(db, current_user)["raises"]:
        for a in (db.query(AuditLog).filter(AuditLog.action.in_(_RAISE_ACTIONS), AuditLog.timestamp >= since)
                  .all()):
            label = _RAISE_ACTIONS[a.action]
            if a.action == "elev_step_cancel" and "automatisk" in (a.details or ""):
                label = "Annulleret automatisk"
            out.append({"at": _utc(a.timestamp), "who": "" if a.action == "elev_step_applied" else a.user_initials,
                        "label": label, "employee_name": "", "text": a.details or ""})
    for d in (db.query(UserAlertDismissal)
              .filter(UserAlertDismissal.user_id == current_user.id, UserAlertDismissal.key.like(OK + "%"),
                      UserAlertDismissal.dismissed_at >= since).all()):
        name, text = _ok_text(db, d.key[len(OK):])
        out.append({"at": _utc(d.dismissed_at), "who": "dig", "label": "OK", "employee_name": name, "text": text})
    out.sort(key=lambda e: e["at"] or "", reverse=True)
    return out


# ── Personlige indstillinger ─────────────────────────────────────────────────

@router.get("/settings")
def get_settings(current_user: AppUser = Depends(get_current_user), db: Session = Depends(get_db)):
    return dict(_settings(db, current_user), sections=_sections(db, current_user))


class SettingsBody(BaseModel):
    raise_notice_days: int = Field(ge=1, le=365)
    raise_remind_days: Optional[int] = Field(default=None, ge=0, le=365)
    other_first_days: int = Field(ge=1, le=30)          # mærkedage og §56 kigger højst 1 måned frem
    other_second_days: Optional[int] = Field(default=None, ge=1, le=30)
    other_on_day: bool = True
    auto_open: bool = True                               # åbn Advarsler selv ved start, når der er nyt


@router.put("/settings")
def put_settings(body: SettingsBody, current_user: AppUser = Depends(get_current_user), db: Session = Depends(get_db)):
    if body.raise_remind_days is not None and body.raise_remind_days >= body.raise_notice_days:
        raise HTTPException(400, "'Påmind igen' skal være færre dage før end varslet")
    if body.other_second_days is not None and body.other_second_days >= body.other_first_days:
        raise HTTPException(400, "Anden påmindelse skal være færre dage før end den første")
    st = db.get(UserAlertSettings, current_user.id)
    if st is None:
        st = UserAlertSettings(user_id=current_user.id)
        db.add(st)
    for k, v in body.model_dump().items():
        setattr(st, k, v)
    db.commit()
    return get_settings(current_user=current_user, db=db)
