"""
Overenskomstsatser med "gælder fra"-dato (2026-10-06).

- MasterAgreementType.hourly_rate er altid den sats der gælder NU (vises i Stamdata).
- MasterAgreementTypeRate-rækker er satsskift: en fremtidig række træder i kraft på
  sin dato (apply_due_rates flytter satsen over i hourly_rate og gemmer den gamle sats
  i old_rate, så ældre lønperioder stadig regnes med den gamle sats).
- Ligger datoen inde i en lønperiode, gælder den nye sats HELE perioden
  → satsen for en periode = satsen der gælder på periodens sidste dag.
"""
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from database.models import AuditLog, MasterAgreementType, MasterAgreementTypeRate


def _rows(db: Session, type_id: int) -> list:
    return (db.query(MasterAgreementTypeRate)
            .filter(MasterAgreementTypeRate.agreement_type_id == type_id)
            .order_by(MasterAgreementTypeRate.valid_from).all())


def agreement_rate_for_period(db: Session, type_name: str, period_start: date, period_end: date) -> Decimal:
    """Timesatsen for overenskomsttypen i lønperioden. Uden daterede satser er det
    altid den nuværende sats (samme resultat som før 2026-10-06)."""
    from calculators.rates_loader import load_agreement_types_from_db
    t = db.query(MasterAgreementType).filter(MasterAgreementType.name == type_name).first()
    if t is None:
        return load_agreement_types_from_db(db).get(type_name, Decimal("0"))
    rows = _rows(db, t.id)
    later = [r for r in rows if r.valid_from > period_end]
    if later and later[0].applied_at is not None:
        # Ældre periode: satsen før skiftet (ukendt før den første historik-række → dens sats)
        first = later[0]
        return Decimal(str(first.old_rate if first.old_rate is not None else first.hourly_rate))
    due = [r for r in rows if r.valid_from <= period_end]
    if due and due[-1].applied_at is None:
        return Decimal(str(due[-1].hourly_rate))       # skiftet er nået, men ikke flyttet endnu
    return Decimal(str(t.hourly_rate))


def apply_due_rates(db: Session, today: date) -> list:
    """Flytter satser hvis dato er nået over i overenskomsttypens nuværende sats."""
    due = (db.query(MasterAgreementTypeRate)
           .filter(MasterAgreementTypeRate.applied_at.is_(None), MasterAgreementTypeRate.valid_from <= today)
           .order_by(MasterAgreementTypeRate.valid_from).all())
    for r in due:
        t = r.agreement_type
        r.old_rate = t.hourly_rate
        t.hourly_rate = r.hourly_rate
        r.applied_at = datetime.now()
        db.add(AuditLog(user_initials="SYSTEM", action="agreement_rate_applied", entity_type="agreement_type",
                        entity_id=t.id, details=f"Ny sats trådt i kraft for '{t.name}': "
                        f"{Decimal(str(r.old_rate)):.2f} → {Decimal(str(r.hourly_rate)):.2f} kr fra {r.valid_from}"))
    if due:
        db.commit()
    return due
